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

# (C) 2011 by Stefan Marsiske, <stefan.marsiske@gmail.com>, Asciimoo

from datetime import datetime
from utils.mappings import COMMITTEE_MAP
from utils.utils import fetch, unws, jdump
from utils.log import log
from db import db

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

BASE_URL = 'http://www.europarl.europa.eu'

def scrape(**kwargs):
    #urltpl="http://www.europarl.europa.eu/committees/en/%s/documents-search.html"
    urltpl="http://www.europarl.europa.eu/committees/en/%s/search-in-documents.html"
    postdata="docType=AGEN&leg=8&miType=text&tabActif=tabResult#sidesForm"
    #nexttpl="http://www.europarl.europa.eu/committees/en/%s/documents-search.html?action=%s&tabActif=tabResult#sidesForm"
    nexttpl="http://www.europarl.europa.eu/committees/en/%s/search-in-documents.html?action=%s&tabActif=tabResult#sidesForm"
    jobs = []
    for com in (k for k in COMMITTEE_MAP.keys()
                if len(k)==4 and k not in ['CODE', 'RETT', 'CLIM', 'TDIP', 'SURE', 'CRIM', 'CRIS']):
        url=urltpl % (com)
        i=0
        agendas=[]
        log(3, 'scraping %s' % com)
        root=fetch(url, params=postdata)
        prev=[]
        while True:
            log(3, "%s %s" % (datetime.now().isoformat(), url))
            tmp=[(a.get('href'), unws(a.xpath('text()')[0]))
                 for a in root.xpath('//p[@class="title"]/a')
                 if len(a.get('href',''))>13]
            if not tmp or prev==tmp: break
            prev=tmp
            for u,title in tmp:
                if title.startswith('DRAFT AGENDA'):
                    #print('comagenda', {'url':u,'committee': com})
                    jobs.append({'url':u,'committee': com})
            i+=1
            url=nexttpl % (com,i)
            try:
                root=fetch(url)
            except:
                log(4, "failed to download url "+url)
                break
    for job in jobs:
        add_job('comagenda', payload=job)


if __name__ == "__main__":
    scrape()
