#!/usr/bin/env python3

from config import DEBUG, DB_DEBUG

from threading import RLock
from datetime import datetime
import inspect
import sys

if DEBUG:
    loglevel = 4 # debug
else:
    loglevel = 3 # info
logfile = sys.stdout
lock = RLock()

LEVELS = ('quiet', 'error', 'warning', 'info', 'debug')

module_mapping = {
    'db.py': 'db',
    'scraper_service.py': 'mgr',
    'webapp.py': 'webapp',
}

def log(level, msg):
    if not logfile: return
    if level > loglevel:
        return
    module = '??? '
    lock.acquire()
    for frame in inspect.stack():
        try:
            fp=frame.filename.split('/')
        except:
            continue
        if len(fp)>1 and fp[-2]=='modules':
            module = fp[-1].split('.')[0]
            break
        if fp[-1] in module_mapping:
            module = module_mapping[fp[-1]]
            break
        if len(fp)>1 and fp[-2]=='scrapers':
            module = f'scraper:{fp[-1]}'
            break
    #else:
    #    if level <= 4:
    #        logfile.write("{ts} log error unknown module: {stack}\n".format(ts=datetime.isoformat(datetime.now()), stack=inspect.stack()[1].filename))

    if module == 'db' and LEVELS[level] == 'debug' and not DB_DEBUG:
        lock.release()
        return

    #stack = ' '.join(f"{frame.filename}:{frame.lineno}" for frame in inspect.stack()[1:])
    #logfile.write("{ts} {module} {level} {stack} {size} {msg}\n".format(ts=datetime.isoformat(datetime.now()), level=LEVELS[level], module=module, msg=msg, stack=stack, size=len(msg)))
    logfile.write("{ts} {module} {level} {msg}\n".format(ts=datetime.isoformat(datetime.now()), level=LEVELS[level], module=module, msg=msg))
    lock.release()

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
