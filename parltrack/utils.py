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

def unws(txt):
    return u' '.join(txt.split())

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
    if type(old) == type(str()): old=unicode(old,'utf8')
    if type(new) == type(str()): new=unicode(new,'utf8')
    if old==None and new!=None:
        return [{'type': 'added', 'data': new, 'path': path}]
    elif new==None and old!=None:
        return [{'type': 'deleted', 'data': old, 'path': path}]
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
        return difflist(old, new, path)
    elif (([type(x) for x in [old, new]] == [ unicode, unicode ] and
           ''.join(old.split()).lower() != ''.join(new.split()).lower()) or
          old != new):
        return [{'type': u'changed', 'data': (old, new), 'path': path}]
    return

class hashabledict(dict):
    def __hash__(self):
        return hash(str(sorted(self.iteritems())))

def difflist(old, new, path):
    if not old:
        oldset=set()
        oldorder=dict()
    elif type(old[0])==type(dict()):
        oldset=set([hashabledict(x) for x in old])
        oldorder=dict([(hashabledict(e),i) for i, e in enumerate(old)])
    elif type(old[0])==type(list()):
        oldset=set([tuple(x) for x in old])
        oldorder=dict([(tuple(e),i) for i, e in enumerate(old)])
    else:
        oldset=set(old)
        oldorder=dict([(e,i) for i, e in enumerate(old)])
    if not new:
        newset=set()
        neworder=dict()
    elif type(new[0])==type(dict()):
        newset=set([hashabledict(x) for x in new])
        neworder=dict([(hashabledict(e),i) for i, e in enumerate(new)])
    elif type(new[0])==type(list()):
        newset=set([tuple(x) for x in new])
        neworder=dict([(tuple(e),i) for i, e in enumerate(new)])
    else:
        newset=set(new)
        neworder=dict([(e,i) for i, e in enumerate(new)])
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
                           cmp=lambda a,b: cmp(len(a[2]),len(b[2])))
        # find deep matches firs
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

from bson.objectid import ObjectId
def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return unicode(obj.isoformat())
    elif type(obj)==ObjectId:
        return unicode(obj)
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))

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
    if debug: print
    if debug: pprint.pprint(item)
    if debug: print
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
                print "!!!Deleted", k
                print change
                print elem
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
            result.append( printdict(elem))
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
                print "!!!Deleted", k
                print change
                print elem
                break
        if not deleted:
            if not tuple(change['path'][:-1]) in res:
                res[tuple(change['path'][:-1])]=(elem, [])
            res[tuple(change['path'][:-1])][1].append(change)
            if debug: pprint.pprint(elem[change['path'][-1]])
        if debug: print
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

def test_diff():
    from a1 import a1 as d1, a2 as d3
    from a2 import a2 as d2
    #pprint.pprint(diff(d3,d1))
    #pprint.pprint(diff(d3,d2))
    pprint.pprint(diff(d1,d2))
    #d1={ 'a': [ { 'aa': 1, 'bb':3 }, {'AA': 1, 'BB': { 'asdf': '2'}}, {'Mm': [ 'a','b','c','d'] } ],
    #     'b': { 'z': 9, 'x': 8 },
    #     'c': [ 1,2,3,4]}
    #d2={ 'a': [ {'aa': 2, 'bb': 3 }, { 'aa': 1, 'bb':3 }, {'AA': 1, 'BB': { 'asdf': { 'asdf': 'qwer'}}}, {'Mm': [ 'a','b','c','d'] } ],
    #     'c': [ 0,1,2,3,4]}
    #import pprint
    #pprint.pprint(diff(d1,d2))

opener=None
def init_opener():
    global opener
    #opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()))
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()),
                                  urllib2.ProxyHandler({'http': 'http://localhost:8123/'}))
    opener.addheaders = [('User-agent', 'parltrack/0.6')]

def fetch_raw(url, retries=5, ignore=[], params=None):
    if not opener:
        init_opener()
    # url to etree
    try:
        f=opener.open(url, params)
    except (urllib2.HTTPError, urllib2.URLError), e:
        if hasattr(e, 'code') and e.code>=400 and e.code not in [504, 502]+ignore:
            logger.warn("[!] %d %s" % (e.code, url))
            raise
        if retries>0:
            time.sleep(4*(6-retries))
            f=fetch_raw(url, retries-1, ignore=ignore, params=params)
        else:
            raise
    return f

def fetch(url, retries=5, ignore=[], params=None):
    try:
        return parse(fetch_raw(url, retries, ignore, params))
    except:
        if retries>0:
            time.sleep(4*(6-retries))
            return fetch(url,retries-1, ignore=ignore)
        else:
            raise
    
    try:
        return parse(f)
    except:
        if retries>0:
            time.sleep(4*(6-retries))
            return fetch(url,retries-1, ignore=ignore)
        else:
            raise
    
    try:
        return parse(f)
    except:
        if retries>0:
            time.sleep(4*(6-retries))
            return fetch(url,retries-1, ignore=ignore)
        else:
            raise

