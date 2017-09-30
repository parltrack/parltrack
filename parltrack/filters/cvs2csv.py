#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pymongo, sys
from datetime import datetime
conn = pymongo.Connection()
db=conn.parltrack


for mep in db.ep_meps2.find():
    term8=False
    for c in mep.get('Constituencies',[]):
        if not c or 'start' not in c: continue
        if c['start']>=datetime(2014,07,01):
            term8=True
    if not term8: continue
    
    name=mep['Name']['full']
    groupid=None
    for const in mep['Constituencies']:
        if const['start']>=datetime(2014,07,01):
            party=const['party']
            country=const['country']
            start=const['start']
            end=const['end']
            break
    for sec in mep['CV']:
        for line in mep['CV'][sec]:
            print ("%s\t%s\t%s\t%s\t%s\t%s\t%s" % (name, country, party, sec, line, start, end)).encode('utf8')
