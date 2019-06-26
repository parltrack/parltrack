#!/usr/bin/env python3
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

# (C) 2014,2019 Stefan Marsiske

from datetime import datetime
from utils.utils import fetch, jdump
from utils.log import log
import sys

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

# 'http://www.europarl.europa.eu/plenary/en/minutes.html?clean=false&leg=7&refSittingDateStart=01/01/2011&refSittingDateEnd=31/12/2011&miType=title&miText=Roll-call+votes&tabActif=tabResult&startValue=10'
def crawl(year, term, **kwargs):
    listurl = 'http://www.europarl.europa.eu/plenary/en/minutes.html'
    PARAMS = '?clean=false&leg=%s&refSittingDateStart=01/01/%s&refSittingDateEnd=31/12/%s&miType=title&miText=Roll-call+votes&tabActif=tabResult'
    params = PARAMS % (term, year, year)
    root=fetch(listurl+params)
    prevdates=None
    dates=root.xpath('//span[@class="date"]/text()')
    i=0
    while dates and dates!=prevdates:
        for date in dates:
            if not date.strip(): continue
            #print(term, date.strip())
            date = datetime.strptime(date.strip(), "%d-%m-%Y").strftime("%Y-%m-%d")
            payload = dict(kwargs)
            payload['term'] = term
            payload['date'] = date
            add_job('pvote', payload=payload)
        i+=1
        root=fetch("%s%s&action=%s" % (listurl,params,i))
        prevdates=dates
        dates=root.xpath('//span[@class="date"]/text()')

def getterms(year):
    if year < 2004:
        log(1,"plenary votes only availabble after 2004, got %d" % year)
        return []
    elif year == 2004:
        return [6]
    elif year%5!=4:
        return [6+(year-2004)//5]
    else:
        return [5+(year-2004)//5,
                6+(year-2004)//5]

def scrape(year=None):
    if year==None: # only scrape current year
        years = [datetime.now().year]
    elif year == "all":
        years = range(2004,datetime.now().year+1)
    elif year >= 2004 and year <= datetime.now().year:
        years = [year]
    else:
        log(1, 'cannot crawl years for "%s"' % year)
        raise ValueError('invalid year in pvotes.scrape: "%s"' % year)
    for year in years:
        for term in getterms(year):
            crawl(year, term)

if __name__ == '__main__':
    year = None
    if len(sys.argv) > 1:
        if sys.argv[1]=="all":
            year = "all"
        else:
            try:
                year = int(sys.argv[1])
            except:
                sys.stderr.write('[!] usage: %s <all|year(2004-...)>\n' % sys.argv[0])
                sys.exit(1)
    scrape(year)
