#!/usr/bin/env python

import json, sys

print sys.stdin.read(1) # skip leading [
print '\t'.join(['mep','group','vote','report','issue','voteid','ep_title','mepid'])
for rec in sys.stdin:
    line = rec[:rec.rfind('}')+1].decode('utf8')
    if not line: continue
    raw = json.loads(line)
    votes = []
    for act in ['Abstain', 'For', 'Against']:
        if not act in raw: continue
        for grp in raw[act]['groups']:
            for mep in grp['votes']:
                print u'\t'.join([
                    mep['name'],
                    grp.get('group',''),
                    act,
                    raw.get('report',''),
                    raw.get('issue_type',''),
                    raw.get('voteid',''),
                    raw.get('eptitle',''),
                    str(mep['ep_id'])]).encode('utf8')
