#!/usr/bin/env python3

from config import DEBUG, DB_DEBUG

from datetime import datetime
import inspect
import sys

loglevel=4 # info
logfile = sys.stdout

LEVELS = ('quiet', 'error', 'warning', 'info', 'debug')

def log(level, msg):
    if not logfile: return
    module = '??? '
    for frame in inspect.stack():
        try:
            fp=frame.filename.split('/')
        except:
            continue
        if len(fp)>1 and fp[-2]=='modules':
            module = fp[-1].split('.')[0]
            break
        if fp[-1]=='db.py':
            module='db'
            break
        if fp[-1]=='module_service.py':
            module='mgr'
            break
        if fp[-1]=='webapp.py':
            module='webapp'
            break
    else:
        if level <= loglevel:
            logfile.write("{ts} log error unknown module: {stack}\n".format(ts=datetime.isoformat(datetime.now()), stack=inspect.stack()[1].filename))
        module = '???'

    if module == 'db' and LEVELS[level] == 'debug' and not DB_DEBUG:
        return

    if level <= loglevel:
        #stack = ' '.join(f"{frame.filename}:{frame.lineno}" for frame in inspect.stack()[1:])
        #logfile.write("{ts} {module} {level} {stack} {size} {msg}\n".format(ts=datetime.isoformat(datetime.now()), level=LEVELS[level], module=module, msg=msg, stack=stack, size=len(msg)))
        logfile.write("{ts} {module} {level} {msg}\n".format(ts=datetime.isoformat(datetime.now()), level=LEVELS[level], module=module, msg=msg))

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
