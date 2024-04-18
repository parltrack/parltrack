#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#    This file is part of parltrack.

#    parltrack is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    parltrack is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with parltrack.  If not, see <http://www.gnu.org/licenses/>.

# (C) 2014, 2019 Stefan Marsiske

from db import db
from utils.utils import fetch_raw, jdump, junws, unws
from utils.log import log
from utils.mappings import VOTE_DOX, VOTE_DOX_RE
from utils.process import process

from collections import defaultdict
from datetime import datetime
from lxml.etree import fromstring, tostring
import requests
import re

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'abort_on_error': True,
    'table': 'ep_votes',
}

docre=re.compile(u'((?:[AB]|RC)[6789]\s*-\s*[0-9]{3,4}\/[0-9]{4})')
refre=re.compile(r'((?:20|19)[0-9]{2}/[0-9]{4}[A-Z]?\((?:ACI|APP|AVC|BUD|CNS|COD|COS|DCE|DEA|DEC|IMM|INI|INL|INS|NLE|REG|RPS|RSO|RSP|SYN)\))')
ignoredox = ['B6-0023/2004', 'B6-0043/2007', 'B6-0155/2004', 'B6-0161/2006', 'B6-0209/2007', 'B6-0223/2005', 'B6-0318/2005',
             'B6-0338/2008', 'B6-0507/2006', 'B6-0521/2006', 'B6-0526/2006', 'B6-0642/2005', 'B7-0045/2012', 'B7-0089/2010',
             'B7-0135/2010', 'B7-0150/2010', 'B8-0138/2019', 'B8-0216/2019', 'B8-0217/2019', 'B8-0218/2019', 'B8-0221/2019',
             'RC6-0133/2008', 'RC6-0135/2009', 'RC6-0217/2008', 'RC6-0219/2008', 'RC6-0241/2008', 'RC6-0242/2008', 'RC6-0244/2008',
             'RC6-0271/2008', 'RC6-0277/2008', 'RC6-0278/2008', 'RC6-0281/2008', 'RC6-0326/2008', 'RC6-0343/2008', 'RC6-0350/2008',
             'RC6-0377/2008', 'RC6-0387/2008', 'RC6-0402/2008', 'RC6-0420/2005', 'RC6-0420/2008', 'RC6-0425/2008', 'RC6-0426/2008',
             'RC6-0428/2008', 'RC6-0518/2007', 'RC6-0521/2008', 'RC6-0523/2008', 'RC6-0527/2008', 'RC6-0549/2008', 'RC6-0554/2008',]

VOT_DATE_RE = re.compile(r'\((\d{4})\)(\d{2})-(\d{2})\(RCV\)_EN\.xml')
VOT_URL_TPL = 'https://www.europarl.europa.eu/doceo/document/PV-9-{0}-{1}-{2}-VOT_EN.xml'


def get_vot_url(url):
    return VOT_URL_TPL.format(*VOT_DATE_RE.search(url).groups())


def get_split_votes(url):
    nodes = fromstring(fetch_raw(get_vot_url(url), binary=True))
    split_votes = {}

    for vn in nodes.xpath('//vote'):
        aref = ''
        vote_refs = defaultdict(list)
        for v in vn.xpath('.//voting'):
            l = junws(v.xpath('.//label')[0])
            if l:
                aref = l.split()[0]
            am = junws(v.xpath('.//amendmentNumber')[0])
            p = junws(v.xpath('.//amendmentSubject')[0])
            if '§' not in p and not am:
                continue
            loc = f'amendment {am}'
            if am == '§':
                loc = p
            vote_refs[loc].append(v.get('votingId'))
        if not vote_refs:
            continue
        for r in vn.xpath('.//remarkSplitVote//item'):
            rt = junws(r.xpath('.//title')[0])
            if rt.startswith('Amendment '):
                rt = 'a' + rt[1:]
            if rt not in vote_refs:
                log(3, f"Cannot find vote reference {rt} @ {url}")
                continue
            split = list({'section': str(v1), 'text': str(v2)} for v1, v2 in zip(r.xpath('.//partSection//text()'), r.xpath('.//partValue//text()')))
            for i, v in enumerate(vote_refs[rt][1:]):
                split_votes[int(v)] = split[i]
                split_votes[int(v)]['location'] = rt
    return split_votes

def votemeta(line, date):
    log(3, 'vote title is "%s"' % line)
    res={'rapporteur': []}
    m=docre.search(line)
    if m:
        doc=m.group(1).replace(' ', '')
        log(4,'setting doc to "%s"' % doc)
        res['doc']=doc
        reports=db.get("dossiers_by_doc", doc)
        if reports:
            res['epref']=[report['procedure']['reference'] for report in reports]
            if len(reports) > 1:
                log(3,"more than 1 dossier referencing document %s, %s" % (doc,[d['procedure']['reference'] for d in reports]))
        else:
            if doc in VOTE_DOX_RE:
                res['epref']=[VOTE_DOX_RE[doc]]
            elif doc not in ignoredox:
                log(2,'%s despite matching regex could not associate dossier with vote in "%s"' % (doc,line))
        return res

    m=refre.search(line)
    if m and db.get('ep_dossiers',m.group(1)):
        res['epref']=[m.group(1)]
        return res
    for k,v in VOTE_DOX.items():
        if k in line:
            res['epref']=[v]
            return res
    log(4,'no associated dossier for: "%s"' % line)
    return res

