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

from utils.utils import fetch
from utils.log import log
from db import db

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

def scrape(all=False, **kwargs):
    if all:
        sources = ['http://www.europarl.europa.eu/meps/en/directory/xml?letter=&leg=']
    else:
        sources = ['http://www.europarl.europa.eu/meps/en/incoming-outgoing/incoming/xml',
                   'http://www.europarl.europa.eu/meps/en/incoming-outgoing/outgoing/xml',
                   'http://www.europarl.europa.eu/meps/en/full-list/xml']
    payload={}
    if 'onfinished' in kwargs:
        payload['onfinished']=kwargs['onfinished']
    if all:
        actives = {e['UserID'] for e in db.meps_by_activity(True)}
        inactives = {e['UserID'] for e in db.meps_by_activity(False)}
        meps = actives | inactives
        # TODO also add any that are in the db but missing from this list and the full directory
        for unlisted in [ 1018, 26833, 1040, 1002, 2046, 23286, 28384, 1866, 28386,
                          1275, 2187, 34004, 28309, 1490, 28169, 28289, 28841, 1566,
                          2174, 4281, 28147, 28302, ]:
            meps.discard(unlisted)
            payload['id']=unlisted
            add_job('mep', dict(payload))
    for src in sources:
        root = fetch(src, prune_xml=True)
        for id in root.xpath("//mep/id/text()"):
            if all: meps.discard(int(id))
            payload['id']=int(id)
            add_job('mep', dict(payload))
    if all:
        log(3,"mepids not in unlisted nor in directory {!r}".format(meps))
        for id in meps:
            payload['id']=id
            add_job('mep', dict(payload))

if __name__ == '__main__':
    #actives = {e['UserID'] for e in db.meps_by_activity(True)}
    #inactives = {e['UserID'] for e in db.meps_by_activity(False)}
    #meps = actives | inactives
    #print(len(meps))
    #print(max(meps))
    #print(len([x for x in meps if x < 113000]))
    scrape(False)
