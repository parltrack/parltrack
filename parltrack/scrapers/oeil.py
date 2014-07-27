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

# (C) 2009-2011 by Stefan Marsiske, <stefan.marsiske@gmail.com>
import pprint
from lxml.etree import tostring
from urlparse import urljoin, urlsplit, urlunsplit
from itertools import izip, izip_longest
import datetime, sys, re, feedparser, traceback
from operator import itemgetter
from flaskext.mail import Message
from parltrack.webapp import mail
from parltrack.utils import diff, htmldiff, fetch, unws, Multiplexer, logger, jdump, textdiff
from parltrack.default_settings import ROOT_URL
from parltrack.scrapers.mappings import ipexevents, COMMITTEE_MAP

BASE_URL = 'http://www.europarl.europa.eu'

import unicodedata
from parltrack.db import db
#from parltrack.scrapers.ipex import IPEXMAP
IPEXMAP={}

def getMEPRef(name, retfields=['_id']):
    if not name: return
    mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.split()).lower()},retfields)
    if not mep and u'ß' in name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower()},retfields)
    if not mep and unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore')!=name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore').split()).lower()},retfields)
    if not mep and len([x for x in name if ord(x)>128]):
        mep=db.ep_meps.find_one({'Name.aliases': re.compile(''.join([x if ord(x)<128 else '.' for x in name]),re.I)},retfields)
    if not mep:
        mep=db.ep_meps2.find_one({'Name.aliases': re.compile(''.join([x if ord(x)<128 else '.' for x in name]),re.I)},retfields)
    if mep:
        return mep['_id']
    else:
        logger.warn('[!] lookup oops %s' % name.encode('utf8'))

def toDate(node):
    for br in node.xpath("br"):
        br.text="\n"
    lines=[x.replace(u"\u00A0",' ').strip() for x in node.xpath(".//text()") if x.replace(u"\u00A0",' ').strip()]
    if len(lines)>1:
        result=[]
        for text in lines:
            if not len(text): continue
            value=[int(x) for x in text.split('/') if len(x)]
            result.append(datetime.datetime(value[2], value[1], value[0]))
        return result
    elif len(lines)==1:
        text=lines[0]
        if not len(text): return None
        value=[int(x) for x in text.split('/') if len(x)]
        return datetime.datetime(value[2], value[1], value[0])
    return None

def toText(node):
    if node is None: return ''
    for br in node.xpath("br"):
        br.text="\n"
    text=u' '.join(u' '.join([x.strip() for x in node.xpath(".//text()") if x.strip()]).replace(u"\u00A0",' ').split())

    links=node.xpath('a')
    if not links: return text
    return {u'title': text, u'url': unicode(urljoin(BASE_URL,links[0].get('href')),'utf8')}

groupurlmap={'http://www.guengl.eu/?request_locale=en': u"GUE/NGL",
             'http://www.eppgroup.eu/home/en/default.asp?lg1=en': u"EPP",
             'http://www.alde.eu/?request_locale=en': u'ALDE',
             'http://www.greens-efa.org/cms/default/rubrik/6/6270.htm?request_locale=en': u'Verts/ALE',
             'http://www.efdgroup.eu/?request_locale=en': u'EFD',
             'http://www.ecrgroup.eu/?request_locale=en': u'ECR',
             'http://www.socialistsanddemocrats.eu/gpes/index.jsp?request_locale=en': u'S&D'}
def toMEP(node):
    tips=[t.xpath('text()')[0]
          if len(t.xpath('text()'))>0
          else groupurlmap[t.xpath("a")[0].get('href')]
          for t in node.xpath('.//span[@class="tiptip"]')]
    [tip.xpath('..')[0].remove(tip)
     for tip
     in node.xpath('.//span[@class="tiptip"]')]

    return [{u'name': toText(p),
             u'group': unicode(group),
             u'mepref': getMEPRef(toText(p))}
            for p, group
            in izip_longest(node.xpath("p"),tips)
            if not toText(p).startswith("The committee decided not to give an opinion")
            ]

