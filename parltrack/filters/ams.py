#!/usr/bin/env python

import json
from collections import defaultdict

def load_items(path,key=None,val=None):
    with open(path, 'r') as fd:
        block=[]
        for line in fd:
            if line.strip() not in [',', '}]', '[{']:
                block.append(line.strip())
                continue
            if line.strip()=='[{':
                block.append('{')
                continue
            if line.strip()=='}]':
                block.append('}')
            item=json.loads(''.join(block))
            block=[]
            if key==None or item.get(key)==val:
                yield item
    yield None

l1order=['Title', 'Recital', 'Chapter', 'Article', 'Citation', 'Annex']
def canloc(item):
    loc = item[0]
    return (l1order.index(loc[0].split()[0]),) + \
           tuple([int(x) if x.isdigit() else x for x in loc[0].split()[1:]]) + \
           tuple([int(x) if x.isdigit() else x for y in loc[1:] for x in y.split()])

def votelist(ams):
    res={}
    for item in ams:
        loc=tuple(item['location'][0][1].split(u' \u2013 '))
        if not loc in res:
            res[loc]={'reference': item['reference'],
                      'ams': [],
                      }
            if 'old' in item:
                res[loc]['old']=item['old']
        same=None
        for lm in res[loc]['ams']:
            if lm['new']==item['new']:
                same=lm
                lm['am'].append({
                    'src': item['src'],
                    'seq': item['seq'],
                    'meps': item['meps'],
                    'justification': item.get('justification'),
                    'orig_lang': item['orig_lang'],
                    'committee': item['committee'][0],
                    })
                break
        if not same:
            res[loc]['ams'].append({
                'new': item['new'],
                'am': [{ 'src': item['src'],
                         'seq': item['seq'],
                         'meps': item['meps'],
                         'justification': item.get('justification'),
                         'orig_lang': item['orig_lang'],
                         'committee': item['committee'][0],
                         }],
                })
    return sorted(res.items(), key=canloc)

import pprint
import pymongo
from bson.objectid import ObjectId

db=pymongo.Connection().parltrack
leadc='LIBE'
print """
<html><head><title>voting list</title>
<meta http-equiv="content-type" content="text/html; charset=utf-8" />
</head>
<body>
<table border="1"><thead><tr><td>Text in consideration</td><td>AM</td><td>Tabled By</td><td>Position of the Rapporteur</td><td>Comments</td><td>Results</td></tr></thead>
"""
with open('dpr.json', 'r') as fd:
    for path, frag in votelist(json.load(fd)):
        #pprint.pprint(frag)
        cnt=0
        res=[]
        for amc in frag['ams']:
            for am in amc['am']:
                cnt+=1
                if am['committee']==leadc:
                    res.append("<td><a href='http://parltrack.euwiki.org/amendment/%s/%s/%s'>AM %s</a></td>" \
                               "<td>%s</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr><tr>" %
                               (frag['reference'],
                                am['committee'],
                                am['seq'],
                                am['seq'],
                                u', '.join([(db.ep_meps2.find_one({'_id': ObjectId(mep)},['Name.full']) or
                                             db.ep_meps.find_one({'_id': ObjectId(mep)},['Name.full']))['Name']['full']
                                            for mep in am.get('meps',[])
                                            ])))
                else:
                    res.append("<td style='background: #ccc;'><a href='http://parltrack.euwiki.org/amendment/%s/%s/%s'>AM %s</a></td>" \
                               "<td style='background: #ccc;'>%s</td>" \
                               "<td style='background: #ccc;'>&nbsp;</td>" \
                               "<td style='background: #ccc;'>&nbsp;</td>" \
                               "<td style='background: #ccc;'>&nbsp;</td></tr><tr>" % (frag['reference'],
                                                                                       am['committee'],
                                                                                       am['seq'],
                                                                                       am['seq'],
                                                                                       am['committee']))
                #pprint.pprint(am)
        print u'<tr><td rowspan="%s" style="vertical-align: top">' % cnt,u' - '.join(path),"</td>"
        print u''.join(res).encode('utf8')
print """
</body
</html>
"""
