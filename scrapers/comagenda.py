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
            if ax[0] and ax[1]: res[ax[0]]=sorted(ax[1])
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
        print(ax[0], ax[1])
        #res[ax[0]]=sorted(ax[1])
        res[ax[0]]=ax[1]
    return res

def scrape(url, committee):
    comid = committee
    root=fetch(url)
    lines=[x for x in root.xpath('//td[@class="contents"]/div/*') if unws(' '.join(x.xpath('.//text()')))]
    if not len(lines): return
    if not unws(' '.join(lines[2].xpath('.//text()')))=='DRAFT AGENDA':
        log(1, "NOT DRAFT AGENDA %s in %s" % (unws(' '.join(lines[2].xpath('.//text()'))), url))
    agenda={u'committee': comid,
            u'committee_full': unws(' '.join(lines[0].xpath('.//text()'))),
            u'src': url,
        }
    i=1
    if unws(' '.join(lines[3].xpath('.//text()')))=="INTERPARLIAMENTARY COMMITTEE MEETING":
        log(2, "skipping interparl com meet")
        return
    if unws(' '.join(lines[6].xpath('.//text()'))).startswith('Room'):
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
        # TODO PROCESS
        process(item, id, db.comagenda, 'ep_comagendas', id+' - '+item['title'])
        #print(jdump(item))
        #res=db.ep_comagendas.find_one(query) or {}
        #d=diff(dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]),
        #       dict([(k,v) for k,v in item.items() if not k in ['_id', 'meta', 'changes',]]))
        #if d:
        #    now=datetime.utcnow().replace(microsecond=0)
        #    if not 'meta' in item: item[u'meta']={}
        #    if not res:
        #        log(3, (u'adding %s%s %s' % (u'%s ' % item['epdoc'] if 'epdoc' in item else '',
        #                                            item['committee'],
        #                                            item['title'])).encode('utf8'))
        #        item['meta']['created']=now
        #        if stats: stats[0]+=1
        #        notify(item,None)
        #    else:
        #        log(3, (u'updating %s%s %s' % (u'%s ' % item['epdoc'] if 'epdoc' in item else '',
        #                                            item['committee'],
        #                                            item['title'])).encode('utf8'))
        #        log(3, d)
        #        item['meta']['updated']=now
        #        if stats: stats[1]+=1
        #        item['_id']=res['_id']
        #        notify(item,d)
        #    item['changes']=res.get('changes',{})
        #    item['changes'][now.isoformat()]=d
        #    #db.ep_comagendas.save(item)
    return data

#TODO
def notify(data,d):
    if not 'epdoc' in data: return
    m=db.notifications.find({'dossiers': data['epdoc']},['active_emails'])
    for g in m:
        if len(g['active_emails'])==0:
            continue
        msg = Message("[PT-Com] %s: %s" %
                      (data['committee'],
                       data['title']),
                      sender = "parltrack@parltrack.euwiki.org",
                      bcc = g['active_emails'])
        msg.body = (u"Parltrack has detected %s%s on the schedule of %s \n"
                    u"\n  on %s"
                    u"\n%s"
                    u"%s"
                    u"\nsee the details here: %s\n"
                    u"\nYour Parltrack team" %
                    (u"a change on " if d else u'',
                     data['epdoc'],
                     data['committee'],
                     data['date'] if 'date' in data else 'unknown date',
                     ("\n  - %s" % u'\n  - '.join(data['list'])) if 'list' in data and len(data['list'])>0 else u"",
                     "\n %s" % (textdiff(d) if d else ''),
                     "%s/dossier/%s" % (ROOT_URL, data['epdoc']),
                    ))
        mail.send(msg)

if __name__ == "__main__":
    if len(sys.argv)>1:
        if sys.argv[1]=="url":
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
