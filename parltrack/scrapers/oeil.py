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

from lxml.html.soupparser import parse
from lxml.etree import tostring
from urlparse import urljoin
from itertools import izip, izip_longest
import urllib2, urllib, cookielib, datetime, sys, re, feedparser
from operator import itemgetter
from flaskext.mail import Message
from parltrack.webapp import mail
from parltrack.utils import diff, htmldiff
from parltrack.default_settings import ROOT_URL
from parltrack.scrapers.mappings import ipexevents, COMMITTEE_MAP
from saver import save_dossier

import unicodedata
try:
    from parltrack.environment import connect_db
    db = connect_db()
except:
    import pymongo
    db=pymongo.Connection().parltrack
from bson.objectid import ObjectId
from parltrack.scrapers.ipex import IPEXMAP

db.dossiers2.ensure_index([('procedure.reference', 1)])
db.dossiers2.ensure_index([('procedure.title', 1)])
db.dossiers2.ensure_index([('activities.actors.mepref', 1)])
db.dossiers2.ensure_index([('activities.actors.commitee', 1)])
db.dossiers2.ensure_index([('meta.created', -1)])
db.dossiers2.ensure_index([('meta.updated', -1)])

# and some global objects
base = 'http://www.europarl.europa.eu/oeil/file.jsp'
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()))
#opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()),
#                              urllib2.ProxyHandler({'http': 'http://localhost:8123/'}))
opener.addheaders = [('User-agent', 'weurstchen/0.6')]

def getMEPRef(name, retfields=['_id']):
    if not name: return
    mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.split()).lower()},retfields)
    if not mep and u'ß' in name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower()},retfields)
    if not mep and unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore')!=name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore').split()).lower()},retfields)
    if not mep:
        mep=db.ep_meps.find_one({'Name.aliases': re.compile(''.join([x if x<128 else '.' for x in name]),re.I)},retfields)
    if mep:
        return mep['_id']
    else:
        print >>sys.stderr, '[!] lookup oops', name.encode('utf8')

def fetch(url, retries=5):
    # url to etree
    try:
        f=opener.open(url)
    except (urllib2.HTTPError, urllib2.URLError), e:
        if hasattr(e, 'code') and e.code>=400 and e.code not in [504]:
            print >>sys.stderr, "[!] %d %s" % (e.code, url)
            raise
        if retries>0:
            f=fetch(url,retries-1)
        else:
            raise
    return parse(f)

def toDate(node):
    for br in node.xpath("br"):
        br.text="\n"
    lines=[x.replace(u"\u00A0",' ').strip() for x in node.xpath(".//text()") if x.replace(u"\u00A0",' ').strip()]
    if len(lines)>1:
        result=[]
        for text in lines:
            if not len(text): continue
            value=[int(x) for x in text.split('/') if len(x)]
            result.append(unicode(datetime.date(value[2], value[1], value[0]).isoformat()))
        return result
    elif len(lines)==1:
        text=lines[0]
        if not len(text): return None
        value=[int(x) for x in text.split('/') if len(x)]
        return unicode(datetime.date(value[2], value[1], value[0]).isoformat())
    return None

def toText(node):
    for br in node.xpath("br"):
        br.text="\n"
    if node is None: return ''
    text=u' '.join(u' '.join([x.strip() for x in node.xpath(".//text()") if x.strip()]).replace(u"\u00A0",' ').split())

    links=node.xpath('a')
    if not links: return text
    return {'title': text, 'url': unicode(urljoin(base,links[0].get('href')),'utf8')}

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
    for row in table.xpath('.//tr'):
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
            (u'doc', toText),
            (u'date', toDate),
            (u'text', toText),
            )
epagents=( (u'committee', toText),
           (u'rapporteur', toLines),
           (u'date', toDate),
           )
cslagents=( (u'council', toText),
           (u'meeting_id', toText),
           (u'date', toDate),
           )
ecagents=( (u'dg', toText),
           (u'commissioner', toText),
           )
