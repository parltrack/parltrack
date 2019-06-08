#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from utils.log import log
def merge_events(d):
    activities=[]
    for ktype in ['docs','events','forecasts','council','commission','otherinst','committees']:
        for item in d.get(ktype,[]):
            if 'date' not in item:
                #other.append(item)
                continue
            if item.get('title') and not 'type' in item:
                item['type'] = item['title']
                del(item['title'])
            if item.get('body')=='EC' and len(d.get('commission', []))==1:
                item.update(d['commission'][0])
            if isinstance(item['date'], list):
                if not len(item['date']):
                    continue
                if len(set(item['date']))==1:
                    item['date']=item['date'][0]
                else:
                    print("more than one date in: ", item)
            if not item.get("body") and item.get('type')!='Final act published in Official Journal':
                log(2,"merge_events: no body for {!r}".format({k:v for k, v in item.items() if k!='summary'}))
                #continue #print(item)
            activities.append(item)
    res=sorted(activities,key=lambda x: x['date'], reverse=True)
    return res

if __name__ == '__main__':
    from db import db
    d = db.dossier('2016/0279(COD)')
    from utils.utils import jdump
    print(jdump(merge_events(d)))
