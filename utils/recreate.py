#!/usr/bin/env python3

import sys, copy, traceback, functools
from utils.log import log

def getitem(item,path):
    if item in ({},[]) or path == []: return item
    if isinstance(item,dict) and path[0] not in item:
        log(1,"getitem: %s not in item" % path[0], item)
        return None

    try:
        return getitem(item[path[0]], path[1:])
    except:
        #print(traceback.format_exc())
        log(1,"getitem:", path, item)
        return None

def sortpaths(a,b):
    # should give this output ['activities', 0, 'docs', 0], ['activities', 0, 'docs', 1, 'url']
    # now gives the reverse
    a=a['path']
    b=b['path']
    if a[:len(b)] == b:
        # b is prefix of a
        return 1
    if b[:len(a)] == a:
        # a is prefix of b
        return -1
    if a>b: return -1
    if a<b: return 1
    return 0

def patch(obj, changes, guess=False, date=''):
    res = copy.deepcopy(obj)
    for l in sorted({len(x['path']) for x in changes}):
        # first handle deletes, they are indexed based on the old indexes
        #for change in sorted(changes, key=lambda x: x['path'], reverse=True):
        for change in sorted(changes, key=functools.cmp_to_key(sortpaths)):
            if change['type']!='deleted': continue
            if len(change['path'])!=l: continue
            obj=getitem(res,change['path'][:-1])
            if obj is None:
                log(1,"could not resolve path '%s', action: %s\ndata: %s" % (change['path'], change['type'], change['data']))
                return
            if isinstance(obj,dict) and change['path'][-1] not in obj:
                log(1,"cannot delete %s what is not there in %s" % (change['path'][-1], change['data']))
                log(1,change,obj)
                return
            elif isinstance(obj,list) and change['path'][-1]>=len(obj):
                log(1,"cannot delete %s what is not there in %s" % (change['path'][-1], change['data']))
                log(1,change,obj)
                return
            elif change['data']==obj[change['path'][-1]]:
                #log(3,"\tdeleting", change['path'])
                del obj[change['path'][-1]]
            else:
                log(1,"wtf change: %s\nobj: %s" % (change, obj))

        # handle adds
        for change in sorted(changes, key=lambda x: x['path']):
            if change['type']!='added': continue
            if len(change['path'])!=l: continue
            obj=getitem(res,change['path'][:-1])
            if obj is None:
                log(1,"could not resolve path '%s', action: %s\ndata: %s" % (change['path'], change['type'], change['data']))
                #log(1,list(x['path'] for x in sorted(changes, key=functools.cmp_to_key(sortpaths))))
                return
            #log(3,"\tadding", change['path'])
            if isinstance(obj,list):
                obj.insert(change['path'][-1],copy.deepcopy(change['data']))
            else:
                obj[change['path'][-1]]=copy.deepcopy(change['data'])

        # handle changes
        for change in changes:
            if change['type']!='changed': continue
            if len(change['path'])!=l: continue
            obj=getitem(res,change['path'][:-1])
            if obj is None:
                log(1,"could not resolve path '%s', action: %s\ndata: %s" % (change['path'], change['type'], change['data']))
                return
            if isinstance(obj,dict) and change['path'][-1] not in obj:
                log(1,"cannot change %s what is not there in %s" % (change['path'][-1], change['data']))
                return
            if isinstance(obj,list) and change['path'][-1]>=len(obj):
                log(1,"cannot change %s what is not there in %s" % (change['path'][-1], change['data']))
                return
            if obj[change['path'][-1]]==change['data'][0]:
                #log(3,"\tchanging", change['path'])
                obj[change['path'][-1]]=copy.deepcopy(change['data'][1])
            else:
                log(1,"wtf", change, obj)
    return res
