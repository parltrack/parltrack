#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#    This file is part of objchanges

#    objchanges is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    objchanges is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with objchanges  If not, see <http://www.gnu.org/licenses/>.

# 2019 (C) Stefan Marsiske <7o5rfu92t@ctrlc.hu>

from operator import itemgetter
from copy import deepcopy
import functools

def diff(old,new):
    o = normalize(deepcopy(old))
    n = normalize(deepcopy(new))
    return _diff(o, n, old, new)

def _diff(old, new, o, n, path=[]):
    if old==None and new!=None:
        return [{'type': 'added', 'path': path, 'data': getitem(n,path)}]
    if new==None and old!=None:
        return [{'type': 'deleted', 'path': path, 'data': getitem(o,path)}]
    if not type(old)==type(new):
        return [{'type': 'changed', 'path': path, 'data': (getitem(o,path), getitem(n,path))}]
    if hasattr(old,'keys'):
        res=[]
        for k in set(list(old.keys()) + list((new or {}).keys())):
            r=_diff(old.get(k),(new or {}).get(k), o, n, path+[k])
            res.extend(r)
        return res
    if hasattr(old,'__iter__') and not isinstance(old,str):
        return difflist(old, new, o, n, path)
    if (([type(x) for x in [old, new]] == [ str, str ] and
           ''.join(old.split()).lower() != ''.join(new.split()).lower()) or
          old != new):
        return [{'type': u'changed', 'path': path, 'data': (getitem(o,path), getitem(n,path))}]
    return []

def difflist(old, new, o, n, path):
    oldset,oldorder=normalize_list(old)
    newset,neworder=normalize_list(new)
    if len(oldset) != len(old) or len(newset) != len(new):
        # we have duplicate elements in the list, fallback to naive difflist
        return naive_difflist(old, new, o, n, path)

    oldunique=sorted(oldset - newset, key=lambda x: oldorder[x])
    newunique=sorted(newset - oldset, key=lambda x: neworder[x])

    # check if all-atomic list
    if any(type(x) not in (dict, list, tuple, hashabledict) for x in oldunique+newunique):
        return atomiclistdiff(o, oldset, oldorder, oldunique, n, newset, neworder, newunique, path)

    # all the same
    if not (oldunique or newunique): return []
    #import code; code.interact(local=locals());
    ret=[]
    for oe in list(oldunique):
        candidates=sorted([(oe, ne,
                            _diff(oe, ne, o, n,
                                 path + [neworder[ne]]))
                            for ne in list(newunique)],
                           key=lambda a: len(a[2]))
        # find deep matches first
        if len(candidates) and (len(candidates[0][2])*3<=(len(candidates[0][1]) if isinstance(candidates[0][1], tuple) else 3)):
            if oldorder[oe] != neworder[candidates[0][1]]:
                oldobj = getitem(o, path + [oldorder[oe]])
                ret.append({'type': u'deleted', 'path': path + [oldorder[oe]], 'data': oldobj})
                ret.append({'type': u'added', 'path': path + [neworder[candidates[0][1]]], 'data': oldobj})
            ret.extend(candidates[0][2])
            oldunique.remove(candidates[0][0])
            newunique.remove(candidates[0][1])
    # handle added
    if newunique:
        ret.extend(sorted([{'type': u'added', 'path': path + [neworder[e]], 'data': getitem(n,path + [neworder[e]])} for e in newunique], key=itemgetter('path')))
    # handle deleted
    if oldunique:
        ret.extend(sorted([{'type': u'deleted', 'path': path + [oldorder[e]], 'data': getitem(o,path + [oldorder[e]])} for e in oldunique], key=itemgetter('path')))
    no = sorted([(neworder[common], common) for common in oldset & newset])
    oo = sorted([(oldorder[common], common) for common in oldset & newset])
    for (ni, ne), (oi, oe) in zip(no,oo):
        if ne == oe: continue
        ret.append({'type': u'changed', 'path': path + [ni], 'data': (oe, ne)})
    return ret

def naive_difflist(old, new, o, n, path):
    # we have duplicate elements in the list, fallback to naive difflist
    os = len(old)
    ns = len(new)
    ret = []
    if os>ns:
        for i, (oe, ne) in enumerate(zip(old[:ns],new)):
            ret.extend(_diff(oe,ne,o,n,path + [i]))
        ret.extend(sorted([{'type': u'deleted',
                            'path': path + [ns+i],
                            'data': getitem(o,path + [ns+i])}
                           for i in range(os - ns)], key=itemgetter('path')))
    elif ns>os:
        for i, (oe, ne) in enumerate(zip(old,new[:os])):
            ret.extend(_diff(oe,ne,o,n,path + [i]))
        ret.extend(sorted([{'type': u'added',
                            'path': path + [os+i],
                            'data': getitem(n,path + [os+i])}
                           for i in range(ns - os)], key=itemgetter('path')))
    else:
        for i, (oe, ne) in enumerate(zip(old,new)):
            ret.extend(_diff(oe,ne,o,n,path + [i]))
    return ret

