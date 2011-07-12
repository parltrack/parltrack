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

from lxml.html.soupparser import parse
from lxml.etree import tostring
from cStringIO import StringIO
from urlparse import urljoin
from itertools import izip_longest
import urllib2, urllib, cookielib, datetime, sys, json, logging, re
from operator import itemgetter
from flaskext.mail import Message
from parltrack.webapp import mail
from parltrack.utils import diff
from parltrack.default_settings import ROOT_URL
import unicodedata
try:
    from parltrack.environment import connect_db
    db = connect_db()
except:
    import pymongo
    db=pymongo.Connection().parltrack
from bson.objectid import ObjectId

db.oeil.ensure_index([('procedure.reference', 1)])
db.oeil.ensure_index([('procedure.title', 1)])
db.oeil.ensure_index([('activities.actors.mepref', 1)])
db.oeil.ensure_index([('activities.actors.commitee', 1)])
db.oeil.ensure_index([('meta.created', -1)])
db.oeil.ensure_index([('meta.updated', -1)])

# and some global objects
base = 'http://www.europarl.europa.eu/oeil/file.jsp'
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookielib.CookieJar()))
opener.addheaders = [('User-agent', 'weurstchen/0.5')]
# connect to  mongo
stats=[0,0]
commitee_actorre=re.compile(r'^EP:.*(by|of) the committee responsible')

def getMEPRef(name):
    if not name: return
    mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.split()).lower()},['_id'])
    if not mep and u'ß' in name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower()},['_id'])
    if not mep and unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore')!=name:
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore').split()).lower()},['_id'])
    if mep:
        return mep['_id']
    else:
        print >>sys.stderr, '[!] lookup oops', name.encode('utf8')

def makeActivities(data):
    #print >> sys.stderr, data
    # merge actors, stages, docs and forecasts
    actors={'CSL': ['Council of the European Union'],
            'ESC': ['Economic and Social Committee'],
            'EDPS': ['European Data Protecion Supervisor'],
            'CJEC': ['Court of Justice of the European Communities'],
            'CJEU': ['Court of Justice of the European Union'],
            'CSL/EP': ['Council of the European Union', 'European Parlament'],}
    tmp=sorted([x for x in
                data['procedure'].get('actors',[])+
                data.get('stages',[])+
                data.get('docs',[])+
                data['procedure'].get('forecasts',[])
                if 'date' in x],
               key=itemgetter('date'))
    # remove cruft
    data['docs']=[]
    if 'stages' in data:
        del data['stages']
    if 'actors' in data['procedure']:
        del data['procedure']['actors']
    if 'forecasts' in data['procedure']:
        del data['procedure']['forecasts']
    stage={}
    res=[]
    # merge items into Activities
    for item in tmp:
        #print >> sys.stderr, item
        #print >> sys.stderr
        if 'type' in item:
            if item['type'] in ['Document annexed to the procedure',
                                'Supplementary initial legislative document']:
                doc={}
                for (k,n) in [('url','source_link'),
                              ('title', 'source'),
                              ('summary_url','stage_document'),
                              ('oj_ref','oj_ref'),
                              ('type','type'),
                              ('summary','text'),
                              ('body','body'),
                              ('date','date')]:
                    if n in item and (k not in ['date', 'body'] or doc):
                        doc[k]=item[n]
                if doc:
                    if (doc.get('title') and
                        candre.match(doc.get('title'))):
                        celexid=tocelex(doc.get('title') ,doc.get('type'))
                        if (celexid and checkUrl("http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=%s:HTML" % celexid)):
                            doc['celexid']=celexid
                    data['docs'].append(doc)
                continue
            # handle normal new stage
            if stage:
                res.append(stage)
            stage=item
            # handle EP/commitee, csl/ep and ESC
            m=commitee_actorre.search(item['type'])
            if m and item.get('body','EP')=='EP':
                dictext(stage,'actors',actors.get('EP',[]))
            elif item.get('body')=='EP':
                dictext(stage,'actors',['European Parlament'])
            else:
                dictext(stage,'actors',actors.get(item.get('body',''),
                                                  [item.get('body','unknown')]))
            doc={}
            for (k,n,d) in [('url','source_link',True),
                            ('title', 'source', True),
                            ('summary_url','stage_document',True),
                            ('oj_ref','oj_ref', True),
                            ('body','body', False),
                            ('type','type', False),
                            ('date','date',False)]:
                if n in item and (k not in ['date','body'] or doc):
                    doc[k]=item[n]
                    if d:
                        del stage[n]
            if (doc and
                doc.get('title') and
                candre.match(doc.get('title'))):
                celexid=tocelex(doc.get('title') ,doc.get('type'))
                if (celexid and checkUrl("http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=%s:HTML" % celexid)):
                    doc['celexid']=celexid

            if 'url' in doc or 'title' in doc or 'summary_url' in doc or 'oj_ref' in doc:
                dictapp(stage, 'documents',doc)
        # handle actors
        elif 'body' in item:
            if ('body' in stage and item['body']!=stage['body']) or (stage and item['date']!=stage.get('date',None)):
                res.append(stage)
                stage={}
            if item['body'] not in ['EC', 'EP']:
                if item['body']=='CSL':
                    stage={'body': 'CSL',
                           'date': item['date'],
                           'type': 'Council meeting',
                           'actors': [item]}
                else:
                    stage={'body': item['body'],
                           'date': item['date'],
                           'actors': [item]}
                continue
            dictext(actors,item['body'],item if type(item)==list else [item])
        # handle documents
        elif 'text' in item:
            newDoc=True
            for (i, doc) in enumerate(stage.get('documents',[])):
                if doc.get('summary_url')==item['url']:
                    newDoc=False
                    stage['documents'][i]['summary']=item['text']
            for (i, doc) in enumerate(data.get('docs',[])):
                if doc.get('summary_url')==item['url']:
                    newDoc=False
                    doc['summary']=item['text']
            if newDoc:
                dictapp(stage,'documents',item)
    if 'EP' in actors and data['procedure']['stage_reached'] in ["Awaiting Parliament 1st reading / single reading / budget 1st stage",
                                                                 "Preparatory phase in Parliament",
                                                                 "Awaiting Parliament 2nd reading",]:
        dictext(data['procedure'],'agents',actors['EP'])
    if stage:
        res.append(stage)
    tmp=tocelex(data['procedure']['reference'],'')
    if tmp and len([True for d in data['docs'] if d['title']==data['procedure']['reference']])==0:
        data['docs'].append({'celexid': tmp,
                             'title': data['procedure']['reference'],
                             'type': "Initial Legislative Document",
                             'date': data['procedure']['date']})
    return list(reversed(res))

