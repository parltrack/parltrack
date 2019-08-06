#!/usr/bin/env python3

from db import db
from utils.log import log
from config import CURRENT_TERM

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

def scrape(all=False, **kwargs):
    jobs=[]
    if all:
        for id in db.keys('ep_meps'):
            mep = db.mep(id)
            payload = dict(kwargs)
            payload['id'] = id
            payload['mepname']=mep['Name']['full']
            payload['terms']= {c.get('term') for c in mep.get('Constituencies',[]) if c}
            jobs.append(payload)
            #add_job('mep_activity', payload)
    else:
        for mep in db.meps_by_activity(True):
            payload = dict(kwargs)
            payload['id'] = mep['UserID']
            payload['mepname']=mep['Name']['full']
            payload['terms']={CURRENT_TERM}
            #add_job('mep_activity', payload)
            jobs.append(payload)
    for payload in jobs:
        add_job('mep_activity', payload)

if __name__ == '__main__':
    #actives = {e['UserID'] for e in db.meps_by_activity(True)}
    #inactives = {e['UserID'] for e in db.meps_by_activity(False)}
    #meps = actives | inactives
    #print(len(meps))
    #print(max(meps))
    #print(len([x for x in meps if x < 113000]))
    scrape(True)
