#!/usr/bin/env python
# -*- coding: utf-8 -*-
#    This file is part of le(n)x.

#    le(n)x is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    le(n)x is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with le(n)x.  If not, see <http://www.gnu.org/licenses/>.

# (C) 2009-2011 by Stefan Marsiske, <stefan.marsiske@gmail.com>

from lxml import etree
from lxml.html.soupparser import parse
from lxml.etree import tostring
from cStringIO import StringIO
from urlparse import urljoin
from itertools import izip_longest
from ctypes import c_int
import urllib2, urllib, cookielib
import datetime, sys, json, pymongo, traceback
from logging import DEBUG
import logging

logger = logging.getLogger(__name__)

def save(data):
    pprint.pprint(data)
    src=data['meta']['source']
    return

    res=docs.find_one({ 'source' : src }) or {}
    d=diff(dict([(k,v) for k,v in data.items() if not k in ['_id', 'meta', 'changes',]]),
           dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]))
    if d:
        if not res:
            logger.info('adding '+ data['procedure']['title'])
            stats[0]+=1
        else:
            logger.info( 'updating '+ data['procedure']['title'])
            stats[1]+=1
            data['_id']=res['_id']
        logger.info(d)
        data['changes']=res.get('changes',{})
        data['changes'][now]=d
        docs.save(data)
        return stats
    return stats

def diff(e1,e2):
    if type(e1) == str:
       e1=unicode(e1,'utf8')
    if type(e1) == tuple:
       e1=list(e1)
    if type(e1) != type(e2):
        return {'new': e1, 'old': e2}
    if type(e1) == list:
        return filter(None,[diff(*k) for k in izip_longest(sorted(e1),sorted(e2))])
    if type(e1) == dict:
        res=[]
        for k in set(e1.keys() + e2.keys()):
            if k == '_id': continue
            r=diff(e1.get(k),e2.get(k))
            if r:
                res.append((k,r))
        return dict(res)
    if e1 != e2:
        return {'new': e1, 'old': e2}
    return

def fetch(url):
    # url to etree
    f=urllib2.urlopen(url)
    #raw=tidy.parseString(raw,
    #        **{'output_xhtml' : 1,
    #           'output-encoding': 'utf8',
    #           'add_xml_decl' : 1,
    #           'indent' : 0,
    #           'tidy_mark' : 0,
    #           'doctype' : "strict",
    #           'wrap' : 0})
    return parse(f)

def toDate(node):
    text=node.xpath("string()").replace(u"\u00A0",' ').strip()
    if text is None or not len(text): return
    lines=text.split('\n')
    if len(lines)>1:
        result=[]
        for text in lines:
            if not len(text.strip()): continue
            value=[int(x) for x in text.strip().split('/') if len(x)]
            result.append(datetime.date(value[2], value[1], value[0]))
        return result
    else:
        if not len(text.strip()): return None
        value=[int(x) for x in text.strip().split('/') if len(x)]
        return datetime.date(value[2], value[1], value[0])

def toText(node):
    if node is None: return ''
    text=node.xpath("string()").replace(u"\u00A0",' ').strip()

    links=node.xpath('a')
    if not links: return text
    return {'title': text, 'url': unicode(urljoin(base,links[0].get('href')),'utf8')}

def toLines(node):
    text=toText(node).split('\n')
    if len(text)==1:
        return text[0]
    else: return text

def urlFromJS(node):
    a=node.xpath('a')
    if(a and
       (a[0].get('href').startswith('javascript:OpenNewPopupWnd(') or
        a[0].get('href').startswith('javascript:ficheUniquePopUp('))):
        return urljoin(base,(a[0].get('href').split("'",2)[1]))
    return ''

def convertRow(cells,fields):
    res={}
    if not len(cells)==len(fields): return None
    for i,cell in enumerate(cells):
        tmp=fields[i][1](cell)
        if tmp: res[fields[i][0].lower().replace(' ', '_')]=tmp
    return res

def toObj(table,fields):
    res=[]
    for row in table.xpath('tr')[2:]:
        items=row.xpath('td')
        value=convertRow(items,fields)
        if value:
            res.append(value)
        # todo, this should be followed, scraped and inserted with a list of the docs, not an url, also this is specific to stages
        #elif toText(row) == 'Follow-up documents':
        #    ['Follow-up documents']=urlFromJS(section)
        #else:
        #    logger.warn('[*] unparsed row: %s' % tostring(row))
    return res

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(Obj), repr(Obj))

def identification(table):
    res={}
    for row in table.xpath('tr'):
        items=row.xpath('td')
        key=items[0].xpath("string()").replace(u"\u00A0",' ').strip()
        if key=='Subject(s)':
            value=[x.replace(u'\u00a0',' ').strip() for x in items[1].xpath('text()')]
        else:
            value=items[1].xpath("string()").replace(u"\u00A0",' ').strip()
        if key.lower()==u'legal basis':
            value=[x.strip() for x in value.split(';')]
        if key and value:
            res[str(key).lower().replace(' ','_')]=value
    return res

