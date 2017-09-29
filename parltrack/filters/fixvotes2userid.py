#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json, sys
import pymongo
from bson.objectid import ObjectId
import re, unicodedata

conn = pymongo.Connection()
db=conn.parltrack

mepmap={u"Juknevičienė": u"RAINYTÉ-BODARD",
        u'Vozemberg': u'VOZEMBERG-VRIONIDI',
        u'Thun und Hohenstein': u'von THUN UND HOHENSTEIN',
        u'Piecha': u'G. Piecha',
        u'Ceballos': u'Valero',
        u"Jordan amCizelj": u"Jordan"}

mepCache={}
def getMep(text,date):
    if text in mepmap:
        text = mepmap[text]
    name=''.join(unicodedata.normalize('NFKD', unicode(text.strip())).encode('ascii','ignore').split()).lower()
    if name in mepCache:
        return mepCache[name]

    if not name: return
    if name.endswith('('): name=name[:-1].strip()
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

def get_mepid(oid):
    if not oid: return
    if oid in mepCache:
        return mepCache[oid]
    mep = db.ep_meps2.find_one({'_id': ObjectId(oid)})
    if mep:
        mepCache[oid]=mep['UserID']
        return mep['UserID']

for vote in db.ep_votes.find():
    for act in ['Abstain', 'For', 'Against']:
	for g in vote.get(act,{'groups': []})['groups']: 
	     for v in g['votes']: 
                mepid=None
		if type(v) == dict and 'id'in v:
                    mepid=get_mepid(v['id']) 
		elif type(v) == dict and 'userid'in v:
                    mepid= getMep(v['name'], vote['ts'])
                elif type(v) in [str, unicode]:
                    mepid=getMep(v, vote['ts'])
                    if mepid:
                        v1 = {'name': v}
                        g['votes'][g['votes'].index(v)]=v1
                        v = v1
                else:
                    print "wtf", repr(v)
                if not mepid: 
                    #print type(v), repr(v), vote['ts']
                    continue
                v['UserID']=mepid
    db.ep_votes.save(vote)
