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
from urllib2 import urlopen
from string import strip
from datetime import datetime
from sys import argv, exit, stderr
from parltrack.scrapers.ep_votes import scrape as scrape_votes

URL = 'http://www.europarl.europa.eu/activities/plenary/pv/calendar.do'

def fetch(url):
    # url to etree
    try:
        f=urlopen(url)
    except:
        return '[!] unable to open %s' % url
    return parse(f)

def getDates(root, future=False):
    dates = []
    # past
    for d in root.xpath("//td[@class='session']/a"):
        day = strip(d.text)
        try:
            day = int(day)
        except:
            continue
        month, year = strip(d.getparent().getparent().getparent().xpath('tr[1]/td[1]/table/tr/td[5]/text()')[0]).split()
        yield datetime.strptime('%s %s %d' % (year, month, day), "%Y %B %d").strftime("%Y%m%d")
    if future:
        for d in root.xpath("//td[@class='session_off']"):
            day = strip(d.text)
            try:
                day = int(day)
            except:
                continue
            month, year = strip(d.getparent().getparent().xpath('tr[1]/td[1]/table/tr/td[5]/text()')[0]).split()
            yield datetime.strptime('%s %s %d' % (year, month, day), "%Y %B %d").strftime("%Y%m%d")


if __name__ == '__main__':
    # dirty but funky oneliner, handles multiple arguments =)
    # if len(set(argv))-1 != len([map(scrape_votes, getDates(fetch(URL+'?language=EN&YEAR='+year))) for year in set(argv) if year.isdigit() and int(year) >= 2004 and int(year) <= 2014 and not stderr.write('[!] Scraping '+year+' votes\n')]): print '[!] usage: %s [years (2004-2014)]' % argv[0]
    try:
        year = int(argv[1])
    except:
        stderr.write('[!] usage: %s [year(2004-2014)]\n' % argv[0])
        exit(1)
    url = '%s?language=EN&YEAR=%d' % (URL, year)
    if year >= 2004 and year < 2009:
        url = url+'&LEG_ID=6'
    # !! important part: getDates(fetch(url)) -> returns: array of dates !!
    map(scrape_votes, getDates(fetch(url)))