def save(data):
    data['activities']=makeActivities(data)
    #print json.dumps(data,default=dateJSONhandler)
    #pprint.pprint(data)
    #return
    src=data['meta']['source']

    res=db.dossiers.find_one({ 'meta.source' : src }) or {}
    d=diff(dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]),
           dict([(k,v) for k,v in data.items() if not k in ['_id', 'meta', 'changes',]]))
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
            msg = Message("Parltrack Notification for %s %s" % (data['procedure']['reference'],data['procedure']['title']),
                          sender = "parltrack@parltrack.euwiki.org",
                          bcc = g['active_emails'])
            msg.body = makemsg(data,d)
            mail.send(msg)
        data['changes']=res.get('changes',{})
        data['changes'][now]=d
        db.dossiers.save(data)
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

def dictapp(d,k,v):
    if not k in d:
        d[k]=[]
    if not v in d[k]:
        d[k].append(v)

def dictext(d,k,v):
    if not k in d:
        d[k]=[]
    d[k].extend([x for x in v if not x in d[k]])

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
def tocelex(title, type):
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
            print >>sys.stderr, "CELEX:5%sAP%s:EN" % (m.group(2),m.group(1))
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
    res=fetch(url)
    return res.xpath('//h1/text()')[0]!="Not available in English."

def fetch(url):
    # url to etree
    try:
        f=urllib2.urlopen(url)
    except urllib2.URLError, e:
        if hasattr(e, 'code') and e.code>=400:
            print >>sys.stderr, "[!] %d %s" % (e.code, url)
            raise
        try:
            # 1st retry
            f=urllib2.urlopen(url)
        except urllib2.URLError:
            if hasattr(e, 'code') and e.code>=400:
                print >>sys.stderr, "[!] %d %s" % (e.code, url)
                raise
            try:
                # 2nd retry
                f=urllib2.urlopen(url)
            except urllib2.URLError:
                raise
    return parse(f)

def toDate(node):
    for br in node.xpath("br"):
        br.text="\n"
    lines=[x.replace(u"\u00A0",' ').strip() for x in node.xpath("text()") if x.replace(u"\u00A0",' ').strip()]
    if len(lines)>1:
        result=[]
        for text in lines:
            if not len(text): continue
            value=[int(x) for x in text.split('/') if len(x)]
            result.append(datetime.date(value[2], value[1], value[0]).isoformat())
        return result
    elif len(lines)==1:
        text=lines[0]
        if not len(text): return None
        value=[int(x) for x in text.split('/') if len(x)]
        return datetime.date(value[2], value[1], value[0]).isoformat()
    return None