from multiprocessing import Pool, Process, JoinableQueue, log_to_stderr
from multiprocessing.sharedctypes import Value
from ctypes import c_bool
from Queue import Empty
from logging import DEBUG, WARN, INFO
import traceback
logger = log_to_stderr()
logger.setLevel(INFO)

class Multiplexer(object):
    def __init__(self, worker, writer, threads=4):
        self.worker=worker
        self.writer=writer
        self.q=JoinableQueue()
        self.done = Value(c_bool,False)
        self.consumer=Process(target=self.consume)
        self.pool = Pool(threads, init_opener)

    def start(self):
        self.done.value=False
        self.consumer.start()

    def addjob(self, url, data=None):
        params=[url]
        if data: params.append(data)
        try:
           return self.pool.apply_async(self.worker,params,callback=self.q.put)
        except:
            logger.error('[!] failed to scrape '+ url)
            logger.error(traceback.format_exc())
            raise

    def finish(self):
        self.pool.close()
        logger.info('closed pool')
        self.pool.join()
        logger.info('joined pool')
        self.done.value=True
        self.q.close()
        logger.info('closed q')
        self.consumer.join()
        logger.info('joined consumer')
        #self.q.join()
        #logger.info('joined q')

    def consume(self):
        param=[0,0]
        while True:
            job=None
            try:
                job=self.q.get(True, timeout=1)
            except Empty:
                if self.done.value==True: break
            if job:
                param = self.writer(job, param)
                self.q.task_done()
        logger.info('added/updated: %s' % param)


from BeautifulSoup import BeautifulSoup, Comment
from itertools import izip_longest
from copy import deepcopy
from collections import defaultdict
from views.views import dossier
from operator import itemgetter
from parltrack.default_settings import ROOT_URL
from lxml.html.soupparser import parse
import pprint
import urllib2, cookielib, sys, time, json

def jdump(d, stats=None):
    # simple json dumper default for saver
    res=json.dumps(d, indent=1, default=dateJSONhandler, ensure_ascii=False)
    if stats:
        print res.encode('utf-8')
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
    ## import pymongo, datetime
    ## db=pymongo.Connection().parltrack
    ## docs=db.dossiers.find({'meta.updated': { '$gt': datetime.datetime(2011,11,24,0,0)}})
    ## print docs.count()
    ## for d in docs:
    ##     print '\n', d['procedure']['reference'], d['procedure']['title']
    ##     print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1]).encode('utf8')

    #test_diff()

    #d=dossier('COD/2007/0247',without_changes=False)
    #print '\n', d['procedure']['reference'], d['procedure']['title']
    #showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1])

    #d=dossier('CNS/2011/0094',without_changes=False)
    #d=dossier('NLE/2011/0097',without_changes=False)
    #d=dossier('NLE/2010/0084',without_changes=False)
    #d=dossier('CNS/2010/0276',without_changes=False)
    #print '\n', d['procedure']['reference'], d['procedure']['title']
    ###print sorted(d['changes'].keys(),reverse=True)
    #pprint.pprint(sorted(d['changes'].keys(),reverse=True))
    #pprint.pprint(sorted(d['changes'].items(),reverse=True)[0][1])
    #print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1]).encode('utf8')

    #d=dossier('COD/2011/0129',without_changes=False)
    #print '\n', d['procedure']['reference'], d['procedure']['title']
    ##print sorted(d['changes'].keys(),reverse=True)
    #print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1]).encode('utf8')

    #d=dossier('COD/2011/0117',without_changes=False)
    #print '\n', d['procedure']['reference'], d['procedure']['title']
    ##print sorted(d['changes'].keys(),reverse=True)
    #print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1]).encode('utf8')

    d=dossier('CNS/2011/0111',without_changes=False)
    #d=dossier('NLE/2008/0137',without_changes=False)
    #print '\n', d['procedure']['reference'], d['procedure']['title']
    ##print sorted(d['changes'].keys(),reverse=True)
    print htmldiff(d,sorted(d['changes'].items(),reverse=True)[0][1]).encode('utf8')

    #print d['procedure']['reference'], d['procedure']['title']
    #d=dossier('NLE/2011/0102',without_changes=False)
    #pprint.pprint (sorted(d['changes'].items(),reverse=True))
    #print 'x'*80
    #pprint.pprint(sorted(d.items(),reverse=True))
    #print showdiff(d,sorted(d['changes'].items(),reverse=True)[0][1])


    ## import pymongo
    ## db=pymongo.Connection().parltrack
    ## d=db.dossiers.find_one({'procedure.reference': 'CNS/2010/0276'})
    ## del d['changes']
    ## pprint.pprint(d)
    ## sys.exit(0)
