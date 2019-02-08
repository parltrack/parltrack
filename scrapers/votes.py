#!/usr/bin/env python
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

# (C) 2014 Stefan Marsiske

from datetime import datetime
from lxml import etree
from parltrack.utils import fetch, fetch_raw, jdump
import re, sys, unicodedata

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

mepCache={}
def getMep(text,date):
    name=''.join(unicodedata.normalize('NFKD', unicode(text.strip())).encode('ascii','ignore').split()).lower()
    if name in mepCache:
        return mepCache[name]

    if not name: return
    if name.endswith('('): name=name[:-1].strip()
    # TODO add date constraints based on groups.start/end
    mep=db.ep_meps2.find_one({'Name.aliases': name,
                             "Constituencies.start" : {'$lt': date},
                             "Constituencies.end" : {'$gt': date}},['UserID'])
    if not mep and u'ß' in text:
        name=''.join(unicodedata.normalize('NFKD', unicode(text.replace(u'ß','ss').strip())).encode('ascii','ignore').split()).lower()
        mep=db.ep_meps2.find_one({'Name.aliases': name,
                                  "Constituencies.start" : {'$lt': date},
                                  "Constituencies.end" : {'$gt': date}},['UserID'])
    if not mep and len([x for x in text if ord(x)>128]):
        mep=db.ep_meps2.find_one({'Name.aliases': re.compile(''.join([x if ord(x)<128 else '.' for x in text]),re.I)},['UserID'])
    if not mep:
        mepCache[name]=None
    else:
        mepCache[name]=mep['UserID']
        return mep['UserID']

def splitMeps(text, res, date):
    ok = False
    splitters=['/',' et ']
    for splitter in splitters:
       for q in text.split(splitter):
           mep=getMep(q,date)
           if mep:
              res['rapporteur'].append({'name': q, 'ref': mep})
              ok=True
       if ok: return True
    print >>sys.stderr, '[$] lookup oops:', text.encode('utf8')
    return ok

def scanMeps(text, res, date):
    tmp=text.split(':')
    if len(tmp)==2:
        return splitMeps(tmp[1], res, date)
    elif len(tmp)==1:
        return splitMeps(text, res, date)
    else:
        print >>sys.stderr, 'huh', line

docre=re.compile(u'(.*)((?:[AB]|RC)[678]\s*-\s*[0-9]{3,4}\/[0-9]{4})(.*)')
tailre=re.compile(r'^(?:\s*-\s*)?(.*)\s*-\s*([^-]*$)')
junkdashre=re.compile(r'^[ -]*(.*)[ -]*$')
rapportre=re.compile(r'(.*)(?:recommendation|rapport|report):?\s?(.*)',re.I)
def votemeta(line, date):
    print >>sys.stderr, line.encode('utf8')
    res={'rapporteur': []}
    m=docre.search(line)
    if m:
        line=''.join([m.group(1),m.group(3)])
        doc=m.group(2).replace(' ', '')
        res['report']=doc
        report=db.dossiers2.find_one({"activities.docs.title": doc},['_id', 'procedure.reference', 'procedure.title'])
        if report:
            res['dossierid']=report['_id']
            res['epref']=report['procedure']['reference']
            res['eptitle']=report['procedure']['title']
    m=tailre.match(line)
    if m:
        res['issue_type']=m.group(2).strip()
        line=m.group(1).strip()
    if line.startswith('RC'):
        res['RC']=True
        line=line[2:].strip()
    m=junkdashre.match(line)
    if m:
        line=m.group(1)
    tmp=line.split(' - ')
    if len(tmp)>1:
        if len(tmp)>2:
            print >>sys.stderr, "many ' - '",line
        line=tmp[0]
        res['issue_type']="%s %s" % (' - '.join(tmp[1:]),res.get('issue_type',''))
    line=line.strip()
    if not line:
        return res
    if line.endswith('()'):
        line=line[:-2].strip()

    if scanMeps(line, res, date):
        return res
    m=rapportre.search(line)
    if m:
        # handle mep
        if m.group(2):
            scanMeps(m.group(2),res, date)
        else:
            scanMeps(m.group(1),res, date)
    return res

# 'http://www.europarl.europa.eu/plenary/en/minutes.html?clean=false&leg=7&refSittingDateStart=01/01/2011&refSittingDateEnd=31/12/2011&miType=title&miText=Roll-call+votes&tabActif=tabResult&startValue=10'
def crawl(year, term):
    listurl = 'http://www.europarl.europa.eu/plenary/en/minutes.html'
    PARAMS = 'clean=false&leg=%s&refSittingDateStart=01/01/%s&refSittingDateEnd=31/12/%s&miType=title&miText=Roll-call+votes&tabActif=tabResult'
    voteurl = 'http://www.europarl.europa.eu/RegData/seance_pleniere/proces_verbal/%s/votes_nominaux/xml/P%s_PV%s(RCV)_XC.xml'
    params = PARAMS % (term, year, year)
    root=fetch(listurl, params=params)
    prevdates=None
    dates=root.xpath('//span[@class="date"]/text()')
    i=10
    while dates and dates!=prevdates:
        for date in dates:
            if not date.strip(): continue
            date = datetime.strptime(date.strip(), "%d-%m-%Y")
            yield voteurl % (date.strftime("%Y/%m-%d"), term, date.strftime("(%Y)%m-%d"))

        root=fetch(listurl, params="%s&startValue=%s" % (params,i))
        prevdates=dates
        i+=10
        dates=root.xpath('//span[@class="date"]/text()')

def get(url):
    print "scraping", url
    root=etree.parse(fetch_raw(url))
    # root is:
    #PV.RollCallVoteResults EP.Number="PE 533.923" EP.Reference="P7_PV(2014)04-17" Sitting.Date="2014-04-17" Sitting.Identifier="1598443"
    votes=[]
    for vote in root.xpath('//RollCallVote.Result'):
        res={u"ts": datetime.strptime(vote.get('Date'), "%Y-%m-%d %H:%M:%S"),
             u"url": url,
             u"voteid": vote.get('Identifier'),
             u"title": vote.xpath("RollCallVote.Description.Text/text()")[0]}
        res.update(votemeta(res['title'], res['ts']))
        for type, stype in [('Result.For','For'), ('Result.Against','Against'), ('Result.Abstention','Abstain')]:
            type = vote.xpath(type)
            if not type: continue
            if len(type)>1: print "[pff] more than one", stype, "entry in vote"
            type = type[0]
            res[stype]={u'total': type.get('Number'),
                        u'groups': [{u'group': group.get('Identifier'),
                                     u'votes': [{u'userid': int(mep.get('MepId')),
                                                 u'ep_id': getMep(mep.xpath('text()')[0].strip(), res['ts']),
                                                 u'name': mep.xpath('text()')[0]}
                                              for mep in group.xpath('PoliticalGroup.Member.Name')]}
                                   for group in type.xpath('Result.PoliticalGroup.List')]}
        # save
        q={'title': res['voteid'],
           'ts':    res['ts']}
        db.ep_votes.update(q, {"$set": res}, upsert=True)
        votes.append(res)
    return votes

def scrape(year):
    if year >= 2004 and year < 2009:
        map(get, crawl(year, 6))
    elif year == 2009:
        map(get, crawl(year, 6))
        map(get, crawl(year, 7))
    elif year < 2014:
        print jdump(map(get, crawl(year, 7))).encode('utf8')
        #map(get, crawl(year, 7))
    else:
        map(get, crawl(year, 7))
        map(get, crawl(year, 8))
