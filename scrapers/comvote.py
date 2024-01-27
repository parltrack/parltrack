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
from utils.utils import fetch_raw, unws, DOSSIERID_RE
from utils.mappings import GROUP_MAP
from utils.process import process

from hashlib import sha256
from json import dumps
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

DOSSIER_ID_TYPOS = {
    '2023/0079(C0D)': '2023/0079(COD)',
    '2021/ 0136 (COD)': '2021/0136(COD)',
    '2023/2829(RSP) (question for oral answer)': '2023/2829(RSP)',
}

VOTE_TYPE_MAP = {
    'final vote by roll call in committee asked for opinion': 'opinion final',
    'final vote by roll call in committee for opinion': 'opinion final',
    'final vote by roll call in committee responsible': 'responsible final',
    'final vote onthe draft report': 'draft final',
    'final vote': 'final',
    'single vote': 'single',
    'vote on the decision to enter into interinstitutional negotiations': 'enter into interinstitutional negotiations',
    'roll call': 'roll call',
    'vote on the draft opinion': 'draft opinion',
    'vote on the draft report': 'draft report',
    'vote on mandate': 'mandate',
    'adoption of draft opinion': 'adoption of draft opinion',
    'final vote by roll call in committee': 'final',
}

COMMITTEES_WITHOUT_DOSSIER_IDS = (
    'AGRI',
    'ENVI',
)

PAREN_LINE_ENDING_RE = re.compile('\(([^)]+)\)\W*$')
NUMBERED_LIST_RE = re.compile('^(\d+\.)+\W*')
DASH_RE = re.compile('\s*[\-–]\s*')


def scrape(committee, url, **kwargs):
    committee = committee.upper()
    try:
        pdf_doc = fetch_raw(url, binary=True)
    except:
        log(1, f'Failed to download pdf from {url} ({committee})')
        return
    res = []
    url_hash = sha256(url.encode('utf-8')).hexdigest()
    with NamedTemporaryFile() as tmp:
        tmp.write(pdf_doc)

        with pdfplumber.open(tmp.name) as pdf:
            try:
                pdfdata = extract_pdf(pdf, committee)
            except Exception as e:
                log(1, f'Failed to extract data from pdf {url} ({committee})')
                print(e)
                return
            if kwargs.get('json_dump'):
                kwargs['committee'] = committee
                kwargs['url'] = url
                for i, data in enumerate(pdfdata):
                    if not type(data) == list:
                        continue
                    try:
                        tables = [x.extract() for x in data]
                        pdfdata[i] = parse_table(tables, url)
                    except:
                        log(1, f'Failed to extract tables from {url} ({committee})')
                        return

                kwargs['pdfdata'] = pdfdata
                try:
                    data = dumps(kwargs)
                except:
                    log(1, f'Failed to JSON serialize pdfdata from {url} ({committee})')
                    return
                with open(f'comvotes_jsons/{committee}_{url_hash}.json', 'w') as outfile:
                    outfile.write(data)
                return

    voteno = 0
    for i, data in enumerate(pdfdata):
        if not type(data) == list:
            continue
        voteno += 1
        tables = [x.extract() for x in data]

        vote = {
            'committee': committee,
            'url': url,
            'id': f'{url_hash}-{voteno}'
        }

        if len(tables) == 1 and committee == 'AGRI':
            pdfdata[i+1] = '\n'.join(' '.join(x for x in t if x) for t in tables[0]) + pdfdata[i+1]
            continue

        try:
            vote['votes'] = parse_table(tables, url)
        except:
            raise(Exception(f'Failed to parse vote table in {url}'))

        text = pdfdata[i-1]

        try:
            vote_details = get_vote_details(committee, text)
        except:
            raise(Exception(f'Failed to parse vote details in {url}'))

        # means that this is part of multiple votes about the same subject
        # we need the additional data from the previous vote
        if len(vote_details) == 1 and 'type' in vote_details and len(res):
            if 'reference' in res[-1]:
                vote_details['reference'] = res[-1]['reference']
            if 'rapporteur' in res[-1]:
                vote_details['rapporteur'] = res[-1]['rapporteur']
            if 'amendments' in res[-1]:
                vote_details['amendments'] = res[-1]['amendments']

        vote.update(**vote_details)

        if 'rapporteur' in vote:
            try:
                fix_rapporteur_data(vote)
            except Exception as e:
                log(1, f'{e} ({url})')
        else:
            log(2, f'Unable to identify rapporteur in {url}')


        if 'reference' in vote and vote['reference']:
            if committee not in COMMITTEES_WITHOUT_DOSSIER_IDS:
                d = db.dossier(vote['reference'])
                if not d:
                    if vote['reference'] in DOSSIER_ID_TYPOS:
                        vote['reference'] = DOSSIER_ID_TYPOS[vote['reference']]
                    else:
                        raise(Exception('Invalid dossier ID "{0}" in {1}. If it is only a typo add it to DOSSIER_ID_TYPOS.'.format(vote["reference"], url)))
            agendas = db.get('comagenda_by_committee_dossier_voted', committee + vote['reference'])
            if not agendas:
                log(2, f'Unable to find agendas for {vote["reference"]} in {url}')
            else:
                for item in agendas[-1]['items']:
                    if item.get('RCV') and item.get('docref') == vote['reference']:
                        vote['time'] = item['start']
            if not 'time' in vote:
                log(2, f'Unable to find date for {vote["reference"]} in {url}')
        else:
            log(2, f'Unable to identify dossier ID for vote {voteno} in {url}')

        if 'type' not in vote or not vote['type'] or vote['type'].lower() not in VOTE_TYPE_MAP:
            if not vote.get('amendments'):
                log(2, f'Unable to identify vote type "{vote["type"]}" in {url}')
        else:
            vote['type'] = VOTE_TYPE_MAP[vote['type'].lower()]

        process(
            vote,
            vote['id'],
            db.com_vote,
            'ep_com_votes',
            vote['id'],
            nodiff=True,
        )
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


