#!/usr/bin/env python3

from datetime import datetime

loglevel=4 # info

LEVELS = ('quiet', 'error', 'warning', 'info', 'debug')

def log(level, msg):
    if level <= loglevel:
        print("{ts} {level} {msg}".format(ts=datetime.isoformat(datetime.now()), level=LEVELS[level], msg=msg))

def set_level(l):
    global loglevel
    loglevel=l
