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
from utils.log import log
from utils.utils import jdump, junws

from os import remove
from os.path import isfile
import re
from subprocess import run
from tempfile import NamedTemporaryFile

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'table': 'ep_comvotes',
    'abort_on_error': True,
}


def scrape(committee, vote_tables, vote_type, aref, test=False, save=True):
    log(3, f'Collecting vote tables for {committee} - {aref} ({vote_type})')
    vote = {
        'committee': committee,
        'vote_type': vote_type,
        'aref': aref,
        'id': f'{aref}-{committee}-{vote_type}',
    }
    vote['votes'] = dict(map(parse_table, vote_tables))

    if test:
        print(jdump(vote))

    if save:
        process(
            vote,
            vote['id'],
            db.com_vote,
            'ep_com_votes',
            vote['id'],
            nodiff=True,
        )


def parse_table(t):
    res = {
        'groups': {}
    }
    v = ''
    for i, row in enumerate(t.xpath('.//tr')):
        c1, c2 = list(map(junws, row.xpath('.//td')))
        if i == 0:
            v = c2
            res['total'] = int(c1)
            continue
        group = c1
        res['groups'][group] = get_meps_by_name(c2, group)
    return v, res


def get_meps_by_name(mep_names, group):
    return [db.mepid_by_name(x, group=group) for x in map(str.strip, mep_names.split(',')) if x]


if __name__ == "__main__":
    #TODO
    pass
