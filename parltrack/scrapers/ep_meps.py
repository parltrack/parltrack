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

import json, urllib2,sys
from datetime import datetime
from string import strip, uppercase
from lxml.html.soupparser import parse
from parltrack.environment import connect_db

BASE_URL = 'http://www.europarl.europa.eu'
db = connect_db()
#proxy_handler = urllib2.ProxyHandler({'http': 'http://localhost:8123/'})
#opener = urllib2.build_opener(proxy_handler)
#("User-agent", "Mozilla/5.0 (Macintosh; U; PPC Mac OS X; en) AppleWebKit/125.2 (KHTML, like Gecko) Safari/125.8"),
#opener.addheaders = [('User-agent', 'parltrack/0.7')]
#urllib2.install_opener(opener)

def fetch(url):
    # url to etree
    try:
        f=urllib2.urlopen(url)
    except urllib2.HTTPError:
        return ''
    return parse(f)

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(Obj), repr(Obj))

def getAddress(txts):
    flag = 0
    ret = {'Address': [], 'Phone': '', 'Fax': ''}
    for addr in txts:
        if not addr:
            continue
        if addr == 'Tel.':
            flag = 1
            continue
        elif addr == 'Fax':
            flag = 2
            continue
        if flag == 1:
            ret['Phone'] = addr
        elif flag == 2:
            ret['Fax'] = addr
        else:
            ret['Address'].append(addr)
    if len(ret['Address'])==7:
        ret['Address']=dict(zip(['Organization','Building','Office','Street','Zip1', 'Zip2', 'City'],ret['Address']))
    else:
        ret['Address']=dict(zip(['Organization','Building','Office','Street','Zip','City'],ret['Address']))
    return ret

def unws(txt):
    return ' '.join(strip(txt).split())

def splitDatedInfo(text,title):
    (period, text)=text.split(' : ',1)
    (start, end)=period.split(' / ',1)
    if end == '...':
        end='31.12.9999' # end of time
    item={title: text,
          'start': datetime.strptime(start,"%d.%m.%Y"),
          'end': datetime.strptime(end,"%d.%m.%Y")}
    return item

def parseMember(userid):
    url='http://www.europarl.europa.eu/members/expert/alphaOrder/view.do?language=EN&id=%s' % userid
    root = fetch(url)
    data = {'active': True}
    if not root or root.xpath('head/title/text()')=='The requested page does not exist.':
        return {'active': False}
    group=unws(''.join(root.xpath("//td[@style='width: 94%;']/span[@class='titlemep']/text()")))
    data['Groups'] = [{ 'role':  unws(''.join(root.xpath("//td[@style='width: 94%;']/span[@class='titlemep2']/text()"))),
                      'group': group,
                      'groupid': group_map[group]}]
    data['Photo'] = '' if not len(root.xpath("//img[@class='photoframe']")) else BASE_URL + root.xpath("//img[@class='photoframe']")[0].attrib['src']
    tmp = map(unws, root.xpath("//td[@class='mep_CVtext']/text()"))
    (d,p)=tmp[-1].split(',',1)
    data['Birth'] = { 'date': datetime.strptime(d, "Born on %d %B %Y"),
                      'place': p.strip() }
    data['Homepage'] = '' if not len(root.xpath("//td[@class='mepurl']/a/text()")) else root.xpath("//td[@class='mepurl']/a/text()")[0]
    # LOL at HTML source - class="mepmail" -> obfuscation?! =))
    data['Mail'] = unws(''.join(root.xpath("//td[@class='mepmail']//text()")))
    data['Addresses'] = { 'Brussels': getAddress(map(strip, root.xpath("//td[@style='width: 225px; white-space: nowrap;']//text()"))),
                          'Strasbourg': getAddress(map(strip, root.xpath("//td[@style='width: 193px; white-space: nowrap;']//text()"))),
                          'Postal': [' '.join(x.split()) for x in root.xpath("//span[@class='txtmep']//text()") if x.strip()][1:]
                          }
    for c in root.xpath("//td[@class='mepcountry']"):
        key=unws(c.text)
        if key in ['Member', 'Substitute', 'Chair', 'Vice-Chair', 'Co-President', 'President', 'Vice-President', 'Parliamentary activities']:
            continue # all urls can be recreated from the UserID
        if key not in ['Curriculum vitae']:
            print >>sys.stderr, '[!] unknown field', key
        data[key] = []
        for cc in c.xpath("../../tr[@class='mep_CVtext']/td[2]"):
            data[key].append(cc.text if not len(cc.xpath('a')) else (cc.text.strip(), BASE_URL+cc.xpath('a')[0].attrib['href']))
    return data