def toText(node):
    if node is None: return ''
    text=''.join([x.strip() for x in node.xpath(".//text()") if x.strip()]).replace(u"\u00A0",' ').strip()

    links=node.xpath('a')
    if not links: return text
    return {'title': text, 'url': unicode(urljoin(base,links[0].get('href')),'utf8')}

def toLines(node):
    for br in node.xpath("br"):
        br.text="\n"
    text=[x.replace(u"\u00A0",' ').strip() for x in node.xpath("text()") if x.replace(u"\u00A0",' ').strip()]
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

def toObj(table,fields,offset=2):
    res=[]
    for row in table.xpath('tr')[offset:]:
        items=row.xpath('td')
        value=convertRow(items,fields)
        if value:
            res.append(value)
        # todo, this should be followed, scraped and inserted with a list of the docs, not an url, also this is specific to stages
        #elif toText(row) == 'Follow-up documents':
        #    ['Follow-up documents']=urlFromJS(section)
        #else:
        #    print >> sys.stderr, ('[*] unparsed row: %s' % tostring(row))
    return res

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif type(obj)==ObjectId:
        return str(obj)
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))

def identification(table):
    res={}
    for row in table.xpath('tr'):
        items=row.xpath('td')
        key=items[0].xpath("string()").replace(u"\u00A0",' ').strip()
        if key=='Subject(s)':
            key='subjects'
            value=[x.replace(u'\u00a0',' ').strip() for x in items[1].xpath('text()')]
        else:
            value=items[1].xpath("string()").replace(u"\u00A0",' ').strip()
            if key.lower()=='reference' and len(items)==3:
                tmp=items[2].xpath("string()").replace(u"\u00A0",' ').strip()
                if tmp.startswith('Date of publication'):
                    tmp=tmp.split(' ')[-1]
                    tmp=[int(x) for x in tmp.split('/') if len(x)]
                    res['date']=datetime.date(tmp[2], tmp[1], tmp[0]).isoformat()
        if key.lower()==u'legal basis':
            value=[x.strip() for x in value.split(';')]
        if key and value:
            res[str(key).lower().replace(' ','_')]=value
    return res

def forecasts(table):
    res=[]
    for row in table.xpath('tr'):
        items=row.xpath('td')
        fc={'type': 'Forecast', 'body': 'EP'}
        key=''.join([x.strip() for x in items[2].xpath(".//text()") if x.strip()]).replace(u"\u00A0",' ').strip()
        if key: fc['title']=key
        url=urlFromJS(items[1])
        if url:
            try:
                tree=fetch(url)
            except urllib2.URLError, e:
                if e.code>=400:
                    print >>sys.stderr, "[!] %d %s" % (e.code, url)
                    continue
            text=[tostring(x) for x in tree.xpath('//table[@class="box_content_txt"]//td/*')]
            fc['doc']={'text':text, 'url':url }
        date=toDate(items[0])
        if date: fc['date']=date
        if 'title' in fc:
            res.append(fc)
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
            print >> sys.stderr, ('bad link %s %s %s %s' % (tostring(items), key, value, url))
    return res

def prevagents(table):
    prevlink=table.xpath('//a[text() = "Previous"]')
    if not prevlink:
        return []
    try:
        t=fetch(urljoin(base,(prevlink[0].get('href').split("'",2)[1]))).xpath("//table[@class='box_content_txt']")[0]
    except urllib2.URLError, e:
        if e.code>=400:
            print >>sys.stderr, "[!] %d %s" % (e.code, url)
            return []
    res=[]
    for row in t.xpath('tr')[1:]:
        items=row.xpath('td')
        value=convertRow(items,agentFields)
        if type(value['rapporteur'])==list:
            if not len(value['rapporteur'])==len(value['rapporteur'])==len(value['rapporteur']):
                print >>sys.stderr, 'wrong multi-agent', value
                continue
            for (i, a) in enumerate(value['rapporteur']):
                res.append({'rapporteur': value['rapporteur'][i],
                            'appointed': value['appointed'][i],
                            'political_group': value['political_group'][i],
                            'commitee': value['commitee']})
        elif value:
                res.append(value)
    return res

