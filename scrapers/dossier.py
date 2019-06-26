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

from db import db
from utils.log import log
from utils.process import process
from utils.mappings import GROUP_MAP, COMMITTEE_MAP
from utils.utils import fetch, fetch_raw, junws, unws, create_search_regex, dossier_search, textdiff
from urllib.parse import urljoin
from datetime import datetime
from lxml.etree import tostring, _ElementUnicodeResult
from lxml.html.soupparser import fromstring
from itertools import zip_longest
from operator import itemgetter
from webapp import mail, app
from flask_mail import Message
from config import ROOT_URL
import unicodedata

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
    root=fetch(url)

    tmp = root.xpath('//div[@id="procedure-file-header"]//div[@class="ep_title"]')
    if len(tmp)!=2: raise ValueError("dossier proc header has not two components")
    ref = junws(tmp[0])

    dossier = {
        'meta': {'source': url,
                 'updated': datetime.utcnow() },
        'procedure': {
            'reference': ref,
            'title': junws(tmp[1])
        },
        'committees': scrape_ep_key_players(root),
        'council': scrape_council_players(root),
        'commission': scrape_commission_players(root),
        'otherinst': scrape_other_players(root),
        'forecasts': scrape_forecasts(root),
        'links': scrape_extlinks(root),
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
        nopreserve=['other', 'forecasts'],
        nostore=not save,
        onchanged=onchanged,
    )
    return dossier

