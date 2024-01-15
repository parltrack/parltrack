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
from utils.utils import fetch_raw, unws
from utils.mappings import GROUP_MAP

from os import remove
from os.path import isfile
import re
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

DOSSIER_RE = re.compile('\d{4}/\d{4}\([A-Z]{3}\)')

DOSSIER_ID_TYPOS = {
    '2023/0079(C0D)': '2023/0079(COD)',
    '2021/ 0136 (COD)': '2021/0136(COD)',
}

VOTE_TYPE_MAP = {
    'final vote by roll call in committee asked for opinion': 'final vote',
    'final vote by roll call in committee for opinion': 'final vote',
    'final vote by roll call in committee responsible': 'final vote',
    'final vote onthe draft report': 'final vote',
    'final vote': 'final vote',
}


def scrape(committee, url, **kwargs):
    committee = committee.upper()
    pdf_doc = fetch_raw(url, binary=True)
    res = []
    with NamedTemporaryFile() as tmp:
        tmp.write(pdf_doc)

        with pdfplumber.open(tmp.name) as pdf:
            pdfdata = extract_pdf(pdf, committee)

    for i, data in enumerate(pdfdata):
        if not type(data) == list:
            continue
        tables = [x.extract() for x in data]

        vote = {
            'committee': committee,
            'url': url,
        }

        if len(tables) < 3:
            raise(Exception('Less than 3 tables belong to a vote in {0}'.format(url)))
        if len(tables) > 3:
            tables = repair_tables(tables)

        vote['votes'] = parse_simple_table(tables)

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
            log(2, f'Unable to identify rapporteur in {url}')

        if not db.dossier(vote['reference']):
            if vote['reference'] in DOSSIER_ID_TYPOS:
                vote['reference'] = DOSSIER_ID_TYPOS[vote['reference']]
            else:
                raise(Exception('Invalid dossier ID "{0}" in {1}. If it is only a typo add it to DOSSIER_ID_TYPOS.'.format(vote["reference"], url)))

        if 'type' not in vote or not vote['type'] or vote['type'].lower() not in VOTE_TYPE_MAP:
            log(2, f'Unable to identify vote type "{vote["type"]}" in {url}')
        else:
            vote['type'] = VOTE_TYPE_MAP[vote['type'].lower()]
        res.append(vote)

    #from IPython import embed; embed()
    from pprint import pprint
    pprint(res)
    return


def extract_pdf(pdf, committee):
    extract_settings = {
        'vertical_strategy': 'lines',
        'horizontal_strategy': 'lines',
    }
    pdfdata = []
    prev_table = None
    #detect_footer(pdf.pages)
    #exit()
    for page in pdf.pages:
        first_text_of_page = True
        for table in page.find_tables(table_settings=extract_settings):
            pageno = prev_pageno = page.page_number - 1
            start_pos = 0
            end_pos = table.bbox[1]
            if prev_table:
                prev_pageno = prev_table.page.page_number - 1
                start_pos = prev_table.bbox[3]
            else:
                prev_pageno = 0

            t = get_text_from_pages(
                pdf.pages,
                start_pageno=prev_pageno,
                end_pageno=pageno,
                start_pos=start_pos,
                end_pos=end_pos,
                committee=committee
            ).strip()
            if t:
                pdfdata.append(t)
            pdfdata.append(table)
            prev_table = table

    # add texts below the last table
    t = get_text_from_pages(
        pdf.pages,
        start_pageno=page.page_number-1,
        end_pageno=pdf.pages[-1].page_number-1,
        start_pos=table.bbox[3],
        end_pos=pdf.pages[-1].height,
        committee=committee
    ).strip()
    if t:
        pdfdata.append(t)

    merged_data = []
    prev_d = None
    for d in pdfdata:
        if type(prev_d) == type(d) == str:
            merged_data[-1] += d
        elif type(d) == pdfplumber.table.Table:
            if type(prev_d) == list:
                prev_d.append(d)
            else:
                merged_data.append([d])
        else:
            merged_data.append(d)
        prev_d = merged_data[-1]
    pdfdata = merged_data
    # prev_tables = None
    # for i, page in enumerate(pdf.pages):
    #     #im = page.to_image()
    #     #im.debug_tablefinder(extract_settings)
    #     #im.save("static/t/debug%d.png" % i)
    #     tables = page.find_tables(table_settings=extract_settings)
    #     if not tables:
    #         continue

    #     start_pageno = 0
    #     # warning: page number is off by one -> pages[0].pageno is 1
    #     pageno = page.page_number - 1
    #     text = []

    #     # get text from below the previous table
    #     if prev_tables:
    #         text.append(get_text_from_page(prev_tables[0].page, starts_from=prev_tables[-1].bbox[3]))
    #         start_pageno = prev_tables[0].page.page_number

    #     # get text from the in between pages
    #     if start_pageno < pageno:
    #         for i in range(start_pageno, pageno):
    #             text.append(get_text_from_page(pdf.pages[i]))

    #     # get text from above the current page
    #     text.append(get_text_from_page(page, ends_at=tables[0].bbox[1]))

    #     #text = '\n\n[NEWPAGE]\n\n'.join(text)
    #     text = '\n\n'.join(text)

    #     if pdfdata and type(pdfdata[-1]) == type(text):
    #         pdfdata[-1] += '\n\n' + text
    #     else:
    #         pdfdata.append(text)

    #     if pdfdata and type(pdfdata[-1]) == list:
    #         pdfdata[-1].extend(tables)
    #     else:
    #         pdfdata.append(tables)

    #     prev_tables = tables

    #from pprint import pprint; pprint(pdfdata); exit(0)
    return pdfdata


