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

def sanitizeHtml(value, base_url=None):
    rjs = r'[\s]*(&#x.{1,7})?'.join(list('javascript:'))
    rvb = r'[\s]*(&#x.{1,7})?'.join(list('vbscript:'))
    re_scripts = re.compile('(%s)|(%s)' % (rjs, rvb), re.IGNORECASE)
    validTags = 'p i strong b u a h1 h2 h3 pre br img'.split()
    validAttrs = 'href src width height'.split()
    urlAttrs = 'href src'.split() # Attributes which should have a URL
    soup = BeautifulSoup(value)
    for comment in soup.findAll(text=lambda text: isinstance(text, Comment)):
        # Get rid of comments
        comment.extract()
    for tag in soup.findAll(True):
        if tag.name not in validTags:
            tag.hidden = True
        attrs = tag.attrs
        tag.attrs = []
        for attr, val in attrs:
            if attr in validAttrs:
                val = re_scripts.sub('', val) # Remove scripts (vbs & js)
                if attr in urlAttrs:
                    val = urljoin(base_url, val) # Calculate the absolute url
                tag.attrs.append((attr, val))

    return soup.renderContents().decode('utf8')

def diff(old, new, path=[]):
    if old==None and new!=None:
        return [{'type': 'added', 'data': new, 'path': path}]
    elif new==None and old!=None:
        return [{'type': 'deleted', 'data': old, 'path': path}]
    if type(old) == str: old=unicode(old,'utf8')
    if type(new) == str: new=unicode(new,'utf8')
    if not type(old)==type(new):
        return [{'type': 'changed', 'data': (old, new), 'path': path}]
    elif hasattr(old,'keys'):
        res=[]
        for k in set(old.keys() + (new or {}).keys()):
            r=diff(old.get(k),(new or {}).get(k), path+[k])
            if r:
                res.extend(r)
        return res
    elif hasattr(old,'__iter__'):
        res=[]
        for item in filter(None,[diff(a,b,path+[(len(old) if len(old)<len(new) else len(new))-(i+1)]) for i,(a,b) in enumerate(izip_longest(reversed(old),reversed(new)))]):
            if type(item)==type(list()):
                res.extend(item)
            else:
                res.append(item)
        return res
    elif old != new:
        return [{'type': 'changed', 'data': (old, new), 'path': path}]
    return

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif type(obj)==ObjectId:
        return str(obj)
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))

def printdict(d,i=0):
    if type(d)==type(list()):
        return (u'\n\t%s' % ('  '*i)).join([printdict(v,i+1 ) for v in d])
    if not type(d)==type(dict()):
        return unicode(d)
    suppress=['mepref','comref', 'text']
    res=['']
    for k,v in [(k,v) for k,v in d.items() if k not in suppress]:
        res.append(u"\t%s%s:\t%s" % ('  '*i,k,printdict(v,i+1)))
    return u'\n'.join(res)

