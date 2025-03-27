#!/usr/bin/env python3
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

# (C) 2009-2011,2018-2019 by Stefan Marsiske, <parltrack@ctrlc.hu>

import notification_model as notif
import unicodedata, requests, re

from config import ROOT_URL
from datetime import datetime, UTC
from db import db
from itertools import zip_longest
from lxml.etree import tostring, _ElementUnicodeResult
from lxml.html.soupparser import fromstring
from operator import itemgetter
from urllib.parse import urljoin
from utils.log import log
from utils.mappings import GROUP_MAP, COMMITTEE_MAP
from utils.notif_mail import send_html_mail
from utils.process import process
from utils.utils import fetch, fetch_raw, junws, unws, create_search_regex, dossier_search, textdiff

BASE_URL = 'https://oeil.secure.europarl.europa.eu'

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'table': 'ep_dossiers',
    'abort_on_error': True,
}

def scrape(url, save=True, **kwargs):
    log(4, 'scrape %s' % url)
    try:
        root=fetch(url)
    except requests.exceptions.HTTPError:
        log(1,"this url returns a hard 404: %s" % url)
        return
    if root.xpath('//span[@class="ep_name" and contains(text(),"This procedure or document does not exist!")]') != []:
        log(1,"this url returns a soft 404: %s" % url)
        return

    #tmp = root.xpath('//div[@id="procedure-file-header"]//div[@class="ep_title"]')
    #if len(tmp)!=2: raise ValueError(f"dossier proc header has not two components")
    tmp = root.xpath('//h2[@class="erpl_title-h1 mb-3"]')
    if len(tmp)!=1: raise ValueError(f"dossier proc header has not one component")
    ref = junws(tmp[0])

    dossier = {
        'meta': {'source': url,
                 'updated': datetime.now(UTC) },
        'procedure': {
            'reference': ref,
            #'title': junws(tmp[1])
            'title': junws(root.xpath('//h2[@class="erpl_title-h2 mb-3"]')[0])
        },
        'committees': scrape_ep_key_players(root),
        'council': scrape_council_players(root),
        'commission': scrape_commission_players(root),
        #'otherinst': scrape_other_players(root), # bears no useful info
        'forecasts': scrape_forecasts(root),
        #'links': scrape_extlinks(root), # todo find example on which to test this
    }
    dossier['procedure'].update(scrape_basic(root, ref))
    dossier['procedure'].update(scrape_technical(root))
    events, edocs = scrape_events(root)
    dossier['events']=events
    docs = scrape_docs(root, edocs)
    dossier['docs'] = docs

    final=scrape_finalact(root)
    if final and final.get('docs'):
        dossier[u'procedure'][u'final']=final.get('docs',[{}])[0]
        for item in dossier['events']:
            if item.get('type')==u'Final act published in Official Journal':
                if final.get('summary'):
                    item[u'summary']=final['summary']
                if  len(final.get('docs'))>1:
                    if not 'docs' in item:
                        item[u'docs']=final['docs']
                    else:
                        item[u'docs'].extend(final['docs'])
                break

    return process(
        dossier,
        ref,
        db.dossier,
        'ep_dossiers',
        ref,
        nopreserve=['other', 'forecasts', 'activities'],
        nostore=not save,
        onchanged=onchanged,
    )

def scrape_basic(root, ref):
    res={}
    for para in root.xpath('//h2[@class="erpl_title-h2 mb-2"][text()="Basic information"]/../../..//p[@class="font-weight-bold mb-1"]'):
        if not para.xpath('./text()'): continue
        title = junws(para)
        if title in [ref, 'Status']: continue
        if title == 'Subject': title = 'subject'
        if title == 'Geographical area': title = 'geographical_area'
        if title not in ['Legislative priorities', 'Notes', 'geographical_area', 'subject']:
            log(3,"basic information of %s has unknown section: '%s'" % (ref, title))
        # this is a fucking mess, there's two columns, in the left one
        # stuff is between <strong> separated by <br /> in the right
        # one <p><strong></p><p>...</p> until the next <p><strong></p>
        #tmp = para.xpath('./following-sibling::p[preceding-sibling::p[@class="font-weight-bold mb-1"][1]]')
        tmp = para.xpath('./following-sibling::p[1]')
        if not tmp:
            log(1,'no content found for section "%s" of %s' % (title, ref))
            continue
        for node in tmp[0].xpath("./node()"):
            if isinstance(node, _ElementUnicodeResult):
                line = unws(node)
                if line:
                    if not title in res: res[title]=[]
                    res[title].append(line)
                continue
            if len(node.xpath('.//text()[not(ancestor::a) and string-length(normalize-space()) > 0]'))>0:
                if not title in res: res[title]=[]
                res[title].append(toText(node))
                continue
            for link in node.xpath('./descendant-or-self::a'):
                if not title in res: res[title]=[]
                res[title].append(toText(link))
    subjects = {}
    for s in res.get('subject',[]):
        id, title = s.split(' ', 1)
        subjects[id]=title
    else:
        res['subject']=subjects
    return res

