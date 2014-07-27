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

from datetime import datetime
from sys import argv, exit, stderr
from parltrack.scrapers.ep_votes import scrape as scrape_votes
from parltrack.utils import fetch

# 'http://www.europarl.europa.eu/plenary/en/minutes.html?clean=false&leg=7&refSittingDateStart=01/01/2011&refSittingDateEnd=31/12/2011&miType=title&miText=Roll-call+votes&tabActif=tabResult&startValue=10'
URL = 'http://www.europarl.europa.eu/plenary/en/minutes.html'
PARAMS = 'clean=false&leg=%s&refSittingDateStart=01/01/%s&refSittingDateEnd=31/12/%s&miType=title&miText=Roll-call+votes&tabActif=tabResult'

from lxml.etree import tostring
def getDates(params):
    root=fetch(URL, params=params)
    #print tostring(root)
    prevdates=None
    dates=root.xpath('//span[@class="date"]/text()')
    i=10
    while dates and dates!=prevdates:
        for date in dates:
            if not date.strip(): continue
            yield datetime.strptime(date.strip(), "%d-%m-%Y").strftime("%Y%m%d")

        root=fetch(URL, params="%s&startValue=%s" % (params,i))
        prevdates=dates
        i+=10
        dates=root.xpath('//span[@class="date"]/text()')

if __name__ == '__main__':
    try:
        year = int(argv[1])
    except:
        stderr.write('[!] usage: %s [year(2004-2014)]\n' % argv[0])
        exit(1)
    term=7
    if year >= 2004 and year < 2009:
        term=6
    params = PARAMS % (term, year, year)
    # !! important part: getDates(fetch(url)) -> returns: array of dates !!
    map(scrape_votes, getDates(params))
    if year==2009:
        params = PARAMS % (6, year, year)
        map(scrape_votes, getDates(params))
