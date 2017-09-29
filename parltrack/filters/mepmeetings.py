#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pymongo, sys
from datetime import datetime
conn = pymongo.Connection()
db=conn.parltrack

for mep in db.ep_meps2.find():
    if "Declarations of Participation" in mep:
        for meeting in mep["Declarations of Participation"]:
            print meeting
