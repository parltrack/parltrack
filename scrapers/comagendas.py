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

from utils.utils import fetch_raw, jdump
from utils.log import log
from utils.mappings import COMMITTEE_MAP
from config import CURRENT_TERM
import datetime, json, requests

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

seen=set()
def topayload(com, year, month, **kwargs):
    url_tpl="https://emeeting.europarl.europa.eu/emeeting/ecomback/ws/EMeetingRESTService/events?" \
            "language=EN&year={year}&month={month}&organ={committee}"
    url = url_tpl.format(committee=com, year=year, month=month)
    if url in seen: return
    seen.add(url)
    log(3,'fetching %s, month: %s %s %s' % (com, year, month, url))
    try:
        meetings=fetch_raw(url, res=True).json()
    except requests.exceptions.HTTPError as e:
        #if e.response.status_code == 500:
        log(3, "failed to get list of draft agendas for %s, month: %s %s, http error code: %s, %s" %
            (com, year, month, e.response.status_code, url))
        return []
    res = []
    for meeting in meetings:
       payload = dict(kwargs)
       #payload['url'] = "https://emeeting.europarl.europa.eu/emeeting/ecomback/ws/EMeetingRESTService/oj?" \
       #                 "language=en&reference=%s&securedContext=false" % meeting["meetingReference"]
       payload['committee']= com
       payload['meeting']=meeting
       res.append(payload)
    return res

def scrape(all=False, **kwargs):
    curyear = datetime.datetime.now().year
    endyear = curyear
    curmonth = datetime.datetime.now().month
    end = (curmonth % 12) + 1
    if end < curmonth:
        endyear = curyear + 1

    if all:
        months = [(2016,12)]
        months.extend([(y,m) for y in range(2017, curyear) for m in range(1,13)])
        months.extend([(curyear, m) for m in range(1,curmonth+1)])
    else:
        months = [(curyear, curmonth)]

    months.append((endyear, end))

    for com in (k for k in COMMITTEE_MAP.keys() if len(k)==4):
        for year, month in months:
            for payload in topayload(com,year,month):
                if __name__ == "__main__":
                    #print(jdump(payload))
                    comagenda.scrape(payload)
                    continue
                add_job('comagenda', payload=payload)
    add_job('comagenda', payload={'publish': True})

if __name__ == "__main__":
    import sys
    import comagenda
    if len(sys.argv) == 2:
        crawl(all=True)
    else:
        crawl(all=False)
