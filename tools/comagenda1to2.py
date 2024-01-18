#!/usr/bin/env python

import json, sys
from utils.utils import jdump
from db import db

with open(sys.argv[1], 'r') as f:
    items = json.load(f)

meetings = {}
for item in items:
    if 'time' not in item:
        if not 'date' in item:
            continue
        item['time']={
            'date': item['date'],
            'end' : item.get('end','')
            }
    if 'docid' not in item:
        item['docid']=f"{item['committee']}({item['date'][:4]}){item['date'][5:7]}{item['date'][8:10]}_XX"
    if item['docid'] in meetings:
        meeting = meetings[item['docid']]
    else:
        meeting = {
            'id' : item['docid'],
            'committee' : item['committee'],
            'src' : item['src'],
            'time': item['time'],
            'city':  item.get('city',''),
            'room' : item.get('room',''),
            'type': item.get('type', ''),
            'items': [],
        }
        meetings[item['docid']]=meeting

    elem = {'title': item['title']}
    meeting['items'].append(elem)

    dossier = {}
    for k in ['comdossier', 'epdoc', 'docref', 'tabling_deadline', 'procedure', 'otherdoc', 'comdoc', 'reading']:
        if k in item:
            dossier[k]=item[k]
    if 'epdoc' not in dossier:
        continue

    for type in item.get('actor',{}):
        for act in item['actor'][type]:
            if 'name' in act:
                if 'actors' not in dossier:
                    dossier['actors']=[]
                dossier['actors'].append({"name": act['name'], "type": type, 'mepref': act['mepref']})
    elem.update(dossier)

for meeting in meetings.values():
    db.put('ep_comagendas', meeting)

db.reindex('ep_comagendas')
db.commit('ep_comagendas')

#print(jdump(meetings))
