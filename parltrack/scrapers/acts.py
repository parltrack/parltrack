#!/usr/bin/env python

# motion : meh?
# qp: titleurl, title, date
# cre: titleurl, title, date

import json, sys, pymongo
from lxml.etree import tostring
from lxml.html.soupparser import fromstring
import requests, time
from multiprocessing import log_to_stderr
from logging import DEBUG, WARN, INFO
logger = log_to_stderr()
logger.setLevel(INFO)

conn = pymongo.Connection()
db=conn.parltrack
dossiers=db.dossiers
meps=db.ep_meps2

PROXIES = {'http': 'http://localhost:8123/'}
HEADERS =  { 'User-agent': 'parltrack/0.7' }

def fetch_raw(url, retries=5, ignore=[], params=None):
    try:
        if params:
            r=requests.POST(url, params=params, proxies=PROXIES, headers=HEADERS)
        else:
            r=requests.get(url, proxies=PROXIES, headers=HEADERS)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout), e:
        if e == requests.exceptions.Timeout:
            retries = min(retries, 1)
        if retries>0:
            time.sleep(4*(6-retries))
            f=fetch_raw(url, retries-1, ignore=ignore, params=params)
        else:
            raise ValueError("failed to fetch %s" % url)
    if r.status_code >= 400 and r.status_code not in [504, 502]+ignore:
        logger.warn("[!] %d %s" % (r.status_code, url))
        r.raise_for_status()
    return r.text

def fetch(url, retries=5, ignore=[], params=None):
    try:
        f = fetch_raw(url, retries, ignore, params)
    except:
        raise
    
    try:
        return fromstring(f)
    except:
        raise

def gettext(url, path):
    if not url: return ''
    return ''.join(tostring(frag) for frag in fetch(url, retries=2).xpath(path))

def getdossier(ref):
    if ref[:4].isalpha() and ref[4]=='_': # handle committee docs
        root = fetch('http://www.europarl.europa.eu/RegistreWeb/search/resultDetail.htm?reference=%s&fragDocu' % ref)
        proc = root.xpath('//span[text()="Procedures in which document is involved :"]/following-sibling::a/text()')
        if proc:
            doc=db.dossiers2.find_one({'procedure.reference': proc[0]},['procedure.subject'])
            if doc:
                return proc[0], tuple(doc['procedure']['subject'])
            print '[x] eek', ref
            return proc[0], tuple()

    # handle other docs
    doc=list(db.dossiers2.find({'activities.docs.title': ref},['procedure.reference', 'procedure.subject']))
    if len(doc) == 1:
        return (doc[0]['procedure']['reference'], tuple(doc[0]['procedure']['subject']))
    else:
        #print >>sys.stderr, '[$] meh', ref
        print '[$] meh', ref

ok = 0
nok = 0
for mep in meps.find({'active': True},['activities', 'Name.full']):
    acts = mep.get('activities')
    if not acts: continue
    dirty = False
    for typ in acts:
        for term in acts[typ]:
            for act in acts[typ][term]:
                if typ in ['COMPARL', 'COMPARL-SHADOW', 'REPORT', 'REPORT-SHADOW'] and 'dossier' not in act:
                    res = set()
                    for doc in act['referenceList']:
                        if doc: res.add(getdossier(doc))
                    if res:
                        if len(res)==1:
                            act['dossier'] =  list(res)[0]
                            dirty = True
                            ok += 1
                        else:
                            #print >>sys.stderr, '[!] wtf', res
                            print '[!] wtf', res
                            nok += 1
                    else:
                        nok += 1
                elif typ == 'QP' and 'text' not in act:
                    act['text']=gettext(act['titleUrl'],'//td[@class="contents"]/*')
                    ok += 1
                    dirty = True
                elif typ == 'CRE' and 'text' not in act:
                    act['text']=gettext(act['titleUrl'],'//p[@class="contents"]')
                    ok += 1
                    dirty = True
                if 'term' not in act:
                    act['term']=term
                    dirty = True
                if 'type' not in act or not act['type']:
                    act['type']=typ
                    dirty = True
    if dirty:
        #print json.dumps(acts, indent=True, ensure_ascii=False).encode('utf8')
        print 'updating:', mep['Name']['full'].encode('utf8')
        meps.update({'_id': mep['_id']}, {'$set': { 'activities': acts}})
print ok, nok