def scrape_basic(root, ref):
    res={}
    for para in root.xpath('//div[@id="basic-information-data"]//p/strong'):
        if not para.xpath('./text()'): continue
        title = junws(para)
        log(4,"title: %s" % title)
        if title in [ref, 'Status']: continue
        if title == 'Subject': title = 'subject'
        if title == 'Geographical area': title = 'geographical_area'
        if title not in ['Legislative priorities', 'Notes', 'geographical_area', 'subject']:
            log(3,"basic information of %s has unknown section: '%s'" % (ref, title))
        # this is a fucking mess, there's two columns, in the left one
        # stuff is between <strong> separated by <br /> in the right
        # one <p><strong></p><p>...</p> until the next <p><strong></p>
        tmp = para.xpath("../following-sibling::p[preceding-sibling::p/strong[1]]")
        if len(tmp)>1:
            log(2, "basic section of %s has more p in 2nd column: %s" % (ref,tmp))
        elif not tmp:
            tmp = para.xpath('./following-sibling::node()[not(self::br) and not(self::strong) and preceding-sibling::strong[1][text()="%s"]]' % para.xpath('./text()')[0])
            if not tmp and not para.xpath('./following-sibling::strong[1]'):
                tmp = para.xpath('./following-sibling::node()[not(self::br)]')
        if not tmp:
            log(1,'no content found for section "%s" of %s' % (title, ref))
        for node in tmp:
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
    for row in root.xpath('//div[@id="keyplayers_sectionPE-content"]//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-row ") and not(contains(concat(" ",normalize-space(@class)," ")," mobileOnly "))]'):
        cells = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]')
        if len(cells) != 3:
            log(1,'EP key players table has not 3 columns: %s' % repr([junws(x) for x in cells]))
            raise ValueError("bad dossier html")
        if 'ep-table-heading-row' in row.get('class'):
            tmp = [junws(x) for x in cells]
            if tmp == ['Committee responsible', 'Rapporteur', 'Appointed']:
                type="Responsible Committee"
            elif tmp == ['Committee for opinion', 'Rapporteur for opinion', 'Appointed']:
                type="Committee Opinion"
            elif tmp == ['Committee for opinion on the legal basis', 'Rapporteur for opinion', 'Appointed']:
                type="Committee Legal Basis Opinion"
            elif tmp ==['Former committee responsible', 'Former rapporteur','Appointed']:
                type="Former Responsible Committee"
            elif tmp == ['Former committee for opinion', 'Former rapporteur for opinion', 'Appointed']:
                type="Former Committee Opinion"
            elif tmp == ['Former committee for opinion on the legal basis', 'Rapporteur for opinion', 'Appointed']:
                type="Former Committee Legal Basis Opinion"
            elif tmp == ['Committee for opinion on the recast technique', 'Rapporteur for opinion', 'Appointed']:
                type="Committee Recast Technique Opinion"
            elif tmp == ['Former committee for opinion on the recast technique', 'Rapporteur for opinion', 'Appointed']:
                type="Fromer Committee Recast Technique Opinion"
            else:
                log(1, "unknown committee header in EP key players %s" % repr(tmp))
                raise ValueError("bad html in EP key players, committee header")
            continue

        if not type:
            log(1,"error no table header for EP key players found")
            raise ValueError("bad html in key players EP section, table header")

        player = {"type": type,
                  'body':'EP'}

        players.append(player)

        # first cell contains committee
        tmp = cells[0].xpath('.//a/@title')
        associated = False
        if len(tmp) == 0:
            tmp = junws(cells[0])
            abbr, name = tmp.split(" ",1)
            name = unicodedata.normalize('NFKD', name).encode('ascii','ignore').decode('utf8')
            if name.endswith(" (Associated committee)"):
                associated=True
                name=name[:-23]
            if not (abbr in COMMITTEE_MAP and name in COMMITTEE_MAP):
                log(1, 'unknown linkless committee in EP key players: "%s" -> u"%s": u"%s"' % (tmp, name, abbr))
                raise ValueError("bad html in key players EP section, linkless committee name")
            player['associated']=associated
        elif len(tmp) == 1:
            tmp=unws(tmp[0])
            tmp = unicodedata.normalize('NFKD', tmp).encode('ascii','ignore').decode('utf8')
            if tmp.endswith(" (Associated committee)"):
                associated=True
                tmp=tmp[:-23]
            if tmp not in COMMITTEE_MAP:
                log(1, 'unknown committee in EP key players: "%s"' % tmp)
                raise ValueError("bad html in key players EP section, committee name")
            name = tmp
            tmp = junws(cells[0])
            abbr = tmp[:4]
        else:
            log(1, 'committee has not one <a> tag: "%s"' % tmp)
            raise ValueError("bad html in key players EP section, committee href")

        player['committee_full']=name
        player['committee']=abbr
        player['associated']=associated

        # last cell contains date
        tmp = junws(cells[2])
        if tmp:
            player['date'] = [datetime.strptime(x, u"%d/%m/%Y") for x in tmp.split()]
        elif "The committee decided not to give an opinion" not in junws(cells[1]):
            player['date'] = []
            #log(1, "no date found for keyplayer appointment")
            #raise ValueError("bad html in key players EP section, appointment date")
        else:
            player['opinion'] = False
            continue
        date = player['date'][0] if player.get('date') else None

        # middle cell is rappporteur
        for x in cells[1].xpath('./div/div[not(@class="shadow-rapporteur")]/a[not(@title="Shadow rapporteur")]'):
            if not 'rapporteur' in player: player['rapporteur']=[]
            (abbr, group) = toGroup(x.xpath('./preceding-sibling::span/span[@class="tiptip"]/@title')[-1])
            name = junws(x)
            if name.startswith('Chair on behalf of committee '):
                name=name[29:]
            mepid = db.mepid_by_name(name, date, group)
            if not mepid:
                log(1,'no mepid found for "%s"' % name)
            player['rapporteur'].append({'name': name,
                                         'mepref': mepid,
                                         'group': group,
                                         'abbr': abbr})
        # check if cell[1] has also shadow rapporteurs listed
        tmp = cells[1].xpath('.//div[@class="shadow-rapporteur"]')
        if len(tmp)>1:
            log(1,"more than 1 shadow-rapporteur class divs found")
            raise ValueError("bad html in key players EP section, shadow raps")
        if len(tmp)==0:
            continue
        shadow_root = tmp[0]
        # handle shadow rapporteurs
        shadows = []
        for link in shadow_root.xpath('./a'):
            (abbr, group) = toGroup(link.xpath('./preceding-sibling::span/span[@class="tiptip"]/@title')[-1])
            name = junws(link)
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
    for row in root.xpath('//div[@id="keyplayers_sectionC-content"]//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-row ")]'):
        cells = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]')
        if len(cells) != 3:
            log(1,"Council key players table has not 3 columns")
            raise ValueError("bad dossier html, Council Key Players")
        if first:
            first = False
            continue

        player = {'body': u'CSL', 'type': u'Council Meeting'}
        players.append(player)

        # first cell contains council configuration
        tmp = cells[0].xpath('.//a/@title')
        if len(tmp)!=1:
            tmp = junws(cells[0])
            if tmp == '':
                log(1, "no council config specified")
                raise ValueError("bad html in key players council section, config missing")
        else:
            tmp = unws(tmp[0])
        player['council']=tmp

        # middle cell is meeting
        tmp = cells[1].xpath('./div/a')
        if len(tmp)!=1:
            log(1, "council meeting has not one <a> tag")
            raise ValueError("bad html in key players Council section, council config href")
        tmp=tmp[0]
        player['meeting_id']=junws(tmp)
        player['url']=str(tmp.get('href'))

        # last cell contains date
        tmp = junws(cells[2])
        if tmp: player['date'] = datetime.strptime(tmp, u"%d/%m/%Y")

    return players


