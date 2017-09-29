#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pymongo, sys
from datetime import datetime
conn = pymongo.Connection()
db=conn.parltrack

for mep in db.ep_meps2.find():
    old = len(repr(mep))
    for ts, changes in mep['changes'].items():
        updated = []
        for delta in changes:
            if delta['path'][0]=='activities': continue
            updated.append(delta)
        mep['changes'][ts]=updated
    #print old - len(repr(mep))
    db.ep_meps2.save(mep)