"""
scrapes the EP section of the key players
"""
def scrape_ep_key_players(root):
    #dbgfrag(root.xpath('//div[@id="keyplayers_sectionPE-content"]')[0])
    #div[@id="keyplayers_sectionPE-content"]
    players = []
    type = None
    for table in root.xpath('//div[@id="erpl_accordion-committee"]//table'):
        #cells = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]')
        cells = table.xpath('./thead/tr/th')
        if len(cells) != 3:
            if [junws(x) for x in cells] == ['Pending final decision on the referral']:
               continue
            log(1,'EP key players table has not 3 columns: %s' % repr([junws(x) for x in cells]))
            raise ValueError("bad dossier html")
        #if 'ep-table-heading-row' in row.get('class'):
        tmp = [junws(x) for x in cells]
        if tmp == ['Committee responsible', 'Rapporteur', 'Appointed']:
            type="Responsible Committee"
        elif tmp in (['Joint Committee Responsible', 'Rapporteur', 'Appointed'], ['Joint committee responsible', 'Rapporteur', 'Appointed']):
            type="Joint Responsible Committee"
        elif tmp == ['Committee for opinion', 'Rapporteur for opinion', 'Appointed']:
            type="Committee Opinion"
        elif tmp == ['Committee for opinion on the legal basis', 'Rapporteur for opinion', 'Appointed']:
            type="Committee Legal Basis Opinion"
        elif tmp ==['Former committee responsible', 'Former rapporteur','Appointed']:
            type="Former Responsible Committee"
        elif tmp ==['Former Joint Committee Responsible', 'Former rapporteur', 'Appointed']:
            type='Former Joint Committee Responsible'
        elif tmp == ['Former committee for opinion', 'Former rapporteur for opinion', 'Appointed']:
            type="Former Committee Opinion"
        elif tmp == ['Former committee for opinion on the legal basis', 'Rapporteur for opinion', 'Appointed']:
            type="Former Committee Legal Basis Opinion"
        elif tmp == ['Committee for opinion on the recast technique', 'Rapporteur for opinion', 'Appointed']:
            type="Committee Recast Technique Opinion"
        elif tmp == ['Former committee for opinion on the recast technique', 'Rapporteur for opinion', 'Appointed']:
            type="Fromer Committee Recast Technique Opinion"
        elif tmp == ['Committee for budgetary assessment', 'Rapporteur for budgetary assessment', 'Appointed']:
            type="Committee for budgetary assessment"
        else:
            log(1, "unknown committee header in EP key players %s" % repr(tmp))
            raise ValueError("bad html in EP key players, committee header")

        if not type:
            log(1,"error no table header for EP key players found")
            raise ValueError("bad html in key players EP section, table header")

        for row in table.xpath('./tbody/tr'):
            player = {"type": type,
                      'body':'EP'}
            cells = row.xpath('./th|./td')
            # first cell contains committee
            tmp = cells[0].xpath('.//a/@title')
            associated = False
            if len(tmp) == 0 and type not in ("Joint Responsible Committee", 'Former Joint Committee Responsible'):
                tmp = junws(cells[0])
                if ' ' in tmp:
                    com_abbr, com_name = tmp.split(" ",1)
                    if com_abbr == 'CJ29' and com_name.startswith('Joint committee procedure'): 
                        player['type']="Joint Responsible Committee"
                        _, coms = com_name.split('-')
                        com_name = []
                        com_abbr = []
                        for c in coms.split(" and "):
                            c=unws(c)
                            if c not in COMMITTEE_MAP:
                                log(1, 'unknown committee in EP Joint Committee listing key players: "%s"' % c)
                                raise ValueError("bad html in key players EP section, joint committee name")
                            com_name.append(COMMITTEE_MAP[c])
                            com_abbr.append(c)
                    else:
                        com_name = unicodedata.normalize('NFKD', com_name).encode('ascii','ignore').decode('utf8')
                        if com_name.endswith(" (Associated committee)"):
                            associated=True
                            com_name=com_name[:-23]
                        if not (com_abbr in COMMITTEE_MAP and com_name in COMMITTEE_MAP):
                            log(1, 'unknown linkless committee in EP key players: "%s" -> u"%s": u"%s"' % (tmp, com_name, com_abbr))
                            raise ValueError("bad html in key players EP section, linkless committee name")
                    player['associated']=associated
                else: # continuation of previous row
                    player = players[-1]
            elif len(tmp) == 1:
                tmp=unws(tmp[0])
                tmp = unicodedata.normalize('NFKD', tmp).encode('ascii','ignore').decode('utf8')
                if tmp.endswith(" (Associated committee)"):
                    associated=True
                    tmp=tmp[:-23]
                if tmp not in COMMITTEE_MAP:
                    log(1, 'unknown committee in EP key players: "%s"' % tmp)
                    raise ValueError("bad html in key players EP section, committee name")
                com_name = tmp
                tmp = junws(cells[0])
                com_abbr = tmp[:4]
            elif type in ("Joint Responsible Committee", 'Former Joint Committee Responsible'):
                com_name = []
                for com_abbr in cells[0].xpath(".//span/abbr/@title"):
                    com_abbr=unws(com_abbr)
                    if com_abbr not in COMMITTEE_MAP:
                        log(1, 'unknown committee in EP Joint Committee listing key players: "%s"' % com_abbr)
                        raise ValueError("bad html in key players EP section, joint committee name")
                    com_name.append(COMMITTEE_MAP[com_abbr])
                com_abbr=[unws(a) for a in cells[0].xpath(".//span/abbr/@title")]
            else:
                log(1, 'committee has not one <a> tag: "%s"' % tmp)
                raise ValueError("bad html in key players EP section, committee href")

            player['committee_full']=com_name
            player['committee']=com_abbr
            player['associated']=associated
            if len(players) == 0 or player != players[-1]: players.append(player)

            # last cell contains date
            tmp = junws(cells[2])
            if tmp:
                dates = [datetime.strptime(x, u"%d/%m/%Y") for x in tmp.split()]
            elif "The committee decided not to give an opinion" not in junws(cells[1]):
                dates = []
                #log(1, "no date found for keyplayer appointment")
                #raise ValueError("bad html in key players EP section, appointment date")
            else:
                player['opinion'] = False

            # middle cell is rappporteur
            for i,x in enumerate(cells[1].xpath('./a[@class="rapporteur mb-25"]')):
                if not 'rapporteur' in player: player['rapporteur']=[]
                name = junws(x)
                m = re.match(r"(.*) \((.*)\)$", name)
                if not m:
                    raise ValueError(f"no group found for {name}")
                else:
                    (group, abbr) = toGroup(m.group(2))
                    name = m.group(1)
                if name.startswith('Chair on behalf of committee '):
                    name=name[29:]
                if len(dates) > i:
                    date = dates[i]
                else:
                    if len(dates):
                        date = dates[0]
                    else:
                        date = ''
                mepid = db.mepid_by_name(name, date, group)
                if not mepid:
                    log(1,'no mepid found for "%s"' % name)
                player['rapporteur'].append({'name': name,
                                             'mepref': mepid,
                                             'date': date,
                                             'group': group,
                                             'abbr': abbr})

            # check if cell[1] has also shadow rapporteurs listed
            tmp = cells[1].xpath('.//div[@id="collapseShadowRapporteur"]')
            if len(tmp)==0:
                continue
            shadow_root = tmp[0]
            # handle shadow rapporteurs
            shadows = []
            date = dates[0] if len(dates) else None
            for link in shadow_root.xpath('./div/a[@class="rapporteur mb-25"]'):
                name = junws(link)
                m = re.match(r"(.*) \((.*)\)$", name)
                if not m:
                    raise ValueError(f"no group found for {name}")
                else:
                    (group, abbr) = toGroup(m.group(2))
                    name = m.group(1)
                if name.startswith('Chair on behalf of committee '): name=name[29:]
                mepid = db.mepid_by_name(name, date, group) # FIXME: we use appointed[0] in hope that all meps fit that date.
                if not mepid:
                    log(1,'no mepid found for "%s"' % name)
                shadows.append({'name': name,
                                'mepref': mepid,
                                'group': group,
                                'abbr': abbr})
            player['shadows']=shadows

    return players


