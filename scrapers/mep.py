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

import sys
import re
import notification_model as notif
from utils.utils import fetch, fetch_raw, unws, jdump, getpdf, textdiff
from utils.process import process
from utils.mappings import buildings, SEIRTNUOC, COMMITTEE_MAP, ORGMAPS, GROUP_MAP, DELEGATIONS, MEPS_ALIASES, TITLES, COUNTRIES
from utils.log import log
from utils.notif_mail import send_html_mail
from config import ROOT_URL
from datetime import datetime
from lxml.html.soupparser import fromstring
from db import db
from scrapers import _findecl as findecl
from webapp import mail, app
from flask_mail import Message

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
    sidebar_check(root, url)

    mep = {
        'UserID'    : id,
        'Name'      : mangleName(unws(' '.join(root.xpath('//span[@class="sln-member-name"]/text()'))), id),
        'Photo'     : "https://www.europarl.europa.eu/mepphoto/%s.jpg" % id,
        'meta'      : {'url': url},
        'Twitter'   : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="Twitter"]/@href')],
        'X'         : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="X"]/@href')],
        'Homepage'  : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="Website"]/@href')],
        'Facebook'  : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="Facebook"]/@href')],
        'Instagram' : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="Instagram"]/@href')],
        'Youtube'   : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="Youtube"]/@href')],
        'LinkedIn'  : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="LinkedIn"]/@href')],
        'Telegram'  : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="Telegram"]/@href')],
        'Blog'      : [unws(x.replace("http:// ","")) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="Blog"]/@href')],
        'Mail'      : [deobfus_mail(x) for x in root.xpath('//div[@id="presentationmep"]//a[@data-original-title="E-mail"]/@href')],
        'Addresses' : parse_addr(root),
        'active'    : False,
    }

    links = root.xpath('//div[@id="presentationmep"]//a/@data-original-title')
    unknown_links = list(sorted(set(links) - set(['Website', 'E-mail', 'Facebook', 'Facebook', 'Youtube', 'Blog', 'X', 'Instagram', 'Telegram', 'LinkedIn'])))
    if len(unknown_links) > 0:
        log(2, f"all links types: {unknown_links}")

    mep = addchangednames(mep)

    birthdate = root.xpath('//time[@class="sln-birth-date"]/text()')
    if len(birthdate)>0:
        mep['Birth']={'date': datetime.strptime(unws(birthdate[0]), u"%d-%m-%Y")}
        place=root.xpath('//time[@class="sln-birth-date"]/following-sibling::span/text()')
        if len(place)>0:
            tmp = unws(' '.join(place))
            if tmp.startswith(", "): tmp=tmp[2:]
            mep['Birth']['place']=tmp

    death = root.xpath('//time[@id="deathDate"]/text()')
    if death:
        mep['Death'] = datetime.strptime(unws(death[0]), u"%d-%m-%Y")

    body = root.xpath('//span[@id="detailedcardmep"]/following-sibling::section')[0]

    if body.xpath('.//h1[text()="Curriculum vitae "]'):
        if not body.xpath('.//h3[@id="no_cv_available"]'):
            updated=unws(body.xpath('.//p[@class="small"]/strong[contains(text(),"Updated: ")]/text()')[0])[len('Updated: '):].replace('CEST ', '').replace('CET ', '')
            try: updated = datetime.strptime(updated, u"%d/%m/%Y")
            except: updated = datetime.strptime(updated, u"%a %b %d %H:%M:%S %Y")
            mep['CV']= {'updated': updated}
            mep['CV'].update({unws(''.join(title.xpath(".//text()"))): [unws(''.join(item.xpath(".//text()"))).replace("-...", "- ...")
                                                                        for item in title.xpath("following-sibling::ul/li")]
                            for title in body.xpath('.//h4')
                            #if not unws(''.join(title.xpath(".//text()"))).startswith("Original version : ")
                            })

    # assistants
    url = "http://www.europarl.europa.eu/meps/en/%s/name/assistants" % id
    root = fetch(url)
    body = root.xpath('//span[@id="detailedcardmep"]/following-sibling::section')[0]
    if unws(' '.join(body.xpath(".//h1/text()"))) == "Assistants":
        for h4 in body.xpath('.//h4'):
            title = unws(''.join(h4.xpath(".//text()")))
            assistants = [unws(''.join(item.xpath(".//text()"))) for item in h4.xpath("../div//span")]
            if title in ['Accredited assistants', 'Local assistants']:
                if not 'assistants' in mep: mep['assistants']={}
                title = title.lower().split()[0]
                if assistants: mep['assistants'][title]=assistants
            elif title in ['Accredited assistants (grouping)', 'Local assistants (grouping)',
                           'Service providers', 'Trainees', 'Paying agents (grouping)', 'Paying agents',
                           'Assistants to the Vice-Presidency/to the Quaestorate', "Assistants to the Quaestorate",
                           "Assistants to the Vice-Presidency"]:
                if not 'assistants' in mep: mep['assistants']={}
                title = title.lower()
                if assistants: mep['assistants'][title]=assistants
            else:
                log(2,'unknown title for assistants "{}" {}'.format(title, url))
                raise ValueError

    # declarations
    root = fetch("http://www.europarl.europa.eu/meps/en/%s/name/declarations" % id)
    body = root.xpath('//span[@id="detailedcardmep"]/following-sibling::section')[0]
    if unws(' '.join(body.xpath(".//h1/text()"))) == "Declarations":
        for title in body.xpath('.//h4'):
            key = unws(''.join(title.xpath('.//text()')))
            if key == 'Declaration of financial interests':
                key = 'Financial Declarations'
                mep[key] = []
                for pdf in title.xpath('./following-sibling::ul/li/a'):
                    url = pdf.xpath('./@href')[0]
                    try:
                        mep[key].append(findecl.scrape(url))
                    except:
                        log(1,"failed to extract findecl from %s" % url)
            elif key == 'Declarations of participation by Members in events organised by third parties':
                key = 'Declarations of Participation'
                mep[key] = []
                for pdf in title.xpath('./following-sibling::ul/li/a')[::-1]: # reversed order, otherwise newer ones get prepended and mess up the diff
                    url = pdf.xpath('./@href')[0]
                    name = unws(''.join(pdf.xpath('.//text()')))
                    mep[key].append({'title': name, 'url': url})
            elif key in ['Declaration of good conduct', 'Voluntary confirmation on the use of the General Expenditure Allowance', 'Declaration on appropriate behaviour','Declaration of private interests', "Declaration on awareness of conflicts of interest"]:

                mep[key] = []
                for pdf in title.xpath('./following-sibling::ul/li/a')[::-1]: # reversed order, otherwise newer ones get prepended and mess up the diff
                    url = pdf.xpath('./@href')[0]
                    name = unws(''.join(pdf.xpath('.//text()')))
                    mep[key].append({'title': name, 'url': url})
            else:
                log(2, 'unknown type of declaration: "%s" http://www.europarl.europa.eu/meps/en/%s/name/declarations' % (key, id))
                key = None
                raise ValueError

    # history
    parse_history(id, root, mep)
    process(mep, id, db.mep, 'ep_meps', mep['Name']['full'], nopreserve=(['Addresses'], ['assistants']), onchanged=onchanged)

    if __name__ == '__main__':
        return mep
    del mep

