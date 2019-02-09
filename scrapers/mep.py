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

import re
from utils.utils import fetch, fetch_raw, unws, jdump
from datetime import datetime
from lxml.html.soupparser import fromstring

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}


def deobfus_mail(txt):
    x = txt.replace('[at]','@').replace('[dot]','.')
    return ''.join(x[len('mailto:'):][::-1])

def scrape(id):
    # we ignore the /meps/en/<id>/<name>/home path, since we can get all info also from other pages
    url = "http://www.europarl.europa.eu/meps/en/%s/name/cv" % id
    root = fetch(url)
    body = root.xpath('//span[@id="mep-card-content"]/following-sibling::div')[0]
    mep = {
        'MepID'     : id,
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
        # cv
        'cv': {
            'updated': datetime.strptime(root.xpath('//span[starts-with(text(),"Updated: ")]/text()')[0], u"Updated: %d/%m/%Y"),
        }
    }
    mep['cv'].update({unws(''.join(title.xpath(".//text()"))): [unws(''.join(item.xpath(".//text()")))
                                                                for item in title.xpath("../../../article//li")]
                      for title in body.xpath('.//h3')
                      if not unws(''.join(title.xpath(".//text()"))).startswith("Original version : ")})
    # assistants
    root = fetch("http://www.europarl.europa.eu/meps/en/%s/name/assistants" % id)
    body = root.xpath('//span[@id="mep-card-content"]/following-sibling::div')[0]
    mep['assistants'] = {unws(''.join(title.xpath(".//text()"))): [unws(''.join(item.xpath(".//text()")))
                                                                for item in title.xpath("../../../article//li")]
                      for title in body.xpath('.//h3')}
    # declarations
    root = fetch("http://www.europarl.europa.eu/meps/en/%s/name/declarations" % id)
    for addr in root.xpath('//div[@class="ep-a_contacts"]/ul/li'):
        print(addr) #, unws(''.join(addr.xpath('.//h3//text()'))))

    body = root.xpath('//span[@id="mep-card-content"]/following-sibling::div')[0]
    #print(jdump(mep))

    # /meps/en/96674/ANNA+MARIA_CORAZZA+BILDT/declarations
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

if __name__ == '__main__':
    scrape(28390)