def scrape_council_players(root):
    players = []
    first = True
    
    for row in root.xpath('//h2[text()="Key players"]/../../..//li[@class="erpl_accordion-item"]/button/span[text()="Council of the European Union"]/../..//table/*[self::thead or self::tbody]/tr'):
        cells = row.xpath('./*[self::th or self::td]')
        if len(cells) != 3:
            log(1,"Council key players table has not 3 columns")
            raise ValueError("bad dossier html, Council Key Players")
        if first:
            first = False
            continue

        player = {'body': u'CSL', 'type': u'Council Meeting'}
        players.append(player)

        # first cell contains council configuration
        tmp = cells[0].xpath('.//a/span/text()')
        if len(tmp)!=1:
            tmp = junws(cells[0])
            if tmp == '':
                log(1, "no council config specified")
                raise ValueError("bad html in key players council section, config missing")
        else:
            tmp = unws(tmp[0])
        player['council']=tmp

        # middle cell is meeting
        tmp = cells[1].xpath('.//a')
        if len(tmp)!=1:
            #tmp = cells[1].xpath('./div/span[@class="ep_name"]')
            if len(tmp)!=1:
                log(1, "council meeting has not one <a> tag")
                raise ValueError("bad html in key players Council section, council config href")
        link = tmp[0]
        player['meeting_id']=unws(link.xpath('./span/text()')[0])
        player['url']=str(link.get('href'))

        # last cell contains date
        tmp = junws(cells[2])
        if tmp: player['date'] = datetime.strptime(tmp, u"%d/%m/%Y")

    return players


def scrape_commission_players(root):
    players = []
    first = True
    for row in root.xpath('//h2[text()="Key players"]/../../..//li[@class="erpl_accordion-item"]/button/span[text()="European Commission"]/../..//table/*[self::thead or self::tbody]/tr'):
        cells = row.xpath('./*[self::th or self::td]')
        if len(cells) != 2:
            log(1,"Commission key players table has not 2 columns")
            raise ValueError("bad dossier html, Commission Key Players")
        if first: # skip table header - quicker than checking for class attribute
            first = False
            continue

        player = {'body': 'EC'}
        players.append(player)

        # first cell contains Commission
        tmp = cells[0].xpath('.//a')
        if len(tmp)!=1:
            tmp = junws(cells[0])
            if tmp == '':
                log(1, "no commission specified")
                raise ValueError("bad html in key players Commission section, commission missing")
        else:
            tmp = unws(tmp[0].xpath('./span/text()')[0])
        player['dg']=tmp

        # middle cell is commissioner
        tmp = cells[1].xpath('./span')
        if len(tmp)!=1:
            log(1, "commissioner has not one member")
            raise ValueError("bad html in key players Commission section, commissioner name")
        tmp=tmp[0]
        player['commissioner']=junws(tmp)

    return players

#def scrape_other_players(root):
#    res = []
#    for other in root.xpath('//li[@id="keyplayers_section4"]'):
#        titles = other.xpath('.//div[@id="keyplayers_section4-title"]')
#        if len(titles)!=1:
#            log(1, "key player other section has not 1 title")
#            raise ValueError("bad dossier html, other key player title")
#        title = junws(titles[0])
#        for content in other.xpath('.//div[@id="keyplayers_section4-content"]'):
#            if len(content)!=1:
#                log(1,'not 1 section found: %d' % len(content))
#                raise ValueError("bad dossier html, other key player content")
#            tmp=junws(content[0])
#            if tmp!=title:
#                log(1,'other key player is not expected string: "%s" -> "%s"' % (title,tmp))
#                raise ValueError("bad html dossier, other key players section")
#            res.append({"name": title})
#    return res

