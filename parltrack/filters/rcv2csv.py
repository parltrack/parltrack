#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json, sys
import pymongo
from bson.objectid import ObjectId
import re, unicodedata

conn = pymongo.Connection()
db=conn.parltrack

# 2015/2103(INL) - A8-0005/2017 - Mady Delvaux - § 44/2

vote = db.ep_votes.find_one({"title" : "A8-0005/2017 -  Mady Delvaux - § 44/2"})
for act in ['Abstain', 'For', 'Against']:
    for g in vote.get(act,{'groups': []})['groups']: 
         for v in g['votes']: 
             mep = db.ep_meps2.find_one({"UserID": v['ep_id']}, {"changes": False})
             print u'\t'.join((act,
                              mep['Name']['family'],
                              mep['Name']['sur'],
                              mep['Constituencies'][0]['country'],  # this is naive and probably buggy
                              g['group'],
                              mep.get('Mail',[''])[0],
                              mep.get('Twitter',[''])[0],
                              mep.get('Facebook',[''])[0],
                              mep['Addresses']['Brussels']['Phone'],
                              )).encode('utf8')
