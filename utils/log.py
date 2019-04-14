#!/usr/bin/env python3

from datetime import datetime
import inspect

loglevel=4 # info

LEVELS = ('quiet', 'error', 'warning', 'info', 'debug')

def log(level, msg):
    scraper = '??? '
    for frame in inspect.stack():
        fp=frame.filename.split('/')
        if len(fp)>1 and fp[-2]=='scrapers':
            scraper = fp[-1].split('.')[0]
            break
        if len(fp)==1:
            if fp[0]=='db.py':
                scraper='db'
                break
            if fp[0]=='scraper_service.py':
                scraper='mgr'
                break
    else:
        print("{ts} log error unknown module: {stack}".format(ts=datetime.isoformat(datetime.now()), stack=inspect.stack()))
        scraper = '???'

    if level <= loglevel:
        print("{ts} {scraper} {level} {msg}".format(ts=datetime.isoformat(datetime.now()), level=LEVELS[level], scraper=scraper, msg=msg))

def set_level(l):
    global loglevel
    loglevel=l