def forecasts(table):
    res={}
    for row in table.xpath('tr'):
        items=row.xpath('td')
        key=items[2].xpath("string()").replace(u"\u00A0",' ').strip()
        date=toDate(items[0])
        if key and date:
            res[key]=date
    return res

def links(table):
    res={}
    for row in table.xpath('tr'):
        items=row.xpath('td')
        key=items[0].xpath("string()").replace(u"\u00A0",' ').strip()
        value=items[1].xpath("string()") .replace(u"\u00A0",' ').strip()
        url=items[1].xpath('a')[0].get('href')
        if key and value:
            res[key]={'Title': value, 'URL': url}
        else:
            logger.info('bad link %s %s %s %s' % (tostring(items), key, value, url))
    return res

def agents(table):
    tmp=toObj(table,agentFields)
    res=[]
    for row in tmp:
        commitee=row['commitee']
        if commitee:
            tmp1=commitee.split('(')
            commitee=tmp1[0].strip()
            comrole=tmp1[1].strip()[:-1]
            if not comrole in ['responsible', 'opinion']:
                print comrole
                comrole=''
            elif comrole.startswith('responsible'):
                comrole=True
            else:
                comrole=False
        if 'Rapporteur' in row:
            # convert Rapporteurs to an own dict
            if not (type(row.get('Appointed'))==type(row.get('Rapporteur'))==type(row.get('Political Group'))==list):
                agent={}
                agent['commitee']=row['Commitee']
                agent['responsible']=comrole
                agent['name']=row.get('Rapporteur')
                agent['function']='MEP'
                agent['appointed']=row.get('Appointed')
                agent['group']=row.get('Political Group')
                res.append(agent)
            else:
                res.append([{'commitee': row['Commitee'],
                            'responsible': comrole,
                            'name': p[0],
                            'function': 'MEP',
                            'appointed': p[1],
                            'group': p[2]}
                           for p in zip(row['Rapporteur'],
                                        row['Appointed'],
                                        row['Political Group'])])
        # make the whole commitee a dict as well
    OtherAgents(table,res)
    return res

def OtherAgents(table,res):
    table=table.xpath('following-sibling::*')
    if not len(table): return
    table=table[0]
    if(not toText(table)=='European Commission and Council of the Union'): return
    table=table.xpath('following-sibling::*')[0]
    for row in table.xpath('tr'):
        fields=row.xpath('td')
        if(len(fields)==3 and toText(fields[0]).startswith('European Commission DG')):
            agent={'institution': toText(fields[0]),
                   'department': toText(fields[1])}
            tmp=toText(fields[2]).split(' ')
            if len(tmp)==3:
                value=[int(x) for x in tmp[2].strip().split('/')]
                agent['submission_date']=datetime.date(value[2], value[1], value[0])
            else:
                print 'other agents, non-date:', tmp
            res.append(agent)
        elif(len(fields)==5 and toText(fields[0]).startswith('Council of the Union')):
            agent={'institution': toText(fields[0]),
                  'department': toText(fields[2]),}
            tmp=urlFromJS(fields[1])
            if tmp: agent['council_doc']=tmp
            tmp=toText(fields[3]).split(' ')
            if len(tmp)==2:
                agent['meeting_id']=tmp[1]
            tmp=toText(fields[4]).split(' ')
            if len(tmp)==2:
                value=[int(x) for x in tmp[1].strip().split('/')]
                agent['meeting_date']=datetime.date(value[2], value[1], value[0])
            res.append(agent)
        else:
            raise ValueError
            logger.error('unparsed row: %s %s' % (len(fields), toText(row)))

def summaries(table):
    tmp=toObj(table,summaryFields)
    for item in tmp:
        if 'url' in item:
            tree=fetch(item['url'])
            text=[tostring(x) for x in tree.xpath('//table[@class="box_content_txt"]//td/*')]
            item['text']=text
    return tmp

stageFields=( ('title', toText),
              ('stage document',urlFromJS),
              ('body',toText),
              ('source reference',toText),
              ('equivalent references', toText),
              ('Vote references', toText),
              ('amendment references', urlFromJS),
              ('Joint Resolution', toText),
              ('date', toDate),
              ('Date of publication in Official Journal', urlFromJS)
            )
agentFields=( ('Commitee', toText),
              ('Rapporteur', toLines),
              ('Political Group',toLines),
              ('Appointed',toDate),
            )
summaryFields=( ('URL', urlFromJS),
                ('Date', toDate),
                ('Title',toText),
              )

