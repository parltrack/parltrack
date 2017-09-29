#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pymongo, sys
from datetime import datetime
conn = pymongo.Connection()
db=conn.parltrack

def getmeps(date,attrs=None):
    return db.ep_meps2.find({'Constituencies': {
                                '$elemMatch':
                                  {'start' : {'$lte': date},
                                   'end' : {'$gte': date}}}},
                            attrs)

def getdate(d):
    return datetime.strptime(d, "%Y/%m/%d")

date=getdate(sys.argv[1])
for mep in getmeps(date):
    name=mep['Name']['full']
    groupid=None
    for group in mep['Groups']:
        if group['start']<=date and group['end']>=date:
            groupid=group['groupid']
            group=group['Organization']
            break
    if not groupid:
        group=''
        groupid=''
    if groupid==[u'NA', u'NI']:
        groupid='NA'
        group='Not attached'
    party=''
    country=''
    for const in mep['Constituencies']:
        if const['start']<=date and const['end']>=date:
            party=const['party']
            country=const['country']
            break
    committees=[]
    for com in mep['Committees']:
        if com['start']<=date and com['end']>=date:
            committees.append((com['role'],com['abbr'],com['Organization']))
    print ("%s\t%s\t%s\t%s\t%s\t%s" % (name, country, party, groupid, group,'\t'.join(("%s\t%s\t%s" % (a,b,c) for a,b,c in committees)))).encode('utf8')
