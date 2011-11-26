#!/usr/bin/env python
# -*- coding: utf-8 -*-
#    This file is part of parltrack.

#    parltrack is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    parltrack is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with parltrack.  If not, see <http://www.gnu.org/licenses/>.

# (C) 2011 by Stefan Marsiske, <stefan.marsiske@gmail.com>

from lxml import etree
from lxml.html.soupparser import parse
from lxml.etree import tostring
from cStringIO import StringIO
from urlparse import urljoin
from tempfile import mkstemp
from time import mktime, strptime
from datetime import datetime
import urllib2, sys, subprocess, re, os, json
from parltrack.environment import connect_db
from mappings import COMMITTEE_MAP
from bson.objectid import ObjectId

DEBUG=False
DEBUG1=False

db = connect_db()
datere=re.compile(r'^([0-9]{1,2} \w+ [0-9]{4}, [0-9]{2}\.[0-9]{2}).*')
block_start=re.compile(r'^([0-9]+)\. {,10}(.*)')
corap=re.compile(r'^ {4,}rapporteur\(s\):? +(.*)')
fields=[(re.compile(r'^ {4,}Rapporteur:? +(.*)'),"Rapporteur"),
        (re.compile(r'^ {4,}Co-rapporteur\(s\):? +(.*)'),"Rapporteur"),
        (corap,"Rapporteur"),
        (re.compile(r'^ {4,}Rapporteur for(?: the)? +(.*)'),"Shadow Rapporteur"),
        (re.compile(r'^ {4,}Responsible:? +(.*)'),'Responsible'),
        (re.compile(r'^ {4,}Opinions:? +(.*)'),"Opinions"),
        ]
misc_block=re.compile(u'^ {3,}(:?\uf0b7 +|\u2022 +)(.*)')
opinion_junk=re.compile(r'^ {3,}opinion: {3,}(.*)')

db.ep_com_meets.ensure_index([('docref', 1)])
COMMITTEES=[x for x in db.ep_com_meets.distinct('committee') if x not in ['Security and Defence', 'SURE'] ]

def fetch(url):
    # url to etree
    print >> sys.stderr, url
    try:
        f=urllib2.urlopen(url)
    except (urllib2.HTTPError, urllib2.URLError):
        try:
            f=urllib2.urlopen(url)
        except (urllib2.HTTPError, urllib2.URLError):
            try:
                f=urllib2.urlopen(url)
            except (urllib2.HTTPError, urllib2.URLError):
                return ''
    raw=parse(f)
    f.close()
    return raw

# title
# INTA/7/05563
# ***I 2011/0039(COD) COM(2011)0082 – C7-0069/2011

instdocre=re.compile(u'(\**)(I*)(?:\s+([-0-9A-Z/()]+))?(?:\s+([-0-9A-Z/()]+))?(?:\s+–\s([-0-9A-Z/()]+))?$')
def getdocs(issue):
    if len(issue['title'].split('\n'))>1:
        #print issue['title'].split('\n')[-2].encode('utf8')
        #print '\n'.join(issue['title'].split('\n')[-1:]).encode('utf8')
        m=instdocre.search(issue['title'].split('\n')[-1])
        if m:
            issue['title']='\n'.join(issue['title'].split('\n')[:-1])
            #print 'asdf', m.groups()
            if m.group(1):
                issue['procedure']=m.group(1)
            if m.group(2):
                issue['reading']=m.group(2)
            if m.group(3):
                tmp="%s/%s/%s" % (m.group(3)[10:13], m.group(3)[:4], m.group(3)[5:9])
                if DEBUG: print >>sys.stderr, 'epdoc', tmp
                dossier=db.dossiers.find_one({'procedure.reference': tmp})
                if dossier:
                    if DEBUG: print >>sys.stderr, 'epdoc!', tmp
                    issue['epdoc']=tmp
                    issue['docref']=dossier['_id']
            if m.group(4):
                dossier=db.dossiers.find_one({'activities.documents.title': m.group(4)})
                if dossier:
                    if 'epdoc' in issue and not dossier['procedure']['reference'] == issue['epdoc']:
                        print >>sys.stderr, '[$] oops ep!=com', dossier['procedure']['reference'], issue['epdoc']
                    issue['docref']=dossier['_id']
                    issue['comdoc']=m.group(4)
            if m.group(5):
                issue['otherdoc']=m.group(5)
        #print '-'*80