def scrape_commission_players(root):
    players = []
    first = True
    for row in root.xpath('//div[@id="keyplayers_sectionEC-content"]//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-row ")]'):
        cells = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]')
        if len(cells) != 2:
            log(1,"Commission key players table has not 2 columns")
            raise ValueError("bad dossier html, Commission Key Players")
        if first: # skip table header - quicker than checking for class attribute
            first = False
            continue

        player = {'body': 'EC'}
        players.append(player)

        # first cell contains Commission
        tmp = cells[0].xpath('.//a/@title')
        if len(tmp)!=1:
            tmp = junws(cells[0])
            if tmp == '':
                log(1, "no commission specified")
                raise ValueError("bad html in key players Commission section, commission missing")
        else:
            tmp = unws(tmp[0])
        player['dg']=tmp

        # middle cell is commissioner
        tmp = cells[1].xpath('./div')
        if len(tmp)!=1:
            log(1, "commissioner has not one member")
            raise ValueError("bad html in key players Commission section, commissioner name")
        tmp=tmp[0]
        player['commissioner']=junws(tmp)

    return players

def scrape_other_players(root):
    res = []
    for other in root.xpath('//li[@id="keyplayers_section4"]'):
        titles = other.xpath('.//div[@id="keyplayers_section4-title"]')
        if len(titles)!=1:
            log(1, "key player other section has not 1 title")
            raise ValueError("bad dossier html, other key player title")
        title = junws(titles[0])
        for content in other.xpath('.//div[@id="keyplayers_section4-content"]'):
            if len(content)!=1:
                log(1,'not 1 section found: %d' % len(content))
                raise ValueError("bad dossier html, other key player content")
            tmp=junws(content[0])
            if tmp!=title:
                log(1,'other key player is not expected string: "%s" -> "%s"' % (title,tmp))
                raise ValueError("bad html dossier, other key players section")
            res.append({"name": title})
    return res

def scrape_events(root):
    events = []
    docs = []
    for row in root.xpath('//div[@id="key_events-data"]//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-row ")]'):
        cells = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]')
        if len(cells) != 4:
            log(1,"Events table has not 3 columns")
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
        node = cells[3].xpath(".//button")
        if len(node)==0:
            if 'docs' in event:
                docs.append({'date': event['date'], 'docs': event['docs']})
            continue
        if len(node)>1:
            log(1,"more than 1 summary button found")
            raise ValueError("bad dossier html, more than 1 summary button")
        tmp = node[0].get('onclick')
        prefix = "location.href='"
        if not tmp.startswith(prefix):
            log(1,"summary button doesn't start with expected prefix")
            raise ValueError("bad dossier html, summary button doesn't start with expected prefix")
        tmp=tmp[len(prefix):-1]
        # fetch summary
        event['summary']=fetchSummary(tmp)
        if 'docs' in event:
            docs.append({'date': event['date'], 'docs': event['docs'], 'summary': event['summary']})

    return events, docs