def prevcls(table):
    prevlink=table.xpath('//a[text() = "Previous Councils"]')
    if not prevlink:
        return []
    try:
        t=fetch(urljoin(base,(prevlink[0].get('href').split("'",2)[1]))).xpath("//table[@class='box_content_txt']")[0]
    except urllib2.URLError, e:
        if e.code>=400:
            print >>sys.stderr, "[!] %d %s" % (e.code, url)
            return []
    res=[]
    for row in t.xpath('tr'):
        fields=row.xpath('td')
        agent={'institution': "Council of the Union",
               'body': 'CSL',
               'department': toText(fields[1]),}
        tmp=urlFromJS(fields[0])
        if tmp: agent['council_doc']=tmp
        tmp=toText(fields[2]).split(' ')
        if len(tmp)==2:
            agent['meeting_id']=tmp[1]
        tmp=toText(fields[3]).split(' ')
        if len(tmp)==2:
            value=[int(x) for x in tmp[1].strip().split('/')]
            agent['date']=datetime.date(value[2], value[1], value[0]).isoformat()
        res.append(agent)
    return res

def agents(table):
    tmp=toObj(table,agentFields)
    tmp.extend(prevagents(table))
    res=[]
    for row in tmp:
        commitee=row['commitee']
        if commitee:
            tmp1=commitee.split('(')
            commitee=tmp1[0].strip()
            comrole=tmp1[1].strip()[:-1]
            if not comrole.split(',')[0] in ['responsible', 'opinion']:
                print >>sys.stderr, comrole
                comrole=''
            elif comrole.startswith('responsible'):
                comrole=True
            else:
                comrole=False
            # convert Rapporteurs to an own dict
            if not (type(row.get('appointed'))==type(row.get('rapporteur'))==type(row.get('political_group'))==list):
                agent={}
                agent['commitee']=commitee
                agent['responsible']=comrole
                agent['name']=row.get('rapporteur')
                agent['mepref']=getMEPRef(row.get('rapporteur'))
                agent['function']='MEP'
                agent['body']='EP'
                agent['date']=row.get('appointed')
                agent['group']=row.get('political_group')
                res.append(agent)
            else:
                res.extend([{'commitee': commitee,
                             'responsible': comrole,
                             'name': p[0],
                             'mepref': getMEPRef(p[0]),
                             'function': 'MEP',
                             'body': 'EP',
                             'date': p[1],
                             'group': p[2]}
                            for p in zip(row['rapporteur'],
                                         row['appointed'],
                                         row['political_group'])])
        # make the whole commitee a dict as well
    res.extend(OtherAgents(table))
    res.extend(prevcls(table))
    return res

def OtherAgents(table):
    res=[]
    if toText(table) not in ['European Commission and Council of the Union', 'Council of the Union']:
        table=table.xpath('following-sibling::*')
        if not len(table): return res
        table=table[0]
    if toText(table) not in ['European Commission and Council of the Union', 'Council of the Union', 'European Commission']:
        print >> sys.stderr, "[!] otheragents parser found this heading: ", toText(table)
        return []
    table=table.xpath('following-sibling::*')[0]
    for row in table.xpath('tr'):
        fields=row.xpath('td')
        if(len(fields)==3 and toText(fields[0]).startswith('European Commission DG')):
            agent={'institution': toText(fields[0]).split('\n')[0].strip(),
                   'body': 'EC',
                   'department': toText(fields[1])}
            tmp=toText(fields[2]).split(' ')
            if len(tmp)==3:
                value=[int(x) for x in tmp[2].strip().split('/')]
                agent['date']=datetime.date(value[2], value[1], value[0]).isoformat()
            res.append(agent)
        elif(len(fields)==5 and toText(fields[0]).startswith('Council of the Union')):
            agent={'institution': toText(fields[0]).split('\n')[0].strip(),
                   'body': 'CSL',
                   'department': toText(fields[2]),}
            tmp=urlFromJS(fields[1])
            if tmp: agent['council_doc']=tmp
            tmp=toText(fields[3]).split(' ')
            if len(tmp)==2:
                agent['meeting_id']=tmp[1]
            tmp=toText(fields[4]).split(' ')
            if len(tmp)==2:
                value=[int(x) for x in tmp[1].strip().split('/')]
                agent['date']=datetime.date(value[2], value[1], value[0]).isoformat()
            res.append(agent)
        else:
            raise ValueError
            print >> sys.stderr, ('unparsed row: %s %s' % (len(fields), toText(row)))
    return res

