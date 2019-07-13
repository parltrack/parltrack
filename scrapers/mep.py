#!/usr/bin/env python3
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

# (C) 2019 by Stefan Marsiske, <parltrack@ctrlc.hu>

import re,sys
from utils.utils import fetch, fetch_raw, unws, jdump, getpdf
from utils.process import process
from utils.mappings import buildings, SEIRTNUOC, COMMITTEE_MAP, ORGMAPS, GROUP_MAP, DELEGATIONS, MEPS_ALIASES, TITLES
from utils.log import log
from datetime import datetime
from lxml.html.soupparser import fromstring
from db import db
from scrapers import _findecl as findecl

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'table': 'ep_meps',
    'abort_on_error': True,
}

def scrape(id, **kwargs):
    # we ignore the /meps/en/<id>/<name>/home path, since we can get all info also from other pages
    url = "http://www.europarl.europa.eu/meps/en/%s/name/cv" % id
    xml = fetch_raw(url) # we have to patch up the returned html...
    xml = xml.replace("</br>","<br/>") # ...it contains some bad tags..
    root = fromstring(xml) # ...which make the lxml soup parser drop some branches in the DOM

    body = root.xpath('//span[@id="mep-card-content"]/following-sibling::div')[0]
    mep = {
        'UserID'    : id,
        'Name'      : mangleName(unws(' '.join(root.xpath('//*[@id="name-mep"]//text()'))), id),
        'Photo'     : "https://www.europarl.europa.eu/mepphoto/%s.jpg" % id,
        'meta'      : {'url': url},
        'Twitter'   : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@class="ep_share"]//a[@title="Twitter"]/@href')],
        'Homepage'  : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@class="ep_share"]//a[@title="Website"]/@href')],
        'Facebook'  : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@class="ep_share"]//a[@title="Facebook"]/@href')],
        'Instagram' : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@class="ep_share"]//a[@title="Instagram"]/@href')],
        'Mail'      : [deobfus_mail(x) for x in root.xpath('//div[@class="ep_share"]//a[@title="E-mail"]/@href')],
        'Addresses' : parse_addr(root),
        'active'    : False,
    }

    birthdate = root.xpath('//time[@id="birthDate"]/text()')
    if len(birthdate)>0:
        mep['Birth']={'date': datetime.strptime(birthdate[0], u"%d-%m-%Y")}
        place=root.xpath('//span[@id="birthPlace"]/text()')
        if len(place)>0:
            mep['Birth']['place']=str(place[0])

    death = root.xpath('//time[@id="deathDate"]/text()')
    if death:
        mep['Death'] = datetime.strptime(unws(death[0]), u"%d-%m-%Y")

    if body.xpath('//span[@class="ep_name" and text()="Curriculum vitae "]'):
        if not body.xpath('//span[@id="no_cv_available"]'):
            mep['CV']= {'updated': datetime.strptime(root.xpath('//span[starts-with(text(),"Updated: ")]/text()')[0], u"Updated: %d/%m/%Y")}
            mep['CV'].update({unws(''.join(title.xpath(".//text()"))): [unws(''.join(item.xpath(".//text()"))).replace("-...", "- ...")
                                                                        for item in title.xpath("../../../article//li")]
                            for title in body.xpath('.//h3')
                            if not unws(''.join(title.xpath(".//text()"))).startswith("Original version : ")})

    # assistants
    url = "http://www.europarl.europa.eu/meps/en/%s/name/assistants" % id
    root = fetch(url)
    body = root.xpath('//span[@id="mep-card-content"]/following-sibling::div')[0]
    if unws(' '.join(body.xpath(".//h1/div/div/span[@class='ep_name']/text()"))) == "Assistants":
        for h3 in body.xpath('.//h3'):
            title = unws(''.join(h3.xpath(".//text()")))
            assistants = [unws(''.join(item.xpath(".//text()"))) for item in h3.xpath("../../../article//li")]
            if title in ['Accredited assistants', 'Local assistants']:
                if not 'assistants' in mep: mep['assistants']={}
                title = title.lower().split()[0]
                if assistants: mep['assistants'][title]=assistants
            elif title in ['Accredited assistants (grouping)', 'Local assistants (grouping)',
                           'Service providers', 'Trainees', 'Paying agents (grouping)', 'Paying agents',
                           'Assistants to the Vice-Presidency/to the Quaestorate']:
                if not 'assistants' in mep: mep['assistants']={}
                title = title.lower()
                if assistants: mep['assistants'][title]=assistants
            else:
                log(2,'unknown title for assistants "{}" {}'.format(title, url))
                raise ValueError

    # declarations
    root = fetch("http://www.europarl.europa.eu/meps/en/%s/name/declarations" % id)
    body = root.xpath('//span[@id="mep-card-content"]/following-sibling::div')[0]
    if unws(' '.join(body.xpath(".//h1/div/div/span[@class='ep_name']/text()"))) == "Declarations":
        for title in body.xpath('.//h3'):
            key = unws(''.join(title.xpath('.//text()')))
            if key == 'Declaration of financial interests':
                key = 'Financial Declarations'
                mep[key] = []
                for pdf in title.xpath('../../following-sibling::div//li//a'):
                    url = pdf.xpath('./@href')[0]
                    #scraper_service.add_job('findecl', payload={'id':id, 'url': url})
                    try:
                        mep[key].append(findecl.scrape(url))
                    except:
                        log(1,"failed to extract findecl from %s" % url)
            elif key == 'Declarations of participation by Members in events organised by third parties':
                key = 'Declarations of Participation'
                mep[key] = []
                for pdf in title.xpath('../../following-sibling::div//li//a')[::-1]: # reversed order, otherwise newer ones get prepended and mess up the diff
                    url = pdf.xpath('./@href')[0]
                    name = unws(''.join(pdf.xpath('.//text()')))
                    mep[key].append({'title': name, 'url': url})
            elif key == 'Declaration of good conduct':
                mep[key] = []
                for pdf in title.xpath('../../following-sibling::div//li//a')[::-1]: # reversed order, otherwise newer ones get prepended and mess up the diff
                    url = pdf.xpath('./@href')[0]
                    name = unws(''.join(pdf.xpath('.//text()')))
                    mep[key].append({'title': name, 'url': url})
            else:
                log(2, 'unknown type of declaration: "%s" http://www.europarl.europa.eu/meps/en/%s/name/declarations' % (key, id))
                key = None
                raise ValueError

    # history
    parse_history(id, root, mep)
    process(mep, id, db.mep, 'ep_meps', mep['Name']['full'], nopreserve=(['Addresses'], ['assistants']))

    if __name__ == '__main__':
        return mep
    del mep