def toLinks(node):
    if node is None: return
    for br in node.xpath("br"):
        br.text="\n"
    ret=[]
    for line in node.xpath(".//text()"):
        if len(unws(line))<1:
            continue
        if line.getparent().tag=='a':
            ret.append({u'title': unws(line), 'url': unicode(urljoin(BASE_URL,line.getparent().get('href')),'utf8')})
        else:
            ret.append({u'title': unws(line)})
    return ret

def toLines(node):
    return [toText(p) for p in node.xpath("p")]

def convertRow(cells,fields):
    res={}
    if not len(cells)==len(fields): return None
    for i,cell in enumerate(cells):
        tmp=fields[i][1](cell)
        if tmp: res[fields[i][0].lower().replace(' ', '_')]=tmp
    return res

def lst2obj(table,fields,offset=0):
    res=[]
    if table==None: return res
    for row in table.xpath('.//tr')[offset:]:
        items=row.xpath('td')
        value=convertRow(items,fields)
        if value:
            res.append(value)
    return res

def form2obj(table,headers=None):
    res={}
    if table==None: return res
    for row in table.xpath('./tbody/tr'):
        k,v=row.xpath('td')
        k=toText(k)
        if headers and k in headers: k=headers[k]
        res[k]=toText(v)
    return res

eventFields=( (u'date', toDate),
              (u'type', toText),
              (u'doc', toText),
              (u'text', toText))
forecastFields=( (u'date', toDate),
                 (u'type', toText))
docFields=( (u'type', toText),
            (u'doc', toLinks),
            (u'date', toDate),
            (u'text', toText),
            )
epagents=( (u'committee', toText),
           (u'rapporteur', toMEP),
           (u'date', toDate),
           )
cslagents=( (u'council', toText),
           (u'meeting_id', toText),
           (u'date', toDate),
           )
ecagents=( (u'dg', toLines),
           (u'commissioner', toLines),
           )
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
             
             'Final act signed by Parliament and Council': u'EP/CSL',
             'Joint text approved by Conciliation Committee co-chairs': u'EP/CSL',
             'Final decision by Conciliation Committee': u'EP/CSL',
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
             "Delegated act not objected by Council": u"EP/CSL",
             "Delegated act not objected by Parliament": u"EP/CSL",

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
             'Proposal withdrawn by Commission': u'EC',
             
             'Results of vote in Parliament': u'EP',
             'Debate in Parliament': u'EP',
             'Vote in plenary scheduled': u'EP',
             'Debate scheduled': u'EP',
             'Vote scheduled': u'EP',
             'Decision by committee, without report': u'EP',
             'Debate in plenary scheduled': u'EP',
             'Referral to associated committees announced in Parliament': u'EP',
             'Indicative plenary sitting date, 1st reading/single reading': u'EP',
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
             'Budgetary report tabled for plenary, 1st reading': u'EP',
             'Budgetary conciliation report tabled for plenary': u'EP',
             'Committee interim report tabled for plenary': u'EP',
             'Referral to joint committee announced in Parliament': u'EP',
             'Budgetary report tabled for plenary, 2nd reading': u'EP',
             
             'Committee of the Regions: opinion': u'CoR',
             'Additional information': u'all',
             }

