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
from urlparse import urljoin
from mappings import COMMITTEE_MAP
from parltrack.utils import diff, htmldiff, fetch, dateJSONhandler, unws, Multiplexer, logger, jdump
import json, re, copy, unicodedata, traceback, sys
from parltrack.db import db

BASE_URL = 'http://www.europarl.europa.eu'

#http://www.europarl.europa.eu/committees/en/IMCO/documents-search.html?&docType=AGEN&leg=7&miType=text
#'http://www.europarl.europa.eu/committees/en/IMCO/documents-search.html?author=&clean=false&committee=2867&docType=AGEN&leg=7&miText=&miType=text&refPe='
#'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fTEXT%2bCOMPARL%2bIMCO-OJ-20111220-1%2b01%2bDOC%2bXML%2bV0%2f%2fEN'

datere=re.compile(r'^(?:\S+ )?([0-9]{1,2} \w+ [0-9]{4}), ([0-9]{1,2}[.:][0-9]{2})( . [0-9]{1,2}[.:][0-9]{2})?')
def toTime(txt):
    m=datere.match(txt)
    if m:
        if m.group(3):
            return { 'date': datetime.strptime("%s %s" % (m.group(1), m.group(2).replace(':','.')), "%d %B %Y %H.%M"),
                     'end': datetime.strptime("%s %s" % (m.group(1), m.group(3)[3:].replace(':','.')), "%d %B %Y %H.%M")}
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
        dossier=db.dossiers2.find_one({'procedure.reference': m.group(3)})
        if dossier:
            issue[u'docref']=dossier['_id']
            issue[u'epdoc']=m.group(3)
        else:
            issue[u'epdoc']=m.group(3)
    if m.group(4):
        dossier=db.dossiers2.find_one({'activities.docs.title': m.group(4)})
        if dossier:
            issue[u'docref']=dossier['_id']
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
                        u'title': unws(txt[i].split(u" \u2013 ")[1])})
            i+=1
        else:
            i+=1
    if i < len(txt) and len(unws(txt[i]).split(u" \u2013 "))>1:
        res.append({u'type': unws(txt[i].split(u" \u2013 ")[0]),
                    u'title': unws(txt[i].split(u" \u2013 ")[1])})
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

        tmp=unws((cells[1].xpath('text()') or [None])[0])
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
                skip=False
                for com in tmp.split(' ,'):
                    if com in COMMITTEE_MAP and len(com)==4:
                        ax[1].append({u'comid': com})
                        skip=True
                if skip:
                    continue
            else:
                logger.warn("[!] unknown committee: %s" % tmp)
                raise
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
    if ax[0] and ax[1]: res[ax[0]]=sorted(ax[1])
    return res

def scrape(url, comid):
    root=fetch(url)
    lines=[x for x in root.xpath('//td[@class="contents"]/div/*') if unws(' '.join(x.xpath('.//text()')))]
    if not len(lines): return
    if not unws(' '.join(lines[2].xpath('.//text()')))=='DRAFT AGENDA':
        logger.error("NOT DRAFT AGENDA %s" % unws(' '.join(lines[2].xpath('.//text()'))))
    agenda={u'committee': comid,
            u'committee_full': unws(' '.join(lines[0].xpath('.//text()'))),
            u'src': url,
        }
    i=1
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
            item.update({'title': ' '.join(txt.split()[1:]),
                         'seq_no': itemcnt,})
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
                        logger.warn('[$] unknown tabling deadline format', tmp.split(':')[1].strip())
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
        logger.debug("(falltrough) %s %s" % (line.tag, txt.encode('utf8')))
    if item: res.append(item)
    return res

