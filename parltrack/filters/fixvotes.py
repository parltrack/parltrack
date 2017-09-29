#!/usr/bin/env python

import json, sys
import pymongo
from bson.objectid import ObjectId

conn = pymongo.Connection()
db=conn.parltrack

mappings = json.load(open('mepids.json'))

for vote in db.ep_votes.find():
    for act in ['Abstain', 'For', 'Against']:
	for g in vote.get(act,{'groups': []})['groups']: 
	     for v in g['votes']: 
		if type(v) == dict and str(v['id']) in mappings:
			print 'mapping', v['id'], 'to', mappings[str(v['id'])] 
			v['id']=ObjectId(mappings[str(v['id'])])
	for c in vote.get(act,{'correctional': []}).get('correctional',[]): 
		if type(c) == dict and str(c['id']) in mappings:
			print 'mapping', c['id'], 'to', mappings[str(c['id'])] 
			c['id']=ObjectId(mappings[str(c['id'])])
	db.ep_votes.save(vote)
