#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pymongo, unicodedata, re, sys
from datetime import datetime
from operator import itemgetter

conn = pymongo.Connection()
db=conn.parltrack
dossiers=db.dossiers
meps=db.ep_meps2

#updates={u'COELHO, Carlos': [u'Coelho Carlo', u'coelho carlo', u'coelhocarlo'],
#	u'TRAKATELLIS, Antonios': [u'M Trakatellis', u'm trakatellis', u'mtrakatellis'],
#	u'FAVA, Claudio': [u'Giovanni Claudio Fava', u'giovanni claudio fava', u'giovanniclaudiofava'],
#	u'TOMCZAK, Witold': [u'W. Tomczak', u'w. tomczak', u'w.tomczak'],
#	u'PĘCZAK, Andrzej Lech': [u'A. Peczak', u'a. peczak', u'a.peczak'],
#	u'SAKELLARIOU, Jannis': [u'Janis Sakellariou', u'janis sakellariou', u'janissakellariou'],
#	u'GOROSTIAGA ATXALANDABASO, Koldo': [u'Koldo Gorostiaga', u'koldo gorostiaga', u'koldogorostiaga'],}
#for k,v in updates.items():
#    mep=db.ep_meps.find_one({'Name.full': k})
#    mep['Name']['aliases'].extend(v)
#    meps.save(mep)

# res=[]
# for mep in meps.find({'Committees.abbr': 'INTA'}):
# 	skip=False
# 	for c in mep['Committees']:
# 		if c['abbr']=='INTA' and c['role']=='Substitute':
# 			skip=True
# 			break
# 	if skip: continue
# 	
# 	res.append((mep['Name']['full'], str(mep['Groups'][0]['groupid']), mep['Addresses']['Brussels']['Address']['Office']))
# for x in sorted(res,key=itemgetter(2)):
# 	print u':'.join(x)
res=[]
for mep in meps.find({'active': True}):
	if not mep.get('Mail'):
		print >>sys.stderr, "[!] nomail:",  mep['Name']['full']
		continue
	res.append("%s <%s>\t%s\t%s" % (mep['Name']['full'],
                                        mep['Mail'][0],
                                        mep.get('Twitter',[''])[0],
                                        mep.get('Facebook',[''])[0]))
for x in sorted(res, reverse=True):
	print x.encode('utf8')