def scrape_technical(root):
    keymap = {'Procedure reference': 'reference',
              'Procedure type': 'type',
              'Procedure subtype': 'subtype',
              'Legislative instrument': 'instrument',
              'Legal basis': 'legal_basis',
              'Mandatory consultation of other institutions': 'other_consulted_institutions',
              'Stage reached in procedure': 'stage_reached',
              'Committee dossier': 'dossier_of_the_committee'}
    res = {}
    key = ''
    for row in root.xpath('//div[@id="technical_information-data"]//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-row ")]'):
        cells = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]')
        if len(cells) != 2:
            log(1,"Technical info table has not 2 columns")
            raise ValueError("bad dossier html, tech info")
        # 1st cell contains name
        tmp = junws(cells[0])
        if tmp:
            key = keymap.get(tmp,tmp)
            res[key] = junws(cells[1])
        else:
            if key=='':
                log(1,"empty technical field, and no previous key")
                raise ValueError("bad dossier html, tech info")
            if not isinstance(res[key], list): res[key]=[res[key]]
            res[key].append(junws(cells[1]))
    # split lists
    for field in ['legal_basis','dossier_of_the_committee']:
        if field in res:
            res[field]=sorted((unws(x) for x in res[field].split(';')))
    return res

def scrape_docs(root, edocs):
    docs = []
    sections = root.xpath('//li[@id="keyplayers_section2"]')
    if len(sections)==0: return []
    if junws(sections[-1].xpath('.//div[@id="keyplayers_section2-title"]')[0])!="All":
        log(1, 'last documents section is not "all"')
        raise ValueError("bad dossier html, documents")
    for row in sections[-1].xpath('.//div[@id="keyplayers_section2-content"]/div/div[contains(concat(" ",normalize-space(@class)," ")," ep-table-row ")]'):
        cells = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]')
        if len(cells) != 6:
            log(1,"Docs table has not 6 columns")
            raise ValueError("bad dossier html, docs")

        doc = {}
        # date is cell 4
        tmp = junws(cells[3])
        if tmp:
            doc['date']=datetime.strptime(tmp, u"%d/%m/%Y")

        # url is cell 3
        for link in cells[2].xpath('.//a'):
            if not 'docs' in doc: doc['docs']=[]
            url=str(link.get('href'))
            title = junws(link)
            if title == '':
                title = link.get('title')
            if title == '':
                log(1, 'no title for link in doc' % tostring(links[1]))
                raise ValueError("bad dossier html, event unnamed link")
            doc['docs'].append({'url': url, 'title': title})
        for alt in cells[2].xpath('.//span/text()[not(ancestor::a) and string-length(normalize-space()) > 0]'):
            if not 'docs' in doc: doc['docs']=[]
            doc['docs'].append({"title": unws(alt)})

        tdoc = {}
        ######
        # title is cell 1
        tdoc['type']=junws(cells[0])

        # 5. institution
        tmp = junws(cells[4])
        if tmp:
            tdoc['body']=tmp

        # 2. code
        tmp = junws(cells[1])
        if tmp:
            if tdoc.get('body')=='NP':
                tdoc['body']=tmp
            elif tmp in COMMITTEE_MAP:
                doc['committee'] = tmp
            else:
                log(2, 'unexpected value in doc/code cell "%s"' % tmp)
                raise ValueError("bad html in doc code")

        # summary is field 6
        node = cells[5].xpath(".//button")
        if len(node)==0:
            doc.update(tdoc)
            docs.append(doc)
            continue
        if len(node)>1:
            log(1,"more than 1 summary button found")
            raise ValueError("bad dossier html, more than 1 summary button")
        tmp = node[0].get('onclick')
        prefix = "location.href='"
        if not tmp.startswith(prefix):
            log(1,"summary button doesn't start with expected prefix")
            raise ValueError("bad dossier html, summary button doesn't start with expected prefix")
        tmp=tmp[len(prefix):-1]
        # fetch summary
        doc['summary']=fetchSummary(tmp)
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
            log(1,"External links info table has not 2 columns")
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
    for row in root.xpath('//div[@id="final_act-data"]//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-row ")]//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]'):
        button = row.xpath(".//button")
        if len(button)==0:
            # try links
            for link in row.xpath(".//a"):
                if not 'docs' in res: res['docs']=[]
                res['docs'].append({'title': junws(link),
                                    'url': str(link.get('href'))})
        elif len(button)==1:
            tmp = button[0].get('onclick')
            prefix = "location.href='"
            if not tmp.startswith(prefix):
                log(1,"summary button doesn't start with expected prefix")
                raise ValueError("bad dossier html, final act")
            tmp=tmp[len(prefix):-1]
            # fetch summary
            res['summary']=fetchSummary(tmp)
        else:
            log(1,"more than 1 summary button found")
            raise ValueError("bad dossier html, final act")
    return res