def getMEPRef(name, retfields=['_id']):
    if not name: return
    mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.split()).lower()},retfields)
    if not mep and u'ß' in name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower()},retfields)
    if not mep and unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore')!=name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore').split()).lower()},retfields)
    if not mep:
        mep=db.ep_meps.find_one({'Name.aliases': re.compile(''.join([x if x<128 else '.' for x in name]),re.I)},retfields)
    if not mep:
        mep=db.ep_meps2.find_one({'Name.aliases': ''.join(name.split()).lower()},retfields)
    if not mep and u'ß' in name:
        mep=db.ep_meps2.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower()},retfields)
    if not mep:
        mep=db.ep_meps2.find_one({'Name.aliases': re.compile(''.join([x if x<128 else '.' for x in name]),re.I)},retfields)
    if mep:
        return mep['_id']
    else:
        logger.warn('[!] lookup oops %s' % name.encode('utf8'))

def getComAgendas():
    urltpl="http://www.europarl.europa.eu/committees/en/%s/documents-search.html?&docType=AGEN&leg=7&miType=text"
    nexttpl="http://www.europarl.europa.eu/committees/en/%s/documents-search.html?tabActif=tabLast&startValue=%s"
    for com in (k for k in COMMITTEE_MAP.keys() if len(k)==4 and k not in ['CODE', 'RETT']):
        url=urltpl % (com)
        i=0
        agendas=[]
        logger.info('scraping %s' % com)
        while True:
            logger.info("crawling %s" % (url))
            root=fetch(url)
            tmp=[(a.get('href'), unws(a.xpath('text()')[0]))
                 for a in root.xpath('//p[@class="title"]/a')
                 if len(a.get('href',''))>13]
            if not tmp: break
            for u,_ in tmp:
                yield (u,com)
            i+=10
            url=nexttpl % (com,i)

def save(data, stats):
    for item in data:
        if not 'committee' in item: continue
        res=db.ep_comagendas.find_one({'committee': item['committee'],
                                       'src': item['src'],
                                       'title': item['title']}) or {}
        d=diff(dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]),
               dict([(k,v) for k,v in item.items() if not k in ['_id', 'meta', 'changes',]]))
        if d:
            now=unicode(datetime.utcnow().replace(microsecond=0).isoformat())
            if not 'meta' in item: item[u'meta']={}
            if not res:
                logger.info((u'adding %s,%s' % (item['committee'], item['seq_no'])).encode('utf8'))
                item['meta']['created']=now
                if stats: stats[0]+=1
            else:
                logger.info((u'updating %s,%s' % (item['committee'], item['seq_no'])).encode('utf8'))
                logger.info(d)
                item['meta']['updated']=now
                if stats: stats[1]+=1
                item['_id']=res['_id']
            item['changes']=res.get('changes',{})
            item['changes'][now]=d
            db.ep_comagendas.save(item)
    if stats: return stats
    else: return data

def crawler(saver=jdump,threads=4):
    m=Multiplexer(scrape,saver,threads=threads)
    m.start()
    [m.addjob(url, data) for url, data in getComAgendas()]
    m.finish()
    logger.info('end of crawl')

def seqcrawler(saver=jdump):
    for u, com in getComAgendas():
        try:
            print saver(scrape(u,com), None).encode('utf8')
        except:
            # ignore failed scrapes
            logger.warn("[!] failed to scrape: %s" % u)
            logger.warn(traceback.format_exc())

if __name__ == "__main__":
    if len(sys.argv)>1:
        if sys.argv[1]=="test":
            print jdump(scrape('http://www.europarl.europa.eu/sides/getDoc.do?type=COMPARL&reference=ECON-OJ-20120109-1&language=EN', 'ECON')).encode('utf8')
            print jdump(scrape('http://www.europarl.europa.eu/sides/getDoc.do?type=COMPARL&reference=LIBE-OJ-20120112-1&language=EN', 'LIBE')).encode('utf8')
            #import code; code.interact(local=locals());
            sys.exit(0)
        elif sys.argv[1]=='url' and len(sys.argv)==4:
            print jdump(scrape(sys.argv[2], sys.argv[3]))
            sys.exit(0)

    # handle opts
    args=set(sys.argv[1:])
    saver=jdump
    if 'save' in args:
        saver=save
    if 'seq' in args:
        res=seqcrawler(saver=saver)
        if 'dry' in args:
            print "[%s]" % ',\n'.join(res).encode('utf8')
    else:
        crawler(saver=saver)