def atomiclistdiff(o, oldset, oldorder, deleted, n, newset, neworder, added, path):
    # todo test reordering atoms that are shared between old and new
    ret = []
    if added:
        ret.extend(sorted([{'type': u'added', 'path': path + [neworder[e]], 'data': getitem(n,path + [neworder[e]])} for e in added], key=itemgetter('path')))
    # handle deleted
    if deleted:
        ret.extend(sorted([{'type': u'deleted', 'path': path + [oldorder[e]], 'data': getitem(o,path + [oldorder[e]])} for e in deleted], key=itemgetter('path')))
    no = sorted([(neworder[common], common) for common in oldset & newset])
    oo = sorted([(oldorder[common], common) for common in oldset & newset])
    for (ni, ne), (oi, oe) in zip(no,oo):
        if ne == oe: continue
        ret.append({'type': u'changed', 'path': path + [ni], 'data': (oe, ne)})
    return ret

class hashabledict(dict):
    val = None
    def __hash__(self):
        if not self.val:
            self.val=hash(str(sorted(self.items())))
        return self.val

def normalize(obj):
    if isinstance(obj,bytes):
        return obj.decode('utf-8')
    if isinstance(obj,str):
        return obj
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    if isinstance(obj,dict):
        return hashabledict({k:normalize(v) for k,v in obj.items()})
    if hasattr(obj, '__iter__'):
        return tuple(normalize(e) for e in obj)
    return obj

def normalize_list(obj):
    if not obj: return set(), {}
    objset=set(obj) # duplicates will be ignored
    objorder={e: i for i, e in enumerate(obj)} # the last duplicates position will overwrite previous positions
    return objset, objorder

#### patch stuff starts here ####

def getitem(item,path):
    if item in ({},[],tuple()) or path in ([],tuple()): return item
    if isinstance(item,dict) and path[0] not in item:
        return None
    try:
        return getitem(item[path[0]], path[1:])
    except:
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
    res = deepcopy(obj)
    for l in sorted({len(x['path']) for x in changes}):
        # first handle deletes, they are indexed based on the old indexes
        #for change in sorted(changes, key=lambda x: x['path'], reverse=True):
        for change in sorted(changes, key=functools.cmp_to_key(sortpaths)):
            if change['type']!='deleted': continue
            if len(change['path'])!=l: continue
            obj=getitem(res,change['path'][:-1])
            if obj is None:
                print("could not resolve path '%s', action: %s\ndata: %s" % (change['path'], change['type'], change['data']))
                return
            if isinstance(obj,dict) and change['path'][-1] not in obj:
                print("cannot delete %s what is not there in %s" % (change['path'][-1], change['data']))
                print(change,obj)
                return
            elif isinstance(obj,list) and change['path'][-1]>=len(obj):
                print("cannot delete %s what is not there in %s" % (change['path'][-1], change['data']))
                print(change,obj)
                return
            elif change['data']==obj[change['path'][-1]]:
                #print("\tdeleting", change['path'])
                del obj[change['path'][-1]]
            else:
                print("wtf deleted: %s\nobj: %s" % (change, obj))

        # handle adds
        for change in sorted(changes, key=lambda x: x['path']):
            if change['type']!='added': continue
            if len(change['path'])!=l: continue
            obj=getitem(res,change['path'][:-1])
            if obj is None:
                print("could not resolve path '%s', action: %s\ndata: %s" % (change['path'], change['type'], change['data']))
                #print(list(x['path'] for x in sorted(changes, key=functools.cmp_to_key(sortpaths))))
                return
            #print("\tadding", change['path'])
            if isinstance(obj,list):
                obj.insert(change['path'][-1],deepcopy(change['data']))
            else:
                obj[change['path'][-1]]=deepcopy(change['data'])

        # handle changes
        for change in changes:
            if change['type']!='changed': continue
            if len(change['path'])!=l: continue
            obj=getitem(res,change['path'][:-1])
            if obj is None:
                print("could not resolve path '%s', action: %s\ndata: %s" % (change['path'], change['type'], change['data']))
                return
            if isinstance(obj,dict) and change['path'][-1] not in obj:
                print("cannot change %s what is not there in %s" % (change['path'][-1], change['data']))
                return
            elif isinstance(obj,list) and change['path'][-1]>=len(obj):
                print("cannot change %s what is not there in %s" % (change['path'][-1], change['data']))
                return
            elif obj[change['path'][-1]]==change['data'][0]:
                #print("\tchanging", change['path'])
                obj[change['path'][-1]]=deepcopy(change['data'][1])
            else:
                print("wtf change", change, obj)
    return res