def scrape_events(root):
    events = []
    docs = []
    for row in root.xpath('//h2[@class="erpl_title-h2 mb-2"][text()="Key events"]/../../../div[@class="table-responsive"]/table/tbody/tr'):
        cells = row.xpath('.//td|.//th')
        if len(cells) != 4:
            log(1,"Events table has not 4 columns")
            raise ValueError("bad dossier html, events")
        event = {}
        events.append(event)
        # 1st cell contains date
        tmp = junws(cells[0])
        if tmp:
            event['date']=datetime.strptime(tmp, u"%d/%m/%Y")
        else:
            log(1,"Event has no date")
            raise ValueError("bad dossier html, event missing date")
        # event
        event['type']=junws(cells[1])
        # map to body
        body = stage2inst.get(event['type'])
        if not body:
            if event['type']!="Final act published in Official Journal":
                log(2, 'no body mapping found for "%s"' % event['type'])
        else:
            event['body']=body
        # docs
        for link in cells[2].xpath('.//a'):
            if not 'docs' in event: event['docs']=[]
            url=str(link.get('href'))
            if not url.startswith('http'):
                url = urljoin(BASE_URL,url)
            title = junws(link)
            if title == '':
                title = link.get('title')
            if not title:
                title = event['type']
            if title == '':
                log(1, 'no title for link in event doc' % tostring(links[1]))
                raise ValueError("bad dossier html, event unnamed link")
            event['docs'].append({'url': url, 'title': title})
        for alt in cells[2].xpath('.//span/text()[not(ancestor::a) and string-length(normalize-space()) > 0]'):
            if not 'docs' in event: event['docs']=[]
            event['docs'].append({"title": unws(alt)})
        # summary

        button = cells[3].xpath("./a[button]")
        if len(button)==0:
            if 'docs' in event:
                docs.append({'date': event['date'], 'docs': event['docs']})
            continue
        if len(button)!=1:
            log(1,"more than 1 summary button found")
            raise ValueError("bad dossier html, more than 1 summary button")

        url = button[0].get('href')
        if not url.startswith('http'):
            url = urljoin(BASE_URL,url)
        # fetch summary
        event['summary']=fetchSummary(url)
        if 'docs' in event:
            docs.append({'date': event['date'], 'docs': event['docs'], 'summary': event['summary']})

    return events, docs

def scrape_technical(root):
    keymap = {'Procedure reference': 'reference',
              'Procedure type': 'type',
              'Nature of procedure': 'subtype',
              'Legislative instrument': 'instrument',
              'Legal basis': 'legal_basis',
              'Mandatory consultation of other institutions': 'other_consulted_institutions',
              'Stage reached in procedure': 'stage_reached',
              'Committee dossier': 'dossier_of_the_committee'}
    res = {}
    key = '' 
    for row in root.xpath('//h2[@class="erpl_title-h2 mb-2"][text()="Technical information"]/../../../div[@class="table-responsive"]/table/tbody/tr'):
        th = row.xpath('.//th')
        if len(th) != 1:
            log(1,"Technical info table has not 1 th columns")
            raise ValueError("bad dossier html, tech info")
        td = row.xpath('.//td')
        if len(td) != 1:
            log(1,"Technical info table has not 1 td columns")
            raise ValueError("bad dossier html, tech info")
        # 1st cell contains name
        tmp = junws(th[0])
        if tmp:
            key = keymap.get(tmp,tmp)
        else:
            if key=='':
                log(1,"empty technical field, and no previous key")
                raise ValueError("bad dossier html, tech info")
            if not isinstance(res[key], list): res[key]=[res[key]]
        for node in td[0].xpath('.//node()'):
            if isinstance(node, _ElementUnicodeResult):
                line = unws(node)
                if line:
                    if key in res:
                        if isinstance(res[key], list):
                            res[key].append(line)
                        else:
                            res[key]=[res[key], line]
                    else:
                        res[key]=line
    return res

def scrape_docs(root, edocs):
    docs = []

    for section in root.xpath('//div[@id="erplAccordionDocGateway"]/ul/li'):
        tmp = section.xpath('./button/span[@class="t-x"]/text()')
        if len(tmp)!=1:
            log(1, f"document section button has not exactly one span: {tmp}")
            continue
        institution = unws(tmp[0])

        for row in section.xpath('.//div[@class="table-responsive"]/table/tbody/tr'):
            cells = row.xpath('.//td|.//th')
            if institution in ('National parliaments', 'European Parliament', 'Other institutions and bodies'):
                offset = 1
                if len(cells) != 5:
                    log(1,f"Docs table has not required amount of columns columns for inst '{institution}': {len(cells)}")
                    raise ValueError("bad dossier html, docs")
            else:
                offset = 0
                if len(cells) != 4:
                    log(1,f"Docs table has not required amount of columns columns for inst '{institution}': {len(cells)}")
                    raise ValueError("bad dossier html, docs")

            doc = {}
            # date is cell 3+offset
            tmp = junws(cells[2+offset])
            if tmp:
                doc['date']=datetime.strptime(tmp, u"%d/%m/%Y")

            # url is cell 2+offset
            for link in cells[1+offset].xpath('.//a'):
                if not 'docs' in doc: doc['docs']=[]
                url=str(link.get('href'))
                title = junws(link)
                if title == '':
                    title = link.get('title')
                if title == '':
                    log(1, 'no title for link in doc' % tostring(links[1]))
                    raise ValueError("bad dossier html, event unnamed link")
                doc['docs'].append({'url': url, 'title': title})
            for alt in cells[1+offset].xpath('.//span/text()[not(ancestor::a) and string-length(normalize-space()) > 0]'):
                if not 'docs' in doc: doc['docs']=[]
                doc['docs'].append({"title": unws(alt)})

            tdoc = {}
            ######
            # title is cell 1
            tdoc['type']=junws(cells[0])
            tdoc['body']=institution

            # 2. code
            if institution in ('National parliaments', 'European Parliament', 'Other institutions and bodies'):
                tmp = junws(cells[1])
                if tmp:
                    if tdoc.get('body') in ('National parliaments', 'Other institutions and bodies'):
                        tdoc['body']=tmp
                    elif tmp in COMMITTEE_MAP:
                        doc['committee'] = tmp
                    else:
                        log(2, 'unexpected value in doc/code cell "%s"' % tmp)
                        raise ValueError("bad html in doc code")

            # summary is field 4+offset
            node = cells[3+offset].xpath("./a[button]")
            if len(node)==0:
                doc.update(tdoc)
                docs.append(doc)
                continue
            if len(node)>1:
                log(1,"more than 1 summary button found")
                raise ValueError("bad dossier html, more than 1 summary button")
            url = node[0].get('href')
            if not url.startswith('http'):
                url = urljoin(BASE_URL,url)
            # fetch summary
            doc['summary']=fetchSummary(url)
            if doc in edocs:
                log(4,'skipping doc, already seen in events: "%s"' % ','.join(x['title'] for x in doc['docs']))
                continue
            doc.update(tdoc)
            docs.append(doc)
    return docs


