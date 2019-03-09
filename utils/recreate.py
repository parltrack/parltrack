#!/usr/bin/env python3

import sys, copy, traceback, functools, copy
from json import loads, dumps
from utils.utils import printdict, diff, showdiff
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

def recreate(changelog, tdate, guess=False):
    res={}
    for date, changes in sorted(changelog.items()):
        if date>tdate: break
        log(1,'merging changelog %s' % date)
        res = patch(res, changes, guess, date)
        if not res: break
        #log(1,dumps(res))
    return res

def revert(obj,tdate=None, guess=False):
    warn=False
    res={k:v for k,v in obj.items() if k not in ('changes','meta')}
    changelog=obj['changes']
    clen = len(changelog.keys())
    for i, (date, changes) in enumerate(sorted(changelog.items(), reverse=True)):
        if tdate and date<tdate: break
        print('undoing changelog %s' % date)
        changes=mergeaddels(changes)

        for l in sorted({len(x['path']) for x in changes}, reverse=True):
            # undo deletes
            for change in sorted(changes, key=lambda x: x['path']):
                if change['type']!='deleted': continue
                if len(change['path'])!=l: continue
                obj=getitem(res,change['path'][:-1])
                if obj is None:
                    log(1,"could not resolve path '%s', action: %s\ndata: %s" % (change['path'], change['type'], change['data']))
                    #print(list(x['path'] for x in sorted(changes, key=functools.cmp_to_key(sortpaths))))
                    return (i,clen)
                #log(3, "\tadding", change['path'])
                if isinstance(obj,list):
                    obj.insert(change['path'][-1],copy.deepcopy(change['data']))
                else:
                    obj[change['path'][-1]]=copy.deepcopy(change['data'])

            # undo adds, they are indexed based on the new indexes
            for change in sorted(changes, key=functools.cmp_to_key(sortpaths)):
                if change['type']!='added': continue
                if len(change['path'])!=l: continue
                obj=getitem(res,change['path'][:-1])
                if obj is None:
                    log(1,"could not resolve path '%s', action: %s\ndata: %s" % (change['path'], change['type'], change['data']))
                    return (i,clen)

                if isinstance(obj,dict) and change['path'][-1] not in obj:
                    log(1,"cannot delete %s what is not there in %s" % (change['path'][-1], change['data']))
                    if not guess: return (i,clen)
                elif isinstance(obj,list) and change['path'][-1]>=len(obj):
                    log(1,"cannot delete %s what is not there in %s" % (change['path'][-1], change['data']))
                    if not guess: return (i,clen)
                elif change['data']==obj[change['path'][-1]]:
                    #log(1,"\tdeleting", change['path'])
                    del obj[change['path'][-1]]
                    continue
                return (i,clen)

            # handle changes
            for change in changes:
                if change['type']!='changed': continue
                if len(change['path'])!=l: continue
                obj=getitem(res,change['path'][:-1])
                if obj is None:
                    log(1,"could not resolve path '%s', action: %s\ndata: %s" % (change['path'], change['type'], change['data']))
                    return (i,clen)
                if isinstance(obj,dict) and change['path'][-1] not in obj:
                    log(1,"cannot delete %s what is not there in %s" % (change['path'][-1], change['data']))
                    if not guess: return (i,clen)
                elif isinstance(obj,list) and change['path'][-1]>=len(obj):
                    log(1,"cannot delete %s what is not there in %s" % (change['path'][-1], change['data']))
                    if not guess: return (i,clen)
                elif obj[change['path'][-1]]==change['data'][1]:
                    #log(1,"\tchanging", change['path'])
                    obj[change['path'][-1]]=copy.deepcopy(change['data'][0])
                    continue
                return (i,clen)

        #log(1,dumps(res))
    return "reverted %d/%d"% (i,clen)

def test():
    fd = sys.stdin
    if fd.read(1) != '[': # skip starting [
        log(1,'no starting [')
        sys.exit(1)
    rec = fd.readline()
    while rec:
        fd.readline() # skip comma
        rec=loads(rec.strip())
        #print("recreating", rec['procedure']['reference'],end=" ")
        d=max(rec['changes'].keys())
        ret=recreate(rec['changes'],d)
        if ret is None or ret[0]:
            #print("failed")
            print(rec['procedure']['reference'])
        else:
            bare={k:v for k,v in rec.items() if k not in ('changes','meta', '_id')}
            d = diff(bare, ret[1])
            if d != []:
                print(rec['procedure']['reference'],d)
            else:
                bare['changes']=rec['changes']
                #global debug
                #debug=True
                print(rec['procedure']['reference'], revert(bare))
                #debug=False
        rec = fd.readline()

if __name__ == "__main__":
   #debug=True
   test()
