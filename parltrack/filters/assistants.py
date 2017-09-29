#!/usr/bin/env python

import json, sys

allj=json.load(sys.stdin)

print '\t'.join(('date','change','type','new','old'))
for date,changes in sorted(allj['changes'].items()):
    for change in changes:
        if change['path'][0]!='assistants': continue
        if len(change['path'])==1:
            #print date, change
            # {u'path': [u'assistants'], u'data': {u'local': [u'CHARBONNEAU Vanessa']}, u'type': u'added'}
            if change['type']=='added':
                for type, asses in change['data'].items():
                    for ass in asses:
                        print '\t'.join((date, 'add', type, ass)).encode('utf8')
            elif change['type']=='deleted':
                for type, asses in change['data'].items():
                    for ass in asses:
                        print '\t'.join((date, 'del', type, '', ass)).encode('utf8')
            else:
                print >>sys.stderr, "changed assistant dicts not implemented"
        else:
            #{u'path': [u'assistants', u'paying agents'], u'data': [u'DADILLON Marie-Alex'], u'type': u'added'}
            if change['type']=='changed':
                print u'\t'.join((date, 'chn', change['path'][1], change['data'][0], change['data'][1])).encode('utf8')
            elif change['type']=='added':
                if isinstance(change['data'], list):
                    for ass in change['data']:
                        print u'\t'.join((date, 'add', change['path'][1], ass)).encode('utf8')
                else:
                    print u'\t'.join((date, 'add', change['path'][1], change['data'])).encode('utf8')
            elif change['type']=='deleted':
                if isinstance(change['data'], list):
                    for ass in change['data']:
                        print '\t'.join((date, 'del', change['path'][1], '', ass)).encode('utf8')
                else:
                    print u'\t'.join((date, 'del', change['path'][1], '', change['data'])).encode('utf8')
