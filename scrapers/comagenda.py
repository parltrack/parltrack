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

# (C) 2011 by Stefan Marsiske, <stefan.marsiske@gmail.com>, Asciimoo

from datetime import datetime
from urllib.parse import urljoin
from utils.mappings import COMMITTEE_MAP
from utils.utils import htmldiff, fetch, dateJSONhandler, unws, jdump, textdiff
from utils.log import log
from utils.objchanges import diff
from utils.process import process
import json, re, copy, unicodedata, traceback, sys
from db import db
from flask_mail import Message
from webapp import mail
from config import ROOT_URL
import notification_model as notif
from utils.notif_mail import send_html_mail

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'table': 'ep_comagendas',
    'abort_on_error': True,
}

BASE_URL = 'http://www.europarl.europa.eu'

#http://www.europarl.europa.eu/committees/en/IMCO/documents-search.html?&docType=AGEN&leg=7&miType=text
#'http://www.europarl.europa.eu/committees/en/IMCO/documents-search.html?author=&clean=false&committee=2867&docType=AGEN&leg=7&miText=&miType=text&refPe='
#'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fTEXT%2bCOMPARL%2bIMCO-OJ-20111220-1%2b01%2bDOC%2bXML%2bV0%2f%2fEN'

datere=re.compile(r'^(?:\S+ )?([0-9]{1,2} \w+ [0-9]{4}), ([0-9]{1,2}[.:][0-9]{2})( . [0-9]{1,2}[.:][0-9]{2})?')
def toTime(txt):
    m=datere.match(txt)
    if m:
        if m.group(3):
            try:
                return { 'date': datetime.strptime("%s %s" % (m.group(1), m.group(2).replace(':','.')), "%d %B %Y %H.%M"),
                         'end': datetime.strptime("%s %s" % (m.group(1), m.group(3)[3:].replace(':','.')), "%d %B %Y %H.%M")}
            except ValueError:
                log(2, "[!] unknown date %s" % txt)
                return
        else:
            return { 'date': datetime.strptime("%s %s" % (m.group(1), m.group(2).replace(':','.')), "%d %B %Y %H.%M") }

instdocre=re.compile(u'(?:(\**)(I*))?\s*([0-9A-Z/()]{12,16})?\s*([0-9A-Z/()]{12,16})?\s*(?:\[[0-9]*\])?\s*(?:–\s([-0-9A-Z/()]{12,16}))?$')
def getdocs(line):
    issue={}
    m=instdocre.search(line)
    if m.group(1):
        issue[u'procedure']=m.group(1)
    if m.group(2):
        issue[u'reading']=m.group(2)
    if m.group(3):
        issue[u'epdoc']=m.group(3)
        dossier=db.dossier(m.group(3))
        if dossier:
            issue[u'docref']=dossier['procedure']['reference']
    if m.group(4):
        dossiers=db.get('dossiers_by_doc', m.group(4)) or []
        dossier = None if not dossiers else dossiers[0]
        if dossier:
            issue[u'docref']=dossier['procedure']['reference']
            issue[u'comdoc']=m.group(4)
        else:
            issue[u'comdoc']=m.group(4)
    if m.group(5):
        issue[u'otherdoc']=m.group(5)
    return issue

def getdoclist(node):
    txt=[x for x in node.xpath('.//text()') if unws(x)]
    i=0
    res=[]
    while i+1 < len(txt):
        if unws(txt[i])[-1]==u"\u2013":
            res.append({u'type': unws(txt[i])[:-2],
                        u'title': unws(txt[i+1]),
                        u'url': urljoin(BASE_URL, txt[i+1].getparent().get('href'))})
            i+=2
        elif len(unws(txt[i]).split(u" \u2013 "))>1:
            res.append({u'type': unws(txt[i].split(u" \u2013 ")[0]),
                        u'title': unws(txt[i].split(u" \u2013 ")[1] if len(txt[i].split(u" \u2013 "))>1 else u'')})
            i+=1
        else:
            i+=1
    if i < len(txt) and len(unws(txt[i]).split(u" \u2013 "))>1:
        res.append({u'type': unws(txt[i]).split(u" \u2013 ")[0],
                    u'title': unws(txt[i]).split(u" \u2013 ")[1]})
    return res