def getXML(url):
    try:
        raw = fetch_raw(url,binary=True)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404: return None
        log(1, "failed to fetch xml from url: %s" % url)
        raise
    try:
        return fromstring(raw)
    except:
        log(1, "failed to parse xml from url: %s" % url)
        raise

def scrape(url, **kwargs):
    log(3,"scraping %s" % (url))
    root = getXML(url)
    if root is None:
        log(1,"could not get votes for", url)
        return # angrily o/
    log(3, "processing plenary votes xml from %s" % url)
    # root is:
    #PV.RollCallVoteResults EP.Number="PE 533.923" EP.Reference="P7_PV(2014)04-17" Sitting.Date="2014-04-17" Sitting.Identifier="1598443"
    split_votes = {}
    try:
        split_votes = get_split_votes(url)
    except Exception as e:
        log(1, f"Failed to process split vote VOT xml: {e}")
    votes=[]
    for vote in root.xpath('//RollCallVote.Result'):
        # hrmpf, some EP seriously used the braindead Y-d-m format sometimes in vote timestamps :/
        time = vote.get('Date')
        if len(time.split()) == 2:
            ts = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
        else:
            ts = datetime.strptime(time, "%Y-%m-%d")
        tmp=vote.get('Identifier')
        if tmp:
            voteid = int(tmp)
        else:
            tmp = vote.get('Number')
            if not tmp:
                log(1, "blimey, could not deduce an id for the vote in %s" % url)
                raise ValueError("no id for vote in %s" % url)
            voteid = "%s-%s" % (ts,tmp)
        title = vote.xpath("RollCallVote.Description.Text")
        if len(title) != 1:
            log(2, "holy ambiguity Batman! This vote doesn't have one title, but %d: %d %s" % (len(title), voteid, url))
            title="!unknown!"
        else:
            title=junws(title[0])
        v={u"ts": ts,
           u"url": url,
           u"voteid": voteid,
           u"title": title,
           'votes':{}}
        v.update(votemeta(v['title'], v['ts']))
        if voteid in split_votes:
            v['split'] = split_votes[voteid]
        if 'epref' not in v:
            ref = vote.xpath("RollCallVote.Description.Text/a/text()")
            if ref:
                v['epref']=unws(ref[0])
        for type, stype in [('Result.For','+'), ('Result.Against','-'), ('Result.Abstention','0')]:
            type = vote.xpath(type)
            if not type: continue
            if len(type)>1:
                log(2, "[pff] more than one %s entry in vote (id:%d) in %s" % (stype, v['voteid'], url))
            type = type[0]
            v['votes'][stype]={'total': int(type.get('Number')),
                               'groups': {}}
            for group in type.xpath('Result.PoliticalGroup.List'):
                g = str(group.get('Identifier'))
                if not g in v['votes'][stype]['groups']:
                    v['votes'][stype]['groups'][g]=[]
                for tag in ['Member.Name', 'PoliticalGroup.Member.Name']:
                    for mep in group.xpath(tag):
                        m = {}
                        name = junws(mep)
                        mepid = mep.get("PersId")
                        if mepid:
                            mepid = int(mepid)
                        else:
                            mepid = db.getMep(name, v['ts'], abbr=g)
                        if mepid:
                            m['mepid']= mepid
                            #if int(mep.get('MepId')) in ambiguous_meps:
                            #    oid = int(mep.get('MepId'))
                            #    ambiguous_meps.remove(oid)
                            #    log(2,'found mepid for previously ambigous obscure_id: "%s": %s' % (oid, mepid))
                        else:
                            mepid = lost_meps.get(mep.get('MepId'))
                            if mepid:
                                m['mepid']= mepid
                            else:
                                m['name']= name
                                m['obscure_id']=int(mep.get('MepId'))  # it's a totally useless and confusing id that is nowhere else used
                        v['votes'][stype]['groups'][g].append(m)
        # save
        process(v, v['voteid'], db.vote, 'ep_votes', v['title'])
        votes.append(v)
    return votes

from utils.process import publish_logs
def onfinished(daisy=True):
    publish_logs(get_all_jobs)
    if daisy:
        add_job("plenaries", {
            "years": [datetime.now().year],
            "onfinished": {"daisy": True},
        })

if __name__ == '__main__':
    import sys
    url = sys.argv[1]
    print(jdump(scrape(url)))