def finalizeIssue(ax, issue):
    #print issue['seq_no'], ax[0].encode('utf8'), ax[1].encode('utf8')
    if DEBUG1: print >>sys.stderr, 'finalize', ax
    if not issue: return
    if ax[0] in ['Opinions', 'Responsible']:
        tmp=scrapOp(ax[1])
        if tmp:
            issue[ax[0]]=tmp
    elif ax[0] in ['Rapporteur', 'Shadow Rapporteur']:
        tmp=scrapRap(ax[1])
        if tmp:
            issue[ax[0]]=tmp
    elif ax[0]:
        if not ax[0]=='Misc':
            issue[ax[0]]=ax[1]

def scrape(comid, url, meeting_date):
    f=urllib2.urlopen(url)
    tmp=mkstemp()
    fd=os.fdopen(tmp[0],'w')
    fd.write(f.read())
    fd.close()
    f.close()
    lines=subprocess.Popen(['pdftotext', '-x', '0', '-y', '20', '-W', '1000', '-H', '740', '-nopgbrk', '-layout', tmp[1], '-'],
                     stdout=subprocess.PIPE).communicate()[0].split('\n')

    os.unlink(tmp[1])
    inblock=False
    res=[]
    state=None
    issue=None
    ax=['','']
    for (i,line) in enumerate(lines):
        if not len(line):
            inblock=False
            if DEBUG: print >>sys.stderr, 'blockend', line.encode('utf8')
            if issue:
                issue['meeting_date']=meeting_date
                getdocs(issue)
                finalizeIssue(ax, issue)
                res.append(issue)
            issue=None
            continue
        line=line.decode('utf8')
        # start a new meeting agenda
        m=datere.match(line)
        if m and not inblock:
            #meeting_date=datetime.fromtimestamp(mktime(strptime(m.group(1),"%d %B %Y, %H.%M")))
            meeting_date=datetime.strptime(m.group(1),"%d %B %Y, %H.%M")
            if DEBUG: print >>sys.stderr, 'date', line.encode('utf8')
            continue
        # start of a new agenda item
        m=block_start.match(line)
        if m:
            inblock=True
            if issue:
                issue['meeting_date']=meeting_date
                getdocs(issue)
                finalizeIssue(ax, issue)
                res.append(issue)
            issue={'committee': comid,'seq_no': int(m.group(1)), 'src': url, 'title': m.group(2)}
            ax=['title', m.group(2)]
            if DEBUG: print >>sys.stderr, 'issue', line.encode('utf8')
            continue
        # ignore all lines not in agenda items
        if not line[0]==' ':
            inblock=False
            if DEBUG: print >>sys.stderr, 'blockend', line.encode('utf8')
            continue
        # check for common fields
        newfield=False
        for field in fields:
            m=field[0].match(line)
            if m:
                finalizeIssue(ax, issue)
                if field[0]==corap and issue['title'].split('\n')[-1].strip().lower().startswith('co-    '):
                    ax=[field[1],"%s\n%s" % (issue['title'].split('\n')[-1].strip()[4:].strip(),m.group(1))]
                    issue['title']='\n'.join(issue['title'].split('\n')[:-1])
                    if DEBUG1: print >>sys.stderr, 'co-rap', ax[1].encode('utf8')
                else:
                    ax=[field[1],m.group(1)]
                newfield=True
                break
        if newfield:
            if DEBUG: print >> sys.stderr, 'newfield', line.encode('utf8')
            continue
        # parse misc agenda items
        m=misc_block.match(line)
        if m and inblock:
            issue['Misc']=issue.get('Misc',[])
            issue['Misc'].append(m.group(2))
            finalizeIssue(ax, issue)
            ax=['Misc','']
            if m.group(2).startswith('Deadline for tabling amendments:'):
                try:
                    issue['tabling_deadline']=datetime.fromtimestamp(mktime(strptime(m.group(2).split(':')[1].strip(),"%d %B %Y, %H.%M")))
                except ValueError:
                    try:
                        issue['tabling_deadline']=datetime.fromtimestamp(mktime(strptime(m.group(2).split(':')[1].strip(),"%d.%m.%Y at %H.%M")))
                    except:
                        print >>sys.stderr, '[$] unknown tabling deadline format', m.group(2).split(':')[1].strip()
            if DEBUG: print >> sys.stderr, 'misc', line.encode('utf8')
            continue

        if inblock and len(line.strip()):
            if ax[0]=='Opinions':
                m=opinion_junk.match(line)
                if m or line.strip()=='opinion:':
                    ax[1]="%s\n%s" % (ax[1],m.group(1))
                else:
                    ax[1]="%s\n%s" % (ax[1],line)
            elif ax[0]=='Misc':
                issue['Misc'][-1]+=line
            elif line.strip().startswith("%s/7/" % comid) and len(line.strip())==12:
                issue['comdossier']=line.strip()
                if DEBUG: print >> sys.stderr, 'comdossier', line.encode('utf8')
                continue
            else:
                ax[1]="%s\n%s" % (ax[1],line)
            if DEBUG: print >> sys.stderr, 'fall-through', line.encode('utf8')
    if issue:
        issue['meeting_date']=meeting_date
        getdocs(issue)
        finalizeIssue(ax, issue)
        res.append(issue)

    #print >>sys.stderr, '\n'.join(["%s %s %s" % (i['tabling_deadline'].isoformat(),
    #                                comid.strip(),
    #                                i.get('comref',i['title'].split('\n')[-2].strip()),
    #                                )
    #                  for i in res
    #                  if 'tabling_deadline' in i]).encode('utf8') or "no deadlines"
    sys.stderr.flush()
    return res

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif type(obj)==ObjectId:
        return str(obj)
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))

