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
                    mep[key].append(findecl.scrape(url))
            elif key == 'Declarations of participation by Members in events organised by third parties':
                key = 'Declarations of Participation'
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
    terms=parse_history(id, root, mep)
    process(mep, id, db.mep, 'ep_meps', mep['Name']['full'], (['Addresses'], ['assistants']))

    # activities
    activities=parse_acts(id, terms)
    process(activities, id, db.activities, 'ep_mep_activities', mep['Name']['full'], nodiff=True)

    if __name__ == '__main__':
        return (mep,activities)
    del activities
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
            addrs[key]['Phone']=li.xpath('.//li[@class="ep_phone"]/a/@href')[0][4:].replace("+33(0)388","+333 88").replace("+32(0)228","+322 28")
            addrs[key]['Fax']=li.xpath('.//li[@class="ep_fax"]/a/@href')[0][4:].replace("+33(0)388","+333 88").replace("+32(0)228","+322 28")
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

refre=re.compile(r'([0-9]{4}/[0-9]{4}[A-Z]?\((?:ACI|APP|AVC|BUD|CNS|COD|COS|DCE|DEA|DEC|IMM|INI|INL|INS|NLE|REG|RPS|RSO|RSP|SYN)\))')
pdfrefcache={}
def pdf2ref(url):
    if url in pdfrefcache:
        return pdfrefcache[url]
    text = getpdf(url)
    for line in text:
        if line.startswith("\x0c"): return None
        m = refre.search(line)
        if m:
            pdfrefcache[url]=m.group(1)
            return m.group(1)
    pdfrefcache[url]=None