def scrape_extlinks(root):
    res = {}
    for row in root.xpath('//div[@id="external_links-data"]//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-row ")]'):
        cells = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]')
        if len(cells) != 2:
            if len(cells) == 3:
                if junws(cells[2])!='':
                    log(3,'extlinks has 3 column with value: %s' % junws(cells[2])) 
            else: 
                log(1,"External links info table has not 2 or 3 columns")
                raise ValueError("bad dossier html, ext links")
        # 1st cell contains name
        title = junws(cells[0])
        if title:
            tmp = cells[1].xpath(".//a")
            if len(tmp)!=1:
                log(1, "ext links has not 1 link")
                raise ValueError("bad dossier html, ext links")
            res[title] = {'title': junws(tmp[0]),
                          'url': str(tmp[0].get('href'))}
        else:
            log(1,"empty ext link title")
            raise ValueError("bad dossier html, ext links")
    return res


def scrape_finalact(root):
    res = {}
    for row in root.xpath('//h2[@class="erpl_title-h2 mb-2"][text()="Final act"]/../../following-sibling::div/ul/li'):
        # try links
        for link in row.xpath(".//a[not(button)]"):
            if not 'docs' in res: res['docs']=[]
            url = str(link.get('href'))
            if not url.startswith('http'):
                url = urljoin(BASE_URL,url)
            res['docs'].append({'title': junws(link),
                                'url': url})
        button = row.xpath("./a[button]")
        if len(button)==1:
            tmp = button[0].get('href')
            # fetch summary
            res['summary']=fetchSummary(tmp)
        elif len(button)!=0:
            log(1,"more than 1 summary button found")
            raise ValueError("bad dossier html, final act")
    return res

def scrape_forecasts(root):
    res = []
    for row in root.xpath('//h2[@class="erpl_title-h2 mb-2"][text()="Forecasts"]/../../../div[@class="table-responsive"]/table/tbody/tr'):
        cells = row.xpath('.//td|.//th')
        if len(cells) != 2:
            log(1,"Forecasts info table has not 2 columns")
            raise ValueError("bad dossier html, forecasts")
        # 1st cell contains date
        forecast={}
        res.append(forecast)

        date = junws(cells[0])
        if not date:
            log(1,"empty date in forecasts")
            raise ValueError("bad dossier html, forecasts")
        forecast['date']=datetime.strptime(date, u"%d/%m/%Y")

        title = junws(cells[1])
        if not title:
            log(1, "forecast has no title")
            raise ValueError("bad dossier html, forecasts")
        forecast['title']=title
    return res


MAP_GROUP = {v: k for k, v in GROUP_MAP.items()}
def toGroup(txt):
    txt = unws(txt)
    if txt in GROUP_MAP:
        return (GROUP_MAP[txt], txt)
    if txt.startswith("ALDE- "):
        return ("ALDE", 'Alliance of Liberals and Democrats for Europe')
    if txt == "Renew Europe group": # goddamn unique slowfakes - if they get an abbrev i hope it won't be ALDE
        return ("Renew", "Renew Europe group")
    if txt in MAP_GROUP:
        return MAP_GROUP[txt], txt
    try:
        _, group = txt.split(' - ', 1)
    except:
        raise ValueError(repr(txt))
    group=unws(group)
    if group in MAP_GROUP:
        return MAP_GROUP[group], group
    if group in GROUP_MAP:
        return GROUP_MAP[group], group
    log(1, "no group mapping found for group %s | %s" % (repr(txt), repr(group)))
    return "Unknown Group", "???"

def toText(node):
    if node is None: return ''
    for br in node.xpath(".//br"):
        br.text="\n"
    text=junws(node).replace(u"\u00A0",' ')
    links=node.xpath('./descendant-or-self::a/@href')
    if not links: return text
    if len(links)>1:
        log(1,"toText: more than one href found in node", links)
    return {u'title': text, u'url': urljoin(BASE_URL,str(links[0]))}

def fetchSummary(path):
    url = urljoin(BASE_URL,path)
    if url in fuckedSummaries:
        tmp=fetch_raw(url)
        # patch it up
        for old,new in fuckedSummaries[url]:
            tmp = tmp.replace(old,new)
        #print(repr(tmp))
        tmp = fromstring(tmp)
    else:
        try:
            tmp=fetch(url)
        except:
            tmp=fetch_raw(url)
            # patch it up
            tmp = tmp.replace('\x0c', '\n')
            #print(repr(tmp))
            try:
                tmp = fromstring(tmp)
            except:
                log(1,"failed to fetch summary url: %s" % url)
                raise ValueError("bad html in summary")
    tmp = tmp.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," erpl_product-content ")]')
    if len(tmp)!=1:
        log(1, "summary nodes len != 1")
        raise ValueError("bad html in summary: %s" % url)
    return [junws(x) for x in tmp[0].xpath('.//div/*')]

fuckedSummaries={
    "https://oeil.secure.europarl.europa.eu/oeil/popups/summary.do?id=910263&t=e&l=en": [("<m<", "&lt;m&lt;")],
    'https://oeil.secure.europarl.europa.eu/oeil/popups/summary.do?id=910263&t=d&l=en': [("<m<", "&lt;m&lt;")],
    'https://oeil.secure.europarl.europa.eu/oeil/popups/summary.do?id=1132498&t=e&l=en': [('The 2011 draft budget ', '<p>The 2011 draft budget ')],


}

################ old/obsolete stuff below #################

groupurlmap={'http://www.guengl.eu/?request_locale=en': u"GUE/NGL",
             'http://www.eppgroup.eu/home/en/default.asp?lg1=en': u"EPP",
             'http://www.alde.eu/?request_locale=en': u'ALDE',
             'http://www.greens-efa.org/cms/default/rubrik/6/6270.htm?request_locale=en': u'Verts/ALE',
             'http://www.greens-efa.eu/?request_locale=en': u'Verts/ALE',
             'http://www.efdgroup.eu/?request_locale=en': u'EFD',
             'http://www.ecrgroup.eu/?request_locale=en': u'ECR',
             'http://www.socialistsanddemocrats.eu/gpes/index.jsp?request_locale=en': u'S&D',
             'http://www.enfgroup-ep.eu/': u'ENF'}