def crawl(db):
    result=[]
    tree=fetch("http://www.europarl.europa.eu/activities/committees/committeesList.do?language=EN")
    select=tree.xpath('//a[@class="commdocmeeting"]')
    for committee_url in select:
        comid=committee_url.xpath('../../td/a')[0].text.strip()
        #if not comid=='BUDG': continue
        print >>sys.stderr, 'checking', comid
        cmurl='http://www.europarl.europa.eu'+committee_url.get('href')
        commeets=fetch(cmurl)
        cmtree=commeets.xpath('//td/a')
        murl=urljoin(cmurl,cmtree[0].get('href'))
        meetdate=datetime.strptime(cmtree[0].xpath('text()')[0],"%d.%m.%Y")
        if meetdate < datetime.now():
            # skip past agendas
            print >>sys.stderr, "skipping past agenda"
            continue
        #print meetdate
        mtree=fetch(murl)
        pdflink=mtree.xpath("//td[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'DRAFT AGENDA') or text() = 'Draft programme']/..//a[text() = 'en']")
        if not pdflink:
            pdflink=mtree.xpath(u"//td[contains(text(),'OJ-réunion')]/..//a[text() = 'en']")
        if not pdflink:
            pdflink=mtree.xpath("//td[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'AGENDA') or contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'PROGRAMME')]/..//a[text() = 'en']")
        if pdflink:
            url=pdflink[0].get('href')
            try:
                data=scrape(comid,url, meetdate)
            except:
                print >>sys.stderr, 'url', url
                raise
            for item in data:
                q={'committee': comid, 'src': url, 'seq_no': item['seq_no']}
                db.ep_com_meets.update(q, {"$set": item}, upsert=True)
            result.append(data)
        else:
            print >> sys.stderr, '[!] Warning: no agenda/programme found', comid, murl
    if len(result):
        print json.dumps(result,indent=1,default=dateJSONhandler)

docre=re.compile(u'(.*)([A-Z][A-Z] \u2013 \S+)$')
def scrapRap(text):
    res={'docs':[],
         'rapporteurs':[]}
    tail=''
    for line in text.split('\n'):
        if line.strip().startswith(u"opinion:"):
            line=line.strip()[8:]
        elif line.strip().startswith(u"for the"):
            line=line.strip()[7:]
        line=line.strip()
        m=docre.search(line)
        if m:
            res['docs'].append(m.group(2).split(u' \u2013 '))
            line=m.group(1).strip()
        if DEBUG1: print >>sys.stderr, 'scrapar', line.encode('utf8')
        if line:
            if tail:
                line="%s %s" % (tail, line)
            m=getMep(line)
            if not m:
                tail=line
                print >>sys.stderr, "[!] docre oops:", line.encode('utf8')
            else:
                if DEBUG1: print >>sys.stderr, 'rapporteur', line.encode('utf8')
                res['rapporteurs'].append(m)
                tail=''
    return res

mepre=re.compile(r'(.*) \((.*)\)$')
def getMep(text):
    if not text.strip(): return
    m=mepre.search(text.strip())
    if m:
        group=m.group(2).strip()
        if group==None:
            return None

        name=m.group(1).strip()
        # TODO add date constraints based on groups.start/end
        mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.split()).lower(),
                                 "Groups.groupid": group})
        if not mep and u'ß' in name:
            mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower(),
                                     "Groups.groupid": group})
        if mep:
            return mep['_id']
        print >>sys.stderr, '[$] lookup oops:', text.encode('utf8')

    #mep=db.ep_meps.find_one({'Name.aliases': ''.join(text.split()).lower().strip()})
    #if not mep and u'ß' in text:
    #    mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower().strip()})
    #if mep:
    #    return mep['_id']

