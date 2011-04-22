#!/usr/bin/env python
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
from multiprocessing import Pool, Process, Queue,  log_to_stderr
from multiprocessing.sharedctypes import Value
from ctypes import c_bool
from Queue import Empty
from itertools import izip_longest
from ctypes import c_int
import urllib2, urllib, cookielib, tidy, datetime, sys, json, pymongo, traceback
from logging import DEBUG

def diff(data, param):
    if not param: param=[0,0]
    k=data['source']
    if not 'Identification' in data:
        logger.error('[!] ERROR no title in: %s\nSkipping' % k)
        return param

    res=docs.find_one({ 'source' : k }) or {}
    d=diffItem(dict([(k,v) for k,v in data.items() if not k in ['_id','source', 'updated', 'changes','__stage_order','__summaries_order']]),
               dict([(k,v) for k,v in res.items() if not k in ['_id','source', 'updated', 'changes','__stage_order','__summaries_order']]))
    if d:
        if not res:
            logger.info('adding '+ data['Identification']['Title'])
            param[0]+=1
        else:
            logger.info( 'updating '+ data['Identification']['Title'])
            param[1]+=1
            data['_id']=res['_id']
        logger.info(d)
        now=datetime.datetime.utcnow().replace(microsecond=0).isoformat()
        data['updated']=now
        data['changes']=res.get('changes',{})
        data['changes'][now]=d
        docs.save(data)
        return param
    return param

def diffItem(e1,e2):
    if type(e1) == str:
       e1=unicode(e1,'utf8')
    if type(e1) == tuple:
       e1=list(e1)
    if type(e1) != type(e2):
        return {'new': e1, 'old': e2}
    if type(e1) == list:
        return filter(None,[diffItem(*k) for k in izip_longest(sorted(e1),sorted(e2))])
    if type(e1) == dict:
        res=[]
        for k in set(e1.keys() + e2.keys()):
            if k == '_id': continue
            r=diffItem(e1.get(k),e2.get(k))
            if r:
                res.append((k,r))
        return dict(res)
    if e1 != e2:
        return {'new': e1, 'old': e2}
    return

def fetch(url):
    # url to etree
    f=urllib2.urlopen(url)
    raw=f.read()
    f.close()
    raw=tidy.parseString(raw,
            **{'output_xhtml' : 1,
               'output-encoding': 'utf8',
               'add_xml_decl' : 1,
               'indent' : 0,
               'tidy_mark' : 0,
               'doctype' : "strict",
               'wrap' : 0})
    return parse(StringIO(str(raw)))

def toDate(node):
    #text=tostring(node,method="text",encoding='utf8').replace('\xc2\xa0',' ').strip()
    text=tostring(node,method="text",encoding=unicode).replace(u"\u00A0",' ').strip().encode('raw_unicode_escape').decode('utf-8')
    if text is None or not len(text): return
    lines=text.split('\n')
    if len(lines)>1:
        result=[]
        for text in lines:
            value=[int(x) for x in text.strip().split('/')]
            result.append(datetime.date(value[2], value[1], value[0]).toordinal())
        return result
    else:
        value=[int(x) for x in text.strip().split('/')]
        return datetime.date(value[2], value[1], value[0]).toordinal()

def toText(node):
    if node is None: return ''
    text=tostring(node,method="text",encoding=unicode).replace(u"\u00A0",' ').strip().encode('raw_unicode_escape').decode('utf-8')

    links=node.xpath('a')
    if not links: return text
    return {'Title': text, 'URL': unicode(urljoin(base,links[0].get('href')),'utf8')}

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
        if tmp: res[fields[i][0]]=tmp
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
        #key=tostring(items[0],method="text",encoding='utf8').strip()
        key=tostring(items[0],method="text",encoding=unicode).replace(u"\u00A0",' ').strip().encode('raw_unicode_escape').decode('utf-8')
        if key=='Subject(s)':
            value=[x.replace('\xc2\xa0',' ').strip() for x in items[1].xpath('text()')]
        else:
            #value=tostring(items[1],method="text",encoding='utf8').replace('\xc2\xa0',' ').strip()
            value=tostring(items[1],method="text",encoding=unicode).replace(u"\u00A0",' ').strip().encode('raw_unicode_escape').decode('utf-8')
        if key and value:
            res[key]=value
    return res

def forecasts(table):
    res={}
    for row in table.xpath('tr'):
        items=row.xpath('td')
        #key=tostring(items[2],method="text",encoding='utf8').replace('\xc2\xa0',' ').strip()
        key=tostring(items[2],method="text",encoding=unicode).replace(u"\u00A0",' ').strip().encode('raw_unicode_escape').decode('utf-8')
        date=toDate(items[0])
        if key and date:
            res[key]=date
    return res

def links(table):
    res={}
    for row in table.xpath('tr'):
        items=row.xpath('td')
        #key=unicode(tostring(items[0],method="text",encoding='utf8').strip(),'utf8')
        key=tostring(items[0],method="text",encoding=unicode).replace(u"\u00A0",' ').strip().encode('raw_unicode_escape').decode('utf-8')
        #value=unicode(tostring(items[1],method="text",encoding='utf8').strip(),'utf8')
        value=tostring(items[1],method="text",encoding=unicode).replace(u"\u00A0",' ').strip().encode('raw_unicode_escape').decode('utf-8')
        url=items[1].xpath('a')[0].get('href')
        if key and value:
            res[key]={'Title': value, 'URL': url}
        else:
            logger.info('bad link %s %s %s %s' % (tostring(items), key, value, url))
    return res

