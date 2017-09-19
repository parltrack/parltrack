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

# (C) 2011 by Adam Tauber, <asciimoo@gmail.com>


from lxml.html.soupparser import parse
import urllib2, urllib, cookielib
from string import strip
from parltrack.environment import connect_db
from parltrack.scrapers.oeil import scrape as oeil_scrape
from os.path import realpath, exists, dirname
from parltrack.scrapers.mappings import STAGES
import sys

db = connect_db()

URL = 'http://www.europarl.europa.eu/oeil/'
LAST_UPDATED_CACHE = "%s/.dossiers_last_updated" % dirname(realpath(__file__))

opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()))
#opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()),
#                              urllib2.ProxyHandler({'http': 'http://localhost:8123/'}))
opener.addheaders = [('User-agent', 'weurstchen/0.5')]

def fetch(url, retries=5):
    # url to etree
    try:
        f=urllib2.urlopen(url)
    except (urllib2.HTTPError, urllib2.URLError), e:
        if hasattr(e, 'code') and e.code>=400 and e.code not in [504]:
            print >>sys.stderr, "[!] %d %s" % (e.code, url)
            raise
        if retries>0:
            f=fetch(url,retries-1)
        else:
            raise
    return parse(f)

def getNewItems(root):
    for d in root.xpath('//td[@class="listlevelthree"]/../td/a'):
        dossier = fetch((URL+d.attrib['href']).encode('utf8'))
        for e in  dossier.xpath('//a[@class="com_acronym"]'):
            d_url = e.attrib['href']
            if not db.dossiers.find_one({'meta.source': URL+d_url}):
                oeil_scrape(URL+d_url)
                # print '[!] NEW ITEM: %s%s scraped!!' % (URL, d_url)

def scrape(url):
    root = fetch(url)
    # TODO optimize this!! (reduce steps)
    if not exists(LAST_UPDATED_CACHE) or open(LAST_UPDATED_CACHE).read() != strip(root.xpath('//div[text()="Data updated on :"]/span/text()')[0]):
        print >>sys.stderr, '[!] Site modification found, scraping unfinished dossiers....'
        for d in db.dossiers.find({'procedure.stage_reached': {'$in': STAGES}},timeout=False):
            oeil_scrape(d['meta']['source'])
            print >>sys.stderr, '\t%s, %s' % (d['procedure']['reference'].encode('utf8'), d['procedure']['title'].encode('utf8'))
        f = open(LAST_UPDATED_CACHE, "w+")
        f.write(strip(root.xpath('//div[text()="Data updated on :"]/span/text()')[0]))
        f.close()
    print >>sys.stderr, '\n[!] Searching/scraping new items..'
    getNewItems(root)
    return True

if __name__ == '__main__':
    print scrape(URL)