def parse_table(tables, url):
    tables = repair_tables(tables)
    if len(tables) == 4:
        return parse_correction_table(tables, url)
    if len(tables) == 3:
        return parse_simple_table(tables, ['for', 'against', 'abstain'], url)
    if len(tables) == 2:
        return parse_simple_table(tables, ['for', 'against'], url)
    raise(Exception('Unexpected table count: {0}'.format(len(tables))))


def parse_simple_table(tables, headers, url):
    results = {
        'for': {'total': 0, 'groups': {}},
        'against': {'total': 0, 'groups': {}},
        'abstain': {'total': 0, 'groups': {}}
    }
    for k, table in zip(headers, tables):
        results[k] = parse_table_section(table, url)
    return results


def parse_correction_table(tables, url):
    results = parse_simple_table(tables[:3], ['for', 'against', 'abstain'])
    results['corrections'] = parse_table_section(tables[3], corrections=True)
    # correct votes by corrections:
    #for vheader, cmepids in corrections['groups'].items():
    #    for cmepid in cmepids:
    #        group_name = ''
    #        for votes in results.values():
    #            for gname, gmepids in votes['groups'].items():
    #                if cmepid in gmepids:
    #                    gmepids.remove(cmepid)
    #                    group_name = gname
    #                    break
    #        res = results[vote_val_map[vheader]]
    #        if group_name in res:
    #            res[group_name].append(cmepid)
    #        else:
    #            res[group_name] = [cmepid]
    return results


def repair_tables(tables, table_count=3):
    fixed_tables = []
    for table in tables:
        while table and not any(table[0]):
            table.pop(0)
        if not table:
            continue
        if not any(x in table[0] for x in ['+', '-', '0']) and 'correction' not in ' '.join(filter(None, table[0])).lower():
            if not fixed_tables:
                raise Exception('Cannot repair table - missing header')
            fixed_tables[-1].extend(table)
        else:
            fixed_tables.append(table)
    return fixed_tables