instmap={'European Parliament': u'EP',
         'European Commission': u'EC',
         'Council of the European Union': u'CSL',
         'Council of the EU': u'CSL',
         'European Central Bank': u'ECB',
         'Committee of the Regions': u'CotR',
         'Other institutions': u'x!x',
         }
otherinst={'Economic and Social Committee': u'ESOC',
           'European Data Protecion Supervisor': u'EDPS',
           'Court of Justice of the European Communities': u'CJEC',
           'Court of Justice of the European Union': u'CJEU',
           'Court of Auditors': u'CoA',
           }
detailsheaders={ 'Committee dossier': u'dossier_of_the_committee',
                 'Legal basis': u'legal_basis',
                 'Legislative instrument': u'instrument',
                 'Procedure reference': u'reference',
                 'Procedure subtype': u'subtype',
                 'Procedure type': u'type',
                 'Stage reached in procedure': u'stage_reached',
                 }
stage2inst={ 'Debate in Council': u'CSL',
             "Parliament's amendments rejected by Council": u'CSL',
             'Decision by Council, 3rd reading': u'CSL',
             'Council position published': u'CSL',
             'Resolution/conclusions adopted by Council': u'CSL',
             'Final act signed': u'CSL',
             'Council position on draft budget published': u'CSL',
             'Draft budget approved by Council': u'CSL',
             'Council position scheduled for adoption': u'CSL',
             'Decision by Council': u'CSL',
             'Act approved by Council, 2nd reading': u'CSL',
             'Council draft budget published': u'CSL',
             'Amended budget adopted by Council': u'CSL',
             "Initial period for examining delegated act 0.8 month(s)": "CSL",
             "Initial period for examining delegated act 2.0 month(s)": "CSL",
             "Initial period for examining delegated act 1.0 month(s)": "CSL",
             "Initial period for examining delegated act extended at Council's request by 1.0 month(s)": "CSL",
             "Initial period for examining delegated act 2.0 month(s)": "CSL",
             "Initial period for examining delegated act 3.0 month(s)": "CSL",
             "Initial period for examining delegated act extended at Parliament's request by 2.0 month(s)": "EP",
             "Initial period for examining delegated act extended at Parliament's request by 3.0 month(s)": "EP",
             "Initial period for examining delegated act extended at Council's request by 3 month(s)": 'CSL',
             "Initial period for examining delegated act extended at Council's request by 1 month(s)": "CSL",
             "Council amended draft budget published": 'CSL',
             "Delegated act not objected by Council": u"CSL",
             "Delegated act objected by Council": 'CSL',

             'Final act signed by Parliament and Council': u'EP/CSL',
             'Joint text approved by Conciliation Committee co-chairs': u'EP/CSL',
             'Final decision by Conciliation Committee': u'EP/CSL',
             'Agreement not reached in budgetary conciliation': 'EP/CSL',
             'Formal meeting of Conciliation Committee': u'EP/CSL',
             'Act adopted by Council after consultation of Parliament': u'EP/CSL',
             "Act adopted by Council after Parliament's 1st reading": u'EP/CSL',
             'Start of budgetary conciliation (Parliament and Council)': u'EP/CSL',
             'Budgetary joint text published': u'EP/CSL',
             'Formal reconsultation of Parliament': u'EP/CSL',
             'Initial period for examining delegated act 1 month(s)': u'EP/CSL',
             'Initial period for examining delegated act 2 month(s)': u'EP/CSL',
             'Initial period for examining delegated act 3 month(s)': u'EP/CSL',
             "Initial period for examining delegated act extended at Council's request by 2 month(s)": u'EP/CSL',
             "Initial period for examining delegated act extended at Parliament's request by 1 month(s)": u'EP/CSL',
             "Initial period for examining delegated act extended at Parliament's request by 2 month(s)": u'EP/CSL',
             "Initial period for examining delegated act extended at Parliament's request by 3 month(s)": u'EP/CSL',

             'European Central Bank: opinion, guideline, report': u'ECB',

             'Legislative proposal published': u'EC',
             'Initial legislative proposal published': u'EC',
             'Modified legislative proposal published': u'EC',
             'Non-legislative basic document published': u'EC',
             'Non-legislative basic document': u'EC',
             'Document attached to the procedure': u'EC',
             'Non-legislative basic document': u'EC',
             'Legislative proposal': u'EC',
             'Commission draft budget published': u'EC',
             'Amended legislative proposal for reconsultation published': u'EC',
             'Commission preliminary draft budget published': u'EC',
             'Commission response to text adopted in plenary': u'EC',
             'Proposal withdrawn by Commission': u'EC',

             "Preparatory document": "EP",
             'Indicative plenary sitting date, 1st reading/single reading': 'EP',
             'Results of vote in Parliament': u'EP',
             'Debate in Parliament': u'EP',
             'Vote in plenary scheduled': u'EP',
             'Debate scheduled': u'EP',
             'Vote scheduled': u'EP',
             'Decision by committee, without report': u'EP',
             'Debate in plenary scheduled': u'EP',
             'Referral to associated committees announced in Parliament': u'EP',
             'Indicative plenary sitting date, 1st reading/single reading': u'EP',
             "Matter referred back to the committee responsible for interinstitutional negotiations": "EP",
             "Approval in committee of the text agreed at 1st reading interinstitutional negotiations": 'EP',
             "Approval in committee of the text agreed at early 2nd reading interinstitutional negotiations": 'EP',
             "Committee report tabled for plenary, reconsultation": 'EP',
             "Committee report tabled for plenary confirming Parliament's position": 'EP',
             "Committee decision to open interinstitutional negotiations with report adopted in committee": 'EP',
             "Committee decision to open interinstitutional negotiations after 1st reading in Parliament": 'EP',
             "Rejection by committee to open interinstitutional negotiations with report adopted in committee": 'EP',
             "Approval in committee of the text agreed at 2nd reading interinstitutional negotiations": 'EP',
             "Initial period for examining delegated act extended at Parliament's request by 4 month(s)": "EP",
             "Committee decision to open interinstitutional negotiations prior to the adoption of the report": 'EP',
             "Committee decision to open interinstitutional negotiations at 2nd reading": 'EP',
             "Committee decision to enter into interinstitutional negotiations announced in plenary (Rule 72)": 'EP',
             "Committee decision to enter into interinstitutional negotiations announced in plenary (Rule 71)": 'EP',
             "Committee decision to enter into interinstitutional negotiations confirmed by plenary (Rule 71)": 'EP',
             "Committee decision to enter into interinstitutional negotiations confirmed by plenary (Rule 71 - vote)": 'EP',
             "Committee decision to enter into interinstitutional negotiations rejected by plenary (Rule 71); file to be put on the agenda of the following part-session": 'EP',
             "Matter referred back to the committee responsible": 'EP',
             'Deadline for 2nd reading in plenary': u'EP',
             'Decision by Parliament, 1st reading/single reading': u'EP',
             'Decision by Parliament, 2nd reading': u'EP',
             'Decision by Parliament, 3rd reading': u'EP',
             'Committee referral announced in Parliament, 1st reading/single reading': u'EP',
             "Internal referral to parliamentary committee(s)": "EP",
             'Committee report tabled for plenary, single reading': u'EP',
             'Committee report tabled for plenary, 1st reading/single reading': u'EP',
             'Report referred back to committee': u'EP',
             'Vote in committee, 1st reading/single reading': u'EP',
             'Vote scheduled in committee, 1st reading/single reading': u'EP',
             'Committee recommendation tabled for plenary, 2nd reading': u'EP',
             'Committee referral announced in Parliament, 2nd reading': u'EP',
             'Vote in committee, 2nd reading': u'EP',
             'Indicative plenary sitting date, 2nd reading': u'EP',
             'Report tabled for plenary, 3rd reading': u'EP',
             'End of procedure in Parliament': u'EP',
             "Proposal for a mandate tabled in plenary": 'EP',
             'Budgetary report tabled for plenary, 1st reading': u'EP',
             'Budgetary conciliation report tabled for plenary': u'EP',
             "Preparatory budgetary report tabled for plenary": 'EP',
             'Committee interim report tabled for plenary': u'EP',
             'Referral to joint committee announced in Parliament': u'EP',
             'Budgetary report tabled for plenary, 2nd reading': u'EP',
             "Delegated act not objected by Parliament": u"EP",
             "Committee referral announced in Parliament": "EP",
             "Vote in committee": "EP",
             "Decision by Parliament": "EP",
             "Committee referral announced in Parliament, 1st reading": "EP",
             "Committee report tabled for plenary, 1st reading": "EP",
             "Decision by Parliament, 1st reading": "EP",
             "Vote in committee, 1st reading": "EP",
             "Committee report tabled for plenary": "EP",
             "Budgetary report tabled for plenary": "EP",

             'Committee of the Regions: opinion': u'CoR',
             'Additional information': u'all',
             }

