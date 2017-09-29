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
	if not mep.get('assistants'):
		print >>sys.stderr, "[!] noassistants:",  mep['Name']['full']
		continue
	for ass in mep['assistants'].get('local',[]):
	 	print ass.encode('utf8')
	for ass in mep['assistants'].get('accredited',[]):
	 	print ass.encode('utf8')