def parse_table_section(table, corrections=False, url=''):
    header_idx = 0
    ret = {'total': 0, 'groups': {}}
    group = ''
    members = ''
    while len([x for x in table[header_idx] if x]) == 0:
        header_idx += 1

    if not corrections:
        h_parts = list(filter(None, table[header_idx]))
        if len(h_parts) > 1:
            ret['total'] = int(h_parts[0])
        else:
            header_idx += 1
            ret['total'] = int(list(filter(None, table[header_idx]))[0])

    for row in table[(header_idx+1):]:
        if not any(row):
            continue
        if len(row) == 2:
            if(row[0]):
                group = resolve_group_name(row[0])
            if group:
                ret['groups'][group] = meps_by_name(row[1].replace('\n', ' '), group)
        else:
            row_split_idx = 4
            if len(row) == 4:
                if row[0]:
                    row_split_idx = 1
                else:
                    row_split_idx = 2
            if len(row) == 6:
                row_split_idx = 3
            row1 = ''.join(filter(None, set(row[:row_split_idx])))
            if row1:
                if members.strip() and group:
                    ret['groups'][group] = meps_by_name(members, group)
                if corrections:
                    group = row1
                else:
                    group = resolve_group_name(row1)
                members = ''
            members += ' ' + ' '.join(filter(None, set(row[row_split_idx:])))

    if members.strip() and group:
        ret['groups'][group] = meps_by_name(members, group)

    mepcount = len(list(x for y in ret['groups'].keys() for x in ret['groups'][y]))

    if not corrections:
        if (ret['total'] == 0 and mepcount != 0) or (ret['total'] != 0 and mepcount == 0):
            msg = f"Vote mep count mismatch: total {ret['total']}, count {mepcount} in {url}"
            log(1, msg)
            raise(Exception(msg))

        if ret['total'] != mepcount:
            log(2, f"Vote mep count mismatch: total {ret['total']}, count {mepcount} in {url}")

    return ret


def meps_by_name(mep_names, group):
    # TODO collect dates as well for better identification (nice to have)
    return [db.mepid_by_name(x, group=group) for x in map(str.strip, mep_names.split(','))]


def fix_rapporteur_data(vote):
    if 'group' in vote['rapporteur']:
        vote['rapporteur']['group'] = resolve_group_name(vote['rapporteur']['group'])
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
    return rname.strip(), rgroup.strip() if rgroup else ''


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
    parts = [x.replace('\n', ' ') for x in text.split('\n\n') if x.strip()]

    if 'ROLL CALL' in parts[-1]:
        vtype = parts[-1]
        parts.pop()
    else:
        vtype = parts[-3].split(':')[0]

    rname, rgroup = parse_rapporteur_with_group(parts[-1], 'Rapporteur: ')

    ref = ''
    refs = DOSSIERID_RE.findall(parts[-2].strip())
    if refs:
        ref = refs[-1]

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
    chunks = list(x.strip() for x in filter(None, text.split('\n\n')))
    if len(chunks) == 1:
        return {'type': ' '.join(chunks[0].split()[1:])}

    if chunks[-1].count('\n') > 0:
        last_newline = chunks[-1].rfind('\n')
        chunks = [chunks[-1][:last_newline].replace('\n', ' ').strip(), chunks[0][:last_newline].strip()]
    else:
        chunks = [x.replace('\n', ' ') for x in chunks]

    vote_type = ' '.join(chunks[-1].split()[1:])

    title_idx = -2
    amendments = False

    if 'amendments' in chunks[-2]:
        amendments = True

    if all(x.isupper() for x in vote_type if x.isalpha()) or 'amendments' in chunks[-2]:
        title_idx = -3
    title = chunks[title_idx]

    if len(title.split()) < 4:
        if len(chunks) > -1*title_idx:
            title += chunks[title_idx-1]
        else:
            return {'type': ' '.join(chunks[title_idx].split()[1:])}

    title_parts = DASH_RE.split(title)

    if len(title_parts) == 3:
        dossier_title = title_parts[0]
        rapporteur_name = title_parts[1]
        dossier_id = title_parts[2]
    else:
        dossier_title = '-'.join(title_parts[0:len(title_parts)-3])
        try:
            rapporteur_name = title_parts[-2]
        except:
            rapporteur_name = ''
        dossier_id = title_parts[-1]

    if not db.dossier(dossier_id):
        dossier_id, rapporteur_name = rapporteur_name, dossier_id
        if not db.dossier(dossier_id):
            return {'type': vote_type}

    ret = {
        'reference': dossier_id,
        'rapporteur': {
            'name': rapporteur_name,
        },
        'type': vote_type,
    }

    if not ret['rapporteur']['name']:
        del(ret['rapporteur'])

    if amendments:
        ret['amendments'] = True

    return ret