def addCelex(doc):
    if (doc.get('title') and
        candre.match(doc.get('title'))):
        celexid=tocelex(doc.get('title'))
        if (celexid and checkUrl("http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=%s:HTML" % celexid)):
            doc[u'celexid']=celexid
    return doc

#comre=re.compile(r'COM\(([0-9]{4})\)([0-9]{4})')
#comepre=re.compile(r'COM/([0-9]{4})/([0-9]{4})')
#secre=re.compile(r'SEC\(([0-9]{4})\)([0-9]{4})')
#secepre=re.compile(r'SEC/([0-9]{4})/([0-9]{4})')
#cesre=re.compile(r'CES([0-9]{4})/([0-9]{4})')
#ecbre=re.compile(r'CON/([0-9]{4})/([0-9]{4})')
#cdrre=re.compile(r'CDR([0-9]{4})/([0-9]{4})')
#care=re.compile(r'RCC([0-9]{4})/([0-9]{4})')
#celexre=re.compile(r'[0-9]{5}[A-Z]{1,2}[0-9]{4}(?:R\([0-9]{2}\))?')
#candre=re.compile(r'(?:[0-9]+)?[^0-9]+[0-9]{4}(?:[0-9]+)?')
#epre=re.compile(r'T[0-9]-([0-9]{4})/([0-9]{4})')
def tocelex(title):
    m=celexre.match(title)
    if m:
        return "CELEX:%s:EN" % (title)
    m=cdrre.match(title)
    if m:
        return "CELEX:5%sAR%s:EN" % (m.group(2),m.group(1))
    m=care.match(title)
    if m:
        return "CELEX:5%sAA%s:EN" % (m.group(2),m.group(1))
    m=epre.match(title)
    if m:
        if checkUrl("http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=CELEX:5%sAP%s:EN:HTML" % (m.group(2),m.group(1))):
            #print >>sys.stderr, "CELEX:5%sAP%s:EN" % (m.group(2),m.group(1))
            return "CELEX:5%sAP%s:EN" % (m.group(2),m.group(1))
    m=cesre.match(title)
    if m:
        if checkUrl("http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=CELEX:5%sAE%s:EN:HTML" % (m.group(2),m.group(1))):
            return "CELEX:5%sAE%s:EN" % (m.group(2),m.group(1))
        elif checkUrl("http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=CELEX:5%sIE%s:EN:HTML" % (m.group(2),m.group(1))):
            return "CELEX:5%sIE%s:EN" % (m.group(2),m.group(1))
        return
    m=ecbre.match(title)
    if m:
        return "CELEX:5%sAB%s:EN" % (m.group(1),m.group(2))
    m=comre.match(title) or comepre.match(title)
    if m:
        for u in ["CELEX:5%sPC%s:EN" % (m.group(1),m.group(2)),
                  "CELEX:5%sDC%s:EN" % (m.group(1),m.group(2)),
                  "CELEX:5%sPC%s(02):EN" % (m.group(1),m.group(2)),
                  "CELEX:5%sPC%s(01):EN" % (m.group(1),m.group(2)),
                  "CELEX:5%sDC%s(02):EN" % (m.group(1),m.group(2)),
                  "CELEX:5%sDC%s(01):EN" % (m.group(1),m.group(2))]:
            if checkUrl("http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=%s:HTML" % u):
                return u
        return
    m=secre.match(title) or secepre.match(title)
    if m:
        return "CELEX:5%sSC%s:EN" % (m.group(1),m.group(2))