def getactors(node):
    res={}
    ax=[None,[]]
    for row in node.xpath('.//tr'):
        cells=row.xpath('./td/p')
        if not cells: continue

        # get role Rapporteur|Responsible|Rapporteur for the opinion|Opinions
        role=cells[0].xpath('text()')
        if role and unws(role[0]):
            #print(ax[1])
            if ax[0] and ax[1]: res[ax[0]]=sorted(ax[1], key=lambda x: x.get('name', ''))
            tmp=unws(role[0])[:-1]
            if tmp=="Rapporteur for the opinion":
                tmp="Rapporteur"
            ax=[tmp,[]]

        tmp=unws((cells[1].xpath('text()') or [''])[0])
        if ax[0] in ["Rapporteur", "Rapporteur for the opinion"] and tmp:
            name=' '.join(tmp.split()[:-1])
            item={u'group': tmp.split()[-1][1:-1],
                  u'name': name,
                  u'mepref': getMEPRef(name) }
            if len(cells)>2:
                item[u'docs']=getdoclist(cells[2])
            ax[1].append(item)
            continue
        if ax[0] in ["Opinions", "Responsible"] and tmp:
            tmp1=tmp.split(u' –',1)
            if len(tmp1)==2:
                (comid, rest)=tmp1
            elif len(tmp1)==1:
                if len(tmp1[0])==4 and tmp1[0].isupper():
                    (comid, rest)=(tmp1,'')
                elif len(tmp1[0])>4 and tmp1[0][4] in ['-', u'–', u':', u'*'] and tmp1[0][:4].isupper():
                    (comid, rest)=(tmp1[:4],tmp1[5:])
                else:
                    skip=False
                    for com in tmp.split(', '):
                        if com in COMMITTEE_MAP and len(com)==4:
                            ax[1].append({u'comid': com})
                            skip=True
                    if skip:
                        continue
            else:
                log(2, "[!] unknown committee: %s" % tmp)
                raise
            if not comid:
                log(2, "[!] unknown committee: %s" % tmp)
            item={u'comid': comid}
            if rest==' Decision: no opinion':
                item[u'response']=u'Decision: no opinion'
            if not rest and len(comid)>4:
                for com in comid.split(', '):
                    ax[1].append({u'comid': com})
                continue
            if len(cells)>2:
                tmp=unws((cells[2].xpath('text()') or [None])[0])
                if tmp:
                    name=' '.join(tmp.split()[:-1])
                    item.update({u'group': tmp.split()[-1][1:-1],
                                 u'name': name,
                                 u'mepref': getMEPRef(name)})
                    if len(cells)>3:
                        item[u'docs']=getdoclist(cells[3])
            ax[1].append(item)
    if ax[0] and ax[1]:
        #print(ax[0], ax[1])
        #res[ax[0]]=ax[1]
        res[ax[0]]=sorted(ax[1], key=lambda x: x.get('name', ''))
    return res

def scrape(url, committee, **kwargs):
    comid = committee
    root=fetch(url)
    lines=[x for x in root.xpath('//td[@class="contents"]/div/*') if unws(' '.join(x.xpath('.//text()')))]
    lines=[x for x in lines if unws(' '.join(x.xpath('.//text()'))) not in ['<EPHeader>', '</EPHeader>']]
    if not len(lines): return
    if not unws(' '.join(lines[2].xpath('.//text()'))) in ['DRAFT AGENDA', '<TitreType> DRAFT AGENDA </TitreType>' ]:
        log(3, "not DRAFT AGENDA %s in %s" % (unws(' '.join(lines[2].xpath('.//text()'))), url))
    agenda={u'committee': comid,
            u'committee_full': unws(' '.join(lines[0].xpath('.//text()'))),
            u'src': url,
        }
    i=1
    if unws(' '.join(lines[3].xpath('.//text()')))=="INTERPARLIAMENTARY COMMITTEE MEETING":
        log(2, "skipping interparl com meet")
        return
    if len(lines)>=7 and unws(' '.join(lines[6].xpath('.//text()'))).startswith('Room'):
            agenda.update({u'docid': unws(' '.join(lines[1].xpath('.//text()'))),
                           u'type': unws(' '.join(lines[3].xpath('.//text()'))),
                           u'time': toTime(unws(' '.join(lines[4].xpath('.//text()')))),
                           u'city': unws(' '.join(lines[5].xpath('.//text()'))),
                           u'room': unws(' '.join(lines[6].xpath('.//text()')))[6:],
                           })
            i=7
    itemcnt=0
    item={}
    schedule=None
    res=[]
    while i < len(lines):
        line=lines[i]
        i+=1
        txt=unws(' '.join(line.xpath('.//text()')))
        if txt in ['* * *', '***']:
            continue # skip end of schedule block

        # 20 December 2011, 16.00 – 16.30
        tmp=toTime(txt)
        if tmp:
            schedule=tmp
            if i<len(lines) and unws(' '.join(lines[i].xpath('.//text()'))) == 'In camera':
                schedule[u'incamera']=True
                i+=1
            continue

        if line.tag=='div':
            item[u'actors']=getactors(line)
            continue
        firsttoken=txt.split()[0]
        # 6. Alternative dispute resolution for consumer disputes and
        #    amending Regulation (EC) No 2006/2004 and Directive
        #    2009/22/EC (Directive on consumer ADR)
        if firsttoken[-1]=='.' and firsttoken[:-1].isdigit() and itemcnt+1==int(firsttoken[:-1]):
            if item: res.append(item)
            itemcnt+=1
            item=copy.deepcopy(agenda)
            item.update({u'title': ' '.join(txt.split()[1:]),
                         u'seq_no': itemcnt,})
            if schedule:
                item.update(schedule)
            continue
        # trailing list of "details"
        # · Presentation by the Commission of the proposal & Impact Assessment
        # · Exchange of views
        if firsttoken==u"·":
            if not 'list' in item: item[u'list']=[]
            tmp=' '.join(txt.split()[1:])
            if tmp.startswith('Deadline for tabling amendments:'):
                try:
                    item[u'tabling_deadline']=datetime.strptime(tmp.split(':')[1].strip(),"%d %B %Y, %H.%M")
                except ValueError:
                    try:
                        item[u'tabling_deadline']=datetime.strptime(tmp.split(':')[1].strip(),"%d.%m.%Y at %H.%M")
                    except:
                        log(2, '[$] unknown tabling deadline format %s' % unws(tmp))
            item[u'list'].append(tmp)
            continue
        # committee dossier
        # IMCO/7/08130
        if txt.startswith("%s/7/" % comid) and len(txt)==12:
            item[u'comdossier']=txt
            continue
        # ***I    2011/0373(COD)       COM(2011)0793 – C7-0454/2011
        tmp=getdocs(txt)
        if tmp:
            item.update(tmp)
            continue
        # fall-through line
        log(4, "(falltrough) %s %s" % (line.tag, txt.encode('utf8')))
    if item: res.append(item)
    save(res)
    return res

