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

def fetch(url):
    # url to etree
    f=urllib2.urlopen(url)
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

#("User-agent", "Mozilla/5.0 (Macintosh; U; PPC Mac OS X; en) AppleWebKit/125.2 (KHTML, like Gecko) Safari/125.8"),
def unws(txt):
    return ' '.join(strip(txt).split())

def details(url):
    root = fetch(url)
    data = { 'Committees': {},
             'URL': url }
    tmp=root.xpath("//td[@class='mepname']/text()")[0].split()
    data['Name'] = { 'name': ' '.join(tmp),
                     'family_name': tmp[-1],
                     'surname': ' '.join(tmp[:-1]),
                     'slug': ''.join(tmp)}
    data['UserID'] = int(url.split('=')[-1])
    data['Party'] = { 'role':  unws(''.join(root.xpath("//td[@style='width: 94%;']/span[@class='titlemep2']/text()"))),
                      'group': unws(''.join(root.xpath("//td[@style='width: 94%;']/span[@class='titlemep']/text()")))}
    data['Photo'] = '' if not len(root.xpath("//img[@class='photoframe']")) else BASE_URL + root.xpath("//img[@class='photoframe']")[0].attrib['src']
    tmp = map(unws, root.xpath("//td[@class='mep_CVtext']/text()"))
    data['National Party'] = tmp[0]
    (d,p)=tmp[1].split(',',1)
    data['Birth'] = { 'date': datetime.strptime(d, "Born on %d %B %Y"),
                      'place': p }
    data['Country'] = root.xpath("//td[@style='width: 91%;']/text()")[0]
    data['Homepage'] = '' if not len(root.xpath("//td[@class='mepurl']/a/text()")) else root.xpath("//td[@class='mepurl']/a/text()")[0]
    # LOL at HTML source - class="mepmail" -> obfuscation?! =))
    data['Mail'] = unws(''.join(root.xpath("//td[@class='mepmail']//text()")))
    data['Addresses'] = { 'Brussels': getAddress(map(strip, root.xpath("//td[@style='width: 225px; white-space: nowrap;']//text()"))),
                          'Strasbourg': getAddress(map(strip, root.xpath("//td[@style='width: 193px; white-space: nowrap;']//text()"))),
                          'Postal': [' '.join(x.split()) for x in root.xpath("//span[@class='txtmep']//text()") if x.strip()][1:]
                          }
    for c in root.xpath("//td[@class='mepcountry']"):
        key=unws(c.text)
        if key in ['Member', 'Substitute', 'Chair', 'Vice-Chair', 'Co-President']:
            if not 'Committees' in data:
                data['Committees']={}
            data['Committees'][key]=[]
            for cc in c.xpath("../../tr[@class='mep_CVtext']/td[2]"):
                if not len(cc.xpath('a')):
                    data['Committees'][key].append({'name': cc.text.strip()})
                else:
                    data['Committees'][key].append({'name': cc.text.strip(), 'url': BASE_URL+cc.xpath('a')[0].attrib['href']})
        elif key in ['President', 'Vice-President']:
            if not 'Roles' in data:
                data['Roles']={}
            data['Roles'][key] = []
            for cc in c.xpath("../../tr[@class='mep_CVtext']/td[2]"):
                data['Roles'][key].append({'name': cc.text.strip()})
        elif key=='Parliamentary activities':
            key='Activities'
            data[key] = []
            for cc in c.xpath("../../tr[@class='mep_CVtext']/td[2]"):
                data[key].append({'name': cc.text.strip(), 'url': BASE_URL+cc.xpath('a')[0].attrib['href']})
        else:
            if key not in ['Curriculum vitae']:
                print >>sys.stderr, '[!] unknown field', key
            data[key] = []
            for cc in c.xpath("../../tr[@class='mep_CVtext']/td[2]"):
                data[key].append(cc.text if not len(cc.xpath('a')) else (cc.text.strip(), BASE_URL+cc.xpath('a')[0].attrib['href']))
    # address datas
    q={'UserID': data['UserID']}
    db.ep_meps.update(q, {"$set": data}, upsert=True)
    #print json.dumps(data, indent=1, default=dateJSONhandler, ensure_ascii=False).encode('utf-8')

if __name__ == "__main__":
    for letter in uppercase:
        root = fetch("%s%s%s%s" % (BASE_URL,
                                   '/members/expert/alphaOrder.do?letter=',
                                   letter,
                                   '&language=EN')
        for data in  root.xpath("//td[@class='box_content_mep']/table/tr/td[2]"):
            details(BASE_URL+data.xpath("a")[0].attrib['href'])