seenurls={}
def checkUrl(url):
    if not url: return False
    if url in seenurls:
        return seenurls[url]
    try:
        res=fetch(url)
    except Exception as e:
        #print >>sys.stderr, "[!] checkurl failed in %s\n%s" % (url, e)
        seenurls[url]=False
    else:
        seenurls[url]=(res.xpath('//h1/text()') or [''])[0]!="Not available in English."
    return seenurls[url]

def onfinished(daisy=False):
    if daisy:
        add_job("mep_activities",{"all": False, "onfinished": {"daisy": True}})
        add_job("pvotes",{"year":None, "onfinished": {"daisy": True}})
        add_job("amendments",{"all":False, "onfinished": {"daisy": True}})
        add_job("comagendas",{"onfinished": {"daisy": True}})
        add_job("plenaries", {"onfinished": {"daisy": True}})

def onchanged(doc, diff):
    id = doc['procedure']['reference']
    dossiers = notif.session.query(notif.Item).filter(notif.Item.name==id).all()
    subject_items = notif.session.query(notif.Item).filter(notif.Item.type=='subjects').all()
    search_items = notif.session.query(notif.Item).filter(notif.Item.type=='search').all()
    recipients = set()
    for i in dossiers:
        for s in i.group.subscribers:
            recipients.add(s.email)
    for i in subject_items:
        if i.name in (x for x in doc['procedure']['subject']):
            for s in i.group.subscribers:
                recipients.add(s.email)
    for i in search_items:
        q = create_search_regex(i.name)
        if dossier_search(q, doc):
            for s in i.group.subscribers:
                recipients.add(s.email)
    if not recipients:
        return
    log(3, "sending dossier changes to " + ', '.join(recipients))
    #(recepients, subject, change, date, url)
    send_html_mail(
        recipients=list(recipients),
        subject="%s %s" % (doc['procedure']['reference'],doc['procedure']['title']),
        obj=doc,
        change=diff,
        date=sorted(doc['changes'].keys())[-1],
        url='%sdossier/%s' % (ROOT_URL, doc['procedure']['reference']),
        text=makemsg(doc, diff)
    )
    return


def makemsg(doc,diff):
    return (u"Parltrack has detected a change in %s %s on OEIL.\n\nPlease follow this URL: %sdossier/%s to see the dossier.\n\nChanges follow\n%s\n\n\nsincerly,\nYour Parltrack team" %
            (doc['procedure']['reference'],
             doc['procedure']['title'],
             ROOT_URL,
             doc['procedure']['reference'],
             textdiff(diff)))


if __name__ == '__main__':
    from utils.log import set_level
    set_level(4)
    #d = db.dossier('2018/0044(COD)')
    #onchanged(d, sorted(d['changes'].items(), reverse=True)[0][1])

    from utils.utils import jdump
    import sys
    print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=%s&l=en" % sys.argv[1], save=False)))

    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2012/2039(INI)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=1992/0449B(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil//popups/ficheprocedure.do?reference=2018/0252(NLE)&l=en", save=False)))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil//popups/ficheprocedure.do?reference=2011/0901(COD)&l=en")))

    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2011/2080(ACI)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2017/2139(DEC)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2010/2168(DEC)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2015/2542(DEA)&l=en")))

    #from utils.log import set_level
    #set_level(3)
    #for r in ['2018/0066(COD)', '2016/0280(COD)', '2010/0802(COD)', '2011/0223(COD)', '2007/0247(COD)', '2009/0035(COD)', '2018/0210(COD)', '2019/2670(RSP)', '2018/0371(COD)', '2018/2167(DEC)', '2018/2168(DEC)', '2018/2237(INI)', '2014/2661(DEA)', '2008/0180(CNS)', '1991/0384(COD)', '2005/0149(COD)', '2011/0135(COD)']:
    #    scrape('http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=%s&l=en' % r)
    #for i in ['556397', '575084', '589377', '556208', '593187', '556397', '16542', '584049', '593435', '588286', '590715', '584049', '590612', '591258', '584049', '556397', '556364', '556398', '589181']:
    #    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=%s" % i)

    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil//popups/ficheprocedure.do?reference=2019/2582(RSP)&l=en")))

    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0066(COD)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2016/0280(COD)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2010/0802(COD)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2011/0223(COD)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2007/0247(COD)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2009/0035(COD)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0210(COD)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2019/2670(RSP)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0371(COD)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/2167(DEC)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/2168(DEC)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/2237(INI)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2014/2661(DEA)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2008/0180(CNS)&l=en")))
    #    #(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=1991/0384(COD)&l=en")))
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2011/0135(COD)"))) # with shadow rapporteurs
    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2005/0149(COD)&l=en")))

    #print(jdump(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=&l=en")))

    #         save(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556397"),[0,0]) # telecoms package
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=575084"))
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=589377"))
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556208")) # with shadow rapporteurs
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=593187")) # with shadow rapporteur
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556397")) # telecoms package
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=16542"))
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=584049")) # two rapporteurs in one committee
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=593435")) # with forecast
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=588286")
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=590715")
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=584049")
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=590612")
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=591258")
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=584049")
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556397") # telecoms package
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556364") # telecoms package
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556398") # telecoms package
    #              scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=589181") # .hu media law

    # diff verification fails:
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/2763(RSP)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0248(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0258(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0198(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0236(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0213(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0196(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0145(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0136(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2018/0088(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2017/0291(COD)&l=en")))
    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2005/0191(COD)&l=en")))
