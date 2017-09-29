#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import pymongo
from bson.objectid import ObjectId
import re, sys, unicodedata

mepmap={'vanbuitenen': 28264, 'devilliers': 2212, 'matoadrover': 28383, 'kinnock': 2123, 'merkies': 96910, 'morin': 38596, 'valenciano': 4334,
        'vitkauskaite': 30475, 'kleva': 23413, 'manner': 96685, "scotta'": 96996, 'briardauconie': 96862, 'obiols': 4328, 'vozemberg': 125065,
        'thunundhohenstein': 96776, 'iglesias': 125031, 'mathieu': 4412, 'landsbergis': 23746, 'nedelcheva': 96848, 'iturgaiz': 28398,
        'auconie': 96862, 'mihaylova': 125128, 'obiolsigerma': 4328, 'valencianomartinez-orozco': 4334, 'stassen': 96905, 'larsen-jensen':
        122404, 'degroen-kouwenhoven': 28265, 'cronberg': 107973, 'vanderkammen': 115868, 'vonwogau': 1224, 'jensen': 4440,
        'jordancizelj': 28291, 'glezos': 1654, 'gentvilas': 28283, 'meyerpleite': 28407, 'devits': 28259, 'jukneviciene': 28273, 'jordan':
        28291, 'savisaar': 97308, 'miranda': 24942, 'vandenburg': 4483, 'ceballos': 124993, 'demagistris': 97129, 'vanderstoep': 96946,
        'meyer': 28407, 'pakarinen': 96685, 'iturgaizangulo': 28398, 'barracciu': 116823, 'dossantos': 21918, 'gabriel': 96848,
        'hutchinson': 28282, 'valero': 124993, 'tsoukalas': 96898, 'krupa': 28334, 'scotta': 96996, 'piecha': 124874}

conn = pymongo.Connection()
db=conn.parltrack
ep_votes=db.ep_votes

# change them according to the mapping
#for vote in db.ep_votes.find():
#    changed=False
#    for act in ['Abstain', 'For', 'Against']:
#	for g in vote.get(act,{'groups': []})['groups']: 
#	     for v in g['votes']: 
#                mepid=None
#                if isinstance(v, dict) and 'ep_id' in v and v['ep_id']:
#                    continue
#                m=mepmap.get(''.join(unicodedata.normalize('NFKD', unicode(v['name'].strip())).encode('ascii','ignore').split()).lower())
#                if m:
#                    v['ep_id']=m
#                    changed=True
#                else:
#                    print >>sys.stderr, v
#    if changed: db.ep_votes.save(vote)

seen = set()
for vote in db.ep_votes.find():
    for act in ['Abstain', 'For', 'Against']:
	for g in vote.get(act,{'groups': []})['groups']: 
	     for v in g['votes']: 
                mepid=None
                if isinstance(v, dict) and 'ep_id' in v and v['ep_id']:
                    continue
                m=mepmap.get(''.join(unicodedata.normalize('NFKD', unicode(v['name'].strip())).encode('ascii','ignore').split()).lower())
                if m:
                    v['ep_id']=m
                if repr(v) in seen: continue
                seen.add(repr(v))
                print v
    #db.ep_votes.save(vote)