def merge_events(events,committees,agents):
    bydate={}
    for event in events:
        if not event['date'] in bydate:
            bydate[event['date']]=[event]
        else:
            bydate[event['date']].append(event)
    #pprint.pprint(sorted([(k,[dict([(k1,v1) for k1,v1 in i.items() if k1!='text']) for i in v]) for k,v in bydate.items()]))
    res=[]
    # merge items to events.
    for date, items in bydate.items():
        actors={} # collects items/actor for a given date
        for item in items:
            if not item.get('body'):
                # find out body, or drop
                body=stage2inst.get(item.get('type'))
                if body:
                    item[u'body']=body
                elif item.get('type')=='Final act published in Official Journal':
                    # this really has no body or all
                    res.append(item)
                    continue
                else:
                    logger.warn('unknown body: %s' % item.get('type'))
                    item[u'body']='unknown'
            # new institution for this date
            if not item['body'] in actors:
                # new body for this date
                actors[item['body']]=item
                if 'doc' in actors[item['body']]:
                    docs=merge_new_docs(actors[item['body']]['doc'], item)
                    del actors[item['body']]['doc']
                    actors[item['body']][u'docs']=docs
                cmts=getCommittee(item,committees)
                if cmts:
                    actors[item['body']][u'committees']=sorted(cmts, key=itemgetter('committee'))
                if item['body']=='EC':
                    actors[u'EC'][u'commission']=sorted([{u'DG': x['dg'],
                                                        u'Commissioner': x['commissioner']} if x.get('commissioner') else {u'DG': x['dg']}
                                                       for x in agents if x['body']=='EC'])
                continue
            # merge any docs
            if 'doc' in item:
                docs=merge_new_docs(item['doc'], item)
                for doc in docs:
                    skip=False
                    # update docs, that are already in there, but with a different 'type'
                    for cdoc in actors[item['body']].get('docs',[]):
                        if cdoc.get('url')==doc.get('url') or cdoc.get('title')==doc.get('title'):
                            cdoc.update(doc)
                            skip=True
                            break
                    if skip: continue
                    try:
                        actors[item['body']][u'docs'].append(doc)
                    except KeyError:
                        actors[item['body']][u'docs']=[doc]
                del item['doc']
            # merge any fields not yet in the actor
            actors[item['body']].update([(k,v) for k,v in item.items() if k not in actors[item['body']]])
        res.extend([x for x in actors.values() if x])
    #pprint.pprint(sorted(res, key=itemgetter('date')))
    #pprint.pprint(sorted([dict([(k1,v1) for k1,v1 in v.items() if k1!='text']) for v in res], key=itemgetter('date')))
    return res

def merge_new_docs(doc, item):
    if type(doc)==type(list()):
        return sorted([merge_new_doc(d, item) for d in doc])
    else:
        return [merge_new_doc(doc, item)]

def merge_new_doc(doc, item):
    if type(doc)!=type(dict()):
        # title only doc
        doc={u'title': doc}
    # carry type
    doc[u'type']=item['type']
    if item.get('text'):
        doc[u'text']=item['text']
        del item['text']
    if not doc['title']:
        doc[u'title']=doc['type']
    # add celex id
    doc=addCelex(doc)
    return doc

def addCelex(doc):
    if (doc.get('title') and
        candre.match(doc.get('title'))):
        celexid=tocelex(doc.get('title'))
        if (celexid and checkUrl("http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=%s:HTML" % celexid)):
            doc[u'celexid']=celexid
    return doc

def getCommittee(item, committees):
    if not item.get('type'): return
    if item['type'] in ['Committee referral announced in Parliament, 1st reading/single reading',
                        'Committee report tabled for plenary, 1st reading/single reading',
                        'Vote in committee, 1st reading/single reading']:
        return sorted([c for c in committees if c.get('committee')!="CODE"],key=itemgetter('committee'))
    if item['type'] in ['Committee recommendation tabled for plenary, 2nd reading',
                        'Committee referral announced in Parliament, 2nd reading',
                        'Vote in committee, 2nd reading']:
        return sorted([c for c in committees if c.get('committee')!="CODE" and c.get('responsible')==True],key=itemgetter('committee'))
    if item['type'] in ['Draft report by Parliament delegation to the Conciliation Committee',
                        'Joint text approved by Conciliation Committee co-chairs',
                        'Final decision by Conciliation Committee',
                        'Formal meeting of Conciliation Committee']:
        return sorted([c for c in committees if c.get('committee')=="CODE"],key=itemgetter('committee'))