instmap={'European Parliament': u'EP',
         'European Commission': u'EC',
         'Council of the European Union': u'CSL',
         'Council of the EU': u'CSL',
         'Other institutions': u'x!x',
         }
otherinst={'Economic and Social Committee': u'ESOC',
           'European Data Protecion Supervisor': u'EDPS',
           'Court of Justice of the European Communities': u'CJEC',
           'Court of Justice of the European Union': u'CJEU',
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
             
             'Final act signed by Parliament and Council': u'EP/CSL',
             'Joint text approved by Conciliation Committee co-chairs': u'EP/CSL',
             'Final decision by Conciliation Committee': u'EP/CSL',
             'Formal meeting of Conciliation Committee': u'EP/CSL',
             
             'Legislative proposal published': u'EC',
             'Modified legislative proposal published': u'EC',
             
             'Results of vote in Parliament': u'EP',
             'Debate in Parliament': u'EP',
             'Debate scheduled': u'EP',
             'Vote scheduled': u'EP',
             'Indicative plenary sitting date, 1st reading/single reading': u'EP',
             'Deadline for 2nd reading in plenary': u'EP',
             'Decision by Parliament, 1st reading/single reading': u'EP',
             'Decision by Parliament, 2nd reading': u'EP',
             'Decision by Parliament, 3rd reading': u'EP',
             'Committee referral announced in Parliament, 1st reading/single reading': u'EP',
             'Committee report tabled for plenary, 1st reading/single reading': u'EP',
             'Vote in committee, 1st reading/single reading': u'EP',
             'Committee recommendation tabled for plenary, 2nd reading': u'EP',
             'Committee referral announced in Parliament, 2nd reading': u'EP',
             'Vote in committee, 2nd reading': u'EP',
             'Report tabled for plenary, 3rd reading': u'EP',
             'End of procedure in Parliament': u'EP',
             }

def merge_events(events,committees):
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
                    item[u'body']=''
            # new institution for this date
            if not item['body'] in actors:
                # new body for this date
                actors[item['body']]=item
                if 'doc' in actors[item['body']]:
                    doc=merge_new_doc(actors[item['body']]['doc'], item)
                    del actors[item['body']]['doc']
                    actors[item['body']][u'docs']=[doc]
                cmts=getCommittee(item,committees)
                if cmts:
                    actors[item['body']][u'committees']=cmts
                continue
            # merge any docs
            if 'doc' in item:
                doc=merge_new_doc(item['doc'], item)
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
        return sorted([c for c in committees if c.get('committee')!="CODE"])
    if item['type'] in ['Committee recommendation tabled for plenary, 2nd reading',
                        'Committee referral announced in Parliament, 2nd reading',
                        'Vote in committee, 2nd reading']:
        return sorted([c for c in committees if c.get('committee')!="CODE" and c.get('responsible')==True])
    if item['type'] in ['Draft report by Parliament delegation to the Conciliation Committee',
                        'Joint text approved by Conciliation Committee co-chairs',
                        'Final decision by Conciliation Committee',
                        'Formal meeting of Conciliation Committee']:
        return sorted([c for c in committees if c.get('committee')=="CODE"])