def deobfus_mail(txt):
    x = txt.replace('[at]','@').replace('[dot]','.')
    return ''.join(x[len('mailto:'):][::-1])

def parse_addr(root):
    # addresses
    addrs = {}
    for li in root.xpath('//div[@class="ep-a_contacts"]/ul/li'):
        key = unws(''.join(li.xpath('.//h3//text()')))
        if key == 'Bruxelles': key = 'Brussels'
        addrs[key]={}
        if key in ['Brussels', 'Strasbourg']:
            phone = li.xpath('.//li[@class="ep_phone"]/a/@href')
            if phone:
                addrs[key]['Phone']=phone[0][4:].replace("+33(0)388","+333 88").replace("+32(0)228","+322 28")
            fax = li.xpath('.//li[@class="ep_fax"]/a/@href')
            if fax:
                addrs[key]['Fax']=fax[0][4:].replace("+33(0)388","+333 88").replace("+32(0)228","+322 28")
        tmp=[unws(x) for x in li.xpath('.//div[@class="ep_information"]//text()') if len(unws(x))]
        if key=='Strasbourg':
            addrs[key][u'Address']=dict(zip([u'Organization',u'Building', u'Office', u'Street',u'Zip1', u'Zip2'],tmp))
            addrs[key][u'Address']['City']=addrs[key]['Address']['Zip2'].split()[1]
            addrs[key][u'Address']['Zip2']=addrs[key]['Address']['Zip2'].split()[0]
            addrs[key][u'Address']['building_code']=buildings.get(addrs[key]['Address']['Building'])
        elif key==u'Brussels':
            addrs[key][u'Address']=dict(zip([u'Organization',u'Building', u'Office', u'Street',u'Zip'],tmp))
            addrs[key][u'Address']['City']=addrs[key]['Address']['Zip'].split()[1]
            addrs[key][u'Address']['Zip']=addrs[key]['Address']['Zip'].split()[0]
            addrs[key][u'Address']['building_code']=buildings.get(addrs[key]['Address']['Building'])
        elif key=='Luxembourg':
            addrs[key][u'Address']=tmp
        elif key=='Postal address':
            addrs['Postal']=tmp
    return addrs

