#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pymongo, unicodedata, re, sys
from datetime import datetime
from operator import itemgetter

conn = pymongo.Connection()
db=conn.parltrack
dossiers=db.dossiers
meps=db.ep_meps2

res=[]
for mep in meps.find({'active': True}):
	if not mep.get('Mail'):
		print >>sys.stderr, "[!] nomail:",  mep['Name']['full']
		continue
	res.append((mep['Name']['full'], "<%s>" % mep['Mail'][0]))
for x in sorted(res, reverse=True):
	print (u' '.join(x)).encode('utf8')
