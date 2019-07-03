#!/usr/bin/env python3

from db import db
from utils.log import log

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

def scrape(all=False, **kwargs):
    if all:
        for id in db.keys('ep_meps'):
            add_job('mep_activity', id)
            #print(id)
    else:
        for mep in db.meps_by_activity(True):
            id = mep['UserID']
            add_job('mep_activity', id)
            #print(id)

if __name__ == '__main__':
    #actives = {e['UserID'] for e in db.meps_by_activity(True)}
    #inactives = {e['UserID'] for e in db.meps_by_activity(False)}
    #meps = actives | inactives
    #print(len(meps))
    #print(max(meps))
    #print(len([x for x in meps if x < 113000]))
    scrape(True)
