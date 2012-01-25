#!/usr/bin/env python
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

# (C) 2012 by Stefan Marsiske, <stefan.marsiske@gmail.com>

import re
from parltrack.utils import fetch, unws
from mappings import CELEXCODES

EURLEXURL="http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri="
GENERIC_FIELDS = [("Classifications",
                   ["Subject matter:","Directory code:","EUROVOC descriptor:","Directory code:"]),
                  ("Miscellaneous information",
                   ["Author:","Form:","Addressee:","Additional information:"]),
                  ("Procedure",
                   ["Procedure number:","Legislative history:"]),
                  ("Relationship between documents",
                   ["Treaty:",
                    "Legal basis:",
                    "Amendment to:",
                    "Amended by:",
                    "Consolidated versions:",
                    "Subsequent related instruments:",
                    "Affected by case:",
                    "Instruments cited:"])]

def scrape(docid):
    (code,lang)=docid.split(":")[1:3]
    st=7 if code[6].isalpha() else 6
    eurlex={'id': {u'docid': docid,
                   u'sector': code[0],
                   u'year': code[1:5],
                   u'doctype': code[5:st],
                   u'refno': code[st:],
                   u'lang': lang,
                   u'typeDesc': CELEXCODES[code[0]]['Document Types'][code[5:st]] if code[5:st] != 'C' else CELEXCODES[code[0]]['Sector'],
                   }}

    root = fetch("%s%s:NOT" % (EURLEXURL,docid))
    eurlex[u'title'] = root.xpath('//h2[text()="Title and reference"]/following-sibling::p/text()')[0]
    # dates
    dates=root.xpath('//h2[text()="Dates"]/following-sibling::ul/text()')
    if len(dates):
        eurlex['dates']=dict([unws(y).split(": ") for y in dates if unws(y)])
    for t,l in GENERIC_FIELDS:
        try:
            s=root.xpath('//h2[text()="%s"]/following-sibling::ul' % t)[0]
        except:
            print 'skipping %s' % t
            continue
        if not len(s): continue
        tmp=dict([(field, [unws(x) if x.getparent().tag!='a' else {u'text': unws(x),
                                                                   u'url': x.getparent().get('href')}
                           for x in s.xpath('./li/strong[text()="%s"]/..//text()' % field)
                           if unws(x) and unws(x)!='/'][1:])
                  for field in l])
        if len(tmp.keys()):
            eurlex[t]=tmp
    return eurlex

if __name__ == "__main__":
    import pprint
    pprint.pprint(scrape("CELEX:32009L0140:EN:HTML"))
    #pprint.pprint(scrape("CELEX:31994D0006:EN:HTML"))
    #pprint.pprint(scrape("CELEX:31994L0006:EN:HTML"))
    #pprint.pprint(scrape("CELEX:51994XP006:EN:HTML"))
    #pprint.pprint(scrape("CELEX:32004L0048:EN:HTML"))
