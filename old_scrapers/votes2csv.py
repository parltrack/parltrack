#!/usr/bin/env python

import json, sys

print sys.stdin.read(1) # skip leading [
for rec in sys.stdin:
    raw = json.loads(rec[:rec.rfind('}')+1].decode('utf8'))
    votes = []
    for act in ['Abstain', 'For', 'Against']:
        for grp in raw[act]['groups']:
            for mep in grp['votes']:
                res = {"group":  grp['group'],
                       "vote":   act}
                if type(mep) == dict:
                    res["mep"] = mep['orig']
                    res["mepid"] = mep['id']
                else:
                    res['mep'] = mep
                votes.append(res)
    raw['votes'] = votes
    del raw['For']; del raw['Abstain']; del raw['Against']
    # print json.dumps(raw, indent=1, ensure_ascii=False).encode('utf8'), ','
    print json.dumps(raw, ensure_ascii=False).encode('utf8'), ','
print ']'
