#!/usr/bin/env python3

import sys
from os.path import exists
from datetime import datetime
from utils.log import LEVELS

def usage():
    print("%s <debug|info|warn(ing)|err(or)> <logfile")
    sys.exit(0)

def parse(line):
    tokens = line.split()
    if len(tokens)<4: return line
    try:
        date = datetime.fromisoformat(tokens[0])
    except:
        return line
    if tokens[1] not in ['db','dossier','dossiers','mep','meps','mgr','pvote','pvotes', 'amendment', 'amendments', 'comagenda', 'comagendas', 'mep_activities', 'mep_activity']:
        return line
    module = tokens[1]
    if tokens[2] not in LEVELS:
        return line
    level = LEVELS.index(tokens[2])
    msg = ' '.join(tokens[3:])
    return (date, module, level, tokens[2], msg)

def dump(date, module, level, levelz, msg):
    color = (lambda x: x,
             lambda x: "\033[41m\033[93m%s\033[0m" % x, # error
             lambda x: "\033[43m\033[90m%s\033[0m" % x, # warning
             lambda x: "%s" % x, # info
             lambda x: "\033[38;2;127;127;127m%s\033[0m" % x) # debug
    cmod = {
        'db': "db",
        "mgr": "mgr",
        "mep": "mep",
        "meps": "\033[38;2;127;127;127mmeps\033[0m",
        "dossier": "dossier",
        "dossiers": "\033[38;2;127;127;127mpvotes\033[0m",
        "pvote": "pvote",
        "pvotes": "\033[38;2;127;127;127mpvotes\033[0m",
        "amendment": "amendment",
        "amendments": "\033[38;2;127;127;127mamendments\033[0m",
        "comagenda": "comagenda",
        "comagendas": "\033[38;2;127;127;127mcomagendas\033[0m",
        "mep_activity": "mep_activity",
        "mep_activities": "\033[38;2;127;127;127mmep_activities\033[0m",
    }
    if dlevel<level:
        return
    print("%s %s %s %s" % (date.isoformat(), cmod[module], color[level](levelz), msg))

dlevel = 0
fname = None
for arg in sys.argv[1:]:
    if arg == 'help':
        usage()
    elif arg == 'debug':
        dlevel=4
    elif arg == 'info':
        dlevel=3
    elif arg in ['warn', 'warning']:
        dlevel=2
    elif arg in ['err', 'error']:
        dlevel=1
    else:
        print('unknown parameter "%s"' % repr(arg))
        usage()

stats = {l:0 for l in LEVELS}
changes = {}
nobody = {}
plev = 0
insummary = False
exceptions=0

buffer = []
for line in sys.stdin:
    tmp = parse(line)
    if tmp==line:
        if line.strip()=='Traceback (most recent call last):':
            plev=0
            exceptions+=1
            buffer.append(line[:-1])
        # some other string
        if dlevel>=plev: # only do stuff if we would print this out anyway
            if not insummary: # strip out summaries
                if line.strip() == '"summary": [':
                    buffer.append(line[:-1]+'...\033[48;2;127;127;127mstripped\033[0m...')
                    insummary=True
                    continue
            else:
                if line.strip() in [']', '],']:
                    insummary=False
                continue
            buffer.append(line[:-1])
    else:
        if buffer:
            # handle buffer
            if dlevel>=plev:
                t = '\n'.join(buffer).strip()
                if t: print("%s\n" % t)
            buffer=[]
        (date, module, level, levelz, msg) = tmp
        stats[levelz]+=1
        if msg.startswith('no body mapping found for'):
            if msg[25:] not in nobody: nobody[msg[25:]]=0
            nobody[msg[25:]]+=1
        #if msg.startswith("preserving deleted path ['other'] for obj id:"): # todo remove
        #    continue
        if module in ['dossier','mep','pvote','amendment', 'comagenda', 'mep_activity'] and level==3 and msg.startswith("adding "):
            if module not in changes: changes[module]={'added':0, 'updated':0}
            changes[module]['added']+=1
        if module in ['dossier','mep','pvote','amendment', 'comagenda', 'mep_activity'] and level==3 and msg.startswith("updating "):
            if module not in changes: changes[module]={'added':0, 'updated':0}
            changes[module]['updated']+=1
        dump(date, module, level, levelz, msg)
        plev = level

if buffer:
    # handle buffer
    if dlevel>=plev:
        t = '\n'.join(buffer).strip()
        if t: print("%s\n" % t)

# print stats
print("stats")
for mod, s in changes.items():
    for l, v  in s.items():
        print("\t%s %s:%d" % (mod,l,v))
print()
print("\t%d exceptions" % exceptions)
for l,v in stats.items():
    if l=='quiet': continue
    print("\t%d %s messages" % (v,l))
print("nobodies")
for l,v in sorted(nobody.items(),key=lambda x: x[1], reverse=True):
    print("\t%4d %s" % (v,l))