def scrape(url):
    try:
        logger.info('scrape '+url)
        tree=fetch(url)
        agents,committees=scrape_actors(tree)
        forecasts=lst2obj((tree.xpath('//table[@id="forecast"]') or [None])[0],forecastFields)
        events=scrape_events(tree)
        procedure=scrape_basic(tree)
        if not procedure: return
        ipext=[]
        for ipexd in IPEXMAP.get(procedure['reference'], {}).get('Dates',[]):
            skip=False
            for event in forecasts+events:
                if event['type'] in ipexevents.get(ipexd['type'],{}).get('oeil',[]) and event['date']==ipexd['date']:
                    skip=True
                    break
            if skip: continue
            ipext.append(ipexd)
        allevents=agents+scrape_docs(tree)+events+forecasts+ipext
        other=[x for x in allevents if not x.get('date')]
        allevents=sorted([x for x in allevents if x.get('date')],key=itemgetter('date'))
        allevents=merge_events(allevents,committees, agents)
        res={u'meta': {'source': url,
                       'timestamp': datetime.datetime.utcnow() },
             u'procedure': procedure,
             u'links': form2obj((tree.xpath('//table[@id="external_links"]') or [None])[0]),
             u'committees': committees,
             u'activities': sorted(allevents, key=itemgetter('date')),
             u'other': other,
             }
        tmp=url.split('id=')
        if len(tmp)>1:
            res['meta']['id']=int(tmp[1])
        # check for "final act"
        finalas=tree.xpath('//div[@id="final_act"]//a')
        final={}
        for link in finalas:
            if link.get('class')=='sumbutton':
                try: summary=fetch("http://www.europarl.europa.eu%s" % link.get('href'))
                except: continue
                final['text']=[unicode(tostring(x)) for x in summary.xpath('//div[@id="summary"]')]
            else:
                if not 'docs' in final: final['docs']=[]
                final['docs'].append({'title': link.xpath('text()')[0].strip(),
                                               'url': link.get('href')})
        if final and final.get('docs'):
            res[u'procedure'][u'final']=final.get('docs',[{}])[0]
            for item in res['activities']:
                if item.get('type')==u'Final act published in Official Journal':
                    if final.get('text'):
                        item[u'text']=final['text']
                    if  len(final.get('docs'))>1:
                       if not 'docs' in item:
                           item[u'docs']=final['docs']
                       else:
                           item[u'docs'].extend(final['docs'])
                    break
        return res
    except:
        logger.error("%s\n%s" % (url,traceback.format_exc()))
        return

def scrape_basic(tree):
    res=form2obj((tree.xpath('//table[@id="technicalInformations"]') or [None])[0],detailsheaders) or {}
    if 'dossier_of_the_committee' in res:
        res['dossier_of_the_committee']=';'.join(sorted((unws(x) for x in res['dossier_of_the_committee'].split(';'))))
    table=(tree.xpath('//table[@id="basic_information"]') or [None])[0]
    if table is None: return res
    res.update({'stage_reached': (table.xpath('.//p[@class="pf_stage"]/text()') or [''])[0].strip(),
                'reference': (table.xpath('.//span[@class="basic_reference"]/text()') or [''])[0].strip(),
                'type': (table.xpath('.//p[@class="basic_procedurefile"]/text()') or [''])[0].strip(),
                'title': (table.xpath('.//p[@class="basic_title"]/text()') or [''])[0].strip(),
                })
    if '' in res:
        del res['']
    if 'legal_basis' in res:
        res[u'legal_basis']=sorted((unws(x) for x in res['legal_basis'].split(';')))
    fields=table.xpath('.//p[@class="basic_content"]/*')
    firstline=u' '.join((table.xpath('.//p[@class="basic_content"]/text()') or [''])[0].split())
    attrib=u'summary'
    if len(firstline):
        if not attrib in res: res[attrib]=[]
        res[attrib]=[firstline]
    for elem in fields:
        if elem.tag=='br' and elem.tail and elem.tail.strip():
            if not attrib in res: res[attrib]=[]
            res[attrib].append(u' '.join(elem.tail.split()))
        elif elem.tag=='strong':
            if attrib in res and res[attrib]:
                res[attrib].sort()
            attrib=u' '.join(elem.xpath('text()')[0].split())
            attrib=detailsheaders.get(attrib,attrib).lower().replace(u" ",u"_")
            if attrib:
                res[attrib]=[]
    return res

def scrape_events(tree):
    res=[]
    for item in lst2obj((tree.xpath('//table[@id="key_events"]') or [None])[0],eventFields):
        if item.get('text'):
            try: summary=fetch(item['text']['url'])
            except: continue
            item['text']=[unicode(tostring(x)) for x in summary.xpath('//div[@id="summary"]')]
        res.append(item)
    return res