def scrape(url):
    tree=fetch(url)
    sections=tree.xpath('//h2')
    if not len(sections):
        # retry once
        tree=fetch(url)
        sections=tree.xpath('//h2')
    if not len(sections):
        # even retry failed :(
        logger.error('[!] ERROR no title in: %s\nSkipping' % k)
        return
    res={'meta': {'source': url,
                  'country': 'eu',
                  'updated': datetime.datetime.utcnow() } }
    for section in sections:
        table=section.xpath('../../../following-sibling::*')[0]
        if section.text in ['Identification procedure', 'Identification', 'Identification resolution', 'Identification document']:
            res['procedure']=identification(table)
        elif section.text in ['Stages procedure', 'Stages', 'Stages resolution']:
            tmp=toObj(table,stageFields)
            res['stages']=[]
            for doc in tmp:
                if 'source_reference' in doc:
                    if type(doc['source_reference'])==dict:
                        doc['source']=doc['source_reference']['title']
                        doc['source_link']=doc['source_reference']['url']
                    else:
                        doc['source']=doc['source_reference']
                    del(doc['source_reference'])
                if 'equivalent_references' in doc:
                    doc['documents']=[doc.get('equivalent_references')]
                    del(doc['equivalent_references'])
                res['stages'].append(doc)
        elif section.text == 'Forecasts procedure':
            res['procedure']['forecasts']=forecasts(table)
        elif section.text in ['Agents procedure', 'Agents', 'Agents document', 'Agents resolution']:
            res['procedure']['actors']=agents(table)
        elif section.text == 'Links to other sources procedure':
            res['procedure']['links']=links(table)
        elif section.text == 'List of summaries':
            res['docs']=summaries(table)
        else:
            logger.warning('[*] unparsed: '+ section.text)
    save(res)

def getStages():
    tree=fetch('http://www.europarl.europa.eu/oeil/search_procstage_stage.jsp')
    select=tree.xpath('//select[@name="stageId"]')[0]
    return [(opt.get('value'), toText(opt))
            for opt
            in select.xpath('option')
            if opt.get('value')]

def nextPage(req):
    response = opener.open(req)
    raw=tidy.parseString(response.read(),
                         **{'output_xhtml' : 1,
                            'output-encoding': 'utf8',
                            'add_xml_decl' : 1,
                            'indent' : 0,
                            'tidy_mark' : 0,
                            'doctype' : "strict",
                            'wrap' : 0})
    tree=parse(StringIO(str(raw)))
    map(scrape, ['http://www.europarl.europa.eu/oeil/'+x.get('href')
                   for x
                   in tree.xpath('//a[@class="com_acronym"]')])

    img=tree.xpath('//a/img[@src="img/cont/activities/navigation/navi_next_activities.gif"]')
    if len(img):
        next='http://www.europarl.europa.eu/'+img[0].xpath('..')[0].get('href')
        logger.info('retrieving next page')
        nextPage(next)

def crawl(fast=True):
    result=[]
    stages=getStages()
    if fast: stages=[x for x in stages if x[1] != 'Procedure completed']
    for (stageid, stage) in stages:
        logger.info( 'crawling: '+ stage)
        data={'xpath': '/oeil/search/procstage/stage',
              'scope': 'stage',
              'searchCriteria': stage,
              'countEStat': True,
              'startIndex': 1,
              'stageId': stageid,
              'pageSize': 50}
        req = urllib2.Request('http://www.europarl.europa.eu/oeil/FindByStage.do',
                              urllib.urlencode(data))
        nextPage(req)
        #result.extend(nextPage(req))
    return result

# and some global objects
base = 'http://www.europarl.europa.eu/oeil/file.jsp'
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()))
opener.addheaders = [('User-agent', 'weurstchen/0.5')]
# connect to  mongo
conn = pymongo.Connection()
db=conn.parltrack
procedures=db.procedures
stats=[0,0]

if __name__ == "__main__":
    import pprint
    scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5563972")
    #crawl(fast=(False if len(sys.argv)>1 and sys.argv[1]=='full' else True))

    # some tests
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5696252")
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5872922")
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5872922"))
    #print 'x'*80
    #scrape("http://www.europarl.europa.eu/oeil/FindByProcnum.do?lang=en&procnum=RSP/2011/2510")
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/FindByProcnum.do?lang=en&procnum=RSP/2011/2510"))
    #print 'x'*80
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5831162")
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5831162"))
    #print 'x'*80
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5632032")
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5632032"))
    #print 'x'*80
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5699432")
    #pprint.pprint(scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5699432"))

    # [*] unparsed row: <tr>
    # <td colspan="99" style="font-size: 1.1em"><img src="/oeil/img/cont/members/navigation/mep-bullet.gif" alt="" border="0"/>&#160; <a href="javascript:OpenNewPopupWnd('/oeil/stage.jsp?id=131832&amp;language=en',%20'width=900,height=400,resizable=1,status=0,toolbar=0,menubar=0,location=0,scrollbars=1,directories=0')" class="EI_lnk">Follow-up documents</a></td>
    # </tr>

