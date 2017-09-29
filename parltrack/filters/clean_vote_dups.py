#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import pymongo
from bson.objectid import ObjectId

conn = pymongo.Connection()
db=conn.parltrack
ep_votes=db.ep_votes

votes = {}
with open('ep_votes.json','r') as fd:
    line = fd.readline().strip()[1:] # skip leading [
    while(line):
        v = json.loads(line) # load line
        try:
            votes[v['ts']]['ids'].append(v['_id'])
            votes[v['ts']]['titles'].append(v['title'])
        except KeyError:
            votes[v['ts']] = {'ids': [v['_id']],
                              'titles': [v['title']]}

        line = fd.readline().strip()
        if line != ',':
            if line == ']':
                break
        line = fd.readline()

delete = []
for t, ids in votes.items():
    if len(ids['ids'])>1:
        #print (u"%2d %s\n\t%s" % (len(ids), t.encode('utf8'), u'\n\t'.join(ids['titles']))).encode('utf8')
        delete.extend([ObjectId(x) for x in ids['ids'][:-1]])
print 'total dups', len(set(delete))
ep_votes.remove({ '_id': { '$in': delete}})