def scrape_docs(tree):
    res=[]
    docs=tree.xpath('//table[@id="doc_gateway"]')
    tabs=[x.xpath('preceding-sibling::h2')[0].xpath('text()')[0] for x in docs]
    for inst, table in izip(tabs, docs):
        if inst in instmap.keys():
            for doc in lst2obj(table, docFields):
                if inst != 'Other institutions':
                    doc[u'body']=instmap[inst]
                else:
                    try:
                        doc[u'body']=otherinst[doc['type'].split(':')[0]]
                    except KeyError:
                        doc[u'body']=''
                if doc['body'] in ['EP','CSL'] and doc['type']=='Joint text approved by Conciliation Committee co-chairs':
                    # skip it twice and hope it's listed in the all documents, so it becomes EP/CSL :)
                    continue
                if doc.get('text'):
                    try: summary=fetch(doc['text']['url'])
                    except: continue
                    doc[u'text']=[unicode(tostring(x)) for x in summary.xpath('//div[@id="summary"]')]
                res.append(doc)
        elif inst != 'All':
            logger.warn(u"[!] unrecognized tab in documents %s" % inst)
    return res

def scrape_actors(tree):
    insts=tree.xpath('//td[@class="players_institution" or @class="players_institution inst_separator"]')
    agents=[]
    meps=[]
    for inst in insts:
        inst_name=''.join([x.strip() for x in inst.xpath('.//text()')])
        for table in inst.xpath('following-sibling::td/table'):
            if inst_name == 'European Parliament':
                meps.extend([x for x in scrape_epagents(table) if x not in meps])
            # Handle council
            elif inst_name == 'Council of the European Union':
                for agent in lst2obj(table, cslagents, 1):
                    agent[u'body']=u'CSL'
                    agent[u'type']=u'Council Meeting'
                    agents.append(agent)
            # and commission
            elif inst_name == 'European Commission':
                for p in table.xpath('.//p[@class="players_head"]'):
                    p.getparent().remove(p)
                for agent in lst2obj(table, ecagents, 0):
                    if len(agent.get('dg','x'))==len(agent.get('commissioner','')):
                        for dg,cmnr in izip(agent['dg'], agent['commissioner']):
                            agent[u'body']=u'EC'
                            agents.append({u'body': u'EC',
                                           u'dg': dg,
                                           u'commissioner': cmnr})
                    else:
                        agents.append({u'body': u'EC',
                                       u'dg': agent['dg']})
                        #logger.warn("commission data wrong: %s" % (agent))
            else:
                "[!] wrong institution name", inst_name
    return (agents, sorted(meps,key=itemgetter('committee')))

def scrape_epagents(table):
    heading=''.join(table.xpath('.//td[@class="players_committee"]')[0].xpath(".//text()")).strip()
    responsible=None
    if heading in [ "Committee responsible", "Former committee responsible"]:
        responsible=True
    elif heading in ["Committee for opinion", "Former committee for opinion"]:
        responsible=False
    else:
        logger.warn(u"[!] unknown committee heading %s" % heading)

    # handle shadows
    shadowelems=table.xpath('//a[@id="shadowRapporteurHeader"]/../following-sibling::div/p//span[@class="players_rapporter_text"]/a')
    tips=[t.xpath('text()')[0] if len(t.xpath('text()'))>0 else groupurlmap[t.xpath("a")[0].get('href')]
          for t in table.xpath('//a[@id="shadowRapporteurHeader"]/../following-sibling::div//span[@class="tiptip"]')]
    shadows={}
    for shadow, group in izip_longest(shadowelems, tips):
        committee=shadow.xpath('./ancestor::td/preceding-sibling::td//acronym/text()')[0]
        if not committee in shadows: shadows[committee]=[]
        if group=='NI': group=u'NI'
        mep={u'name': unicode(shadow.xpath('text()')[0]),
             u'group': unicode(group)}
        tmp=getMEPRef(shadow.xpath('text()')[0])
        if tmp:
           mep[u'mepref']=tmp
        else:
            raise IndexError
        shadows[committee].append(mep)
    # delete the uneccessary shadow elements - so the following regular lst2obj get's what it expects
    for todel in table.xpath('//a[@id="shadowRapporteurHeader"]/..'):
        parent=todel.xpath('..')[0]
        parent.remove(todel.xpath('following-sibling::div')[0])
        parent.remove(todel)

    # handle each row of agents
    agents=[]
    for agent in lst2obj(table,epagents,1):
        agent[u'responsible']=responsible
        agent[u'body']=u'EP'
        if agent.get('rapporteur'):
            meps=[]
            for mep in agent['rapporteur']:
                if unws(mep['name']).startswith("The committee decided not to give an opinion"):
                    del agent['rapporteur'][agent['rapporteur'].index(mep)]
                    agent[u'opinion']=None
                    continue
                tmp=getMEPRef(mep['name'])
                if tmp:
                    meps.append({u'mepref': tmp,
                                 u'group': mep['group'],
                                 u'name': mep['name']})
                else:
                    raise IndexError
            agent[u'rapporteur']=meps

        abbr=agent['committee'][:4]
        if abbr=='BUDE': abbr='BUDG'
        if not abbr in COMMITTEE_MAP.keys():
            logger.warn(u"[!] uknown committee abbrev %s" % abbr)
            agent[u'committee_full']=agent['committee']
            if agent['committee'][4]==' ' and abbr.isalpha():
                agent[u'committee']=abbr
        else:
            agent[u'committee_full']=agent['committee'][5:]
            agent[u'committee']=abbr

        if agent.get(u'committee') in shadows.keys():
            agent[u'shadows']=shadows[agent['committee']]

        if not agent in agents: agents.append(agent)
    return agents

