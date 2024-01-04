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
from utils.utils import fetch_raw, jdump
from utils.log import log
import sys

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

seen = set()

def crawl(year, term, **kwargs):
    url = 'https://www.europarl.europa.eu/RegistreWeb/services/search'
    params = {"dateCriteria":{"field":"DATE_DOCU","startDate":None,"endDate":None},"accesses":[],"types":["PPVD"],"authorCodes":[],"fragments":[],"geographicalAreas":[],"eurovocs":[],"directoryCodes":[],"subjectHeadings":[],"policyAreas":[],"institutions":[],"authorAuthorities":[],"recipientAuthorities":[],"authorOrRecipientAuthorities":[],"nbRows":10,"references":[],"relations":[],"authors":[],"currentPage":1,"sortAndOrder":"DATE_DOCU_DESC","excludesEmptyReferences":False,"fulltext":None,"title":None,"summary":None}

    params['years']=[year]
    params['terms']=[term]

    res=fetch_raw(url, asjson=params, res=True).json()
    while(len(res.get('references',[]))>0):
        for r in res['references']:
            for x in r['fragments']:
                if x.get('value') != 'RCV': continue
                for v in x['versions']:
                    for f in v.get('fileInfos',[]):
                        if f['typeDoc']!='text/xml': continue
                        if f['url'] in seen: continue
                        seen.add(f['url'])
                        payload = dict(kwargs)
                        payload['url'] = f['url']
                        #print(payload)
                        add_job('pvote', payload=payload)
        params["currentPage"]+=1
        res=fetch_raw(url, asjson=params, res=True).json()

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

def scrape(year=None, **kwargs):
    if year is None: # only scrape current year
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