def parse_acts(id, terms):
    activity_types=(('plenary-speeches', 'CRE'),
                    ('reports', "REPORT"),
                    ('reports-shadow', "REPORT-SHADOW"),
                    ('opinions', "COMPARL"),
                    ('opinions-shadow', "COMPARL-SHADOW"),
                    ('motions-instit', "MOTION"),
                    ('oral-questions', "OQ"),
                    # other activities
                    ('written-explanations', 'WEXP'),
                    ('major-interpellations', 'MINT'),
                    ('written-questions', "WQ"),
                    ('motions-indiv', "IMOTION"),
                    ('written-declarations', "WDECL"))
    activities={}
    for type, TYPE in activity_types:
        for term in terms:
            start = 0
            cnt = 20
            url = "http://www.europarl.europa.eu/meps/en/%s/loadmore-activities/%s/%s/?from=%s&count=%s" % (id, type, term, start, cnt)
            try:
                root = fetch(url)
            except:
                log(1,"failed to fetch {}".format(url))
                raise ValueError
                #continue
            #print(url, file=sys.stderr)
            while(len(root.xpath('//article'))>0):
                for node in root.xpath('//article'):
                    if type == 'written-explanations':
                        item = {
                            'title': unws(''.join(node.xpath('.//div[@class="ep-p_text erpl-activity-title"]//text()'))),
                            'date': datetime.strptime(node.xpath('.//time/@datetime')[0], u"%Y-%m-%dT%H:%M:%S"),
                            'date-type': str(node.xpath('.//time/@itemprop')[0]),
                            'text': unws(''.join(node.xpath('.//div[@class="ep-a_text"]//text()')))}
                    elif type == 'written-declarations':
                        item = {
                            'title': unws(''.join(node.xpath('.//div[@class="ep-p_text erpl-activity-title"]//text()'))),
                            'date': datetime.strptime(node.xpath('.//time/@datetime')[0], u"%Y-%m-%dT%H:%M:%S"),
                            'date-type': str(node.xpath('.//time/@itemprop')[0]),
                            'formats': [{'type': unws(fnode.xpath('./text()')[0]),
                                        'url': str(fnode.xpath('./@href')[0]),
                                        'size': unws(fnode.xpath('./span/text()')[0])}
                                        for fnode in node.xpath('.//div[@class="ep-a_links"]//a')],
                            'authors': [{'name': name.strip(), "mepid": db.mepid_by_name(name.strip())} for name in unws(''.join(node.xpath('.//span[@class="ep_name erpl-biblio-authors"]//text()'))).split(',')],
                        }
                        for info in node.xpath('.//span[@class="erpl-biblio-addinfo"]'):
                            label, value = info.xpath('.//span[@class="erpl-biblio-addinfo-label"]')
                            label = unws(''.join(label.xpath('.//text()')))[:-2]
                            value = unws(''.join(value.xpath('.//text()')))
                            if 'date' in label.lower():
                                value = datetime.strptime(value, u"%d-%m-%Y")
                            if label == 'Number of signatories':
                                number, date = value.split(' - ')
                                value = int(number)
                                item["No of sigs date"] = datetime.strptime(date, u"%d-%m-%Y")
                            item[label]=value
                    else:
                        # all other activities share the following scraper
                        ref = unws(''.join(node.xpath('.//time/following-sibling::text()')))
                        if ref.startswith('- '):
                            ref = ref[2:]
                        if ref.endswith(' -'):
                            ref = ref[:-2]

                        item = {
                            'url': str(node.xpath('.//a/@href')[0]),
                            'date': datetime.strptime(node.xpath('.//time/@datetime')[0], u"%Y-%m-%dT%H:%M:%S"),
                            'date-type': str(node.xpath('.//time/@itemprop')[0]),
                            'reference': ref,
                        }

                        if type in ['opinions-shadow', 'opinions']:
                            item['title']=unws(''.join(node.xpath('.//div[@class="ep-p_text erpl-activity-title"]//text()')))
                        else:
                            item['title']=unws(''.join(node.xpath('.//a//text()')))

                        abbr = unws(''.join(node.xpath('.//abbr/text()')))
                        if abbr:
                            item['committee']=abbr

                        formats = []
                        for fnode in node.xpath('.//div[@class="ep-a_links"]//a'):
                            elem = {'type': unws(fnode.xpath('./text()')[0]),
                                    'url': fnode.xpath('./@href')[0]}
                            tmp=fnode.xpath('./span/text()')
                            if len(tmp) > 0:
                                elem['size']=unws(tmp[0])
                            formats.append(elem)
                        if formats:
                            item['formats']=formats

                        if type=='opinions-shadow':
                            for f in item['formats']:
                                if f['type'] == 'PDF':
                                    ref = pdf2ref(f['url'])
                                    if ref is not None:
                                        item['dossiers']=[ref]
                                    break
                        else:
                           # try to deduce dossier from document reference
                           dossiers = db.get('dossiers_by_doc', item['reference']) or []
                           if len(dossiers)>0:
                               item['dossiers']=[d['procedure']['reference'] for d in dossiers]
                           elif not '+DOC+PDF+' in item['url']:
                               # try to figure out the associated dossier by making an (expensive) http request to the ep
                               #log(4, "fetching %s" % item['url'])
                               try:
                                   refroot = fetch(item['url'])
                               except:
                                   refroot = None
                               if refroot is not None:
                                   if '/doceo/' in item['url']: # stupid new EP site removed the spand with the procedure, bastards.
                                       fulla = refroot.xpath('//table[@class="buttondocwin"]//a/img[@src="/doceo/data/img/navi_moredetails.gif"]/..')
                                       if fulla:
                                           fullurl = fulla[0].get('href')
                                           if fullurl.endswith('.html'):
                                               if fullurl[-7:-5]!='EN':
                                                   fullurl=fullurl[:-7]+'EN.html'
                                               log(4,'loading activity full text page')
                                               refroot = fetch(fullurl)
                                       else:
                                           log(4,'no fulla for %s' % item['url'])
                                   anchor = refroot.xpath('//span[@class="contents" and text()="Procedure : "]')
                                   if len(anchor)==1:
                                       dossier = anchor[0].xpath("./following-sibling::a/text()")
                                       if len(dossier)==1:
                                           item['dossiers']=[unws(dossier[0])]
                                       elif len(dossier)>1:
                                           log(2,"more than one dossier in ep info page: %d %s" % (len(dossier),item['url']))
                                   elif len(anchor)>1:
                                       log(2,"more than one anchor in ep info page: %d %s" % (len(anchor),item['url']))

                    item['term']=term
                    if TYPE not in activities:
                        activities[TYPE]=[]
                    activities[TYPE].append(item)
                if len(root.xpath('//article')) < cnt:
                    break
                start += cnt
                url = "http://www.europarl.europa.eu/meps/en/%s/loadmore-activities/%s/%s/?from=%s&count=%s" % (id, type, term, start, cnt)
                try:
                    root = fetch(url)
                except:
                    log(1,"failed to fetch {}".format(url))
                    #raise ValueError
                    break
                #print(url, file=sys.stderr)
        if TYPE in activities:
            activities[TYPE]=sorted(activities[TYPE],key=lambda x: x['date'])
    activities['mep_id']=id
    return activities

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
                        (u"%s%s%s"    % (sur, title, family)),
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
    terms = []
    for term in root.xpath('//nav[@class="ep_tableofcontent-menu table-of-contents-menu"]//span[text()="History of parliamentary service"]/../../..//li//span[@class="ep_name"]//text()'):
        if not term.endswith("parliamentary term"):
            log(2, 'history menu item does not end as expected with "parliamentary term": %s http://www.europarl.europa.eu/meps/en/%s/name/declarations' % (term, id))
            raise ValueError
            #continue
        term = int(term[0])
        terms.append(term)

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
                        u'groupid':      GROUP_MAP[org],
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
    return terms

def onfinished(daisy=True):
    db.commit('ep_mep_activities')
    db.reindex('ep_mep_activities')
    if daisy:
        from scraper_service import add_job
        add_job("dossiers",{"all":True, 'onfinished': {'daisy': True}})

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
