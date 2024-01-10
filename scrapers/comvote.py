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
from utils.utils import fetch_raw
from utils.mappings import GROUP_MAP

from os import remove
from os.path import isfile
from subprocess import run
from tempfile import NamedTemporaryFile


import pdfplumber


GABBRS = set(GROUP_MAP.values())

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'table': 'ep_comvotes',
    'abort_on_error': True,
}

DOSSIER_ID_TYPOS = {
    '2023/0079(C0D)': '2023/0079(COD)',
    '2021/ 0136 (COD)': '2021/0136(COD)',
}


def scrape(committee, url, **kwargs):
    committee = committee.upper()
    pdf_doc = fetch_raw(url, binary=True)
    res = []
    with NamedTemporaryFile() as tmp:
        tmp.write(pdf_doc)

        with pdfplumber.open(tmp.name) as pdf:
            pdfdata = extract_pdf(pdf)

    for i, data in enumerate(pdfdata):
        if not type(data) == list:
            continue
        tables = [x.extract() for x in data]

        vote = {
            'committee': committee,
            'url': url,
        }

        if len(tables) == 3:
            vote['votes'] = parse_simple_table(tables)
            #from pprint import pprint
            #pprint(t_res)
        else:
            print(tables)
            raise(Exception("TODO"))
            #t_res = parse_table_with_corrections(tables)

        text = pdfdata[i-1]
        vote_details = get_vote_details(committee, text)

        # means that this is part of multiple votes about the same subject
        # we need the additional data from the previous vote
        if len(vote_details) == 1 and 'type' in vote_details and len(res):
            vote_details['reference'] = res[-1]['reference']
            if 'rapporteur' in res[-1]:
                vote_details['rapporteur'] = res[-1]['rapporteur']

        vote.update(**vote_details)

        if 'rapporteur' in vote:
            fix_rapporteur_data(vote)
        else:
            log(2, f'Unable to identify rapporteur {vote["rapporteur"]["name"]} in {url}')

        if not db.dossier(vote['reference']):
            if vote['reference'] in DOSSIER_ID_TYPOS:
                vote['reference'] = DOSSIER_ID_TYPOS[vote['reference']]
            else:
                raise(Exception(f'Invalid dossier ID "{vote["reference"]}" in {url}. If it is only a typo add it to DOSSIER_ID_TYPOS.'))

        if 'type' not in vote or not vote['type']:
            log(2, f'Unable to vote type {vote["rapporteur"]["name"]} in {url}')

        res.append(vote)

    #from IPython import embed; embed()
    from pprint import pprint
    pprint(res)
    return


def extract_pdf(pdf):
    extract_settings = {
        'vertical_strategy': 'lines',
        'horizontal_strategy': 'lines',
    }
    pdfdata = []
    prev_tables = None
    for i, page in enumerate(pdf.pages):
        #im = page.to_image()
        #im.debug_tablefinder(extract_settings)
        #im.save("static/t/debug%d.png" % i)
        tables = page.find_tables(table_settings=extract_settings)
        if not tables:
            continue

        start_pageno = 0
        # warning: page number is off by one -> pages[0].pageno is 1
        pageno = page.page_number - 1
        text = []

        # get text from below the previous table
        if prev_tables:
            text.append(get_text_from_page(prev_tables[0].page, starts_from=prev_tables[-1].bbox[3]))
            start_pageno = prev_tables[0].page.page_number

        # get text from the in between pages
        if start_pageno < pageno:
            for i in range(start_pageno, pageno):
                text.append(get_text_from_page(pdf.pages[i]))

        # get text from above the current page
        text.append(get_text_from_page(page, ends_at=tables[0].bbox[1]))

        #text = '\n\n[NEWPAGE]\n\n'.join(text)
        text = '\n\n'.join(text)

        if pdfdata and type(pdfdata[-1]) == type(text):
            pdfdata[-1] += '\n\n' + text
        else:
            pdfdata.append(text)

        if pdfdata and type(pdfdata[-1]) == list:
            pdfdata[-1].extend(tables)
        else:
            pdfdata.append(tables)

        prev_tables = tables
    return pdfdata


def get_vote_details(committee, text):
    return COMM_DETAIL_PARSERS[committee](text)


def get_text_from_page(page, starts_from=None, ends_at=None):
    if starts_from is None:
        starts_from = 0
    if ends_at is None:
        ends_at = page.height

    text = page.crop((0, starts_from, page.width, ends_at)).extract_text(layout=True)
    text = '\n'.join(map(str.strip, text.split('\n'))).strip()

    return text


def parse_simple_table(tables):
    results = {
        'for': {'total': 0, 'groups': {}},
        'against': {'total': 0, 'groups': {}},
        'abstain': {'total': 0, 'groups': {}}
    }
    for i, table in zip(['for', 'against', 'abstain'], tables):
        results[i] = parse_table_section(table)
    return results


def parse_table_section(table):
    ret = {'total': 0, 'groups': {}}
    group = ''
    members = ''
    ret['total'] = int(list(filter(None, table[0]))[0])

    for row in table[1:]:
        if len(row) == 2:
            group = resolve_group_name(row[0])
            ret['groups'][group] = meps_by_name(row[1].replace('\n', ' '), group)
        else:
            row_split_idx = 4
            if len(row) == 4:
                row_split_idx = 2
            row1 = ''.join(filter(None, set(row[:row_split_idx])))
            if row1:
                if members.strip():
                    ret['groups'][group] = meps_by_name(members, group)
                group = resolve_group_name(row1)
                members = ''
            members += ' ' + ' '.join(filter(None, set(row[row_split_idx:])))

    if members.strip():
        ret['groups'][group] = meps_by_name(members, group)

    mepcount = len(list(x for y in ret['groups'].keys() for x in ret['groups'][y]))

    if ret['total'] != mepcount:
        msg = f"Vote mep count mismatch: total {ret['total']}, count {mepcount}"
        log(1, msg)
        raise(Exception(msg))

    return ret


