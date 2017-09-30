#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pymongo, sys
from datetime import datetime
conn = pymongo.Connection()
db=conn.parltrack

def mepname(mep):
    return mep['Name']['full']
def mepid(mep):
    return mep['UserID']

def dossiertitle(dossier):
    return dossier['procedure']['title']
def dossierid(dossier):
    return dossier['procedure']['reference']

if sys.argv[1]=='meps':
    table=db.ep_meps2
    itemid=mepid
    itemtitle=mepname
elif sys.argv[1]=='dossiers':
    table=db.dossiers2
    itemid=dossierid
    itemtitle=dossiertitle
else:
    print "pls provide meps|dossiers as first param at least"
    sys.exit(1)

path=[]
type=None

if len(sys.argv)>2: path=sys.argv[2].split('/')
if len(sys.argv)>3: type=sys.argv[3]

if type not in ['added','deleted','changed',None]:
    print 'wrong type:', type, "pls use either added|updated"

for item in table.find():
    for ts, changes in item['changes'].items():
        updated = []
        for delta in changes:
            if type and delta['type']!=type: continue
            skip=False
            for p1,p2 in zip(delta['path'],path):
                if p1!=p2: skip=True
            if skip: continue
            print u'\t'.join([ts, unicode(itemid(item)), itemtitle(item), delta['type'], '/'.join(unicode(x) for x in delta['path']), unicode(delta['data'])]).encode('utf8')
