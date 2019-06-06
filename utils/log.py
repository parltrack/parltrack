#!/usr/bin/env python3

from datetime import datetime
import inspect
import sys

loglevel=4 # info
logfile = sys.stdout

LEVELS = ('quiet', 'error', 'warning', 'info', 'debug')

def log(level, msg):
    if not logfile: return
    scraper = '??? '
    for frame in inspect.stack():
        fp=frame.filename.split('/')
        if len(fp)>1 and fp[-2]=='scrapers':
            scraper = fp[-1].split('.')[0]
            break
        if fp[-1]=='db.py':
            scraper='db'
            break
        if fp[-1]=='scraper_service.py':
            scraper='mgr'
            break
        if fp[-1]=='webapp.py':
            scraper='webapp'
            break
    else:
        if level <= loglevel:
            logfile.write("{ts} log error unknown module: {stack}\n".format(ts=datetime.isoformat(datetime.now()), stack=inspect.stack()))
        scraper = '???'

    if level <= loglevel:
        logfile.write("{ts} {scraper} {level} {msg}\n".format(ts=datetime.isoformat(datetime.now()), level=LEVELS[level], scraper=scraper, msg=msg))

def set_level(l):
    global loglevel
    loglevel=l

def set_logfile(l):
    global logfile
    if logfile and logfile not in [sys.stdout, sys.stderr]:
        logfile.close()
        logfile=None
    if l in [sys.stdout, sys.stderr]:
        logfile = l
    elif l:
        logfile=open(l,'w')
