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

# (C) 2019 by Stefan Marsiske, <parltrack@ctrlc.hu>

from utils.utils import unws, jdump
from lxml.html.soupparser import fromstring
from datetime import datetime
#from mappings import COMMITTEE_MAP, buildings, group_map, COUNTRIES, SEIRTNUOC
#from urllib.parse import urljoin
#import unicodedata, traceback, sys, json
#from utils.multiplexer import Multiplexer, logger
#from model import Mep
#import findecl

def crawler(all=False):
    if all:
        sources = ['http://www.europarl.europa.eu/meps/en/directory/xml?letter=&leg=']
    else:
        sources = ['http://www.europarl.europa.eu/meps/en/incoming-outgoing/incoming/xml',
                   'http://www.europarl.europa.eu/meps/en/incoming-outgoing/outgoing/xml',
                   'http://www.europarl.europa.eu/meps/en/full-list/xml']
    if all:
        for unlisted in [ 1018, 26833, 1040, 1002, 2046, 23286, 28384, 1866, 28386,
                          1275, 2187, 34004, 28309, 1490, 28169, 28289, 28841, 1566,
                          2174, 4281, 28147, 28302, ]:
            yield unlisted
    for src in sources:
        root = fetch(src)
        for id in root.xpath("//mep/id/text()"):
            print int(id)

def crawler_cb(all, txt):

def deobfus_mail(txt):
    x = txt.replace('[at]','@').replace('[dot]','.')
    return ''.join(x[len('mailto:'):][::-1])

def scraper(id, txt):
    root = fromstring(txt[txt.find('?>')+2:])
    mep = {
        'name'      : unws(' '.join(root.xpath('//*[@id="name-mep"]//text()'))),
        'twitter'   : root.xpath('//div[@class="ep_share"]//a[@title="Twitter"]/@href'),
        'homepage'  : root.xpath('//div[@class="ep_share"]//a[@title="Website"]/@href'),
        'facebook'  : root.xpath('//div[@class="ep_share"]//a[@title="Facebook"]/@href'),
        'email'     : [deobfus_mail(x) for x in root.xpath('//div[@class="ep_share"]//a[@title="E-mail"]/@href')],
        'instagram' : root.xpath('//div[@class="ep_share"]//a[@title="Instagram"]/@href'),
        'Birth'     : {
            'date'  : datetime.strptime(root.xpath('//time[@id="birthDate"]/text()')[0], u"%d-%m-%Y"),
            'place' : root.xpath('//span[@id="birthPlace"]/text()')[0]
        },
    }

    print(jdump(mep))
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/home
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/cv
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/declarations
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/assistants
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/history/8
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/history/7
    # activities
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/main-activities/plenary-speeches
    # or /meps/en/96674/loadmore-activities/plenary-speeches/8/?from=10&count=100
    # or /meps/en/96674/loadmore-activities/written-explanations/8/?from=10&count=100
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/main-activities/reports
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/main-activities/reports-shadow
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/main-activities/opinions-shadow
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/main-activities/motions-instit
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/main-activities/oral-questions
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/other-activities/written-explanations
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/other-activities/written-questions-other
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/other-activities/motions-indiv
    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/other-activities/written-declarations
    pass

if __name__ == '__main__':
    #crawler()
    from utils.utils import fetch_raw
    scraper(28390, fetch_raw("http://www.europarl.europa.eu/meps/en/%s/name/%s" % (id, 'home')))
