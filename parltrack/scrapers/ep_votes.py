#!/usr/bin/env python

# externally depends on wvHtml

from lxml.html.soupparser import parse
from tempfile import mkdtemp, mkstemp
import urllib2, json, sys, subprocess, os
from cStringIO import StringIO

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
    res=subprocess.Popen(['wvHtml', tmp[1], '-'],
                     stdout=subprocess.PIPE).communicate()[0]
    os.unlink(tmp[1])
    return parse(StringIO(res))

def getVotes(f):
    tree=fetchVotes(f)

    res=[]
    for issue in tree.xpath('//div[@name="Heading 1"]'):
        # get rapporteur, report id and report type
        tmp=issue.xpath('string()').strip()
        (tmp1, issue_type)=tmp.split(' - ')
        tmp=tmp1.split(' ')
        vote={'rapporteur': ' '.join(tmp[1:-1]),
              'report': tmp[-1],
              'issue_type': issue_type}
        # get timestamp
        vote['ts']=issue.xpath('following::td')[0].xpath('string()').strip()
        # get the +/-/0 votes
        for decision in issue.xpath('ancestor::table')[0].xpath("following::table")[0:3]:
            total,k=[x.strip() for x in decision.xpath('.//text()') if x.strip()]
            vote[k]={'total': total}
            for cur in decision.xpath('../following-sibling::*'):
                if cur.xpath('.//table'):
                    break
                group=cur.xpath('.//b/text()')
                if group:
                    group=group[0].strip()
                    vote[k][group]=[x.strip() for x in cur.xpath('.//b/following-sibling::text()')[0].split(', ')]
                    # strip of ":    " after the group name
                    vote[k][group][0]=vote[k][group][0][1:].strip()
        # get the correctional votes
        cor=issue.xpath('ancestor::table')[0].xpath("following::table")[3]
        for row in cor.xpath('tr')[1:]:
            k,voters=[x.xpath('string()').strip() for x in row.xpath('td')]
            vote[k]['correctional']=[x.strip() for x in voters.split(', ') if x.strip()]
        # a simple sanity check
        for x in ['+', '-', '0']:
            tot=0
            total=0
            for k in vote[x]:
                if k=='total':
                    total=vote[x][k]
                else:
                    tot+=len(vote[x][k])
            if total!=tot+len(vote[x]['correctional']):
                print "sanity check failed number of votes inconsistent!"
                raise
        res.append(vote)
    return res

if __name__ == "__main__":
    print json.dumps(getVotes(sys.argv[1]))