def parse_hist_date(txt):
    tmp = txt.split(' / ')
    if len(tmp)==2:
        (start, end) = tmp
    elif len(tmp)==1:
        start = txt.split()[0]
        end = "31-12-9999"
    else:
        raise ValueError
    return datetime.strptime(unws(start), u"%d-%m-%Y"), datetime.strptime(unws(end), u"%d-%m-%Y")

def mangleName(name, id):
    sur=[]
    family=[]
    tmp=name.split(' ')
    title=None
    for i,token in enumerate(tmp):
        if ((token.isupper() and not isabbr(token)) or
            token in ['de', 'van', 'von', 'del'] or
            (token == 'in' and tmp[i+1]=="'t" ) or
            (token[:2]=='Mc' and token[2:].isupper())):
            family=tmp[i:]
            break
        else:
            sur.append(token)
    sur=u' '.join(sur)
    family=u' '.join(family)
    for t in TITLES:
        if sur.endswith(t):
            sur=sur[:-len(t)]
            title=t
            break
        if sur.startswith(t):
            sur=sur[len(t)+1:]
            title=t
            break
    res= { u'full': name,
           u'sur': sur,
           u'family': family}

    aliases = set([family,
                   name,
                   u"%s %s" % (sur, family),
                   u"%s %s" % (family, sur)])
    if title:
        res[u'title']=title
        aliases |= set([(u"%s %s"     % (title, family)),
                        (u"%s %s %s"  % (title, family, sur)),
                        (u"%s %s %s"  % (title, sur, family)),
                        (u"%s %s %s"  % (sur, title, family)),
                        (u"%s %s %s"  % (sur, family, title)),
                        (u"%s %s %s"  % (family, sur, title)),
                        (u"%s %s %s"  % (family, title, sur))])
    if id in MEPS_ALIASES:
        aliases|=set(MEPS_ALIASES[id])
    res[u'aliases']=sorted([x for x in set(unws(n) for n in aliases) if x])
    return res

def isabbr(token):
    if len(token) % 2 != 0: return False
    if not token[::2].isupper(): return False
    if [1 for x in token[1::2] if x!='.']: return False
    return True

