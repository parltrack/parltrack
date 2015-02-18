#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pymongo, json, re, sys
from datetime import datetime, date
from parltrack.utils import dateJSONhandler
from operator import itemgetter
import unicodedata
conn = pymongo.Connection()
db=conn.parltrack

#def jdump(obj):
#   return json.dumps(obj,
#         indent=1, default=dateJSONhandler, ensure_ascii=False).encode('utf8')

def getmeps(date,attrs=None):
    return db.ep_meps2.find({'Constituencies.start' : {'$lte': date},
                             'Constituencies.end' : {'$gte': date}},
                            attrs)

def getdate(d):
    return datetime.strptime(d, "%Y/%m/%d")

_8th = getdate('2014/07/01')
#print getmeps(getdate('2014/08/01')).count()

mepCache={}
def getMep(text,userid,date):
    if userid in mepCache:
        return mepCache[userid]
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
        mepCache[userid]=mep['UserID']
        return mep['UserID']
    #print 'not mapped', text.encode('utf8')
    mepCache[userid]=None

last = None
meps = {}
_404 = set()
seen = set()
for vote in db.ep_votes.find({'ts' : {'$gte': _8th}}).sort([('ts', -1)]):
    if vote['ts'].isoformat() in seen:
        continue
    day = vote['ts'].replace(hour=0, minute=0, second=0, microsecond=0)
    if last != day:
        #print day
        meps.update({v['UserID']: {'name': v['Name']['full'],
                                   'last': v['Name']['family'],
                                   'active': v['active'],
                                   'votes': (meps[v['UserID']]['votes']+1) if v['UserID'] in meps else 1,
                                   'voted': meps[v['UserID']]['voted'] if v['UserID'] in meps else 0}
                     for v in getmeps(vote['ts'],
                                      ['active', 'UserID', 'Name.family', 'Name.full'])})
        last = day
    else:
        for m in getmeps(vote['ts'], ['UserID']):
            meps[m['UserID']]['votes']+=1
    total = 0
    vtotal = 0
    for iv in ['For', 'Against', 'Abstain']:
        vtotal+=int(vote[iv]['total'])
        for group in vote[iv]['groups']:
            for mep in group['votes']:
                mepid = getMep(mep['name'], mep['userid'], day)
                if mepid:
                    meps[mepid]['voted']+=1
                else:
                    _404.add(mep['name'])
                total+=1
    if total != vtotal:
        print >>sys.stderr, "[!] vtotal!=total"
    seen.add(vote['ts'].isoformat())

print 'name,id,voted,votes,percent,active'
for mep in sorted(((mep['name'],
                    mep['voted'],
                    mep['votes'],
                    (mep['voted']*100)/float(mep['votes']),
                    mep['active'],
                    id,
                    ((mep['voted']*-100)/float(mep['votes']),mep['last']))
                  for id, mep in meps.items()),
                  key=itemgetter(6)):
    print (u'"%s",%s,%s,%s,%3.2f,%s' % (mep[0], mep[5], mep[1], mep[2], mep[3], mep[4])).encode('utf8')
#print len(_404), u', '.join(sorted(_404)).encode('utf8')