def summaries(table):
    tmp=toObj(table,summaryFields,0)
    for item in tmp:
        if 'url' in item:
            try:
                tree=fetch(item['url'])
            except:
                continue
            text=[tostring(x) for x in tree.xpath('//table[@class="box_content_txt"]//td/*')]
            item['text']=text
    return tmp

stageFields=( ('type', toText),
              ('stage document',urlFromJS),
              ('body',toText),
              ('source reference',toText),
              ('equivalent references', toText),
              ('Vote references', toText),
              ('amendment references', urlFromJS),
              ('Joint Resolution', toText),
              ('date', toDate),
              ('oj ref', toText)
            )
agentFields=( ('Commitee', toText),
              ('Rapporteur', toLines),
              ('political_group',toLines),
              ('Appointed',toDate),
            )
summaryFields=( ('URL', urlFromJS),
                ('Date', toDate),
                ('title',toText),
              )

def scrape(url):
    try:
        tree=fetch(url)
    except urllib2.URLError, e:
        if e.code>=400:
            print >>sys.stderr, "[!] %d %s" % (e.code, url)
            return

    sections=tree.xpath('//h2')
    if not len(sections):
        # retry once
        try:
            tree=fetch(url)
        except urllib2.URLError, e:
            if e.code>=400:
                print >>sys.stderr, "[!] %d %s" % (e.code, url)
                return []
        sections=tree.xpath('//h2')
    if not len(sections):
        # even retry failed :(
        print >> sys.stderr, ('[!] ERROR no title in: %s\nSkipping' % k)
        return
    res={'meta': {'source': url,
                  'id': int(url.split('id=')[1]),
                  'country': 'eu',
                  'timestamp': datetime.datetime.utcnow() } }
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
                    doc['alt_refs']=[doc.get('equivalent_references')]
                    del(doc['equivalent_references'])
                res['stages'].append(doc)
        elif section.text.strip().startswith('Forecasts'):
            res['procedure']['forecasts']=forecasts(table)
        elif section.text in ['Agents procedure', 'Agents', 'Agents document', 'Agents resolution']:
            tmp=agents(table)
            res['procedure']['agents']=[x for x in tmp if not 'date' in x or not x['date']]
            res['procedure']['actors']=sorted([x for x in tmp if 'date' in x and x['date']],key=itemgetter('date'))
        elif section.text == 'Links to other sources procedure':
            res['procedure']['links']=links(table)
        elif section.text == 'List of summaries':
            res['docs']=summaries(table)
        #else:
        #    print >> sys.stderr, ('[*] unparsed: '+ section.text)
    save(res)

def getStages():
    try:
        tree=fetch('http://www.europarl.europa.eu/oeil/search_procstage_stage.jsp')
    except urllib2.URLError, e:
        if e.code>=400:
            print >>sys.stderr, "[!] %d %s" % (e.code, url)
            return []
    select=tree.xpath('//select[@name="stageId"]')[0]
    return [(opt.get('value'), toText(opt))
            for opt
            in select.xpath('option')
            if opt.get('value')]

def nextPage(req):
    response = opener.open(req)
    tree=parse(response)
    map(scrape, ['http://www.europarl.europa.eu/oeil/'+x.get('href')
                   for x
                   in tree.xpath('//a[@class="com_acronym"]')])

    img=tree.xpath('//a/img[@src="img/cont/activities/navigation/navi_next_activities.gif"]')
    if len(img):
        next='http://www.europarl.europa.eu/'+img[0].xpath('..')[0].get('href')
        print >> sys.stderr, ('retrieving next page')
        nextPage(next)

def crawl(fast=True):
    result=[]
    stages=getStages()
    if fast: stages=[x for x in stages if x[1] != 'Procedure completed']
    for (stageid, stage) in stages:
        print >> sys.stderr, ( 'crawling: '+ stage)
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

if __name__ == "__main__":
    import platform
    if platform.machine() in ['i386', 'i686']:
        import psyco
        psyco.full()
    #crawl(fast=(False if len(sys.argv)>1 and sys.argv[1]=='full' else True))
    scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=10001243")
    #import pprint
    #print '['
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5882862")
    #print ','
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5907152")
    #print ','
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5840492")
    #print ','
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5906122")
    #scrape("")
    #print ','
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5912582")
    #print ','
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5840492")
    #print ','
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5563972")
    #print ','
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5563642")
    #print ','
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5563982")
    #print ','
    #scrape("http://www.europarl.europa.eu/oeil/file.jsp?id=5891812")
    #print ']'

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