def getMEPRef(name):
    if not name: return
    mep=db.mep(name)
    if mep:
        return mep['UserID']
    else:
        log(2, '[!] lookup oops %s' % name.encode('utf8'))

def save(data):
    for item in data:
        if not 'committee' in item: continue
        d = None
        if 'date' in item:
            d = item['date']
        elif 'end' in item:
            d = item['end']
        elif 'time' in item:
            d = item['time']

        if not isinstance(d, str):
            d = str(d)

        id = item['committee']+d+str(item['seq_no'])
        item['id'] = id
        process(item, id, db.comagenda, 'ep_comagendas', id+' - '+item['title'], onchanged=onchanged)
    return data

def onchanged(doc, diff):
    if not 'epdoc' in doc: return
    id = doc['epdoc']
    dossiers = notif.session.query(notif.Item).filter(notif.Item.name==id).all()
    recipients = set()
    for i in dossiers:
        for s in i.group.subscribers:
            recipients.add(s.email)
    if not recipients:
        return
    log(3, "sending comagenda changes to " + ', '.join(recipients))
    #(recepients, subject, change, date, url)
    send_html_mail(
        recipients=list(recipients),
        subject="[PT-Com] %s: %s" % (doc['committee'],doc['title']),
        obj = doc,
        change=diff,
        date=(sorted(doc['changes'].keys()) or ['unknown'])[-1],
        url='%scommittee/%s' % (ROOT_URL, doc['committee']),
        text=''.join((u"Parltrack has detected %s%s on the schedule of %s \n"
                    u"\n  on %s"
                    u"\n%s"
                    u"%s"
                    u"\nsee the details here: %s\n"
                    u"\nYour Parltrack team" %
                    (u"a change on " if diff else u'',
                     doc['epdoc'],
                     doc['committee'],
                     doc['date'] if 'date' in doc else 'unknown date',
                     ("\n  - %s" % u'\n  - '.join(doc['list'])) if 'list' in doc and len(doc['list'])>0 else u"",
                     "\n %s" % (textdiff(diff) if diff else ''),
                     "%sdossier/%s" % (ROOT_URL, doc['epdoc']),
                    )))
    )

from utils.process import publish_logs
def onfinished(daisy=True):
    publish_logs(get_all_jobs)

if __name__ == "__main__":
    if len(sys.argv)>1:
        if sys.argv[1]=='url' and len(sys.argv)==4:
            print(jdump(scrape(sys.argv[2], sys.argv[3])))
            sys.exit(0)
        elif sys.argv[1]=="url":
            print('-'*30)
            print(jdump(scrape(sys.argv[2], 'XXXX')))
            print('-'*30)
            sys.exit(0)
        if sys.argv[1]=="test":
            #print(jdump([(u,d) for u,d in getComAgendas()]))
            print(jdump(scrape('http://www.europarl.europa.eu/sides/getDoc.do?type=COMPARL&reference=LIBE-OJ-20120112-1&language=EN', 'LIBE')))
            #import code; code.interact(local=locals());
            sys.exit(0)
        elif sys.argv[1]=='url' and len(sys.argv)==4:
            print(jdump(scrape(sys.argv[2], sys.argv[3])))
            sys.exit(0)

    # handle opts
    #args=set(sys.argv[1:])
    #saver=jdump
    #if 'save' in args:
    #    saver=save
    #if 'seq' in args:
    #    res=seqcrawler(saver=saver)
    #else:
    #    crawler(saver=saver)
