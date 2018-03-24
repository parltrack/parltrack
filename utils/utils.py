#!/usr/bin/env python

# -*- coding: utf-8 -*-
#    This file is part of parltrack.

#    parltrack is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    parltrack is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with parltrack.  If not, see <http://www.gnu.org/licenses/>.

# (C) Stefan Marsiske <stefan.marsiske@gmail.com>

debug=False

import pprint
import sys, json
from bs4 import BeautifulSoup, Comment
try:
    from itertools import izip_longest
except:
    from itertools import zip_longest as izip_longest
from operator import itemgetter
from config import ROOT_URL

if sys.version[0] == '3':
    unicode = str

def unws(txt):
    return u' '.join(txt.split())

def normalize_obj(obj):
    if type(obj) == str:
        return unicode(obj)
    if type(obj) == bytes:
        return obj.decode('utf-8')
    elif hasattr(obj, 'isoformat'):
        return unicode(obj.isoformat())
    return obj

def diff(old, new, path=[]):
    old=normalize_obj(old)
    new=normalize_obj(new)
    if old==None and new!=None:
        return [{'type': 'added', 'data': new, 'path': path}]
    elif new==None and old!=None:
        return [{'type': 'deleted', 'data': old, 'path': path}]
    if not type(old)==type(new):
        return [{'type': 'changed', 'data': (old, new), 'path': path}]
    elif hasattr(old,'keys'):
        res=[]
        for k in set(list(old.keys()) + list((new or {}).keys())):
            r=diff(old.get(k),(new or {}).get(k), path+[k])
            if r:
                res.extend(r)
        return res
    elif hasattr(old,'__iter__') and not isinstance(old,str):
        return difflist(old, new, path)
    elif (([type(x) for x in [old, new]] == [ unicode, unicode ] and
           ''.join(old.split()).lower() != ''.join(new.split()).lower()) or
          old != new):
        return [{'type': u'changed', 'data': (old, new), 'path': path}]
    return

class hashabledict(dict):
    val = None
    def __hash__(self):
        if not self.val:
            self.val=hash(str(sorted(self.items())))
        return self.val

def normalize_list(obj):
    if not obj:
        objset=set()
        objorder=dict()
    elif dict in {type(x) for x in obj}:
        objset={hashabledict(x) if isinstance(x,dict) else x for x in obj}
        objorder={hashabledict(e) if isinstance(e,dict) else e: i for i, e in enumerate(obj)}
    elif list in {type(x) for x in obj}:
        objset={tuple(x) if isinstance(x, list) else x for x in obj}
        objorder={tuple(e) if isinstance(e, list) else e: i for i, e in enumerate(obj)}
    else:
        objset=set(obj)
        objorder={e:i for i, e in enumerate(obj)}
    return objset, objorder

def difflist(old, new, path):
    oldset,oldorder=normalize_list(old)
    newset,neworder=normalize_list(new)
    oldunique=set(oldset) - set(newset)
    newunique=set(newset) - set(oldset)
    # all the same
    if not (oldunique or newunique): return
    #import code; code.interact(local=locals());
    ret=[]
    for oe in list(oldunique):
        candidates=sorted([(oe, ne,
                            diff(oe,
                                 ne,
                                 path + [neworder[tuple(ne)]
                                         if type(ne)==type(list())
                                         else neworder[ne]]))
                            for ne in list(newunique)],
                           key=lambda a: len(a[2]))
        # find deep matches first
        skip=False
        for c in candidates:
            for d in c[2]:
                if len(d['path'])-len(path)+1<1:
                    skip=True
                    break
            if skip:
                skip=False
                continue
            ret.extend(c[2])
            oldunique.remove(c[0])
            newunique.remove(c[1])
            skip=True
            break
        if skip:
            continue
        if len(candidates) and len(candidates[0][2])*3<=len(ne):
            ret.extend(candidates[0][2])
            oldunique.remove(candidates[0][0])
            newunique.remove(candidates[0][1])
    # handle added
    if newunique:
        ret.extend(sorted([{'type': u'added', 'data': e, 'path': path + [neworder[e]]} for e in newunique], key=itemgetter('path')))
    # handle deleted
    if oldunique:
        ret.extend(sorted([{'type': u'deleted', 'data': e, 'path': path + [oldorder[e]]} for e in oldunique], key=itemgetter('path')))
    return ret

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return unicode(obj.isoformat())
    elif type(obj)==bytes:
        return obj.decode('utf-8')
    else:
        raise TypeError('Object of type {0} with value of {1} is not JSON serializable'.format(type(obj), repr(obj)))

def printdict(d,i=0):
    if type(d)==type(list()):
        return (u'\n\t%s' % ('  '*i)).join([printdict(v,i+1 ) for v in d])
    if not type(d) in [dict, hashabledict]:
        return unicode(d)
    suppress=['mepref','comref', 'text']
    res=['']
    for k,v in [(k,v) for k,v in d.items() if k not in suppress]:
        res.append(u"\t%s%s:\t%s" % ('  '*i,k,printdict(v,i+1)))
    return u'\n'.join(res)

