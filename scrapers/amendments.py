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

# (C) 2012,2019 by Stefan Marsiske, <parltrack@ctrlc.hu>

from utils.utils import fetch, junws
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

skipurls=['http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-483.680%2b02%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-454.387%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-456.679%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-494.504%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.705%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.767%2b02%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-454.385%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-465.012%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-496.504%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.724%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.721%2b02%2bDOC%2bPDF%2bV0%2f%2fEN',
          'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.723%2b03%2bDOC%2bPDF%2bV0%2f%2fEN']

def crawl(term, update=False, test=[], **kwargs):
    seen = set()
    url="https://www.europarl.europa.eu/committees/en/documents/search?committeeMnemoCode=%s&textualSearchMode=TITLE&textualSearch=&documentTypeCode=AMCO&reporterPersId=&procedureYear=&procedureNum=&procedureCodeType=&peNumber=&aNumber=&aNumberYear=&documentDateFrom=&documentDateTo=&meetingDateFrom=&meetingDateTo=&performSearch=true&term=%s&page=%s&pageSize={}".format(itemsPerPage)
    jobs = []
    for com in (k for k in test or COMMITTEE_MAP.keys() if len(k)==4):
        i=0
        log(3,'crawling %s, term: %s' % (com, term))
        try:
            root=fetch(url % (com, term, i))
        except requests.exceptions.HTTPError as e:
            #if e.response.status_code == 500:
            log(3, "failed to get list of amendments for %s in term %d, http error code: %s" % (com, term, e.response.status_code))
            continue
        prev=[]
        while True:
            log(3, "crawling amendments search page %s for %s term %s" % (i, com, term))
            tmp=[]
            #for a in root.xpath('//a[@title="open this PDF in a new window"]'):
            for a in root.xpath('//a[@class="erpl_document-subtitle-pdf"]'):
                u=a.get('href','')
                if (len(u)<=13):
                    log(2,'url is too short, skipping: "%s"' % u)
                    continue
                if u in seen or u in skipurls or (not u.endswith('EN') and not u.endswith('_EN.pdf')):
                    log(3,"skipping url: %s" % repr(u))
                    continue
                seen.add(u)
                tmp.append(u)
                rs = a.xpath('../../following-sibling::div/span[@class="erpl_document-subtitle-author"]')
                r = [y for y in [junws(x) for x in rs] if y]
                try:
                    payload = dict(kwargs)
                    payload['url'] = u
                    payload['meps'] = r
                    if test:
                        print(payload)
                    else:
                        add_job('amendment', payload=payload)
                except:
                    print(u, r)

            if not tmp or prev==tmp or len(tmp) < itemsPerPage:
                break
            prev=tmp

            if update: break

            i+=1
            try:
                root=fetch(url % (com, term, i))
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 500:
                    log(3, "failed to page %s of draft agendas for %s in term %d" % (i, com, term))
                break

def scrape(all=False, **kwargs):
    if all:
        for term in range(6,CURRENT_TERM+1):
            crawl(term, update=False, **kwargs)
    else:
        crawl(CURRENT_TERM, update=True, **kwargs)

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 2:
        crawl(9, update=False, test=[sys.argv[1]])
    else:
        scrape(all=True)
