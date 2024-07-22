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
import sys, json, re
try:
    from itertools import izip_longest
except:
    from itertools import zip_longest as izip_longest
from operator import itemgetter
from config import ROOT_URL, USER_AGENT, CACHE_DIR
from utils.log import log
from utils.objchanges import hashabledict

DOSSIERID_RE=re.compile(r'([0-9]{4}/[0-9]{4}[A-Z]?\((?:ACI|APP|AVC|BUD|CNS|COD|COS|DCE|DEA|DEC|IMM|INI|INL|INS|NLE|REG|RPS|RSO|RSP|SYN)\))')

if sys.version[0] == '3':
    unicode = str

def unws(txt):
    return u' '.join(txt.split())

def junws(node):
    return unws(' '.join(node.xpath('.//text()')))

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
from cachecontrol import CacheControl
from cachecontrol.caches.file_cache import FileCache

HEADERS =  { 'User-agent': USER_AGENT }
sess = CacheControl(requests.Session(), cache=FileCache(CACHE_DIR+"/scraper", forever=True))

def fetch_raw(url, retries=5, ignore=[], params=None, asjson=None, binary=False, res=False):
    try:
        if params or asjson:
            r=sess.post(url, params=params, json=asjson, headers=HEADERS)
        else:
            r=sess.get(url, headers=HEADERS)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        if e == requests.exceptions.Timeout:
            retries = min(retries, 1)
        if retries>0:
            time.sleep(4*(6-retries))
            return fetch_raw(url, retries-1, ignore=ignore, params=params, asjson=asjson, binary=binary, res=res)
        else:
            raise ValueError("failed to fetch %s" % url)
    if r.status_code == 429:
        #retries = min(retries, 1)
        if retries>0:
            time.sleep(5*(6-retries))
            return fetch_raw(url, retries-1, ignore=ignore, params=params, asjson=asjson, binary=binary, res=res)
    if r.status_code >= 400 and r.status_code not in [504, 502]+ignore:
        r.raise_for_status()
    if res: return r
    if binary: return r.content
    return r.text

def fetch(url, retries=5, ignore=[], params=None, prune_xml=False):
    xml = fetch_raw(url, retries, ignore, params)
    # cut <?xml [..] ?> part
    if prune_xml:
        xml = xml[xml.find('?>')+2:]
    return fromstring(xml)

from tempfile import mkstemp
from sh import pdftotext
import os
def getpdf(pdf):
    (fd, fname)=mkstemp()
    fd=os.fdopen(fd, 'wb')
    try:
        fd.write(fetch_raw(pdf, binary=True))
    except:
        return []
    fd.close()
    text=pdftotext('-layout', fname, '-')
    os.unlink(fname)
    return text.split('\n')

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

from datetime import datetime, date
def asDate(d):
    d = d.split('T')[0]
    try:
        d=datetime.strptime(d, "%d/%m/%Y")
    except ValueError:
        try:
            d=datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            try:
                d=datetime.strptime(d, "%Y/%m/%d")
            except ValueError:
                d=datetime.strptime(d, "%d-%m-%Y")
    return d.date()


# shorten legal bases
def clean_lb(dossier):
    for lbstrip, prefix in [("Treaty on the Functioning of the EU TFEU ", 'TFEU'),
                            ("Treaty on the Functioning of the EU ", 'TFEU'),
                            ("Rules of Procedure of the European Parliament EP ", 'RoP'),
                            ("Rules of Procedure EP ", 'RoP')]:
        for i, lb in enumerate(dossier.get('procedure', {}).get('legal_basis',[])):
            if lb.startswith(lbstrip):
                dossier['procedure']['legal_basis'][i]="%s %s" % (prefix,lb[len(lbstrip):])


def create_search_regex(query):
    search_terms = query.split()
    if len(search_terms) == 1:
        return re.compile(re.escape(search_terms[0]), re.I | re.M | re.U)
    return re.compile('(?=.*' + ')(?=.*'.join(map(re.escape, search_terms)) + ')', re.I | re.M | re.U)


def mep_search(search_re, m):
    if (
        search_re.search(m['Name']['full'])
        ): return True
    return False


def dossier_search(search_re, d):
    if (
        search_re.search(d['procedure']['title'])
        or search_re.search(d['procedure']['reference'])
        or search_re.search(' '.join(d['procedure'].get('subject', [])))
        or search_re.search(d.get('celexid', ''))
        ): return True
    return False


terms = {
    1: {'start': '1979-07-11', 'end': '1984-07-23'},
    2: {'start': '1984-07-24', 'end': '1989-07-24'},
    3: {'start': '1989-07-25', 'end': '1994-07-18'},
    4: {'start': '1994-07-19', 'end': '1999-07-19'},
    5: {'start': '1999-07-20', 'end': '2004-07-19'},
    6: {'start': '2004-07-20', 'end': '2009-07-13'},
    7: {'start': '2009-07-14', 'end': '2014-06-30'},
    8: {'start': '2014-07-01', 'end': '2019-07-01'},
    9: {'start': '2019-07-02', 'end': '2024-07-15'},
    10: {'start': '2024-07-16', 'end': ''},
}


def end_of_term(term):
    if not term in terms:
        return
    return terms[term]['end']

from math import log2
_suffixes = ['bytes', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
def file_size(size):
    # determine binary order in steps of size 10
    # (coerce to int, // still returns a float)
    order = int(log2(size) / 10) if size else 0
    # format file size
    # (.4g results in rounded numbers for exact matches and max 3 decimals,
    # should never resort to exponent values)
    return '{:.1f} {}'.format(size / (1 << (order * 10)), _suffixes[order])

def diff_prettyHtml(self, diffs):
    """Convert a diff array into a pretty HTML report.
    Args:
      diffs: Array of diff tuples.
    Returns:
      HTML representation.
    """
    html = []
    for (op, data) in diffs:
      text = (data.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;").replace("\n", "&para;<br>"))
      if op == self.DIFF_INSERT:
        html.append("<ins>%s</ins>" % text)
      elif op == self.DIFF_DELETE:
        html.append("<del>%s</del>" % text)
      elif op == self.DIFF_EQUAL:
        html.append("<span>%s</span>" % text)
    return "".join(html)

def format_dict(d):
    if type(d)==list:
        return u'<ul>%s</ul>' % '\n'.join(["<li>%s</li>" % printdict(v) for v in d])
    if type(d)==datetime:
        return "%s" % d.isoformat()[:10]
    elif not type(d)==dict:
        return "%s" % unicode(d)
    res=['']
    for k,v in [(k,v) for k,v in d.items() if k not in ['mepref','comref']]:
        if type(v) == dict or (type(v)==list and len(v)>1):
            res.append(u"<dl><dt class='more'>%s</dt><dd class='hidden'>%s</dd></dl>" % (k,printdict(v)))
        else:
            res.append(u"<dl><dt>%s</dt><dd>%s</dd></dl>" % (k,printdict(v)))
    return '%s' % u'\n'.join(res)


if __name__ == "__main__":
    pass