comre=re.compile(u'([A-Z]{4})(?: \(AL\)|\*?) –(.*)')
comlistre=re.compile(u'[A-Z]{4}(?:(?: \u2013|,) [A-Z]{4})*$')
def scrapOp(text):
    res=[]
    c={'docs':[], 'rapporteurs': []}
    tail=''
    for line in text.split('\n'):
        if line.strip().startswith(u"opinion:"):
            line=line.strip()[8:].strip()

        if comlistre.match(line):
            res.extend([{'committee': x.strip(), 'docs':[], 'rapporteurs': []} for x in line.split(', ')])
            if DEBUG1: print >>sys.stderr, 'comlistre', line.encode('utf8')
            continue

        m=comre.search(line)
        if m:
            if DEBUG1: print >>sys.stderr, 'comre', line.encode('utf8')
            #name=m.group(2)
            #mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.split()).lower()})
            #if not mep and u'ß' in name:
            #    mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower()})
            #if mep:
            #    c['rapporteurs'].append(mep['_id'])
            #else:
            #    print >>sys.stderr, '[%] warning tail not empty', tail.encode('utf8')
            if tail:
                print >>sys.stderr, '[%] warning tail not empty', tail.encode('utf8')
                tail=''
            if 'committee' in c:
                res.append(c)
            c={'committee': m.group(1),
               'docs':[],
               'rapporteurs': []}
            line=m.group(2).strip()

        m=docre.search(line)
        if m:
            if DEBUG1: print >>sys.stderr, 'docs', m.group(2).encode('utf8')
            c['docs'].append(m.group(2).split(u' \u2013 '))
            line=m.group(1).strip()

        if not len(line.strip()):
            if DEBUG1: print >>sys.stderr, 'emptyline', line.encode('utf8')
            continue
        if line=='Decision: no opinion':
            c['response']='Decision: no opinion'
            if DEBUG1: print >>sys.stderr, 'noop', line.encode('utf8')
            continue
        if line.strip() in ['***']:
            if DEBUG1: print >>sys.stderr, 'stars', line.encode('utf8')
            continue
        if len(tail):
            if line.strip().startswith(u'\u2013'):
                line=line.strip()[1:]
            line=' '.join((tail.strip(), line.strip()))
            tail=''
            if DEBUG1: print >>sys.stderr, 'tailupdate', line.encode('utf8')
        m=getMep(line)
        if m:
            c['rapporteurs'].append(m)
            line=''
        if line.strip():
            tail=line.strip()
    if 'committee' in c or 'committees' in c:
        if tail:
            name=tail.strip()
            mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.split()).lower()})
            if not mep and u'ß' in name:
                mep=db.ep_meps.find_one({'Name.aliases': ''.join(name.replace(u'ß','ss').split()).lower()})
            if mep:
                c['rapporteurs'].append(mep['_id'])
            else:
                print >>sys.stderr, '[%] warning tail not empty', tail.encode('utf8')
        res.append(c)
    return res


if __name__ == "__main__":
    crawl(db)
    #DEBUG=True
    #DEBUG1=True
    #print json.dumps(scrape('ASDF','http://www.europarl.europa.eu/meetdocs/2009_2014/documents/juri/oj/872/872316/872316en.pdf', datetime(2011,6,21)),indent=1,default=dateJSONhandler)
    #print json.dumps(scrape('JURI','http://www.europarl.europa.eu/meetdocs/2009_2014/documents/juri/oj/869/869993/869993en.pdf', datetime(2011,6,21)),indent=1,default=dateJSONhandler)

    #print json.dumps(scrape('BUDG','http://www.europarl.europa.eu/meetdocs/2009_2014/documents/cont/oj/869/869879/869879en.pdf', datetime(2011,6,21)),indent=1,default=dateJSONhandler)
    #print json.dumps(scrape('INTA','http://www.europarl.europa.eu/meetdocs/2009_2014/documents/inta/oj/869/869969/869969en.pdf', datetime(2011,6,21)),indent=1,default=dateJSONhandler)
    #print json.dumps(scrape('LIBE','http://www.europarl.europa.eu/meetdocs/2009_2014/documents/libe/oj/867/867690/867690en.pdf'),indent=1,default=dateJSONhandler)
    # find some tabling dates: db.ep_com_meets.find({'tabling_deadline' : { $exists : true }}).sort({'tabling_deadline': -1})