def showdiff(item,diffs):
    if debug: pprint.pprint(diffs)
    #pprint.pprint(diffs)
    if debug: print()
    if debug: pprint.pprint(item)
    if debug: print()
    if debug: pprint.pprint(offsetd)
    res={}
    for change in diffs:
        if debug: pprint.pprint( change )
        # added dicts should be terminal
        if change['type'] in ['added', 'deleted'] and type(change['data'])==type(dict()):
            if len(change['path'])>1:
                tmpk=tuple(change['path'][:-1])
            else:
                tmpk=tuple(change['path'])
            if not tmpk in res:
                res[tmpk]=(change['data'], [change])
            else:
                res[tmpk][1].append(change)
            continue
        elem=item
        deleted=False
        # find the parent element of the changed one
        for k in change['path'][:-1]:
            try:
                elem=elem[k]
            except (KeyError, IndexError):
                # whoops, should not happen, really.
                deleted=True
                print("!!!Deleted", k)
                print(change)
                print(elem)
                break
        if debug: pprint.pprint( elem )
        if not deleted:
            if not tuple(change['path'][:-1]) in res:
                res[tuple(change['path'][:-1])]=(elem, [])
            res[tuple(change['path'][:-1])][1].append(change)
            if debug: pprint.pprint(elem[change['path'][-1]])
        if debug: print()
    # print result as ascii
    result=[]
    for path, (elem, changes) in sorted(res.items()):
        result.append('/'.join(map(str,path)))
        skip=False
        for c in changes:
            if c['type']=='added':
                if type(c['data'])==type(dict()):
                    result.append( "+\t%s" % "\n+\t".join(printdict(c['data']).split('\n')))
                    skip=True
                    continue
                else:
                    result.append( '+\t%s: <strong>%s</strong>' % (c['path'][-1],"\n+\t".join(printdict(c['data']).split('\n'))))
            elif c['type']=='deleted':
                if type(c['data'])==type(dict()):
                    result.append( "-\t%s" % "\n-\t".join(printdict(c['data']).split('\n')))
                    skip=True
                    continue
                else:
                    #import code; code.interact(local=locals());
                    if debug: pprint.pprint(c['data'])
                    result.append( '-\t%s: <del>%s</del>' % (c['path'][-1],"\n-\t".join(printdict(c['data']).split('\n'))))
            elif c['type']=='changed':
                result.append( '!\t%s: <strong>%s</strong><del>%s</del>' % (c['path'][-1],"\n!\t".join(printdict(c['data'][1]).split('\n')),"\n!\t".join(printdict(c['data'][0]).split('\n'))))
            else:
                continue # ignore/suppress unknown types
            if type(elem)==type(dict()) and c['path'][-1] in elem:
                del elem[c['path'][-1]]
        if not skip and not type(elem)==type(list()):
            result.append(printdict(elem))
    return '\n'.join(result)

def getorder(d):
    keys=set(d.keys())
    if 'reference' in keys:
        return ['reference', 'title', 'committee', 'legal_basis', 'stage_reached', 'dossier_of_the_committee', 'subjects']
    elif 'responsible' in keys:
        return ['committee', 'responsible', 'name', 'group', 'date']
    elif 'documents' in keys:
        return ['type', 'date', 'body', 'documents', 'actors']
    elif keys >= set(['title', 'type', 'actors']):
        return ['title', 'type', 'url', 'date']
    elif keys >= set(['title', 'type']):
        return ['title', 'url']
    return list(keys)

def htmldict(d):
    if type(d)==type(list()):
        return (u'<ul style="list-style-type: none;"">%s</ul>' % ''.join(["<li>%s</li>" % htmldict(v) for v in d]))
    if not type(d) in [dict, hashabledict]:
        return unicode(d)
    suppress=['mepref','comref']
    res=['<dl>']
    for k,v in [(k,d[k]) for k in getorder(d) if k not in suppress and d.get(k)!=None]:
        res.append(u"<li style='list-style-type: none;'><dt style='display: inline-block; width: 10em; text-transform: capitalize;'>%s</dt><dd style='display: inline'>%s</dd></li>" % (k,htmldict(v)))
    res.append('</dl>')
    return u''.join(res)