def scrape(url):
    try:
        logger.info('scrape '+url)
        tree=fetch(url)
        agents,committees=scrape_actors(tree)
        forecasts=lst2obj((tree.xpath('//table[@id="forecast"]') or [None])[0],forecastFields)
        events=scrape_events(tree)
        procedure=scrape_basic(tree)
        ipext=[]
        for ipexd in (IPEXMAP[procedure['reference']] or {}).get('Dates',[]):
            skip=False
            for event in forecasts+events:
                if event['type']==ipexevents.get(ipexd['type'],{}).get('oeil','asdf') and event['date']==ipexd['date']:
                    skip=True
                    break
            if skip: continue
            ipext.append(ipexd)
        allevents=agents+scrape_docs(tree)+events+forecasts+ipext
        other=[x for x in allevents if not x.get('date')]
        allevents=sorted([x for x in allevents if x.get('date')],key=itemgetter('date'))
        allevents=merge_events(allevents,committees)
        res={u'meta': {'source': url,
                       'id': int(url.split('id=')[1]),
                       'timestamp': datetime.datetime.utcnow() },
             u'procedure': procedure,
             u'links': form2obj((tree.xpath('//table[@id="external_links"]') or [None])[0]),
             u'committees': committees,
             u'activities': sorted(allevents, key=itemgetter('date')),
             u'other': other,
             }
        # check for "final act"
        finalas=tree.xpath('//div[@id="final_act"]//a')
        final={}
        for link in finalas:
            if link.get('class')=='sumbutton':
                try: summary=fetch("http://www.europarl.europa.eu%s" % link.get('href'))
                except: continue
                final['text']=[tostring(x) for x in summary.xpath('//div[@id="summary"]')]
            else:
                if not 'docs' in final: final['docs']=[]
                final['docs'].append({'title': link.xpath('text()')[0].strip(),
                                     'url': link.get('href')})
        if final:
            res[u'procedure'][u'final']=final['docs'][0]
            for item in res['activities']:
                if item.get('type')==u'Final act published in Official Journal':
                    if final.get('text'):
                        item[u'text']=final['text']
                    if not 'docs' in item:
                        item[u'docs']=[final['docs'][1]]
                    else:
                        item[u'docs'].append(final['docs'][1])
                    break
        return res
    except:
        logger.error(traceback.format_exc())
        return

def scrape_basic(tree):
    res=form2obj(tree.xpath('//table[@id="technicalInformations"]')[0],detailsheaders)
    table=(tree.xpath('//table[@id="basic_information"]') or [None])[0]
    if table is not None: return
    res.update({ 'stage_reached': (table.xpath('.//p[@class="pf_stage"]/text()') or [''])[0].strip(),
                 'reference': (table.xpath('.//span[@class="basic_reference"]/text()') or [''])[0].strip(),
                 'type': (table.xpath('.//p[@class="basic_procedurefile"]/text()') or [''])[0].strip(),
                 'title': (table.xpath('.//p[@class="basic_title"]/text()') or [''])[0].strip(),
                 })
    if '' in res:
        del res['']
    if 'legal_basis' in res:
        res[u'legal_basis']=sorted((x.strip() for x in res['legal_basis'].split(';')))
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
            attrib=u' '.join(elem.xpath('text()')[0].split()).lower().replace(u" ",u"_")
            if attrib:
                res[attrib]=[]
    return res

def scrape_events(tree):
    res=[]
    for item in lst2obj((tree.xpath('//table[@id="key_events"]') or [None])[0],eventFields):
        if item.get('text'):
            try: summary=fetch(item['text']['url'])
            except: continue
            item['text']=[tostring(x) for x in summary.xpath('//div[@id="summary"]')]
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
                    doc[u'text']=[tostring(x) for x in summary.xpath('//div[@id="summary"]')]
                res.append(doc)
        elif inst != 'All documents':
            print "[!] unrecognized tab in documents", inst
    return res

def scrape_actors(tree):
    insts=tree.xpath('//td[@class="players_institution" or @class="players_institution inst_separator"]')
    agents=[]
    meps=[]
    for inst in insts:
        inst_name=''.join([x.strip() for x in inst.xpath('.//text()')])
        for table in inst.xpath('following-sibling::td/table'):
            if inst_name == 'European Parliament':
                #meps.extend([x for x in scrape_epagents(table) if x not in meps])
                meps.extend(scrape_epagents(table))
            # Handle council
            elif inst_name == 'Council of the European Union':
                for agent in lst2obj(table, cslagents, 1):
                    agent['body']='CSL'
                    agents.append(agent)
            # and commission
            elif inst_name == 'European Commission':
                for agent in lst2obj(table, ecagents, 1):
                    agent['body']='EC'
                    agents.append(agent)
            else:
                "[!] wrong institution name", inst_name
    return (agents, sorted(meps))