def scrape_forecasts(root):
    res = []
    for row in root.xpath('//div[@id="forecast-data"]//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-row ")]'):
        cells = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," ep-table-cell ")]')
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

def toGroup(txt):
    txt = unws(txt)
    if txt in GROUP_MAP:
        return (GROUP_MAP[txt], txt)
    if txt.startswith("ALDE- "):
        return ("ALDE", 'Alliance of Liberals and Democrats for Europe')
    try:
        _, group = txt.split(' - ', 1)
    except:
        print(repr(txt))
        raise
    group=unws(group)
    return GROUP_MAP[group], group

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
    tmp = tmp.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," ep-m_product ")]')
    if len(tmp)!=2:
        log(1, "summary nodes len != 2")
        raise ValueError("bad html in summary: %s" % url)
    return [junws(x) for x in tmp[1].xpath('.//div/div/*')]

fuckedSummaries={
    "https://oeil.secure.europarl.europa.eu/oeil/popups/summary.do?id=910263&t=e&l=en": [("<m<", "&lt;m&lt;")],
    'https://oeil.secure.europarl.europa.eu/oeil/popups/summary.do?id=910263&t=d&l=en': [("<m<", "&lt;m&lt;")],
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
             'http://www.enfgroup-ep.eu/': u'ENF'} # todo fix when website available
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
             "Matter referred back to the committee responsible": 'EP',
             'Deadline for 2nd reading in plenary': u'EP',
             'Decision by Parliament, 1st reading/single reading': u'EP',
             'Decision by Parliament, 2nd reading': u'EP',
             'Decision by Parliament, 3rd reading': u'EP',
             'Committee referral announced in Parliament, 1st reading/single reading': u'EP',
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

#def save(data, stats):
    #if not NOMAIL:
    #    m=db.notifications.find({'dossiers': data['procedure']['reference']},['active_emails'])
    #    for g in m:
    #        if len(g['active_emails'])==0:
    #            continue
    #        msg = Message("[PT] %s %s" % (data['procedure']['reference'],data['procedure']['title']),
    #                      sender = "parltrack@parltrack.euwiki.org",
    #                      bcc = g['active_emails'])
    #        #msg.html = htmldiff(data,d)
    #        msg.body = makemsg(data,d)
    #        mail.send(msg)
    #log(2, htmldiff(data,d))
    #log(2, makemsg(data,d))

def onfinished(daisy=True):
    if daisy:
        from scraper_service import add_job
        add_job("pvotes",{"year":"all", "onfinished": {"daisy": True}})
        add_job("amendments",{"all":True, "onfinished": {"daisy": True}})

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
    msg = Message("[PT] %s %s" % (doc['procedure']['reference'],doc['procedure']['title']),
		  sender = "parltrack@parltrack.euwiki.org",
		  bcc = list(recipients))
    #msg.html = htmldiff(doc,d)
    msg.body = makemsg(doc,diff)
    with app.context():
        mail.send(msg)
    return


def makemsg(doc,diff):
    return (u"Parltrack has detected a change in %s %s on OEIL.\n\nPlease follow this URL: %s/dossier/%s to see the dossier.\n\nChanges follow\n%s\n\n\nsincerly,\nYour Parltrack team" %
            (doc['procedure']['reference'],
             doc['procedure']['title'],
             ROOT_URL,
             doc['procedure']['reference'],
             textdiff(diff)))


if __name__ == '__main__':
    from utils.utils import jdump
    print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2012/2039(INI)&l=en")))
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

    #print(jdump(scrape("https://oeil.secure.europarl.europa.eu/oeil//popups/ficheprocedure.do?reference=2019/2582(RSP)&amp;l=en")))

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
