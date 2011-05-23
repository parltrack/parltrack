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

# externally depends on wvHtml

from lxml.html.soupparser import parse
from lxml.etree import tostring
from tempfile import mkdtemp, mkstemp
import urllib2, json, sys, subprocess, os
from cStringIO import StringIO
from parltrack.environment import connect_db

db = connect_db()

def fetchVotes(d):
    url="%s%s%s" % ("http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-//EP//NONSGML+PV+",
                    d,
                    "+RES-RCV+DOC+WORD+V0//EN&language=EN")
    f=urllib2.urlopen(url)
    tmp=mkstemp()
    fd=os.fdopen(tmp[0],'w')
    fd.write(f.read())
    fd.close()
    f.close()
    res=subprocess.Popen(['/usr/bin/wvHtml', tmp[1], '-'],
                     stdout=subprocess.PIPE).communicate()[0]
    os.unlink(tmp[1])
    return parse(StringIO(res))

def getVotes(f):
    tree=fetchVotes(f)

    res=[]
    items=tree.xpath('//div[@name="Heading 1"]')
    if not items:
        items=tree.xpath('//div[@name="VOTE INFO TITLE"]')
    for issue in items:
        # get rapporteur, report id and report type
        tmp=issue.xpath('string()').strip()
        vote={}
        if tmp.startswith('Report: '):
            (tmp,issue_type)=tmp.split(' - ')
            tmp=tmp.split(' ')
            vote['rapporteur']=' '.join(tmp[:-1])
            vote['report']=tmp[-1]
            vote['issue_type']=issue_type
        else:
            tmp=tmp.split(' - ')
            vote['report']=tmp[0]
            if len(tmp)==2:
                vote['issue_type']=tmp[1]
            elif len(tmp)==3:
                # sometimes a rapporteur, sometimes some kind of title
                rapporteurs=True
                rtmp=[]
                for mep in tmp[1].split(' and '):
                    mtmp=mep.split()
                    slug="%s%s" % (''.join(mtmp[:-1]), mtmp[-1].upper())
                    mep=db.ep_meps.find_one({"Name.slug": slug})
                    if not mep:
                        rapporteurs=False
                        break
                    # TODO remove str conversion if writing to db!!!!!!!!!!!!!
                    rtmp.append(str(mep['_id']))
                if not rapporteurs:
                    vote['title']=tmp[1]
                else:
                    vote['rapporteurs']=rtmp
                vote['issue_type']=tmp[2]
        # get timestamp
        vote['ts']=issue.xpath('following::td')[0].xpath('string()').strip()
        # get the +/-/0 votes
        for decision in issue.xpath('ancestor::table')[0].xpath("following::table")[0:3]:
            total,k=[x.strip() for x in decision.xpath('.//text()') if x.strip()]
            vote[k]={'total': total}
            for cur in decision.xpath('../following-sibling::*'):
                group=cur.xpath('.//b/text()')
                if group:
                    next=group[0].getparent().xpath('following-sibling::*/text()')
                    if next and next[0]==group[1]:
                        group=''.join(group[:2]).strip()
                    else:
                        group=group[0].strip()
                    voters=[x.strip() for x in cur.xpath('.//b/following-sibling::text()')[0].split(', ') if x.strip()]
                    if voters:
                        # strip of ":    " after the group name
                        voters[0]=voters[0][1:].strip()
                        vtmp=[]
                        for name in voters:
                            mep=None
                            for query in [{'Name.familylc': name.lower(),"Party.groupid": group},
                                          {'Name.slug1': ''.join(name.split()).lower(),"Party.groupid": group},
                                          {'Name.familylc': name.lower()}, # TODO Remove this, when we have historical data on MEPs activites/affiliations
                                          ]:
                                mep=db.ep_meps.find_one(query)
                                if mep:
                                    # TODO remove str conversion if writing to db!!!!!!!!!!!!!!!!!!
                                    vtmp.append(str(mep))
                                    break
                            if not mep:
                                print >>sys.stderr, '[?] warning unknown MEP', name.encode('utf8'), group.encode('utf8')
                                vtmp.append(name)
                        vote[k][group]=vtmp
                if cur.xpath('.//table'):
                    break
        # get the correctional votes
        cor=issue.xpath('ancestor::table')[0].xpath("following::table")[3]
        has_corr=' '.join([x for x in cor.xpath('tr')[0].xpath('.//text()') if x.strip()]).find(u"ПОПРАВКИ В ПОДАДЕНИТЕ ГЛАСОВЕ И НАМЕРЕНИЯ ЗА ГЛАСУВАНЕ")!=-1
        if has_corr:
            for row in cor.xpath('tr')[1:]:
                k,voters=[x.xpath('string()').strip() for x in row.xpath('td')]
                voters=[x.strip() for x in voters.split(', ') if x.strip()]
                if voters:
                    vote[k]['correctional']=voters
        res.append(vote)
    return res

if __name__ == "__main__":
    import platform
    if platform.machine() in ['i386', 'i686']:
        import psyco
        psyco.full()
    #getVotes(sys.argv[1])
    print json.dumps(getVotes(sys.argv[1]))