#def is_same_without_pageno(strings):
#    for i, chars in enumerate(zip(*strings)):
#        print(chars)
#        if 1 != len(set(chars)):
#            if not strings[0][i].isdigit():
#                return False
#            new_strings = []
#            for string in strings:
#                end = i
#                while string[end].isdigit() :
#                    end += 1
#                new_strings.append(string[:i]+string[end:])
#            if len(set(new_strings)) == 1:
#                return True
#            return False
#    return True
#
#
#def detect_footer(pages, start=1):
#    page_texts = [[line for line in p.extract_text(layout=True).split('\n') if unws(line)] for p in pages[start:]]
#    header = []
#    footer = []
#    from difflib import ndiff
#    for i in range(5, 0, -1):
#        cand = [unws(''.join(p[-i:])) for pageno,p in enumerate(page_texts)]
#        if(is_same_without_pageno(cand)):
#            return i
#    return 0


def get_vote_details(committee, text):
    return COMM_DETAIL_PARSERS[committee](text)


def get_text_from_page(page, start_pos=None, end_pos=None):
    if start_pos is None:
        start_pos = 0
    if end_pos is None:
        end_pos = page.height

    text = page.crop((0, start_pos, page.width, end_pos)).extract_text(layout=True)
    text = '\n'.join(map(str.strip, text.split('\n'))).strip()

    return text


def get_text_from_pages(pages, start_pageno, end_pageno, start_pos, end_pos, committee):
    cut_header = HEADER_CUTTERS.get(committee, lambda x:x)
    cut_footer = FOOTER_CUTTERS.get(committee, lambda x:x)

    if start_pageno == end_pageno:
        t = get_text_from_page(pages[start_pageno], start_pos, end_pos)
        if start_pos == 0:
            t = cut_header(t)
        if end_pos == pages[start_pageno].height:
            t = cut_footer(t)
        return t

    text = []
    # first page
    t = cut_footer(get_text_from_page(pages[start_pageno], start_pos=start_pos))
    if start_pos == 0:
        text.append(cut_header(t))
    else:
        text.append(t)
    # middle pages
    text.extend([cut_footer(cut_header(get_text_from_page(pages[start_pageno+i+1]))) for i in range(end_pageno - start_pageno - 1)])

    # last page
    t = get_text_from_page(pages[end_pageno], end_pos=end_pos)
    if end_pos == pages[end_pageno].height:
        text.append(cut_footer(t))
    else:
        text.append(t)

    return '\n\n'.join(filter(None, text))


def parse_simple_table(tables):
    results = {
        'for': {'total': 0, 'groups': {}},
        'against': {'total': 0, 'groups': {}},
        'abstain': {'total': 0, 'groups': {}}
    }
    for i, table in zip(['for', 'against', 'abstain'], tables):
        results[i] = parse_table_section(table)
    return results


def repair_tables(tables):
    fixed_tables = []
    for table in tables:
        if not any(x in table[0] for x in ['+', '-', '0']):
            if not fixed_tables:
                raise Exception('Cannot repair table - missing header')
            fixed_tables[-1].extend(table)
        else:
            fixed_tables.append(table)
    if len(fixed_tables) != 3:
        raise Exception('Cannot repair table - unknown error')
    return fixed_tables


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

    if (ret['total'] == 0 and mepcount != 0) or (ret['total'] != 0 and mepcount == 0):
        msg = f"Vote mep count mismatch: total {ret['total']}, count {mepcount}"
        log(1, msg)
        raise(Exception(msg))

    if ret['total'] != mepcount:
        log(2, f"Vote mep count mismatch: total {ret['total']}, count {mepcount}")

    return ret


def meps_by_name(mep_names, group):
    # TODO collect dates as well for better identification (nice to have)
    return [db.mepid_by_name(x, group=group) for x in map(str.strip, mep_names.split(','))]


def fix_rapporteur_data(vote):
    if 'group' in vote['rapporteur']:
        try:
            vote['rapporteur']['group'] = resolve_group_name(vote['rapporteur']['group'])
        except Exception as e:
            log(1, e)
    # TODO try to find missing group information (date required)
    vote['rapporteur']['mep_id'] = db.mepid_by_name(vote['rapporteur']['name'], group=vote['rapporteur'].get('group'))