def parse_deve_details(text):
    chunks = list(x.replace('\n', ' ') for x in filter(None, text.split('\n\n')))
    rname, rgroup = parse_rapporteur_with_group(chunks[-2], 'Rapporteur: ')
    dossier_id = DOSSIERID_RE.findall(chunks[-3])[-1]
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
    try:
        title_split = [x.strip() for x in chunks[-3].split('–')]
        rname, rgroup = parse_rapporteur_with_group(title_split[2], 'rapporteur: ')
    except:
        return {'type': ' '.join(chunks[-1].split()[1:]), 'amendments': True}
    ret = {
        'reference': DOSSIERID_RE.findall(title_split[1])[-1],
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
        'type': chunks[-1].strip(),
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
        'reference': DOSSIERID_RE.findall(title_split[1])[-1],
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
    try:
        title = chunks[-2]
        title_split = [x.strip() for x in title.split('–')]
        rname, rgroup = parse_rapporteur_with_group(title_split[-1], '')
    except:
        return {'type': vtype}
    ret = {
        'reference': title_split[-2],
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
    dossier_id = DOSSIERID_RE.findall(title_split[-2])[-1]
    ret = {
        'reference': dossier_id,
        'rapporteur': {
            'name': rname,
            'group': rgroup,
        },
        'type': vtype,
    }
    return ret


def parse_envi_details(text):
    lines = text.splitlines()
    vtype = NUMBERED_LIST_RE.sub( '', lines[-1].replace('', '')).strip()
    line_idx = 2
    while not NUMBERED_LIST_RE.match(lines[-line_idx]) and line_idx < len(lines):
        line_idx += 1
    title_line = NUMBERED_LIST_RE.sub( '', ' '.join(lines[-line_idx:-1]), 1).strip()
    if 'Rapporteur:' in title_line or 'Co-rapporteurs' in title_line:
        title = ' '.join(DASH_RE.split(title_line)[:-1])
    else:
        rapp = PAREN_LINE_ENDING_RE.search(title_line)
        if rapp:
            title = title_line[:rapp.start()].strip()
        else:
            title = title_line
    ret = {
        'reference': '',
        'title': title,
        'type': vtype,
    }
    return ret


def parse_agri_details(text):
    chunks = list(x.replace('\n', ' ').strip() for x in filter(None, text.split('\n\n')))
    vtype = DASH_RE.split(chunks.pop())[-1]
    title = chunks[1].split('Rapporteur')[0].strip()
    dossier_ids = DOSSIERID_RE.findall(title)
    if dossier_ids:
        ref = dossier_ids[-1]
        title = title.replace(dossier_ids[-1], '').strip()
    else:
        ref = ''
    ret = {
        'reference': ref,
        'title': title,
        'type': vtype,
    }
    return ret


def cut_inta_footer(text):
    text = '\n'.join(text.splitlines()[:-3]).strip()
    return text


def cut_imco_footer(text):
    return '\n'.join(text.splitlines()[:-3]).strip()


def cut_regi_footer(text):
    return '\n'.join(text.splitlines()[:-1]).strip()

def cut_pech_footer(text):
    if text.split('\n')[-1].strip().isnumeric():
        return '\n'.join(text.splitlines()[:-1]).strip()
    return text


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
    'ENVI': parse_envi_details,
    'AGRI': parse_agri_details,
}

HEADER_CUTTERS = {
}

FOOTER_CUTTERS = {
    'IMCO': cut_imco_footer,
    'INTA': cut_inta_footer,
    'REGI': cut_regi_footer,
    'PECH': cut_pech_footer,
}

if __name__ == "__main__":
    from utils.utils import jdump
    from sys import argv

    if len(argv) == 3:
        print(jdump(scrape(argv[1].upper(), argv[2])))
    else:
        print("Test scraper with the following arguments: [COMMITTEE] [PDFURL]")
