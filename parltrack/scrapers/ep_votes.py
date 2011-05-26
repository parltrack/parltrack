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
import urllib2, json, sys, subprocess, os, re
from cStringIO import StringIO
from parltrack.environment import connect_db
from datetime import datetime
from ep_meps import group_map
from bson.objectid import ObjectId

db = connect_db()
db.ep_meps.ensure_index([('Name.aliases', 1)])
db.ep_meps.ensure_index([('Name.familylc', 1)])

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

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif type(obj)==ObjectId:
        return str(obj)
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))

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
        # get timestamp
        vote['ts']= datetime.strptime(issue.xpath('following::td')[0].xpath('string()').strip().replace('.000',''),
                          "%d/%m/%Y %H:%M:%S")
        if tmp.startswith('Report: '):
            (tmp,issue_type)=tmp.split(' - ')
            tmp=tmp.split(' ')
            mep=' '.join(tmp[:-1])[8:]
            vote['rapporteur']=mep
            mep=db.ep_meps.find_one({"Name.aliases": mep.lower(),
                                     "Constituencies.start" : {'$lt': vote['ts']},
                                     "Constituencies.end" : {'$gt': vote['ts']}})
            if not mep and u'ß' in vote['rapporteur']:
                mep=db.ep_meps.find_one({"Name.aliases": vote['rapporteur'].replac(u'ß','ss').lower(),
                                         "Constituencies.start" : {'$lt': vote['ts']},
                                         "Constituencies.end" : {'$gt': vote['ts']}})
            if mep:
                vote['rapporteur']=mep['_id']
            vote['report']=tmp[-1]
            report=db.dossiers.find_one({"activities.documents.title": tmp[-1]})
            if report:
                vote['report']=report['_id']
            vote['issue_type']=issue_type
        else:
            tmp=tmp.split(' - ')
            vote['report']=tmp[0]
            report=db.dossiers.find_one({"activities.documents.title": tmp[0]})
            if report:
                vote['report']=report['_id']
            if len(tmp)==2:
                vote['issue_type']=tmp[1]
            elif len(tmp)==3:
                # sometimes a rapporteur, sometimes some kind of title
                rapporteurs=True
                rtmp=[]
                for name in tmp[1].split(' and '):
                    mep=db.ep_meps.find_one({"Name.aliases": name.lower()})
                    if not mep and u'ß' in name:
                        mep=db.ep_meps.find_one({"Name.aliases": name.replac(u'ß','ss').lower()})
                    if not mep:
                        rapporteurs=False
                        break
                    rtmp.append(mep['_id'])
                if not rapporteurs:
                    vote['title']=tmp[1]
                else:
                    vote['rapporteurs']=rtmp
                vote['issue_type']=tmp[2]
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
                    voters=[x.strip() for x in cur.xpath('.//b/following-sibling::text()')[0].split(',') if x.strip()]
                    if voters:
                        # strip of ":    " after the group name
                        if voters[0][0]==':': voters[0]=voters[0][1:].strip()
                        vtmp=[]
                        for name in voters:
                            mep=None
                            queries=[({'Name.familylc': name.lower(),
                                       "Groups.groupid": group,
                                       "Groups.start" : {'$lt': vote['ts']},
                                       "Groups.end" : {'$gt': vote['ts']} },1),
                                     ({'Name.aliases': ''.join(name.split()).lower(),
                                       "Groups.groupid": group,
                                       "Groups.start" : {'$lt': vote['ts']},
                                       "Groups.end" : {'$gt': vote['ts']}},2),
                                     ({'Name.familylc': re.compile(name,re.I),
                                       "Groups.groupid": group,
                                       "Groups.start" : {'$lt': vote['ts']},
                                       "Groups.end" : {'$gt': vote['ts']}},2),
                                     # TODO Remove this, when we have historical data on MEPs activites/affiliations
                                     ({'Name.familylc': name.lower()},3),
                                     ({'Name.aliases': re.compile(name,re.I)},4),
                                     ]
                            if u'ß' in name:
                                queries.extend([({'Name.familylc': name.replace(u'ß','ss').lower(),
                                       "Groups.groupid": group,
                                       "Groups.start" : {'$lt': vote['ts']},
                                       "Groups.end" : {'$gt': vote['ts']} },1),
                                     ({'Name.aliases': ''.join(name.split()).replace(u'ß','ss').lower(),
                                       "Groups.groupid": group,
                                       "Groups.start" : {'$lt': vote['ts']},
                                       "Groups.end" : {'$gt': vote['ts']}},2),
                                     ({'Name.familylc': re.compile(name.replace(u'ß','ss'),re.I),
                                       "Groups.groupid": group,
                                       "Groups.start" : {'$lt': vote['ts']},
                                       "Groups.end" : {'$gt': vote['ts']}},2),
                                     # TODO Remove this, when we have historical data on MEPs activites/affiliations
                                     ({'Name.familylc': name.replace(u'ß','ss').lower()},3),
                                     ({'Name.aliases': re.compile(name.replace(u'ß','ss'),re.I)},4)])
                            for query,q in queries:
                                mep=db.ep_meps.find_one(query)
                                if mep:
                                    # TODO remove str conversion if writing to db!!!!!!!!!!!!!!!!!!
                                    #vtmp.append(mep['_id'])
                                    vtmp.append({'id': mep['_id'], 'q': q, 'orig': name})
                                    if q>2: print >>sys.stderr, '[!]', q, name.encode('utf8'), group
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
                k,voters=[x.xpath('string()').strip() for x in row.xpath('td') if x.xpath('string()').find(u"ПОПРАВКИ В ПОДАДЕНИТЕ ГЛАСОВЕ И НАМЕРЕНИЯ ЗА ГЛАСУВАНЕ")==-1]
                if k not in ['0','+','-']: continue
                voters=[x.strip() for x in voters.split(',') if x.strip()]
                if voters:
                    vote[k]['correctional']=[]
                    for name in voters:
                        mep=None
                        queries=[({'Name.familylc': name.lower(),
                                   "Constituencies.start" : {'$lt': vote['ts']},
                                   "Constituencies.end" : {'$gt': vote['ts']} }, 1),
                                 ({'Name.aliases': ' '.join(name.split()).lower(),
                                   "Constituencies.start" : {'$lt': vote['ts']},
                                   "Constituencies.end" : {'$gt': vote['ts']} },2),
                                 ]
                        if u'ß' in name:
                            queries.extend([({'Name.familylc': name.replace(u'ß','ss').lower(),
                                   "Constituencies.start" : {'$lt': vote['ts']},
                                   "Constituencies.end" : {'$gt': vote['ts']} }, 1),
                                 ({'Name.aliases': ' '.join(name.split()).replace(u'ß','ss').lower(),
                                   "Constituencies.start" : {'$lt': vote['ts']},
                                   "Constituencies.end" : {'$gt': vote['ts']} },2)])
                        for query,q in queries:
                            mep=db.ep_meps.find_one(query)
                            if mep:
                                vote[k]['correctional'].append({'id': mep['_id'], 'q': q, 'orig': name})
                                break
                        if not mep:
                            print >>sys.stderr, '[?] warning unknown MEP', name.encode('utf8')
                            vote[k]['correctional'].append(name)
        res.append(vote)
    return res

if __name__ == "__main__":
    import platform
    if platform.machine() in ['i386', 'i686']:
        import psyco
        psyco.full()
    #getVotes(sys.argv[1])
    print json.dumps(getVotes(sys.argv[1]),indent=1, default=dateJSONhandler)