def agents(table):
    res={}
    tmp=toObj(table,agentFields)
    for row in tmp:
        if 'Rapporteur' in row:
            # convert Rapporteurs to an own dict
            if not (type(row['Appointed'])==type(row['Rapporteur'])==type(row['Political Group'])==list):
                meps=[{'Rapporteur': row['Rapporteur'],
                      'Appointed': row['Appointed'],
                      'Group': row['Political Group']}]
            else:
                meps=[{'Rapporteur': p[0], 'Appointed': p[1], 'Group': p[2]}
                      for p in zip(row['Rapporteur'],row['Appointed'],row['Political Group'])]
            row['Rapporteurs']={}
            for mep in meps:
                row['Rapporteurs'][mep['Rapporteur'].replace('.','')]={'Date': mep['Appointed'], 'Group': mep['Group']}
            del(row['Rapporteur'])
            del(row['Appointed'])
            del(row['Political Group'])

        # make the whole commitee a dict as well
        commitee=row['Commitee']
        if commitee:
            del(row['Commitee'])
            tmp1=commitee.split('(')
            commitee=tmp1[0].strip()
            row['role']=tmp1[1].strip()[:-1]
            if commitee in res:
                logger.error('duplicate agents: %s' % commitee)
                #raise ValueError('duplicate agents: %s' % commitee)
                raise ValueError
            res[commitee]=row
    OtherAgents(table, res)
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
            item={'Agent': toText(fields[0]), }
            key=toText(fields[1])
            tmp=toText(fields[2]).split(' ')
            if len(tmp)==3:
                value=[int(x) for x in tmp[2].strip().split('/')]
                item['Date']=datetime.date(value[2], value[1], value[0]).toordinal()
            res[key]=item
        elif(len(fields)==5 and toText(fields[0]).startswith('Council of the Union')):
            item={'Agent': 'Council of the Union',
                  'URL': urlFromJS(fields[1]),}
            key=toText(fields[2])
            tmp=toText(fields[3]).split(' ')
            if len(tmp)==2:
                item['Meeting number']=tmp[1]
            tmp=toText(fields[4]).split(' ')
            if len(tmp)==2:
                value=[int(x) for x in tmp[1].strip().split('/')]
                item['Date']=datetime.date(value[2], value[1], value[0]).toordinal()
            res[key]=item
        else:
            raise ValueError
            logger.error('unparsed row: %s %s' % (len(fields), toText(row)))

def stages(table):
    tmp=toObj(table,stageFields)
    res={}
    order=[]
    for stage in tmp:
        if not 'stage' in stage:
            raise ValueError, 'no stage' % stage
        key=stage['stage']
        if key in res:
            raise ValueError, 'duplicate stage' % key
        order.append(key)
        del(stage['stage'])
        res[key]=stage
    return (res, order)

def summaries(table):
    tmp=toObj(table,summaryFields)
    res={}
    order=[]
    for summary in tmp:
        if not 'Title' in summary:
            raise ValueError, 'no title' % summary
        key=summary['Title']
        if key in res:
            raise ValueError, 'duplicate summary' % key
        order.append(key)
        del(summary['Title'])
        res[key]=summary
    return (res, order)

stageFields=( ('stage', toText),
              ('stage document',urlFromJS),
              ('source institution',toText),
              ('source reference',toText),
              ('Equivalent references', toText),
              ('Vote references', toText),
              ('Amendment references', urlFromJS),
              ('Joint Resolution', toText),
              ('Date of document', toDate),
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
    res={'source': url}
    for section in sections:
        table=section.xpath('../../../following-sibling::*')[0]
        if section.text in ['Identification procedure', 'Identification', 'Identification resolution', 'Identification document']:
            res['Identification']=identification(table)
        elif section.text in ['Stages procedure', 'Stages', 'Stages resolution']:
            res['Stages'],res['__stage_order']=stages(table)
        elif section.text == 'Forecasts procedure':
            res['Forecasts']=forecasts(table)
        elif section.text in ['Agents procedure', 'Agents', 'Agents document', 'Agents resolution']:
            res['Agents']=agents(table)
        elif section.text == 'Links to other sources procedure':
            res['Links to other sources procedure']=links(table)
        elif section.text == 'List of summaries':
            res['List of summaries'],res['__summaries_order']=summaries(table)
        else:
            logger.warning('[*] unparsed: '+ section.text)
    return res

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
    map(m.addjob, ['http://www.europarl.europa.eu/oeil/'+x.get('href')
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

class Multiplexer(object):
    def __init__(self, worker, writer, threads=8):
        self.worker=worker
        self.writer=writer
        self.consumer=Process(target=self.consume)
        self.pool = Pool(threads)   # reduce if less aggressive
        self.consume = Value(c_bool,True)
        self.q=Queue()

    def start(self):
        self.consume.value=True
        self.consumer.start()

    def addjob(self, url):
        try:
            self.pool.apply_async(self.worker,[url],callback=self.q.put)
        except:
            logger.error('[!] failed to scrape '+ url)
            traceback.print_exc(file=sys.stderr)
            #raise

    def finish(self):
        self.pool.close()
        self.pool.join()
        self.consume.value=False
        self.consumer.join()

    def consume(self):
        param=None
        while True:
            try:
                param = self.writer(self.q.get(True, timeout=1), param)
            except Empty:
                if not self.consume.value: break
        logger.info('result: %s' % param)

# and some global objects
base = 'http://www.europarl.europa.eu/oeil/file.jsp'
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()))
opener.addheaders = [('User-agent', 'weurstchen/0.5')]
# connect to  mongo
conn = pymongo.Connection()
db=conn.oeil
docs=db.docs
logger = log_to_stderr()
logger.setLevel(DEBUG)

if __name__ == "__main__":
    m=Multiplexer(scrape,diff)
    m.start()
    crawl(fast=(False if len(sys.argv)>1 and sys.argv[1]=='full' else True))
    m.finish()

    # some tests
    #import pprint
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

