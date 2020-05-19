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

# (C) 2011, 2019, 2020 by Stefan Marsiske, <parltrack@ctrlc.hu>, Asciimoo

from utils.utils import fetch, unws
from utils.log import log
from utils.mappings import COMMITTEE_MAP
from config import CURRENT_TERM
import requests

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

itemsPerPage=30


def crawl(term, test=[], **kwargs):
    seen = set()
    url="https://www.europarl.europa.eu/committees/en/documents/search?committeeMnemoCode=%s&textualSearchMode=TITLE&textualSearch=&documentTypeCode=AGEN&reporterPersId=&procedureYear=&procedureNum=&procedureCodeType=&peNumber=&aNumber=&aNumberYear=&documentDateFrom=&documentDateTo=&meetingDateFrom=&meetingDateTo=&performSearch=true&term=%s&page=%s&pageSize={}".format(itemsPerPage)
    jobs = []
    for com in (k for k in test or COMMITTEE_MAP.keys() if len(k)==4):
        i=0
        log(3,'crawling %s, term: %s' % (com, term))
        try:
            root=fetch(url % (com, term, i))
        except requests.exceptions.HTTPError as e:
            #if e.response.status_code == 500:
            log(3, "failed to get list of draft agendas for %s in term %d, http error code: %s" % (com, term, e.response.status_code))
            continue
        prev=[]
        while True:
            log(3, "crawling comagenda search page %s for %s term %s" % (i, com, term))
            tmp=[]
            for a in root.xpath('//a[@class="erpl_document-subtitle-pdf"]'):
                u=a.get('href','')
                if (len(u)<=13):
                    log(2,'url is too short, skipping: "%s"' % u)
                    continue
                if u in seen or (not u.endswith('EN') and not u.endswith('_EN.pdf')):
                    log(3,"skipping url: %s" % repr(u))
                    continue
                seen.add(u)
                tmp.append(u)
                try:
                    payload = dict(kwargs)
                    payload['url'] = u
                    payload['committee']= com
                    if test:
                        print(payload)
                    else:
                        add_job('comagenda', payload=payload)
                except:
                    print(u, r)

            if not tmp or prev==tmp or len(tmp) < itemsPerPage:
                break
            prev=tmp
            i+=1
            try:
                root=fetch(url % (com, term, i))
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500:
                    log(3, "failed to page %s of draft agendas for %s in term %d" % (i, com, term))
                break

def scrape(all=False, **kwargs):
    if all:
        for term in range(7,CURRENT_TERM+1):
            crawl(term)
    else:
        crawl(CURRENT_TERM)

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 2:
        crawl(9, test=[sys.argv[1]])
    else:
        scrape(all=True)