def mangleName(name):
    family=name.split(', ')[0]
    try:
        sur=name.split(', ')[1]
    except:
        sur=''
    tmp=family.split()
    title=None
    if tmp[0] in ['Sir', 'Lady', 'Baroness', 'Baron', 'Lord', 'Earl', 'Duke']:
        title=tmp[0]
        family=' '.join(tmp[1:])
    res= { 'full': name,
             'sur': sur,
             'family': family,
             'familylc': family.lower(),
             'aliases': ["%s %s" % (family, sur),
                         ("%s %s" % (family, sur)).lower(),
                         "%s %s" % (sur, family),
                         ("%s %s" % (sur, family)).lower(),
                         ''.join(("%s%s" % (family, sur)).split()),
                         ''.join(("%s%s" % (sur, family)).split()),
                         ''.join(("%s%s" % (family, sur)).split()).lower(),
                         ''.join(("%s%s" % (sur, family)).split()).lower(),
                         family.lower(),
                         family],}
    if title:
        res['title']=title
        res['aliases'].extend(["%s %s %s" % (title ,family, sur),
                               "%s %s %s" % (title, sur, family),
                               ("%s %s %s" % (title, sur, family)).lower(),
                               "%s %s %s" % (title, family, sur),
                               ("%s %s %s" % (title, family, sur)).lower(),
                               "%s %s" % (title, family),
                               ''.join(("%s%s%s" % (title, family, sur)).split()),
                               ''.join(("%s%s%s" % (title, sur, family)).split()),
                               ''.join(("%s%s%s" % (title, family, sur)).split()).lower(),
                               ''.join(("%s%s%s" % (title, sur, family)).split()).lower(),
                               ])
    if family in meps_aliases:
           res['aliases'].extend(meps_aliases[family])
    return res

def parseRoles(c, data):
    key=unws(c.text)
    if key=='Parliamentary activities':
        return data # all urls can be recreated from the UserID
    for cc in c.xpath("../../tr[@class='mep_CVtext']/td[2]"):
        name=' '.join(cc.xpath('string()').split())
        item=splitDatedInfo(name,'Organization')
        item['Role']=key
        if len(cc.xpath('a')):
            item['url']=BASE_URL+cc.xpath('a')[0].attrib['href']
        found=False
        for start, field in orgmaps:
            if item['Organization'].startswith(start):
                if not field in data:
                    data[field]=[]
                data[field].append(item)
                found=True
                break
        if found:
            continue
        if item['Organization'] in GROUPS or item['Organization'] in group_map:
                if not 'Groups' in data:
                    data['Groups']=[]
                if item['Organization'] in group_map:
                    item['groupid']=group_map[item['Organization']]
                # TODO find out exact date of when the 2001 term started
                elif item['start']>datetime.strptime("30092001","%d%m%Y"):
                    print >>sys.stderr, '[!] unrecognized group', key, item
                data['Groups'].append(item)
                continue
        print >>sys.stderr, '[!] unrecognized data', key, item
    return data

def scrape(userid, name):
    data = { 'Constituencies': [],
             'Name' : mangleName(name),
             'UserID': userid }
    # retrieve supplemental info for currently active meps
    data.update(parseMember(userid))

    # process also historical data
    root=fetch("http://www.europarl.europa.eu/members/public/inOut/viewOutgoing.do?language=EN&id=%s" % data['UserID'])
    # process info of Constituencies
    for line in root.xpath("//table[@class='titlemep']/tr"):
        tmp=[' '.join(x.split()).strip() for x in line.xpath('td/text()') if ' '.join(x.split()).strip()]
        (period, group)=tmp[1].split(' : ',1)
        try:
            (start, end)=period.split(' / ',1)
        except:
            start=period.split()[0]
            end='31.12.9999' # end of time
            data['Groups'][0].update({'start':datetime.strptime(start,"%d.%m.%Y"), 'end': datetime.strptime(end,"%d.%m.%Y")})
        start=datetime.strptime(start,"%d.%m.%Y")
        end=datetime.strptime(end,"%d.%m.%Y")
        data['Constituencies'].append({
            'start': start,
            'end': end,
            'country': tmp[0],
            'party': group})
    # process other historical data
    for c in root.xpath("//td[@class='mepcountry']"):
        data=parseRoles(c, data)
    q={'UserID': data['UserID']}
    db.ep_meps.update(q, {"$set": data}, upsert=True)
    print json.dumps(data, indent=1, default=dateJSONhandler, ensure_ascii=False).encode('utf-8')

group_map={ "Confederal Group of the European United Left - Nordic Green Left": 'GUE/NGL',
            "Confederal Group of the European United Left-Nordic Green Left": 'GUE/NGL',
            'Confederal Group of the European United Left / Nordic Green Left': 'GUE/NGL',
            'Confederal Group of the European United Left/Nordic Green Left': 'GUE/NGL',
            "European Conservatives and Reformists": 'ECR',
            'European Conservatives and Reformists Group': 'ECR',
            "Europe of freedom and democracy Group": 'EFD',
            'Europe of Freedom and Democracy Group': 'EFD',
            "Group of the Alliance of Liberals and Democrats for Europe": 'ALDE',
            "Group of the Greens/European Free Alliance": "Verts/ALE",
            "Group of the Progressive Alliance of Socialists and Democrats in the European Parliament": "S&D",
            "Non-attached Members": "NI",
            'Group for a Europe of Democracies and Diversities': 'EDD',
            'Group of the European Liberal Democrat and Reform Party': 'ELDR',
            'Group of the European Liberal, Democrat and Reform Party': 'ELDR',
            'Group indépendence/Démocratie': ['ID','INDDEM'],
            'Independence/Democracy Group': ['ID', 'INDDEM'],
            'Identity, Tradition and Sovereignty Group': 'ITS',
            'Non-attached Members': ['NA','NI'],
            'Non-attached': ['NA','NI'],
            "Group of the European People's Party (Christian Democrats) and European Democrats": 'PPE-DE',
            "Group of the European People's Party (Christian Democrats)": 'PPE',
            "Group of the European People's Party (Christian-Democratic Group)": "PPE",
            'Group of the Party of European Socialists': 'PSE',
            'Socialist Group in the European Parliament': 'PSE',
            'Technical Group of Independent Members': 'TDI',
            'Group indépendence/Démocratie': 'UEN',
            'Union for a Europe of Nations Group': 'UEN',
            'Union for Europe of the Nations Group': 'UEN',
            'Group of the Greens / European Free Alliance': 'Verts/ALE',
            'Greens/EFA': 'Verts/ALE',
            }