def htmldiff(item,diffs):
    res={}
    for change in diffs:
        if debug: pprint.pprint( change )
        # added dicts should be terminal
        if change['type'] in ['added', 'deleted'] and type(change['data'])==type(dict()):
            if len(change['path'])>1:
                tmpk=tuple(change['path'][:-1])
            else:
                tmpk=tuple(change['path'])
            if not tmpk in res:
                res[tmpk]=(change['data'], [change])
            else:
                res[tmpk][1].append(change)
            continue
        elem=item
        deleted=False
        # find the parent element of the changed one
        for k in change['path'][:-1]:
            try:
                elem=elem[k]
            except (KeyError, IndexError):
                # whoops, should not happen, really.
                deleted=True
                print("!!!Deleted", k)
                print(change)
                print(elem)
                break
        if not deleted:
            if not tuple(change['path'][:-1]) in res:
                res[tuple(change['path'][:-1])]=(elem, [])
            res[tuple(change['path'][:-1])][1].append(change)
            if debug: pprint.pprint(elem[change['path'][-1]])
        if debug: print()
    # generate html result
    result=['<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n<head>\n<title></title></head><body><p>Parltrack has detected a change in %s %s on OEIL.\n\nPlease follow this URL: %s/dossier/%s to see the dossier.\n\nsincerly,\nYour Parltrack team"</p><dl style="font-family:Trebuchet MS,Tahoma,Verdana,Arial,sans-serif; font-size: .8em;">' %
            (item['procedure']['reference'],
             item['procedure']['title'],
             ROOT_URL,
             item['procedure']['reference'],)
            ]
    for path, (elem, changes) in sorted(res.items()):
        result.append('<dt style="margin-top: 1em; text-transform: capitalize;">%s<dt><dd>' % '/'.join(map(str,path)))
        skip=False
        for c in changes:
            if c['type']=='added':
                result.append( '<li style="list-style-type: none;"><strong><dt style="display: inline-block; width: 10em; text-transform: capitalize;">%s</dt><dd style="display: inline">%s</dd></strong></li>' % (c['path'][-1],htmldict(c['data'])))
                if type(c['data'])==type(dict()):
                    skip=True
                    continue
            elif c['type']=='deleted':
                result.append( "<li style='list-style-type: none;'><dt style='display: inline-block; width: 10em; text-transform: capitalize;'><del style='text-decoration: line-through;'>%s</del></dt><dd style='display: inline'><del style='text-decoration: line-through;'>%s</del></dd></li>" % (c['path'][-1], htmldict(c['data'])))
                if type(c['data'])==type(dict()):
                    skip=True
                    continue
            elif c['type']=='changed':
                result.append( '<li style="list-style-type: none;"><dt style="display: inline-block; width: 10em; text-transform: capitalize;">%s</dt><dd style="display: inline"><strong>%s</strong><del>%s</del></dd></li>' % (c['path'][-1],htmldict(c['data'][1]),htmldict(c['data'][0])))
            else:
                continue # ignore/suppress unknown types
            if type(elem)==type(dict()) and c['path'][-1] in elem:
                del elem[c['path'][-1]]
        if not skip and not type(elem)==type(list()):
            result.append("%s" % htmldict(elem))
    return "%s</dd></dl></body></html>" % ''.join(result)

##### fetch url implementation

from lxml.html.soupparser import fromstring
import requests, time

PROXIES = {} #'http': 'http://localhost:8123/'}
HEADERS =  { 'User-agent': 'parltrack/0.8' }

def fetch_raw(url, retries=5, ignore=[], params=None):
    try:
        if params:
            r=requests.POST(url, params=params, proxies=PROXIES, headers=HEADERS)
        else:
            r=requests.get(url, proxies=PROXIES, headers=HEADERS)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        if e == requests.exceptions.Timeout:
            retries = min(retries, 1)
        if retries>0:
            time.sleep(4*(6-retries))
            f=fetch_raw(url, retries-1, ignore=ignore, params=params)
        else:
            raise ValueError("failed to fetch %s" % url)
    if r.status_code >= 400 and r.status_code not in [504, 502]+ignore:
        r.raise_for_status()
    return r.text

def fetch(url, retries=5, ignore=[], params=None):
    xml = fetch_raw(url, retries, ignore, params)
    # cut <?xml [..] ?> part
    xml = xml[xml.find('?>')+2:]
    return fromstring(xml)

def jdump(d, stats=None):
    # simple json dumper default for saver
    res=json.dumps(d, indent=1, default=dateJSONhandler, ensure_ascii=False)
    if stats:
        print(res.encode('utf-8'))
        stats[0]+=1
        return stats
    else:
        return res

def textdiff(d):
    res=[]
    for di in sorted(d,key=itemgetter('path')):
        if 'text' in di['path'] or 'summary' in di['path']:
            res.append(u'\nsummary text changed in %s' % u'/'.join([str(x) for x in di['path']]))
            continue
        if di['type']=='changed':
            res.append(u'\nchanged %s from:\n\t%s\n  to:\n\t%s' % (u'/'.join([str(x) for x in di['path']]),di['data'][0],printdict(di['data'][1])))
            continue
        res.append(u"\n%s %s:\t%s" % (di['type'], u'/'.join([str(x) for x in di['path']]), printdict(di['data'])))
    return '\n'.join(res)

if __name__ == "__main__":
    pass