def get_new_dossiers():
    f = feedparser.parse('http://www.europarl.europa.eu/oeil/search/result.rss?lastProcedurePublished=7&all&limit=100')
    if not f:
        return
    for item in f.entries:
        url=urljoin(BASE_URL, urlunsplit(('','')+urlsplit(item.link)[2:]))
        yield (url, item.title)

def get_all_dossiers():
    for year in xrange(datetime.date.today().year, 1972, -1):
        tree=fetch('http://www.europarl.europa.eu/oeil/widgets/resultwidget.do?lang=en&noHeader=false&q=objectReferenceN:N-%s/????\(*\)'
                   % (year))
        count=int(tree.xpath('//span[@class="resultNumber"]/text()')[0].strip())
        tree=fetch('http://www.europarl.europa.eu/oeil/widgets/resultwidget.do?lang=en&limit=%s&noHeader=false&q=objectReferenceN:N-%s/????\(*\)'
                   % (count,year))
        links=tree.xpath('//a[@class="reference rssEntry_id rssEntry_title rssEntry_updated"]')
        for link in links:
            yield (urljoin(BASE_URL,link.get('href')),
                   (link.xpath('text()') or [''])[0])

def get_active_dossiers():
    for doc in db.dossiers2.find({ 'procedure.stage_reached' : { '$not' : { '$in': [ "Procedure completed",
                                                                                          "Procedure rejected",
                                                                                          "Procedure lapsed or withdrawn"
                                                                                          ] }} }, timeout=False):
        yield (doc['meta']['source'],doc['procedure']['title'])

def crawl(urls, threads=4):
    m=Multiplexer(scrape,save, threads=threads)
    m.start()
    [m.addjob(url) for url, title in urls]
    m.finish()
    logger.info('end of crawl')

def crawlseq(urls, null=False):
    stats=[0,0]
    [save(scrape(url),stats)
     for url, title in urls
     if (null and db.dossiers2.find_one({'meta.source': url},['_id'])==None) or not null]
    logger.info('end of crawl %s' % stats)

comre=re.compile(r'COM\(([0-9]{4})\)([0-9]{4})')
comepre=re.compile(r'COM/([0-9]{4})/([0-9]{4})')
secre=re.compile(r'SEC\(([0-9]{4})\)([0-9]{4})')
secepre=re.compile(r'SEC/([0-9]{4})/([0-9]{4})')
cesre=re.compile(r'CES([0-9]{4})/([0-9]{4})')
ecbre=re.compile(r'CON/([0-9]{4})/([0-9]{4})')
cdrre=re.compile(r'CDR([0-9]{4})/([0-9]{4})')
care=re.compile(r'RCC([0-9]{4})/([0-9]{4})')
celexre=re.compile(r'[0-9]{5}[A-Z]{1,2}[0-9]{4}(?:R\([0-9]{2}\))?')
candre=re.compile(r'(?:[0-9]+)?[^0-9]+[0-9]{4}(?:[0-9]+)?')
epre=re.compile(r'T[0-9]-([0-9]{4})/([0-9]{4})')
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

