#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pymongo, json, re, sys
from datetime import datetime, date
from parltrack.utils import dateJSONhandler, jdump, diff, logger
from operator import itemgetter
import unicodedata
conn = pymongo.Connection()
db=conn.parltrack

from lxml.etree import tostring
from lxml.html.soupparser import fromstring
import requests, time

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
        return []
    return fromstring(f)

mepmap={
        u'Башир': 'Bashir',
        u'Valcárcel': u'VALCÁRCEL SISO',
        u'Valenciano Martínez-Orozco': u'Valenciano ',
        u'Vozemberg': u'VOZEMBERG-VRIONIDI',
        }

def getdate(d):
    return datetime.strptime(d, "%Y/%m/%d")

mepCache={}
def getMep(text,date):
    if text in mepCache:
        return mepCache[text]
    text=mepmap.get(text,text)
    name=''.join(unicodedata.normalize('NFKD', unicode(text.strip())).encode('ascii','ignore').split()).lower()
    if not name: return
    mep=db.ep_meps2.find_one({'Name.aliases': name,
                              "Constituencies.start" : {'$lte': date},
                              "Constituencies.end" : {'$gte': date}},
                             ['UserID', 'Name.full'])
    if not mep and u'ß' in text:
        name=''.join(unicodedata.normalize('NFKD', unicode(text.replace(u'ß','ss').strip())).encode('ascii','ignore').split()).lower()
        mep=db.ep_meps2.find_one({'Name.aliases': name,
                                  "Constituencies.start" : {'$lte': date},
                                  "Constituencies.end" : {'$gte': date}},
                                 ['UserID', 'Name.full'])
    if not mep:
        mep=db.ep_meps2.find_one({'Name.aliases': re.compile("%s$" % name),
                                  "Constituencies.start" : {'$lte': date},
                                  "Constituencies.end" : {'$gte': date}},
                                 ['UserID', 'Name.full'])
        #if mep: print 'meh', name, text.encode('utf8')
    if mep:
        #print 'mapped', text.encode('utf8'), mep['Name']['full'].encode('utf8')
        mepCache[text]=mep['UserID']
        return mep['UserID']
    #print 'not mapped', text.encode('utf8')
    #mepCache[text]=None

def comvotes():
    return db.dossiers2.find({"activities.docs.type" : "Committee report tabled for plenary, 1st reading/single reading"})

def scrape(url, date, committee, doc, ep_ref):
    root=fetch(url)
    if not root:
       print >>sys.stderr, "meh", url
       raise
    # root contains 3 tables
    # '//tr[@class="doc_title"]//span[text()="FINAL VOTE BY ROLL CALL IN COMMITTEE RESPONSIBLE"]/../../following-sibling::tr//table'
    rcv = {'url': url,
           'ts': date,
           'doc': doc,
           'ep_ref': ep_ref} # todo also add doc title,reference
    if committee: rcv['committee']=committee
    found=False
    for table in root.xpath('//tr[@class="doc_title"]//span[text()="FINAL VOTE BY ROLL CALL IN COMMITTEE RESPONSIBLE"]/../../following-sibling::tr//table'):
        count= int(' '.join((' '.join(table.xpath('.//tr')[0].xpath('./td')[0].xpath('.//text()'))).split()))
        vtype=' '.join(' '.join(table.xpath('.//tr')[0].xpath('./td')[1].xpath('.//text()')).split())
        #print count, vtype
        tc = 0
        rcv[vtype]={u'total': count,
                    u'groups': []}
        for row in table.xpath('.//tr')[1:-1]:
            group=' '.join(' '.join(row.xpath('./td')[0].xpath('.//text()')).split())
            meps=(' '.join(' '.join(row.xpath('./td')[1].xpath('.//text()')).split())).split(', ')
            if meps==[''] and count==0: continue
            rcv[vtype]['groups'].append({'group': group,
                                         'votes': [{'ep_id': getMep(mep,date), 'name': mep} for mep in sorted(meps)]})
            #meps=[getMep(mep, date) or mep for mep in meps]
            #print group, meps
            tc+=len(meps)
            found=True
        if(tc!=count):
            print >>sys.stderr, tc, "!=", count, 'for', vtype
    return rcv if found else None

startyear=datetime(2016,4,28)
stats=[0,0]
seen=set([])
for dossier in comvotes():
    url=None
    date=None
    com=None
    errors=[]
    for act in dossier['activities']:
        if act['type']=="Vote in committee, 1st reading/single reading":
            if(date and date!=act['date']): errors.append(' '.join(("already had date", dossier['procedure']['reference'], repr(date), repr(act['date']))))
            date=act['date']
            continue
        if act['type']=="Committee report tabled for plenary, 1st reading/single reading":
            for doc in act.get('docs',[]):
                if not doc['type']=="Committee report tabled for plenary, 1st reading/single reading": continue
                if('url' in doc):
                    if(url and url!=doc['url']): errors.append(' '.join(("already had url", dossier['procedure']['reference'], url)))
                    url=doc['url']
            for c in act.get('committees',[]):
                if c['responsible']==True:
                    if(com and com!=c['committee']): errors.append(' '.join(("already had com", dossier['procedure']['reference'], repr(com), repr(c['committee']))))
                    com=c['committee']
    if not date: continue
    if(date<=startyear): continue
    if not url: continue
    if url in seen: continue
    seen.add(url)
    vote=scrape(url,date, com, dossier['procedure']['title'], dossier['procedure']['reference'])
    if vote:
        #print >>sys.stderr, date, url
        logger.info(url)
        if errors: print >>sys.stderr, '\n'.join(errors)
        if not com: print >>sys.stderr, "no com!!!"
        #print >>sys.stderr, jdump(vote).encode('utf8')
        q={'url': vote['url'],
           'ts':  vote['ts']}
        obj = db.ep_com_votes.find_one(q) or {}

        d=diff(dict([(k,v) for k,v in obj.items() if not k in ['_id', 'meta', 'changes']]),
               dict([(k,v) for k,v in vote.items() if not k in ['_id', 'meta', 'changes',]]))
        if d:
            now=datetime.utcnow().replace(microsecond=0)
            if not 'meta' in vote: vote[u'meta']={}
            if not obj:
                logger.info((u'adding %s%s %s' % (u'%s ' % vote['ep_ref'] if 'ep_ref' in vote else '',
                                                    vote['committee'],
                                                    vote['doc'])).encode('utf8'))
                vote['meta']['created']=now
                if stats: stats[0]+=1
                #notify(vote,None)
            else:
                logger.info((u'updating %s%s %s' % (u'%s ' % vote['ep_ref'] if 'ep_ref' in vote else '',
                                                    vote['committee'],
                                                    vote['doc'])).encode('utf8'))
                logger.info(d)
                vote['meta']['updated']=now
                if stats: stats[1]+=1
                vote['_id']=obj['_id']
                #notify(vote,d)
            vote['changes']=vote.get('changes',{})
            vote['changes'][now.isoformat()]=d
            db.ep_com_votes.save(vote)
print >>sys.stderr, "com_votes added/updated:", stats