def scrape_epagents(table):
    heading=''.join(table.xpath('.//td[@class="players_committee"]')[0].xpath(".//text()")).strip()
    responsible=None
    if heading in [ "Committee responsible", "Former committee responsible"]:
        responsible=True
    elif heading in ["Committee for opinion", "Former committee for opinion"]:
        responsible=False
    else:
        print "[!] unknown committee heading", heading

    # remove tooltips
    [tip.xpath('..')[0].remove(tip) for tip in table.xpath('.//span[@class="tiptip"]')]

    # handle shadows
    shadowelems=table.xpath('//a[@id="shadowRapporteurHeader"]/../following-sibling::div/p//span[@class="players_rapporter_text"]/a')
    shadows={}
    for shadow in shadowelems:
        committee=shadow.xpath('./ancestor::td/preceding-sibling::td//acronym/text()')[0]
        if not committee in shadows: shadows[committee]=[]
        mep={u'name': shadow.xpath('text()')[0] }
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
        agent[u'body']='EP'

        if agent.get('rapporteur',[''])[0].strip().startswith("The committee decided not to give an opinion"):
            del agent['rapporteur']
            agent[u'opinion']=None
        elif agent.get('rapporteur'):
            meps=[]
            for mep in agent['rapporteur']:
                tmp=getMEPRef(mep)
                if tmp:
                    meps.append({u'mepref': tmp,
                                 u'name': mep})
                else:
                    raise IndexError
            agent[u'rapporteur']=meps

        abbr=agent['committee'][:4]
        if not abbr in COMMITTEE_MAP.keys():
            print "[!] uknown committee abbrev", abbr
            agent[u'committee_full']=agent['committee']
            del agent['committee']
        else:
            agent[u'committee_full']=agent['committee'][4:]
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
        yield (item.link, item.title)

def get_all_dossiers():
    for year in xrange(datetime.date.today().year, 1972, -1):
        tree=fetch('http://www.europarl.europa.eu/oeil/widgets/resultwidget.do?lang=en&noHeader=false&q=objectReferenceN:N-%s/????\(*\)'
                   % (year))
        count=int(tree.xpath('//span[@class="resultNumber"]/text()')[0].strip())
        tree=fetch('http://www.europarl.europa.eu/oeil/widgets/resultwidget.do?lang=en&limit=%s&noHeader=false&q=objectReferenceN:N-%s/????\(*\)'
                   % (count,year))
        links=tree.xpath('//a[@class="reference rssEntry_id rssEntry_title rssEntry_updated"]')
        for link in links:
            yield (urljoin(base,link.get('href')),
                   (link.xpath('text()') or [''])[0])

def crawl(urls, threads=4):
    m=Multiplexer(scrape,save, threads=threads)
    m.start()
    [m.addjob(url) for url, title in urls]
    m.finish()
    logger.info('end of crawl')

def crawlseq(urls):
    [save(scrape(url),[0,0]) for url, title in urls]
    logger.info('end of crawl')

from multiprocessing import Pool, Process, JoinableQueue, log_to_stderr
from multiprocessing.sharedctypes import Value
from ctypes import c_bool
from Queue import Empty
from logging import DEBUG, WARN, INFO
import traceback
logger = log_to_stderr()
logger.setLevel(INFO)