def resolve_group_name(g):
    if g == 'unknown':
        return g

    if g in GABBRS:
        return g

    if g in GROUP_MAP:
        return GROUP_MAP[g]

    raise(Exception('Cannot identify group "{0}". Please resolve it manually and add it to utils/mappings.py:GROUP_MAP'.format(g)))


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
    splits = rdata.split('(')
    if len(splits) == 1:
        return splits[0].strip(), ''

    rname, rgroup = splits
    while rgroup and not rgroup[-1].isalpha():
        rgroup = rgroup[:-1]
    return rname.strip(), rgroup.split()[0].strip() if rgroup else ''


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


def parse_deve_details(text):
    chunks = list(x.replace('\n', ' ') for x in filter(None, text.split('\n\n')))
    rname, rgroup = parse_rapporteur_with_group(chunks[-2], 'Rapporteur: ')
    dossier_id = DOSSIER_RE.findall(chunks[-3])[-1]
    ret = {
        'reference': dossier_id,
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
        'type': chunks[-1],
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


def parse_imco_details(text):
    chunks = list(x.replace('\n', ' ') for x in filter(None, text.split('\n\n')))
    vtype = ' '.join(chunks[-1].split()[1:])
    title = chunks[-2]
    title_split = [x.strip() for x in title.split('–')]
    try:
        rname, rgroup = parse_rapporteur_with_group(title_split[2], '')
    except:
        return {'type': vtype}
    ret = {
        'reference': title_split[1],
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
        'type': vtype,
    }
    return ret


def parse_regi_details(text):
    lines = text.splitlines()
    vtype = ' '.join(lines[-1].split()[1:])
    chunks = list(x.replace('\n', ' ') for x in filter(None, '\n'.join(lines[:-1]).split('\n\n')))
    title = chunks[-1]
    title_split = [x.strip() for x in title.split(',')]
    try:
        rname = title_split[-1]
        dossier_id = title_split[-2]
    except:
        return {'type': vtype}
    ret = {
        'reference': dossier_id,
        'rapporteur': {
            'name': rname,
            'group': '',
        },
        'type': vtype,
    }
    return ret


def parse_sede_details(text):
    # TODO collect more data: we only have 1 published pdf
    lines = text.splitlines()
    dossier_id = lines[-1].strip()
    ret = {
        'reference': dossier_id,
        'type': 'FINAL VOTE BY ROLL CALL IN COMMITTEE RESPONSIBLE',
    }
    return ret


def parse_droi_details(text):
    chunks = list(x.replace('\n', ' ').strip() for x in filter(None, text.split('\n\n')))
    for i, d in enumerate(chunks):
        if d.startswith('Table of Contents'):
            break
    dossier_id = chunks[i+1].split('-')[-1]
    rapp_and_type = chunks[i+2].split('-')
    vtype = rapp_and_type[-1].split('...')[0].strip()
    rname, rgroup = parse_rapporteur_with_group('-'.join(rapp_and_type[:-1]), 'Rapporteur:')
    ret = {
        'reference': dossier_id,
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
        'type': vtype,
    }
    return ret


def parse_afco_details(text):
    lines = text.splitlines()
    vtype = lines[-1]
    lines.pop()
    while lines and not lines[-1]:
        lines.pop()
    title = ' '.join(lines[max(idx for idx,l in enumerate(lines) if not l):])
    title_split = [x.strip() for x in title.split(',')]
    rname, rgroup = parse_rapporteur_with_group(title_split[-1], 'Rapporteur: ')
    dossier_id = DOSSIER_RE.findall(title_split[-2])[-1]
    ret = {
        'reference': dossier_id,
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
        'type': vtype,
    }
    return ret


def cut_imco_footer(text):
    return '\n'.join(text.splitlines()[:-3]).strip()


def cut_regi_footer(text):
    return '\n'.join(text.splitlines()[:-1]).strip()


COMM_DETAIL_PARSERS = {
    'AFET': parse_afet_details,
    'ITRE': parse_itre_details,
    'IMCO': parse_imco_details,
    'INTA': parse_inta_details,
    'PECH': parse_pech_details,
    'CULT': parse_cult_details,
    'REGI': parse_regi_details,
    'AFCO': parse_afco_details,
    'SEDE': parse_sede_details,
    'DEVE': parse_deve_details,
    'DROI': parse_droi_details,
}

HEADER_CUTTERS = {
}

FOOTER_CUTTERS = {
    'IMCO': cut_imco_footer,
    'REGI': cut_regi_footer,
}

if __name__ == "__main__":
    from utils.utils import jdump
    from sys import argv

    if len(argv) == 3:
        print(jdump(scrape(argv[1].upper(), argv[2])))
    else:
        print("Test scraper with the following arguments: [COMMITTEE] [PDFURL]")
