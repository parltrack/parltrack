#!/usr/bin/env python2.6

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
from sys import argv, exit

URL = 'http://www.europarl.europa.eu/activities/plenary/pv/calendar.do'

def fetch(url):
    # url to etree
    try:
        f=urlopen(url)
    except:
        return '[!] unable to open %s' % url
    return parse(f)

def getDates(root):
    dates = []
    # past
    for d in root.xpath("//td[@class='session']/a"):
        day = strip(d.text)
        try:
            day = int(day)
        except:
            continue
        month, year = strip(d.getparent().getparent().getparent().xpath('tr[1]/td[1]/table/tr/td[5]/text()')[0]).split()
        dates.append(datetime.strptime('%s %s %d' % (year, month, day), "%Y %B %d"))
    # future
    for d in root.xpath("//td[@class='session_off']"):
        day = strip(d.text)
        try:
            day = int(day)
        except:
            continue
        month, year = strip(d.getparent().getparent().xpath('tr[1]/td[1]/table/tr/td[5]/text()')[0]).split()
        dates.append(datetime.strptime('%s %s %d' % (year, month, day), "%Y %B %d"))
    return dates


if __name__ == '__main__':
    try:
        year = int(argv[1])
    except:
        print '[!] usage: %s [year(2004-2014)]' % argv[0]
        exit(1)
    url = '%s?language=EN&YEAR=%d' % (URL, year)
    if year >= 2004 and year < 2009:
        url = url+'&LEG_ID=6'
    # !! important part: getDates(fetch(url)) -> returns: array of datetime objects !!
    print '[!] YEAR %d' % year
    print '_'*60
    print '\n'.join(map(str, getDates(fetch(url))))