class Multiplexer(object):
    def __init__(self, worker, writer, threads=4):
        self.worker=worker
        self.writer=writer
        self.q=JoinableQueue()
        self.done = Value(c_bool,False)
        self.consumer=Process(target=self.consume)
        self.pool = Pool(threads)

    def start(self):
        self.done.value=False
        self.consumer.start()

    def addjob(self, url):
        try:
           return self.pool.apply_async(self.worker,[url],callback=self.q.put)
        except:
            logger.error('[!] failed to scrape '+ url)
            logger.error(traceback.format_exc())
            raise

    def finish(self):
        self.pool.close()
        logger.info('closed pool')
        self.pool.join()
        logger.info('joined pool')
        self.done.value=True
        self.consumer.join()
        logger.info('joined consumer')
        self.q.close()
        logger.info('closed q')
        self.q.join()
        logger.info('joined q')

    def consume(self):
        param=[0,0]
        while True:
            job=None
            try:
                job=self.q.get(True, timeout=1)
            except Empty:
                if self.done.value==True: break
            if job:
                param = self.writer(job, param)
                self.q.task_done()
        logger.info('added/updated: %s' % param)

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
    src=data['meta']['source']
    res=db.dossiers2.find_one({ 'meta.source' : src }) or {}
    d=diff(dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]),
           dict([(k,v) for k,v in data.items() if not k in ['_id', 'meta', 'changes',]]))
    #logger.warn(d)
    if d:
        now=datetime.datetime.utcnow().replace(microsecond=0).isoformat()
        if not res:
            print ('\tadding %s - %s' % (data['procedure']['reference'],data['procedure']['title'])).encode('utf8')
            data['meta']['created']=data['meta']['timestamp']
            del data['meta']['timestamp']
            sys.stdout.flush()
            stats[0]+=1
        else:
            print ('\tupdating  %s - %s' % (data['procedure']['reference'],data['procedure']['title'])).encode('utf8')
            data['meta']['updated']=data['meta']['timestamp']
            del data['meta']['timestamp']
            sys.stdout.flush()
            stats[1]+=1
            data['_id']=res['_id']
            #print >> sys.stderr, (d)
        m=db.notifications.find({'dossiers': data['procedure']['reference']},['active_emails'])
        for g in m:
            if len(g['active_emails'])==0:
                continue
            msg = Message("[PT] %s %s" % (data['procedure']['reference'],data['procedure']['title']),
                          sender = "parltrack@parltrack.euwiki.org",
                          #bcc = g['active_emails'])
                          bcc = ['stef@ctrlc.hu'])
            msg.html = htmldiff(data,d)
            msg.body = makemsg(data,d)
            mail.send(msg)
        data['changes']=res.get('changes',{})
        data['changes'][now]=d
        db.dossiers2.save(data)
    return stats

def printdict(d,i=0):
    if type(d)==type(list()):
        return (u'\n\t%s' % ('  '*i)).join([printdict(v,i+1) for v in d])
    if not type(d)==type(dict()):
        return unicode(d)
    res=['']
    for k,v in [(k,v) for k,v in d.items() if k not in ['mepref','comref']]:
        res.append(u"\t%s%s:\t%s" % ('  '*i,k,printdict(v,i+1)))
    return u'\n'.join(res)

def makemsg(data, d):
    res=[]
    for di in sorted(d,key=itemgetter('path')):
        if 'text' in di['path'] or 'summary' in di['path']:
            res.append(u'\nsummary text changed in %s' % '/'.join([str(x) for x in di['path']]))
            continue
        if di['type']=='changed':
            res.append(u'\nchanged %s from:\n\t%s\n  to:\n\t%s' % ('/'.join([str(x) for x in di['path']]),di['data'][0],printdict(di['data'][1])))
            continue
        res.append(u"\n%s %s:\t%s" % (di['type'], '/'.join([str(x) for x in di['path']]), printdict(di['data'])))

    dt='\n'.join(res)
    return (u"Parltrack has detected a change in %s %s on OEIL.\n\nPlease follow this URL: %s/dossier/%s to see the dossier.\n\nChanges follow\n%s\n\n\nsincerly,\nYour Parltrack team" %
            (data['procedure']['reference'],
             data['procedure']['title'],
             ROOT_URL,
             data['procedure']['reference'],
             dt))

if __name__ == "__main__":
    #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=587675")
    crawl(get_all_dossiers(), threads=8)
    #crawl(get_new_dossiers())
    #crawlseq(get_new_dossiers())
    sys.exit(0)
    pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=593187")) # with shadow rapporteurs
    pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556397")) # telecoms package
    pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=584049")) # two rapporteurs in one committee
    pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=593435")) # with forecast
    #scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=588286")
    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=590715")
    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=584049")
    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=590612")
    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=591258")
    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=584049")
    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556397") # telecoms package
    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556364") # telecoms package
    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=556398") # telecoms package
    scrape("http://www.europarl.europa.eu/oeil/popups/ficheprocedure.do?id=589181") # .hu media law
