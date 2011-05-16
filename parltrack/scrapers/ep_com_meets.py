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

datere=re.compile(r'^[0-9]{1,2} \w+ [0-9]{4}, [0-9]{2}\.[0-9]{2}( . [0-9]{2}\.[0-9]{2})?')
block_start=re.compile(r'^([0-9]+)\. {,10}(.*)')
fields=[(re.compile(r'^ {,10}Rapporteur: {3,}(.*)'),"Rapporteur"),
        (re.compile(r'^ {,10}Rapporteur for the (.*)'),"Shadow Rapporteur"),
        (re.compile(r'^ {,10}Responsible: {3,}(.*)'),'Responsible'),
        (re.compile(r'^ {,10}Opinions: {3,}(.*)'),"Opinions"),
        ]
misc_block=re.compile(r'^ {,10}\xef\x82\xb7 {3,}(.*)')
opinon_junk=re.compile(r'^ {,10}opinion: {3,}(.*)')
comref_re=re.compile(r' {3,}(COM\([0-9]{4}\)[0-9]{4})')

def fetch(url):
    # url to etree
    #print >> sys.stderr, url
    f=urllib2.urlopen(url)
    raw=parse(f)
    f.close()
    return raw

def scrape(comid, url):
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
    meeting_date=None
    for (i,line) in enumerate(lines):
        if not len(line): continue
        # start a new meeting agenda
        m=datere.match(line)
        if m and not inblock:
            meeting_date=datetime.fromtimestamp(mktime(strptime(m.group(0),"%d %B %Y, %H.%M")))
            continue
        # start of a new agenda item
        m=block_start.match(line)
        if m:
            inblock=True
            if ax[0]:
                issue[ax[0]]=ax[1]
            if issue:
                if meeting_date:
                    issue['meeting_date']=meeting_date
                res.append(issue)
            issue={'committee': comid,'seq no': m.group(1), 'src': url}
            ax=['title', m.group(2)]
            continue
        # ignore all lines not in agenda items
        if not line[0]==' ':
            inblock=False
            continue
        # check for common fields
        newfield=False
        for field in fields:
            m=field[0].match(line)
            if m:
                issue[ax[0]]=ax[1]
                ax=[field[1], m.group(1)]
                newfield=True
                break
        if newfield:
            continue
        # parse misc agenda items
        m=misc_block.match(line)
        if m:
            issue['Misc']=issue.get('Misc',[])
            issue['Misc'].append(m.group(1))
            if m.group(1).startswith('Deadline for tabling amendments:'):
                issue['tabling deadline']=datetime.fromtimestamp(mktime(strptime(m.group(1).split(':')[1].strip(),"%d %B %Y, %H.%M")))
            continue

        if inblock and len(line.strip()):
            if ax[0]=='Rapporteur (opinion)':
                m=opinon_junk.match(line)
                if m or line=='opinion:':
                    ax[1]="%s\n%s" % (ax[1],m.group(1))
            elif ax[0]=='title':
                m=comref_re.search(line)
                if m:
                    issue['comref']=m.group(1)
            ax[1]="%s\n%s" % (ax[1],line)

    print >>sys.stderr, '\n'.join(["%s %s %s" % (i['tabling deadline'].isoformat(),
                                    comid.strip(),
                                    i.get('comref',i['title'].split('\n')[-2].strip()),
                                    )
                      for i in res
                      if 'tabling deadline' in i])
    sys.stderr.flush()
    return res

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(Obj), repr(Obj))

def crawl(db):
    result=[]
    tree=fetch("http://www.europarl.europa.eu/activities/committees/committeesList.do?language=EN")
    select=tree.xpath('//a[@class="commdocmeeting"]')
    for committee_url in select:
        comid=committee_url.xpath('../../td/a')[0].text.strip()
        cmurl='http://www.europarl.europa.eu'+committee_url.get('href')
        commeets=fetch(cmurl)
        cmtree=commeets.xpath('//td/a')
        murl=urljoin(cmurl,cmtree[0].get('href'))
        mtree=fetch(murl)
        pdflink=mtree.xpath("//td[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'DRAFT AGENDA') or text() = 'Draft programme']/..//a[text() = 'en']")
        if not pdflink:
            pdflink=mtree.xpath(u"//td[contains(text(),'OJ-réunion')]/..//a[text() = 'en']")
        if not pdflink:
            pdflink=mtree.xpath("//td[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'AGENDA') or contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'PROGRAMME')]/..//a[text() = 'en']")
        if pdflink:
            url=pdflink[0].get('href')
            try:
                data=scrape(comid,url)
            except:
                print url
                raise
            for item in data:
                q={'src': url, 'seq no': item['seq no']}
                db.ep_com_meets.update(q, {"$set": item}, upsert=True)
            result.append(data)
        else:
            print >> sys.stderr, '[!] Warning: no agenda/programme found', comid, murl
    # TODO save to mongo
    print json.dumps(result,default=dateJSONhandler)

if __name__ == "__main__":
    db = connect_db()
    crawl(db)
    # find some tabling dates: db.ep_com_meets.find({'tabling deadline' : { $exists : true }}).sort({'tabling deadline': -1})
