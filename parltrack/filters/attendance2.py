#!/usr/bin/env python
# -*- coding: utf-8 -*-

# get all voting dates based on forecasts:
# db.dossiers2.find({activities: { $elemMatch: {"type": "Vote in plenary scheduled", "date": {"$gt": ISODate("2014-10-24T00:00:00Z")}}}},{"activities.date":true, "activities.type": true}).sort({"activities.date" : -1 })

import pymongo, json, re, sys
from datetime import datetime, date
from parltrack.utils import dateJSONhandler
from operator import itemgetter
import unicodedata
conn = pymongo.Connection()
db=conn.parltrack


from lxml.etree import tostring
from lxml.html.soupparser import fromstring
import requests, time
from multiprocessing import log_to_stderr
from logging import DEBUG, WARN, INFO
logger = log_to_stderr()
logger.setLevel(INFO)

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

def getmeps(date,attrs=None):
    return db.ep_meps2.find({'Constituencies.start' : {'$lte': date},
                             'Constituencies.end' : {'$gte': date}},
                            attrs)

def getdate(d):
    return datetime.strptime(d, "%Y/%m/%d")

mepmap={
        u'Башир': 'Bashir',
        u'Valcárcel': u'VALCÁRCEL SISO',
        u'Valenciano Martínez-Orozco': u'Valenciano ',
        u'Vozemberg': u'VOZEMBERG-VRIONIDI',
        }

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

def votingdays(day):
    seen=set([])
    res=[]
    for ts in db.ep_votes.find({'ts' : {'$gte': day}},['ts']).distinct('ts'):
        ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if ts in seen: continue
        seen.add(ts)
        res.append(ts)
    return sorted(res)

last = None
meps = {}
seen = set()
# http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-//EP//TEXT+PV+20150429+ATT-REG+DOC+XML+V0//EN&language=EN
urltpl = "http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-//EP//TEXT+PV+%04d%02d%02d+ATT-REG+DOC+XML+V0//EN&language=EN"
_8th = getdate('2014/07/01')
#print getmeps(getdate('2014/08/01')).count()
for day in votingdays(_8th):
    url = urltpl % (day.year, day.month, day.day)
    root=fetch(url)
    if not root:
       print >>sys.stderr, "meh", url
       raise
    data=root.xpath('//p[@class="contents"]')
    if not (len(data)==4 and
            data[0].xpath(".//text()") == ['Present:'] and
            data[2].xpath(".//text()") == ['Excused:']):
       print >>sys.stderr, "wtf, not present/excused, where expected", url
       print >>sys.stderr, len(data), repr(data[0].xpath(".//text()")), repr(data[2].xpath(".//text()"))
       raise
    allmeps={x['UserID']: x['active'] for x in getmeps(day,['UserID', 'active'])}
    for text in data[1].xpath('.//text()')[0].split(', '):
       mep=getMep(text,day)
       if not mep:
          print >>sys.stderr, 'illegal MEP', day, text, mep, url
          continue
          #raise
       if not mep in meps: meps[mep]={'name': text,'present': 0, 'excused':0, 'awol': 0, 'active': allmeps[mep]}
       if not meps[mep]['name']: meps[mep]['name']=text
       meps[mep]['present']+=1
       del allmeps[mep]
    for text in data[3].xpath('.//text()')[0].split(', '):
       mep=getMep(text,day)
       if not mep:
          print >>sys.stderr, "meh, no mep", url, text, day
          continue
          #raise
       if not mep in meps: meps[mep]={'name': text,'present': 0, 'excused':0, 'awol': 0, 'active': allmeps[mep]}
       if not meps[mep]['name']: meps[mep]['name']=text
       meps[mep]['excused']+=1
       del allmeps[mep]
    for mep in allmeps:
       if not mep in meps: meps[mep]={'name': '','present': 0, 'excused':0, 'awol': 0, 'active': 'unknown'}
       meps[mep]['awol']+=1

#for mep, cnts in sorted(meps.items()):
#    print "%s\t%s\t%s\t%s\t%s" % (cnts['present'], cnts['excused'], cnts['awol'], mep, cnts['name'].encode('utf8'))

print 'name,id,voted,votes,percent,active,excused,awol'

for mep in sorted(((mep['name'],
                    mep['present'],
                    mep['present']+mep['excused']+mep['awol'],
                    (mep['present']*100)/float(mep['present']+mep['excused']+mep['awol']),
                    mep['active'],
                    id,
                    ((mep['present']*-100)/float(mep['present']+mep['excused']+mep['awol']),mep['name']),
                    mep['excused'],
                    mep['awol'])
                  for id, mep in meps.items()),
                  key=itemgetter(6)):
    print (u'"%s",%s,%s,%s,%3.2f,%s,%s,%s' % (mep[0], mep[5], mep[1], mep[2], mep[3], mep[4], mep[7], mep[8])).encode('utf8')
