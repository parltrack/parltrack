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

# (C) 2011 by Stefan Marsiske, <parltrack@ctrlc.hu>, Asciimoo

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


def getnullq(term):
    url="http://www.europarl.europa.eu/committees/en/search-in-documents.html"
    postdata="docType=AGEN&leg=%s&miType=text&tabActif=tabResult#sidesForm" % term
    res = []
    i=0
    log(4, 'initializing com agenda null query for term %d' % term)
    root=fetch(url, params=postdata)
    tmp=[(a.get('href'), unws(a.xpath('text()')[0]))
         for a in root.xpath('//p[@class="title"]/a')
         if len(a.get('href',''))>13]
    return [u for u,title in tmp if title.startswith('DRAFT AGENDA')]

def crawl(term, **kwargs):
    url="https://www.europarl.europa.eu/committees/en/%s/search-in-documents.html"
    postdata="documentDateStart=&meetingDateEnd=&documentType=&docType=AGEN&folderComCode=&refAYear=&refProcYear=&folderId=&documentDateEnd=&author=&clean=false&tabActif=tabResult&real_form_name=sidesForm&meetingDateStart=&folderLegId=&refPe=&refProcCode=&miType=text&refProcNum=&refANum=&miText=&leg=%s&committee=%s&source=&action=%s"
    # clean=false&leg=8&action=0&tabActif=tabResult&committee=2863&docType=AGEN&author=&refPe=&refANum=&refAYear=&miType=text&miText=&documentType=&documentDateStart=&documentDateEnd=&meetingDateStart=&meetingDateEnd=&folderComCode=&folderLegId=&folderId=&refProcYear=&refProcNum=&refProcCode=
    nullq = getnullq(term)
    jobs = []
    for com in (k for k in COMMITTEE_MAP.keys() if len(k)==4):
        i=0
        log(3,'crawling %s, term: %s' % (com, term))
        try:
            root=fetch(url % com, params=(postdata % (term, com, i)))
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 500:
                log(3, "failed to get list of draft agendas for %s in term %d" % (com, term))
                continue
        prev=[]
        while True:
            log(3, "crawling comagenda search page %s for %s term %s" % (i, com, term))
            tmp=[(a.get('href'), unws(a.xpath('text()')[0]))
                 for a in root.xpath('//p[@class="title"]/a')
                 if len(a.get('href',''))>13]
            if not tmp or prev==tmp:
                break
            prev=tmp
            tmp =[u for u,title in tmp if title.startswith('DRAFT AGENDA')]
            if tmp == nullq:
                log(4,"no agenda items found for %s in term %d" % (com, term))
                break
            for u in tmp:
                jobs.append({'url':u,'committee': com})
            i+=1
            try:
                root=fetch(url % com, params=(postdata % (term, com, i)))
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500:
                    log(3, "failed to page %s of draft agendas for %s in term %d" % (i, com, term))
                break
    for job in jobs:
        add_job('comagenda', payload=job)

def scrape(all=False, **kwargs):
    if all:
        for term in range(7,CURRENT_TERM+1):
            crawl(term)
    else:
        crawl(CURRENT_TERM)

if __name__ == "__main__":
    scrape(all=True)