def deobfus_mail(txt):
    x = re.sub(r'^mailto:', '', txt).replace('[at]', '@').replace('[dot]', '.')
    return ''.join(x[::-1])

def parse_addr(root):
    # addresses
    addrs = {}
    for li in root.xpath('//section[@id="contacts"]//div[@class="card-body"]'):
        key = unws(''.join(li.xpath('./div[1]//text()')))
        if key == 'Bruxelles': key = 'Brussels'
        addrs[key]={}
        if key in ['Brussels', 'Strasbourg']:
            phone = li.xpath('.//li/svg[@class="es_icon es_icon-phone"]/../a/@href')
            if phone:
                addrs[key]['Phone']=phone[0][4:].replace("+33(0)388","+333 88").replace("+32(0)228","+322 28")
            fax = li.xpath('.//li/svg[@class="es_icon es_icon-fax"]/../a/@href')
            if fax:
                addrs[key]['Fax']=fax[0][4:].replace("+33(0)388","+333 88").replace("+32(0)228","+322 28")
        #tmp=[unws(x) for x in li.xpath('.//li[1]//text()') if len(unws(x))]
        tmp=[unws(x) for x in li.xpath('.//div[@class="erpl_contact-card-list"]/span//text()') if len(unws(x))]
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
        if ((token.replace("ß", "ẞ").isupper() and not isabbr(token)) or
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
        if sur.endswith(' '+t):
            sur=sur[:-len(t)+1]
            title=t
            break
        if sur.startswith(t+' '):
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
    for term in root.xpath('//div[@id="sectionsNavPositionInitial"]//div[@class="erpl_side-navigation"]/div/ul/li//span[text()="History of parliamentary service"]/../following-sibling::div//ul/li//a/span[@class="t-x"]/text()'):
        if not term.endswith("parliamentary term"):
            log(2, 'history menu item does not end as expected with "parliamentary term": %s http://www.europarl.europa.eu/meps/en/%s/name/declarations' % (term, id))
            raise ValueError
            #continue
        term = int(term[:-(3+len("parliamentary term"))])
        if (id,term) in {(124870,9),(129141,9)}: continue # jeppe kofod, and frans timmermanns never really got started.
        root = fetch("http://www.europarl.europa.eu/meps/en/%s/name/history/%s" % (id, term))
        body = root.xpath('//div[@id="status"]')[0]
        for title in body.xpath('.//h4'):
            key = unws(''.join(title.xpath('.//text()')))
            if key in [None,'']:
                log(2, "empty history section http://www.europarl.europa.eu/meps/en/%s/name/history/%s" % (id,term))
                raise ValueError
                #continue
            #mep[key] = []
            for item in title.xpath('./following-sibling::ul/li'):
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
                    if end == datetime.strptime("31.12.9999", u"%d.%m.%Y"):
                        mep['active']=True
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
                    if not org in GROUP_MAP:
                        log(5, "no groupid found for group: %s" % org)
                    mep[u'Groups'].append(
                        {u'role':        role,
                        u'Organization': org,
                        # u'country':      country, # this value is missing from the latest EP website
                        u'groupid':      GROUP_MAP.get(org,org),
                        u'start':        start,
                        u'end':          end,
                        })
                    if end == datetime.strptime("31.12.9999", u"%d.%m.%Y"):
                        mep['active']=True
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

def addchangednames(mep):
    mepid = mep['UserID']
    m=db.get('ep_meps', mepid)
    if not m: return mep
    prevnames = [c['data'][0]
                 for changes in m.get('changes',{}).values()
                 for c in changes
                 if c['path']==['Name','full']]
    aliases = set(mep['Name']['aliases'])
    for name in prevnames:
        aliases |= set(mangleName(name,mepid)['aliases'])
    mep['Name']['aliases'] = sorted([x for x in set(unws(n) for n in aliases) if x])
    return mep

def onfinished(daisy=True):
    if daisy:
        from scraper_service import add_job
        add_job("dossiers",{"all":False, 'onfinished': {'daisy': True}})

def onchanged(mep, diff):
    log(4, "calling onchanged for mep")
    today = datetime.now()

    country = mep['Constituencies'][-1]['country']
    mep_items = notif.session.query(notif.Item).filter(notif.Item.type=='meps_by_country').filter(notif.Item.name==country).all()

    #log(4, "type of today : %s" % (type(today)))
    for c in mep.get('Committees', []):
        #log(4, "type of c.end: %s" % (type(c['end'])))
        if c['end'] > today:
            if not 'abbr' in c: continue
            committee = c['abbr']
            mep_items.extend(notif.session.query(notif.Item).filter(notif.Item.type=='meps_by_committee').filter(notif.Item.name==committee).all())

    for g in mep.get('Groups', []):
        #log(4, "type of g.end: %s" % (type(g['end'])))
        if g['end'] > today:
            if not 'groupid' in g: continue
            group = g['groupid']
            mep_items.extend(notif.session.query(notif.Item).filter(notif.Item.type=='meps_by_group').filter(notif.Item.name==group).all())

    recipients = set()
    for i in mep_items:
        for s in i.group.subscribers:
            recipients.add(s.email)
    if not recipients:
        log(4, "no subscribers found for mep " + str(mep['UserID']))
        return
    log(3, "sending mep changes to " + ', '.join(recipients))
    send_html_mail(
        recipients=list(recipients),
        subject="%s %s" % (mep['UserID'],mep['Name']['full']),
        obj=mep,
        change=diff,
        date=today,
        url='%smep/%s' % (ROOT_URL, mep['UserID']),
        text=makemsg(mep, diff)
    )
    return

def makemsg(mep,diff):
    return (u"Parltrack has detected a change in %s on europarl.eu.\n\nPlease follow this URL: %smep/%s to see the MEP.\n\nChanges follow\n%s\n\n\nsincerly,\nYour Parltrack team" %
            (mep['Name']['full'],
             ROOT_URL,
             mep['UserID'],
             textdiff(diff)))

known_sidebar = { "Home": [],
                "Main parliamentary activities": [
                    'Contributions to plenary debates',
                    "Reports - as rapporteur",
                    "Reports - as shadow rapporteur",
                    "Opinions - as rapporteur",
                    "Opinions - as shadow rapporteur",
                    "Oral questions",
                    "Major interpellations",
                    "Motions for resolutions"],
                "Other parliamentary activities": [
                    "Questions for written answer (including answers)",
                    "Individual motions for resolutions",
                    "Written explanations of vote",
                    "Proposals for a Union act",
                    ],
                "Curriculum vitae": [],
                "Declarations": [],
                "Assistants": [],
                "Penalties": [],  # todo at least scrape the urls pointing at them
                "Meetings": [
                    "Past meetings",
                    "Future meetings",
                    ],
                "History of parliamentary service": [
                    "10th parliamentary term",
                    "9th parliamentary term",
                    "8th parliamentary term",
                    "7th parliamentary term",
                    "6th parliamentary term",
                    "5th parliamentary term",
                    "4th parliamentary term",
                    "3rd parliamentary term",
                    "2nd parliamentary term",
                    "1st parliamentary term",
                    ]
                }

def sidebar_check(root,url):
    sidebar = root.xpath('//div[@id="sectionsNavPositionInitial"]//div[@class="erpl_side-navigation"]/div/ul')
    if len(sidebar)!=1: 
        log(1,"sidebar has not 1 element: %s" % url)
        raise ValueError
    for li in sidebar[0].xpath('./li'):
        title = li.xpath('./a/span[@class="t-x"]/text()') 
        if len(title)!=1:
            log(1,"title has not 1 element: %s" % url)
            raise ValueError
        title = unws(title[0])
        if title not in known_sidebar:
            log(2, '"%s" not in known_sidebar items, in %s' % (title,url))
        subtitles = li.xpath('.//div/ul/li/a/span[@class="t-x"]/text()')
        for s in subtitles:
            s=unws(s)
            if s not in known_sidebar[title]:
                log(2, '"%s" -> "%s" not in known_sidebar items, in %s' % (title,s,url))


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
