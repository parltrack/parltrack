#!/usr/bin/env python
# -*- coding: utf-8 -*-
#    This file is part of parltrack

#    parltrack is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    parltrack is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with parltrack  If not, see <http://www.gnu.org/licenses/>.

# (C) 2009-2011 by Stefan Marsiske, <stefan.marsiske@gmail.com>

from lxml.html.soupparser import parse
from operator import itemgetter
import urllib2, cookielib, sys, csv, datetime, re, collections, unicodedata
from parltrack.scrapers.mappings import ipexevents as dates

try:
    from parltrack.environment import connect_db
    db = connect_db()
except:
    import pymongo
    db=pymongo.Connection().parltrack

class IpexMap:
    def __init__(self):
        self.map={}

    def __getitem__(self, name):
        if not self.map:
            self.map=getIpexData()
        return self.map.get(name)

# and some global objects
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()),
                              urllib2.ProxyHandler({'http': 'http://localhost:8123/'}))
opener.addheaders = [('User-agent', 'weurstchen/0.5')]
csv.register_dialect('hash', delimiter='#', quoting=csv.QUOTE_NONE)
IPEXMAP=IpexMap()

def UnicodeDictReader(utf8_data, **kwargs):
    csv_reader = csv.DictReader(utf8_data, dialect="hash", **kwargs)
    for row in csv_reader:
        yield dict([(key, unicode(value, 'utf-8')) for key, value in row.iteritems()])

def fetch(url, retries=3):
    # url to etree
    try:
        f=urllib2.urlopen(url, timeout=32)
    except (urllib2.HTTPError, urllib2.URLError), e:
        if hasattr(e, 'code') and e.code>=400:
            print >>sys.stderr, "[!] %d %s" % (e.code, url)
            return None
        if retries>0:
            f=fetch(url,retries-1)
        else:
            return None
    return f

def toDate(text):
    if not len(text): return None
    value=[int(x) for x in text.split('/') if len(x)]
    return datetime.date(value[2], value[1], value[0]).isoformat()

def getMEPRef(name):
    if not name: return
    mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.split()).lower()},['_id', 'Groups'])
    if not mep and u'ß' in name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower()},['_id', 'Groups'])
    if not mep and unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore')!=name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore').split()).lower()},['_id', 'Groups'])
    if mep:
        return mep
    else:
        print >>sys.stderr, '[!] lookup oops', name.encode('utf8')

def getMEPGroup(mep,date=None):
    if not date:
        date=datetime.datetime.now()
    else:
        value=[int(x) for x in date.split('/') if len(x)]
        date=datetime.datetime(value[2], value[1], value[0])
    for group in mep['Groups']:
        if group['start']<=date and group['end']>=date:
            if not 'groupid' in group:
                return group['Organization']
            elif type(group.get('groupid'))==list:
                return group['groupid'][0]
            return group['groupid']

cdates=[u'Date', u'EP officialisation', u'Deadline Amendments', u'EP 1R Committee']

refre=re.compile(r'([0-9/]*)[(]([A-Z]{3})')
basre=re.compile(r'([A-Z]{3})[(]([0-9]{4})[)]([0-9]{4})')
def getIpexData():
    page=parse(fetch('http://www.ipex.eu/IPEXL-WEB/epdoc.do'))
    title=None
    for url in page.xpath('//div[@id="widgetContent_LU_WID"]//a'):
        title=u''.join(url.xpath('text()'))
        if title == u'a. Legislative procedures (currently ongoing or ended during the 7th Parliamentary term)':
            a=url
            break
    assert title == u'a. Legislative procedures (currently ongoing or ended during the 7th Parliamentary term)', "title changed on ipex: %s" % title
    url="http://www.ipex.eu%s" % a.get('href')
    items=list(csv.DictReader(fetch(url), dialect="hash"))
    ipexmap={}
    for item in items:
        date=None
        for k in cdates[::-1]:
            if item[k]:
                date=item[k]
                break
        item['Rapporteur']=[[x['_id'],getMEPGroup(x,date)] for x in filter(None,[getMEPRef(mep) for mep in item['Rapporteur'].decode('raw_unicode_escape').split(', ')])]
        item['Shadows']=[[x['_id'],getMEPGroup(x,date)] for x in filter(None,[getMEPRef(mep) for mep in item['Shadows'].decode('raw_unicode_escape').split(', ')])]
        item['Dates']=[]
        for k in dates.keys():
            tmp=item[k].split(' ')
            body=dates[k]['body']
            if len(tmp)==1:
                try:
                    tmp1=toDate(tmp[0])
                    if tmp1:
                        item['Dates'].append({'type': 'Event', 'body': body, 'date': tmp1, 'title': k})
                except:
                    print k, tmp[0]
                    raise
            elif len(tmp)>1:
                tmp1=toDate(tmp[-1])
                if tmp1:
                    item['Dates'].append({'type': 'Event', 'body': body, 'date': tmp1, 'title': k})
            else:
                print >>sys.stderr, "[!]", k, item[k]
            del item[k]
        item['Dates']=sorted(item['Dates'])
        tmp=refre.match(item['ProcRef'])
        if tmp: item['ProcRef']=u'/'.join(tmp.groups()[::-1])
        tmp=basre.match(item['Bas Doc'])
        if tmp:
            item['Base Doc']=u"%s/%s/%s" % tmp.groups()
            del item['Bas Doc']
        item['Com Opinion']=filter(None,item['Com Avis'].split(';'))
        item['title']=item['Titre EN'].decode('raw_unicode_escape')
        item['subject']=item['Theme'].decode('raw_unicode_escape')
        item['Com Responible']=item['ComFond'].decode('raw_unicode_escape')
        for k in ['ComFond', 'Theme', ' ', 'Titre EN', 'Com Avis']:
            del item[k]
        for k in item.keys():
            if not item[k]:
                del item[k]
        ipexmap[item['ProcRef']]=item

        # other fields
        # 'ComFond': 'BUDG',
        # 'Phase': '8.10 Ended',
        # 'Pol Group': 'PPE',
        # 'Type': 'DBA',
        # 'url OEIL': 'http://www.europarl.europa.eu/oeil/FindByProcnum.do?lang=en&procnum=BUD/2009/2048'
        # 'Scrutiny': 'http://www.ipex.eu/ipex/cms/home/Documents/dossier_CNS20110817'
    return ipexmap

if __name__ == "__main__":
    #print IPEXMAP['COD/2011/0211']
    #import code; code.interact(local=locals());
    import pprint
    pprint.pprint(getIpexData().values())