def checkUrl(url):
    if not url: return False
    try:
        res=fetch(url)
    except Exception, e:
        #print >>sys.stderr, "[!] checkurl failed in %s\n%s" % (url, e)
        return False
    return (res.xpath('//h1/text()') or [''])[0]!="Not available in English." # TODO check this

def save(data, stats):
    if not data: return stats
    src=data['meta']['source']
    res=db.dossiers2.find_one({ 'meta.source' : src }) or {}
    d=diff(dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]),
           dict([(k,v) for k,v in data.items() if not k in ['_id', 'meta', 'changes',]]))
    #logger.warn(pprint.pformat(d))
    if d:
        now=datetime.datetime.utcnow().replace(microsecond=0).isoformat()
        if not res:
            logger.info(('adding %s - %s' % (data['procedure']['reference'],data['procedure']['title'])).encode('utf8'))
            data['meta']['created']=data['meta']['timestamp']
            del data['meta']['timestamp']
            sys.stdout.flush()
            stats[0]+=1
        else:
            logger.info(('updating  %s - %s' % (data['procedure']['reference'],data['procedure']['title'])).encode('utf8'))
            data['meta']['updated']=data['meta']['timestamp']
            del data['meta']['timestamp']
            sys.stdout.flush()
            stats[1]+=1
            data['_id']=res['_id']
            logger.info(jdump(d))
        m=db.notifications.find({'dossiers': data['procedure']['reference']},['active_emails'])
        for g in m:
            if len(g['active_emails'])==0:
                continue
            msg = Message("[PT] %s %s" % (data['procedure']['reference'],data['procedure']['title']),
                          sender = "parltrack@parltrack.euwiki.org",
                          bcc = g['active_emails'])
            #msg.html = htmldiff(data,d)
            msg.body = makemsg(data,d)
            mail.send(msg)
        #logger.info(htmldiff(data,d))
        #logger.info(makemsg(data,d))
        data['changes']=res.get('changes',{})
        data['changes'][now]=d
        db.dossiers2.save(data)
    return stats

def makemsg(data, d):
    return (u"Parltrack has detected a change in %s %s on OEIL.\n\nPlease follow this URL: %s/dossier/%s to see the dossier.\n\nChanges follow\n%s\n\n\nsincerly,\nYour Parltrack team" %
            (data['procedure']['reference'],
             data['procedure']['title'],
             ROOT_URL,
             data['procedure']['reference'],
             textdiff(d)))

if __name__ == "__main__":
    args=set(sys.argv[1:])
    null=False
    if 'null' in args:
        null=True
    if len(sys.argv)<2:
        print "%s full|fullseq|new|update|updateseq|test" % (sys.argv[0])
    if sys.argv[1]=="full":
        crawl(get_all_dossiers(), threads=4)
    elif sys.argv[1]=="fullseq":
        crawlseq(get_all_dossiers(), null=null)
    elif sys.argv[1]=="newseq":
        crawlseq(get_new_dossiers(), null=null)
    elif sys.argv[1]=="new":
        crawl(get_new_dossiers())
    elif sys.argv[1]=="update":
        crawl(get_active_dossiers())
    elif sys.argv[1]=="updateseq":
        crawlseq(get_active_dossiers(), null=null)
    elif sys.argv[1]=="url":
        #print jdump(scrape(sys.argv[2])).encode('utf8')
        res=scrape(sys.argv[2])
        #print >>sys.stderr, pprint.pformat(res)
        save(res,[0,0])
    elif sys.argv[1]=="test":
        save(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556397"),[0,0]) # telecoms package
        #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=575084"))
        #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=589377"))
        #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556208")) # with shadow rapporteurs
        #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?reference=2011/0135(COD)")) # with shadow rapporteurs
        #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=593187")) # with shadow rapporteur
        #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556397")) # telecoms package
        sys.exit(0)
        pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=16542"))
        pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=584049")) # two rapporteurs in one committee
        pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=593435")) # with forecast
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=588286")
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=590715")
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=584049")
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=590612")
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=591258")
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=584049")
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556397") # telecoms package
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556364") # telecoms package
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556398") # telecoms package
        #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=589181") # .hu media law