def meps_by_name(mep_names, group):
    # TODO collect dates as well for better identification (nice to have)
    return [db.mepid_by_name(x, group=group) for x in map(str.strip, mep_names.split(','))]


def fix_rapporteur_data(vote):
    vote['rapporteur']['mep_id'] = db.mepid_by_name(vote['rapporteur']['name'], group=vote['rapporteur'].get('group'))
    if 'group' in vote['rapporteur']:
        vote['rapporteur']['group'] = resolve_group_name(vote['rapporteur']['group'])


def resolve_group_name(g):
    if g in GABBRS:
        return g

    if g in GROUP_MAP:
        return GROUP_MAP[g]

    raise(Exception(f'Cannot identify group "{g}". Please resolve it manually and add it to utils/mappings.py:GROUP_MAP'))


#import re
#vt_header_re = re.compile(r'\W+([0-9]+)\W+\+\W+')
# pdftotext -nopgbrk -layout RCVs.pdf RCVs.txt
#def scrape(committee, url, **kwargs):
#    committee = committee.upper()
#    pdf_doc = fetch_raw(url, binary=True)
#    with NamedTemporaryFile() as tmp:
#        text_fname = tmp.name + '.txt'
#        tmp.write(pdf_doc)
#        cmd = ['pdftotext', '-nopgbrk', '-layout', tmp.name, text_fname]
#        ret = run(cmd)
#        if ret.returncode:
#            log(1, 'pdftotext process returned with non 0 status code ({0}) while executing "{1}"'.format(ret.returncode, ', '.join(cmd)))
#            cleanup(text_fname)
#            return
#
#    with open(text_fname) as tfile:
#        pdftext = tfile.read()
#
#    for m in vt_header_re.finditer(pdftext):
#        print(dir(m))
#        idx = m.span()
#        print(pdftext[idx[0]:idx[1]])
#    res = []
#    cleanup(text_fname)
#    return save(res)


def cleanup(fname):
    if isfile(fname):
        remove(fname)


def save(data):
    print("SAVING", data)
    return data

def parse_rapporteur_with_group(text, replace_string):
    rdata = text.replace(replace_string, '')
    rname, rgroup = rdata.split(' (')
    while rgroup and not rgroup[-1].isalpha():
        rgroup = rgroup[:-1]
    return rname, rgroup


def parse_afet_details(text):
    lines = text.split('\n')

    rname, rgroup = parse_rapporteur_with_group(lines[-1], 'Rapporteur: ')

    ref = lines[-2].strip()

    for i, l in enumerate(reversed(lines)):
        # trying to find the first empty line above the dossier title
        if not l and i > 2:
            typeidx = i
            break

    vtype = lines[-(typeidx+2)]

    ret = {
        'reference': ref,
        'type': vtype,
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
    }
    return ret


def parse_cult_details(text):
    parts = [x.replace('\n', ' ') for x in text.split('\n\n')]

    rname, rgroup = parse_rapporteur_with_group(lines[-1], 'Rapporteur: ')

    ref = parts[-2].strip()
    if ref.startswith('('):
        ref = ref[1:]
    if ref.endswith('))'):
        ref = ref[:-1]

    vtype = parts[-3].split(':')[0]

    ret = {
        'reference': ref,
        'type': vtype,
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
    }
    return ret


def parse_pech_details(text):
    lines = text.split('\n')
    vote_type = ' '.join(lines[-1].split()[1:])
    if len(lines) < 3:
        raise(Exception("Too few lines in a PECH pdf"))

    last_newline = [i for i,x in enumerate(lines[:-2]) if not x][-1]
    title = ' '.join(lines[last_newline:-2])[3:].strip()
    title_parts = list(map(str.strip, title.split('-')))
    if len(title_parts) == 3:
        dossier_title = title_parts[0]
        rapporteur_name = title_parts[1]
        dossier_id = title_parts[2]
    else:
        dossier_title = '-'.join(title_parts[0:len(title_parts)-3])
        rapporteur_name = title_parts[-2]
        dossier_id = title_parts[-1]

    ret = {
        'reference': dossier_id,
        'rapporteur': {
            'name': rapporteur_name,
        },
        'type': vote_type,
    }
    return ret


def parse_inta_details(text):
    chunks = list(x.replace('\n', ' ') for x in filter(None, text.split('\n\n')))
    title_split = [x.strip() for x in chunks[-3].split('–')]
    rname, rgroup = parse_rapporteur_with_group(title_split[2], 'rapporteur: ')
    ret = {
        'reference': title_split[1],
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
        'type': chunks[-1],
    }
    return ret


def parse_itre_details(text):
    chunks = list(x.replace('\n', ' ') for x in filter(None, text.split('\n\n')))
    title = chunks[-1]
    title_split = [x.strip() for x in title.split('-')]
    try:
        rname, rgroup = parse_rapporteur_with_group(title_split[2], 'Rapporteur: ')
    except:
        return {'type': title_split[0]}
    ret = {
        'reference': title_split[1],
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
        'type': title_split[-1],
    }
    return ret


COMM_DETAIL_PARSERS = {
    'AFET': parse_afet_details,
    'ITRE': parse_itre_details,
    'INTA': parse_inta_details,
    'PECH': parse_pech_details,
    'CULT': parse_cult_details,
}

if __name__ == "__main__":
    from utils.utils import jdump
    from sys import argv

    if len(argv) == 3:
        print(jdump(scrape(argv[1].upper(), argv[2])))
    else:
        print("Test scraper with the following arguments: [COMMITTEE] [PDFURL]")
