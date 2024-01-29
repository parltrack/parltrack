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

# (C) 2024 by Stefan Marsiske, <stefan.marsiske@gmail.com>, asciimoo

from db import db
from scrapers import comvote
from utils.log import log
from utils.utils import fetch, junws

from requests.exceptions import HTTPError

BASE_URL = 'https://www.europarl.europa.eu/committees/en/{0}/meetings/votes'

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'table': 'ep_comvotes',
    'abort_on_error': True,
}

url_filters = {
    'EMPL': lambda url: 'RCV' in url or 'Roll-call' in url,
}


def scrape(active=True, dry=False, committee=None, json_dump=False, **kwargs):
    if committee:
        committees = [committee]
    else:
        if not active:
            committees = filter(None, db.committees().keys())
        else:
            committees = [x for (x,y) in db.committees().items() if y['active'] and x]

    log(4, 'Collecting com vote PDFs for the following committees: ' + ', '.join(sorted(committees)))

    for c in committees:
        log(4, "Collecting PDFs for committee '{0}'".format(c))
        url = BASE_URL.format(c.lower())

        try:
            dom = fetch(url)
        except HTTPError as e:
            if e.response.status_code == 404:
                if all:
                    level = 4
                else:
                    level = 1
                log(level, "Votes URL not found for committee '{0}'".format(c))
            else:
                log(1, "Unknown HTTP error when fetching comvotes URL {0} for committee '{1}' (STATUS CODE: {2})".format(url, c, e.response.status_code))
            continue

        pdf_count = 0

        #for href in dom.xpath('//div[@class="erpl_product"]//div[@class="erpl_links-list mb-2"]//ul/li/a/@href'):
        for elem in dom.xpath('//div[@class="erpl_product"]'):
            title = junws(elem.xpath('.//div[@class="erpl_product-header mb-2"]')[0])
            for link in elem.xpath('.//div[@class="erpl_links-list mb-2"]//ul/li/a'):
                link_text = junws(link)
                href = link.get('href')

                if not href.endswith('.pdf'):
                    continue
                if c in url_filters and not url_filters[c](href):
                    continue

                pdf_count += 1

                if db.get('com_votes_by_pdf_url', href):
                    continue

                job_args = dict(kwargs)
                job_args['url'] = href
                job_args['committee'] = c
                job_args['link_text'] = link_text
                job_args['title'] = title
                job_args['json_dump'] = False
                if json_dump:
                    job_args['json_dump'] = True

                if dry:
                    print(job_args)
                    continue

                try:
                    add_job('comvote', payload=job_args)
                except:
                    comvote.scrape(**job_args)

        if not pdf_count:
            log(1, "No PDF found for committee '{0}'".format(c))


if __name__ == '__main__':
    from sys import argv
    dry = False
    if len(argv) > 1:
        if argv[1] == 'json_dump':
            #scrape(dry=dry, active=True, json_dump=True, committee='PECH')
            scrape(dry=dry, active=True, json_dump=True)
        else:
            scrape(dry=dry, active=True, committee=argv[1])
    else:
        scrape(dry=dry, active=True)