def showdiff(item,diffs):
    if debug: pprint.pprint(diffs)
    if debug: print
    item=deepcopy(item)
    # calculate offset for lists with newly added elements
    offsetd = defaultdict(int)
    for p in [tuple(change['path'][:-1])
              for change in diffs
              if type(change['path'][-1])==type(int()) and change['type']=='added']:
        offsetd[p]+=1
    # readd temporarily (deepcopied object, remember?)
    # the deleted elements of lists and dicts
    for change in sorted(diffs,cmp=lambda x,y: (cmp(len(x['path']),
                                                   len(y['path'])) or
                                                cmp(y['path'][-1],
                                                    x['path'][-1]))):
        if change['type']=='deleted':
            elem=item
            cp=[]
            for k in change['path'][:-1]:
                if tuple(cp) in offsetd.keys():
                    try:
                        k=int(k)+offsetd[tuple(cp)]
                    except:
                        pass
                cp.append(k)
                elem=elem[k]
            if type(change['path'][-1])==type(int()):
                elem.insert(change['path'][-1],change['data'])
            elif type(change['path'][-1])in [type(str()),type(unicode())]:
                elem[change['path'][-1]]=change['data']
    res={}
    if debug: pprint.pprint(item)
    if debug: print
    if debug: pprint.pprint(offsetd)
    for change in diffs:
        if debug: pprint.pprint( change )
        # added dicts should be terminal
        if change['type']=='added' and type(change['data'])==type(dict()):
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
        cp=[]
        # find the parent element of the changed one
        for k in change['path'][:-1]:
            # adjust for all newly added dicts in a list (activities, e.g.)
            # the diff does not count for those in the index of lists
            if tuple(cp) in offsetd.keys():
                try:
                    k=int(k)+offsetd[tuple(cp)]
                except:
                    pass
            cp.append(k)
            try:
                elem=elem[k]
            except KeyError, IndexError:
                # whoops, should not happen, really.
                deleted=True
                print "!!!Deleted", k, elem
                break
        if debug: pprint.pprint( elem )
        if not deleted:
            if not tuple(change['path'][:-1]) in res:
                res[tuple(change['path'][:-1])]=(elem, [])
            res[tuple(change['path'][:-1])][1].append(change)
            if debug: pprint.pprint(elem[change['path'][-1]])
        if debug: print
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
                    result.append( '+\t%s: <strong>%s</strong>' % (c['path'][-1],printdict(c['data'])))
            elif c['type']=='deleted':
                #import code; code.interact(local=locals());
                if debug: pprint.pprint(c['data'])
                result.append( '-\t%s: <del>%s</del>' % (c['path'][-1],printdict(c['data'])))
            elif c['type']=='changed':
                result.append( '!\t%s: <strong>%s</strong><del>%s</del>' % (c['path'][-1],printdict(c['data'][1]),printdict(c['data'][0])))
            else:
                continue # ignore/suppress unknown types
            if type(elem)==type(dict()) and c['path'][-1] in elem:
                del elem[c['path'][-1]]
        if not skip and not type(elem)==type(list()):
            result.append( printdict(elem))
    return '\n'.join(result)

def test_diff():
    d1={ 'a': [ { 'aa': 1, 'bb':3 }, {'AA': 1, 'BB': { 'asdf': '2'}}, {'Mm': [ 'a','b','c','d'] } ],
         'b': { 'z': 9, 'x': 8 },
         'c': [ 1,2,3,4]}
    d2={ 'a': [ {'aa': 2, 'bb': 3 }, { 'aa': 1, 'bb':3 }, {'AA': 1, 'BB': { 'asdf': { 'asdf': 'qwer'}}}, {'Mm': [ 'a','b','c','d'] } ],
         'c': [ 0,1,2,3,4]}
    import pprint
    pprint.pprint(diff(d1,d2))

from BeautifulSoup import BeautifulSoup, Comment
from itertools import izip_longest
from copy import deepcopy
from collections import defaultdict
from views.views import dossier

if __name__ == "__main__":
    #test_diff()

    #d=dossier('COD/2007/0247',without_changes=False)
    #print '\n', d['procedure']['reference'], d['procedure']['title']
    #showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1])

    import pprint
    #d=dossier('CNS/2011/0094',without_changes=False)
    #d=dossier('NLE/2011/0097',without_changes=False)
    d=dossier('NLE/2010/0084',without_changes=False)
    print '\n', d['procedure']['reference'], d['procedure']['title']
    #print sorted(d['changes'].keys(),reverse=True)
    print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1]).encode('utf8')

    #d=dossier('COD/2011/0129',without_changes=False)
    #print '\n', d['procedure']['reference'], d['procedure']['title']
    ##print sorted(d['changes'].keys(),reverse=True)
    #print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1]).encode('utf8')

    #d=dossier('COD/2011/0117',without_changes=False)
    #print '\n', d['procedure']['reference'], d['procedure']['title']
    ##print sorted(d['changes'].keys(),reverse=True)
    #print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1]).encode('utf8')

    #d=dossier('CNS/2011/0111',without_changes=False)
    #print '\n', d['procedure']['reference'], d['procedure']['title']
    #print sorted(d['changes'].keys(),reverse=True)
    #print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1]).encode('utf8')

    #print d['procedure']['reference'], d['procedure']['title']
    #d=dossier('NLE/2011/0102',without_changes=False)
    #pprint.pprint (sorted(d['changes'].items(),reverse=True))
    #print 'x'*80
    #pprint.pprint(sorted(d.items(),reverse=True))
    #print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1])