def parse_history(id, root, mep):
    for term in root.xpath('//nav[@class="ep_tableofcontent-menu table-of-contents-menu"]//span[text()="History of parliamentary service"]/../../..//li//span[@class="ep_name"]//text()'):
        if not term.endswith("parliamentary term"):
            log(2, 'history menu item does not end as expected with "parliamentary term": %s http://www.europarl.europa.eu/meps/en/%s/name/declarations' % (term, id))
            raise ValueError
            #continue
        term = int(term[0])
        root = fetch("http://www.europarl.europa.eu/meps/en/%s/name/history/%s" % (id, term))
        body = root.xpath('//span[@id="mep-card-content"]/following-sibling::div')[0]
        for title in body.xpath('.//div[@class="ep_gridrow ep-o_productlist"]//h3'):
            key = unws(''.join(title.xpath('.//text()')))
            if key in [None,'']:
                log(2, "empty history section http://www.europarl.europa.eu/meps/en/%s/name/history/%s" % (id,term))
                raise ValueError
                #continue
            #mep[key] = []
            for item in title.xpath('../../following-sibling::article//li'):
                interval = unws(''.join(item.xpath('./strong/text()')))
                post = item.xpath('./strong/following-sibling::text()')[0][3:]
                if key in ["National parties", "Constituencies"]:
                    key='Constituencies'
                    # parse date interval
                    try:
                        start, end = parse_hist_date(interval)
                    except:
                        log(1, "illegal date interval: %s http://www.europarl.europa.eu/meps/en/%s/name/history/%s" % (interval, id, term))
                        raise ValueError
                        #continue
                    # parse party and country
                    cstart = post.rfind(' (')
                    if post[cstart+2:-1] in SEIRTNUOC:
                        country = post[cstart+2:-1]
                        party = post[:cstart]
                    else:
                        log(2, '%s unknown country: %s' % (id, post[cstart+2:-1]))
                        raise ValueError
                        party='unknown'
                        country='unknown'
                    if not key in mep: mep[key]=[]
                    mep[key].append({u'party': party, u'country': country, u'start': start, u'end': end, 'term': term})
                    if end == datetime.strptime("31.12.9999", u"%d.%m.%Y"):
                        mep['active']=True
                elif key in ['Member', 'Substitute', 'Chair', 'Vice-Chair', 'Co-President', 'President', 'Vice-President', 'Observer', 'Quaestor', 'Substitute observer']:
                    # memberships in various committees, delegations and EP mgt
                    try:
                        start, end = parse_hist_date(interval)
                    except:
                        log(2,"illegal date interval: %s http://www.europarl.europa.eu/meps/en/%s/name/history/%s" % (interval, id, term))
                        raise ValueError
                        #continue
                    item={u'role': key,
                        u'Organization': unws(post),
                        u'start': start,
                        u'end': end,
                        u'term': term,
                        }
                    for start, field in ORGMAPS:
                        if item['Organization'].startswith(start):
                            if field=='Committees':
                                if item['Organization'] in COMMITTEE_MAP:
                                    item[u'abbr']=COMMITTEE_MAP[item['Organization']]
                                else:
                                    log(5, "no abbr found for committee: %s" % item['Organization'])
                            if field=='Delegations':
                                if item['Organization'] in DELEGATIONS:
                                    item[u'abbr']=DELEGATIONS[item['Organization']]
                                else:
                                    log(5, "no abbr found for delegation: %s" % item['Organization'])
                            if not field in mep: mep[field]=[]
                            mep[field].append(item)
                            break
                elif key == u'Political groups':
                    try:
                        start, end = parse_hist_date(interval)
                    except:
                        log(1, "illegal date interval: %s http://www.europarl.europa.eu/meps/en/%s/name/history/%s" % (interval, id,term))
                        raise ValueError
                        #continue
                    tmp = post.split(u' - ')
                    if len(tmp)>1:
                        org = ' - '.join(tmp[:-1])
                        role = tmp[-1]
                    elif post.endswith(' -'):
                        org=post[:-2]
                        role=''
                    elif post in ['Non-attached Members', 'Non-attached']:
                        org=post
                        role='Member'
                    else:
                        log(2, '[!] political group line "%s", http://www.europarl.europa.eu/meps/en/%s/name/history/%s' % (post, id,term))
                        raise ValueError
                        #continue
                    if not u'Groups' in mep: mep[u'Groups']=[]
                    mep[u'Groups'].append(
                        {u'role':        role,
                        u'Organization': org,
                        # u'country':      country, # this value is missing from the latest EP website
                        u'groupid':      GROUP_MAP.get(org,org),
                        u'start':        start,
                        u'end':          end,
                        })
                else:
                    log(2, '[!] unknown field "%s" http://www.europarl.europa.eu/meps/en/%s/name/history/%s' % (key, id,term))
                    raise ValueError

    # reorder historical lists in ascending order, so new entries are appended and don't mess up the diffs
    for k in ('Constituencies', 'Groups', 'Committees', 'Delegations', 'Staff'):
        if not k in mep: continue
        mep[k]=[e for e in sorted(mep[k], key=lambda x: (x['start'],
                                                         x['end'],
                                                         x.get('Organization',
                                                               x.get('party'))))]

def onfinished(daisy=True):
    if daisy:
        from scraper_service import add_job
        add_job("dossiers",{"all":False, 'onfinished': {'daisy': True}})

if __name__ == '__main__':
    #scrape(28390)
    #scrape(96779)
    #scrape(96674)
    #scrape(28469)
    #scrape(96843)
    #scrape(1393) # 1-3rd term
    #scrape(96992)
    #scrape(1275)
    print(jdump(scrape(int(sys.argv[1]))))
    #print(jdump({k: v for k,v in scrape(1428).items() if k not in ['changes']}))