orgmaps=[('Committee o', 'Committees'),
        ('Temporary committee ', 'Committees'),
        ('Temporary Committee ', 'Committees'),
        ('Subcommittee on ', 'Committees'),
        ('Special Committee ', 'Committees'),
        ('Special committee ', 'Committees'),
        ('Legal Affairs Committee', 'Committees'),
        ('Political Affairs Committee', 'Committees'),
        ('Delegation','Delegations'),
        ('Members from the European Parliament to the Joint ', 'Delegations'),
        ('Membres fron the European Parliament to the ', 'Delegations'),
        ('Conference of ', 'Staff'),
        ("Parliament's Bureau", 'Staff'),
        ('European Parliament', 'Staff'),
        ('Quaestors', 'Staff'),]

GROUPS=[
   'Communist and Allies Group',
   'European Conservative Group',
   'European Conservatives and Reformists',
   'European Democratic Group',
   'Europe of freedom and democracy Group',
   'Europe of Nations Group (Coordination Group)',
   'Forza Europa Group',
   'Confederal Group of the European United Left',
   'Confederal Group of the European United Left/Nordic Green Left',
   'Confederal Group of the European United Left - Nordic Green Left',
   'Christian-Democratic Group',
   "Group of the European People's Party ",
   'Group for a Europe of Democracies and Diversities',
   'Group for the European United Left',
   'Group for the Technical Coordination and Defence of Indipendent Groups and Members',
   'Group of Independents for a Europe of Nations',
   'Group of the Alliance of Liberals and Democrats for Europe',
   'Group of the European Democratic Alliance',
   'Group of the European Liberal, Democrat and Reform Party',
   'Group of the European Radical Alliance',
   'Group of the European Right',
   'Group of the Greens/European Free Alliance',
   'Group of the Party of European Socialists',
   'Group of the Progressive Alliance of Socialists and Democrats in the European Parliament',
   "Group of the European People's Party (Christian Democrats) and European Democrats",
   "Group of the European People's Party (Christian Democrats)",
   'Group Union for Europe',
   'Identity, Tradition and Sovereignty Group',
   'Independence/Democracy Group',
   'Left Unity',
   'Liberal and Democratic Group',
   'Liberal and Democratic Reformist Group',
   'Non-attached',
   'Non-attached Members',
   "Rainbow Group: Federation of the Green Alternative European Links, Agelev-Ecolo, the Danish People's Movement against Membership of the European Community and the European Free Alliance in the European Parliament",
   'Rainbow Group in the European Parliament',
   'Socialist Group',
   'Socialist Group in the European Parliament',
   'Technical Coordination and Defence of Independent Groups and Members',
   'Technical Group of Independent Members - mixed group',
   'Technical Group of the European Right',
   'The Green Group in the European Parliament',
   'Union for Europe of the Nations Group', ]

meps_aliases={
    u'GRÈZE': ['GREZE', 'greze', 'Catherine Greze', 'catherine greze'],
    u'SCOTTÀ': ["SCOTTA'", "scotta'"],
    u"in 't VELD": ["in't VELD", "in't veld", "IN'T VELD"],
    u'MORKŪNAITĖ-MIKULĖNIENĖ': [u"MORKŪNAITĖ Radvilė",u"morkūnaitė radvilė",u"radvilė morkūnaitė ",u"Radvilė MORKŪNAITĖ ", u"MORKŪNAITĖ", u"morkūnaitė"],
    }

if __name__ == "__main__":
    seen=[]
    for letter in uppercase:
        for term in [5, 6, 7]:
            root = fetch("http://www.europarl.europa.eu/members/archive/term%d.do?letter=%s&language=EN" % (
                term,
                letter))
            for data in  root.xpath("//td[@class='box_content_mep']/table/tr/td[2]"):
                userid=dict([x.split('=') for x in data.xpath("a")[0].attrib['href'].split('?')[1].split('&')])['id']
                if not userid in seen:
                    print >>sys.stderr,data.xpath('a/text()')[0].encode('utf8')
                    scrape(userid,data.xpath('a/text()')[0])
                    seen.append(userid)
