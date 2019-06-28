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

# (C) 2012,2019 by Stefan Marsiske, <stefan.marsiske@gmail.com>

from utils.utils import fetch, junws
from utils.log import log
from utils.mappings import COMMITTEE_MAP
from config import CURRENT_TERM

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

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

def getComAms(term, update=False, **kwargs):
    seen = set()
    urltpl="http://www.europarl.europa.eu/committees/en/%s/search-in-documents.html"
    #for doctype in ['AMCO', 'RPCD', 'OPCD']:
    doctype = 'AMCO'
    postdata="clean=false&leg=%s&docType=%s&miType=text&tabActif=tabResult" % (term, doctype)
    nexttpl="action=%s"
    for com in (k for k in COMMITTEE_MAP.keys()
                if len(k)==4 and k not in ['CODE', 'RETT', 'CLIM', 'TDIP', 'SURE', 'CRIM', 'CRIS']):
        url=urltpl % (com)
        i=0
        log(3,'%s crawling %s, term: %s' % (doctype, com, term))
        root=fetch(url, params=postdata)
        prev=[]
        while True:
            log(3, "page %s of %s" % (i, url))
            tmp=[]
            for a in root.xpath('//a[@title="open this PDF in a new window"]'):
                u=a.get('href','')
                if (len(u)<=13):
                    log(2,'url is too short, skipping: "%s"' % u)
                    continue
                if u in seen or u in skipurls or (not u.endswith('EN') and not u.endswith('_EN.pdf')):
                    log(3,"skipping url: %s" % repr(u))
                    continue
                seen.add(u)
                rs = a.xpath('../../../p[@class="rapporteurs clearfix"]')
                if len(rs)!=1:
                    log(1,"len(rs)==%d!=1 in %s" % (len(rs), url))
                    raise ValueError("HTML strangeness in %s" % url)
                r = junws(rs[0])
                tmp.append(u)
                try:
                    payload = dict(kwargs)
                    payload['url'] = u
                    payload['meps'] = r
                    add_job('amendment', payload=payload)
                except:
                    print(u, r)

            if not tmp or prev==tmp:
                break
            prev=tmp

            if update: break

            i+=1
            root=fetch(url, params="%s&%s" % (postdata, nexttpl % i))

def scrape(all=False, **kwargs):
    if all:
        # todo enable also 6th term
        for term in range(7,CURRENT_TERM+1):
            getComAms(term, update=False, **kwargs)
    else:
        getComAms(CURRENT_TERM, update=True, **kwargs)

if __name__ == "__main__":
    scrape(all=False)
