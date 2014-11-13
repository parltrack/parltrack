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


from datetime import datetime
from mappings import COMMITTEE_MAP, buildings, group_map, COUNTRIES, SEIRTNUOC
from urlparse import urljoin
import unicodedata, traceback, sys, json
from parltrack.utils import diff, fetch, fetch_raw, unws, Multiplexer, logger, jdump
from parltrack.db import db
import findecl
#from lxml import etree

current_term=8
BASE_URL = 'http://www.europarl.europa.eu'

def getAddress(root):
    res={}
    for div in root.xpath('../following-sibling::div[@class="boxcontent" or @class="boxcontent nobordertop"]/ul[@class="contact"]'):
        key=unws(''.join(div.xpath('./preceding-sibling::h4/text()')))
        if key not in ['Bruxelles', 'Strasbourg', 'Postal address', 'Luxembourg']:
            continue
        if key=='Bruxelles': key=u'Brussels'
        elif key=='Postal address': key=u'Postal'
        res[key]={}
        if key in ['Brussels', 'Strasbourg', 'Luxembourg']:
            tmp=div.xpath('./following-sibling::ul[@class="link_collection_noborder"]//span[@class="phone"]/text()')
            if tmp:
                res[key][u'Phone'] = unws(tmp[0]).replace('(0)','')
            tmp=div.xpath('./following-sibling::ul[@class="link_collection_noborder"]//span[@class="fax"]/text()')
            if tmp:
                res[key][u'Fax'] = unws(tmp[0]).replace('(0)','')
        tmp=[unws(x) for x in div.xpath('./li[@class="address"]//text()') if len(unws(x))]
        if key=='Strasbourg':
            res[key][u'Address']=dict(zip([u'Organization',u'Building', u'Office', u'Street',u'Zip1', u'Zip2'],tmp))
            res[key][u'Address']['City']=res[key]['Address']['Zip2'].split()[1]
            res[key][u'Address']['Zip2']=res[key]['Address']['Zip2'].split()[0]
            res[key][u'Address']['building_code']=buildings.get(res[key]['Address']['Building'])
        elif key=='Brussels':
            res[key][u'Address']=dict(zip([u'Organization',u'Building', u'Office', u'Street',u'Zip'],tmp))
            res[key][u'Address']['City']=res[key]['Address']['Zip'].split()[1]
            res[key][u'Address']['Zip']=res[key]['Address']['Zip'].split()[0]
            res[key][u'Address']['building_code']=buildings.get(res[key]['Address']['Building'])
        elif key=='Luxembourg':
            res[key][u'Address']=tmp
        elif key=='Postal':
            res[key]=tmp
        else:
            logger.error("wtf %s" % key)
    return res

def getMEPGender(id):
    try:
        mepraw=fetch("http://www.europarl.europa.eu/meps/fr/%s/_home.html" % (id), ignore=[500])
    except Exception, e:
        logger.error("mepgender %s" % e)
        return 'n/a'
    borntxt=mepraw.xpath('//div[@class="zone_info_mep_transparent_mep_details"]//span[@class="more_info"]/text()')
    if len(borntxt)>0:
        if unws(borntxt[-1]).startswith(u'décédé'):
            hint=borntxt[-2].replace(u"\u00A0",' ').split()[0]
        else:
            hint=borntxt[-1].replace(u"\u00A0",' ').split()[0]
        if hint==u"Née":
            return "F"
        elif hint==u"Né":
            return "M"
    logger.warn('[!] no birth/gender data http://www.europarl.europa.eu/meps/fr/%s/get.html' % id)
    return 'n/a'

def getMEPDeclarations(id):
    try:
        dom = fetch("http://www.europarl.europa.eu/meps/en/%s/_declarations.html" % (id), ignore=[500])
    except Exception, e:
        logger.error("mepdeclaration %s" % e)
        return []
    pdf_links = dom.xpath('//ul[@class="link_collection_noborder"]//a[@class="link_pdf"]/@href')
    if not pdf_links:
        logger.warn('[!] no declaration data http://www.europarl.europa.eu/meps/en/%s/_declarations.html' % id)
    return pdf_links

activitymap={"CRE" : "Speeches",
             "REPORT" : "Reports",
             "REPORT-SHADOW" : "Shadow reports",
             "MOTION" : "Motions for resolution",
             "COMPARL" : "Opinion",
             "COMPARL-SHADOW" : "Opinion shadow",
             "WDECL" : "Written declarations",
             "QP" : "Parlamentiary questions"}

def getactivities(mepid, terms=[8]):
    urltpl = 'http://www.europarl.europa.eu/meps/en/%s/see_more.html?type=%s&leg=%s&index=%s'
    #ctjson={'content-type': 'application/json'}
    actions={}
    for type in activitymap.keys():
        actions[type]={}
        for term in terms:
            term=str(term)
            actions[type][term]=[]
            idx=0
            while True:
                res=fetch_raw(urltpl % (mepid,type,term,idx)) #, headers=ctjson)
                ret=json.load(res)
                actions[type][term].extend(ret['documentList'])
                idx=ret['nextIndex']
                if idx in [-1,0]: break
            if not actions[type][term]:
                del actions[type][term]
        if not actions[type]:
            del actions[type]

    return actions

def parseMember(userid):
    url='http://www.europarl.europa.eu/meps/en/%s/_history.html' % userid
    logger.info("scraping %s" % url)
    root = fetch(url, ignore=[500])

    data = {
        u'active': False,
        u'Photo': unicode(urljoin(BASE_URL,"/mepphoto/%s.jpg" % userid)),
        u'meta': {u'url': url}
        }

    mepdiv=root.xpath('//div[@class="zone_info_mep_transparent_mep_details"]')
    if len(mepdiv) == 1:
        mepdiv = mepdiv[0]
    else:
        logger.error("len(mepdiv) not 1: %s" % str(list(mepdiv)))
    data[u'Name'] = mangleName(unws(' '.join(mepdiv.xpath('.//li[@class="mep_name"]//text()'))))

    borntxt=mepdiv.xpath('.//span[@class="more_info"]/text()')
    if len(borntxt)>0:
        if unws(borntxt[-1]).startswith('died on '):
            try:
                data[u'Death'] = datetime.strptime(unws(borntxt[-1]), u"died on %d %B %Y")
            except ValueError:
                logger.warn('[!] failed to scrape birth data %s' % url)
                logger.warn(traceback.format_exc())
            tmp = borntxt[-2].split(',', 1)
        else:
            tmp = borntxt[-1].split(',', 1)
        if len(tmp)==2:
            (d, p) = tmp
        else:
            d,p = tmp[0], None
        try:
            data[u'Birth'] = { u'date': datetime.strptime(unws(d), u"Born on %d %B %Y")}
        except ValueError:
            logger.warn('[!] failed to scrape birth data %s' % url)
            logger.warn(traceback.format_exc())
        finally:
            if p:
                if 'Birth' in data:
                    data[u'Birth'][u'place'] = unws(p)
                else:
                    data[u'Birth'] = unws(p)
    else:
        logger.warn('[!] no birth data %s' % url)

    # scrape stuff from right column
    addif(data,u'RSS',[unicode(urljoin(BASE_URL,x.get('href')),'utf8')
                       for x in root.xpath('//ul[@class="link_collection_noborder"]/li/a[@class="link_rss"]')])
    addif(data,u'Homepage',[x.get('href')
                            for x in root.xpath('//ul[@class="link_collection_noborder"]/li/a[@class="link_website"]')])
    addif(data,u'Twitter',[x.get('href')
                           for x in root.xpath('//ul[@class="link_collection_noborder"]/li/a[@class="link_twitt"]')])
    addif(data,u'Facebook',[x.get('href')
                           for x in root.xpath('//ul[@class="link_collection_noborder"]/li/a[@class="link_fb"]')])
    addif(data,u'Mail',[x.get('href')[7:].replace('[dot]','.').replace('[at]','@')[::-1]
                        for x in root.xpath('//ul[@class="link_collection_noborder"]/li/a[@class="link_email"]')])
    # contact information
    for span in root.xpath('//div[@id="content_right"]//h3'):
        title=unws(''.join(span.xpath('.//text()')))
        if title in ['Accredited assistants', 'Local assistants']:
            if not 'assistants' in data: data['assistants']={}
            addif(data['assistants'],
                  title.lower().split()[0],
                  [unws(x) for x in span.xpath('../following-sibling::div[@class="boxcontent"][1]//li/text()')])
        elif title == "Contacts":
            addif(data,u'Addresses',getAddress(span))

    # scrape main content
    for section in root.xpath('//div[@id="content_left"]/div[@class="boxcontent nobackground"]/h4'):
        key=unws(''.join(section.xpath('.//text()')))
        if key=="National parties":
            # constituencies
            key='Constituencies'
            for constlm in section.xpath('./following-sibling::ul[@class="events_collection bullets"][1]/li'):
                line=unws(u' '.join([unicode(x) for x in constlm.xpath('.//text()')]))
                try:
                    interval, party = line.split(' : ',1)
                except ValueError:
                    continue
                tmp = interval.split(' / ')
                if not key in data: data[key]=[]
                if len(tmp)==2:
                    (start, end) = tmp
                else:
                    start = interval.split()[0]
                    end = "31.12.9999"
                cstart = party.rfind(' (')
                if party[cstart+2:-1] in SEIRTNUOC:
                    country = party[cstart+2:-1]
                    party = party[:cstart]
                else:
                    logger.warn('unknown country: %s' % party[cstart+2:-1])
                    country='unknown'
                #print etree.tostring(constlm, pretty_print=True)
                data[key].append({
                    u'party':     party,
                    u'country':   country,
                    u'start':     datetime.strptime(unws(start), u"%d.%m.%Y"),
                    u'end':       datetime.strptime(unws(end), u"%d.%m.%Y"),
                    })
        elif key in ['Member', 'Substitute', 'Chair', 'Vice-Chair', 'Co-President', 'President', 'Vice-President', 'Observer', 'Quaestor']:
            # memberships in various committees, delegations and EP mgt
            for constlm in section.xpath('./following-sibling::ul[@class="events_collection bullets"][1]/li'):
                line=unws(u' '.join([unicode(x) for x in constlm.xpath('.//text()')]))
                try:
                    interval, org = line.split(' : ',1)
                except:
                    continue
                tmp = interval.split(' / ')
                if len(tmp)==2:
                    (start, end) = tmp
                else:
                    start = interval.split()[0]
                    end = "31.12.9999"
                item={u'role': key,
                      u'abbr': COMMITTEE_MAP.get(org),
                      u'Organization': org,
                      u'start':     datetime.strptime(unws(start), u"%d.%m.%Y"),
                      u'end':       datetime.strptime(unws(end), u"%d.%m.%Y"),
                      }
                for start, field in orgmaps:
                    if item['abbr'] in COMMITTEE_MAP or item['Organization'].startswith(start):
                        if not field in data: data[field]=[]
                        if field=='Committees' and item['Organization'] in COMMITTEE_MAP:
                            item[u'committee_id']=COMMITTEE_MAP[item['Organization']]
                        data[field].append(item)
                        break
        elif key == u'Political groups':
            for constlm in section.xpath('./following-sibling::ul[@class="events_collection bullets"][1]/li'):
                line=unws(u' '.join([unicode(x) for x in constlm.xpath('.//text()')]))
                interval, org = line.split(' : ',1)
                tmp = org.split(u' - ')
                if len(tmp)>1:
                    org = ' - '.join(tmp[:-1])
                    role = tmp[-1]
                elif org.endswith(' -'):
                        org=org[:-2]
                        role=''
                else:
                    logger.error('[!] political group line %s' % line)
                    continue
                tmp = interval.split(' / ')
                if len(tmp)==2:
                    (start, end) = tmp
                else:
                    start = interval.split()[0]
                    end = "31.12.9999"
                if not u'Groups' in data: data[u'Groups']=[]
                data[u'Groups'].append(
                    {u'role':         role,
                     u'Organization': org,
                     u'country':      COUNTRIES.get(unws(constlm.get('class')).upper(), 'unknown country: %s' % unws(constlm.get('class'))),
                     u'groupid':      group_map[org],
                     u'start':        datetime.strptime(unws(start), u"%d.%m.%Y"),
                     u'end':          datetime.strptime(unws(end), u"%d.%m.%Y"),
                     })
        else:
            logger.error('[!] unknown field %s' % key)

    # sort all lists in descending order
    for fld in ['Constituencies', 'Groups', 'Committees', 'Delegations', 'Staff']:
        if not fld in data: continue
        data[fld]=sorted(data[fld],
                         key=lambda x: x.get('end',x['start']),
                         reverse=True)

    # get CV - page (is on separate http path :/)
    cvurl='http://www.europarl.europa.eu/meps/en/%s/_cv.html' % userid
    root = fetch(cvurl, ignore=[500])
    data[u'CV']=[unws(x) for x in root.xpath('//p[@class="details_cv"]/text()')]

    return data

def addif(target, key, val):
    if val:
        target[key]=val

def mangleName(name):
    sur=[]
    family=[]
    tmp=name.split(' ')
    title=None
    for i,token in enumerate(tmp):
        if ((token.isupper() and token not in ['E.', 'K.', 'A.']) or
            token in ['de', 'van', 'von', 'del'] or
            (token == 'in' and tmp[i+1]=="'t" ) or
            (token[:2]=='Mc' and token[2:].isupper())):
            family=tmp[i:]
            break
        else:
            sur.append(token)
    sur=' '.join(sur)
    family=' '.join(family)
    for t in Titles:
        if sur.endswith(t):
            sur=sur[:-len(t)]
            title=t
            break
    res= { u'full': name,
           u'sur': sur,
           u'family': family,
           u'familylc': family.lower(),
           u'aliases': [family,
                       family.lower(),
                       u''.join(family.split()).lower(),
                       u"%s %s" % (sur, family),
                       u"%s %s" % (family, sur),
                       (u"%s %s" % (family, sur)).lower(),
                       (u"%s %s" % (sur, family)).lower(),
                       u''.join(("%s%s" % (sur, family)).split()),
                       u''.join(("%s%s" % (family, sur)).split()),
                       u''.join(("%s%s" % (family, sur)).split()).lower(),
                       u''.join(("%s%s" % (sur, family)).split()).lower(),
                      ],}
    if title:
        res[u'title']=title
        res[u'aliases'].extend([(u"%s %s" % (title, family)).strip(),
                                (u"%s %s %s" % (title ,family, sur)).strip(),
                                (u"%s %s %s" % (title, sur, family)).strip(),
                                (u"%s %s %s" % (title, family, sur)).strip(),
                                (u"%s %s %s" % (title, sur, family)).lower().strip(),
                                (u"%s %s %s" % (title, family, sur)).lower().strip(),
                                (u''.join(("%s%s%s" % (title, family, sur)).split())).strip(),
                                (u''.join(("%s%s%s" % (title, sur, family)).split())).strip(),
                                (u''.join(("%s%s%s" % (sur, title, family)).split())).strip(),
                                (u''.join(("%s%s%s" % (sur, family, title)).split())).strip(),
                                u''.join(("%s%s" % (title, family)).split()).lower().strip(),
                                u''.join(("%s%s%s" % (family, sur, title)).split()).lower().strip(),
                                u''.join(("%s%s%s" % (family, title, sur)).split()).lower().strip(),
                                u''.join(("%s%s%s" % (title, family, sur)).split()).lower().strip(),
                                u''.join(("%s%s%s" % (title, sur, family)).split()).lower().strip(),
                                ])
    if  u'ß' in unicode(name):
        res[u'aliases'].extend([x.replace(u'ß','ss') for x in res['aliases']])
    if unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore')!=name:
        res[u'aliases'].extend([unicodedata.normalize('NFKD', unicode(x)).encode('ascii','ignore') for x in res['aliases']])
    if "'" in name:
        res[u'aliases'].extend([x.replace("'","") for x in res['aliases']])
    if name in meps_aliases:
           res[u'aliases'].extend(meps_aliases[name])
    res[u'aliases']=[x for x in set(res[u'aliases']) if x]
    return res

def scrape(userid):
    mep=parseMember(userid)
    mep['UserID']=userid
    try:
        mep['Gender'] = getMEPGender(userid)
    except:
        pass
    mep['Financial Declarations']=[findecl.scrape(url) for url in getMEPDeclarations(userid)]
    mep['activities']=getactivities(userid)

    # set active for all meps having a contituency without an enddate
    for c in mep.get('Constituencies',[]):
        if c['end'] == datetime.strptime("31.12.9999", u"%d.%m.%Y"):
            mep['active']=True
            break
    return mep

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

meps_aliases={
    u"GRÈZE, Catherine": ['GREZE', 'greze', 'Catherine Greze', 'catherine greze', u'Grčze', u'grcze'],
    u"SCOTTÀ, Giancarlo": ["SCOTTA'", "scotta'"],
    u"in 't VELD, Sophia": ["in't VELD", "in't veld", "IN'T VELD", "in'tveld", u'in `t Veld', u'in `t veld', u'in`tveld'],
    u"MORKŪNAITĖ-MIKULĖNIENĖ, Radvilė": [u"MORKŪNAITĖ Radvilė",u"morkūnaitė radvilė",u"radvilė morkūnaitė ",u"Radvilė MORKŪNAITĖ ", u"MORKŪNAITĖ", u"morkūnaitė"],
    u"MUSTIN-MAYER, Christine": ['Barthet-Mayer Christine', 'barthet-mayer christine', 'barthet-mayerchristine'],
    u"YÁÑEZ-BARNUEVO GARCÍA, Luis": [ u'Yañez-Barnuevo García', u'yañez-barnuevogarcía', u'Luis Yañez-Barnuevo García', u'luisyanez-barnuevogarcia'],
    u"ZAPPALA', Stefano": [ u'Zappalà', u'zappalà'],
    u"OBIOLS, Raimon": [u'Obiols i Germà', u'obiols i germà', u'ObiolsiGermà', u'obiolsigermà', u'Raimon Obiols i Germà', u'raimonobiolsigermà', u'OBIOLS i GERMÀ' ],
    u"CHATZIMARKAKIS, Jorgo": [u'Chatzimartakis', u'chatzimartakis'],
    u"XENOGIANNAKOPOULOU, Marilisa": [u'Xenagiannakopoulou', u'xenagiannakopoulou'],
    u"GRÄSSLE, Ingeborg": [u'Graessle', u'graessle'],
    u"VIRRANKOSKI, Kyösti": [u'Virrankoski-Itälä', u'virrankoski-itälä'],
    u"SARYUSZ-WOLSKI, Jacek": [u'Saryus-Wolski', u'saryus-wolski'],
    u"PITTELLA, Gianni": [u'Pitella', u'pitella'],
    u"EHLER, Christian": [u'Ehlert', u'ehlert', u'Jan Christian Ehler', u'janchristianehler'],
    u'COELHO, Carlos': ['Coehlo', u'coehlo', u'Coelho Carlo', u'coelho carlo', u'coelhocarlo'],
    u"Ó NEACHTAIN, Seán": [u"O'Neachtain", u"o'neachtain"],
    u"GALEOTE, Gerardo": [u'Galeote Quecedo', u'galeote quecedo',u'GaleoteQuecedo', u'galeotequecedo'],
    u'MARTIN, Hans-Peter': [u'Martin H.P.',u'martinh.p.', u'mmHans-Peter Martin', u'mmhans-petermartin' ],
    u'MARTIN, David': [u'D. Martin', u'd. martin', u'D.Martin', u'd.martin', u'Martin David W.', u'martindavidw.'],
    u'DÍAZ DE MERA GARCÍA CONSUEGRA, Agustín': [u'Díaz de Mera', u'díazdemera'],
    u'MEYER, Willy': [u'Meyer Pleite', u'meyer pleite', u'MeyerPleite', u'meyerpleite', u'Willy Meyer Pleite', u'willymeyerpleite'],
    u'ROBSAHM, Maria': [u'Carlshamre', u'carlshamre'],
    u'HAMMERSTEIN, David': [u'Hammerstein Mintz', u'hammersteinmintz'],
    u'AYUSO, Pilar': [u'Ayuso González', u'ayusogonzález'],
    u'PÖTTERING, Hans-Gert': [u'Poettering', u'poettering'],
    u'VIDAL-QUADRAS, Alejo': [u'Vidal-Quadras Roca', u'vidal-quadrasroca'],
    u'EVANS, Jill': [u'Evans Jillian', u'evansjillian'],
    u'BADIA i CUTCHET, Maria': [u'Badía i Cutchet', u'badíaicutchet', u'Badia Cutchet', u'badiacutchet'],
    u'AUCONIE, Sophie': [u'Briard Auconie', u'briardauconie', u'Sophie Briard Auconie', u'sophiebriardauconie'],
    u'BARSI-PATAKY, Etelka': [u'Barsi Pataky', u'barsipataky'],
    u'NEYNSKY, Nadezhda': [u'Mihaylova', u'mihaylova', u'Nadezhda Mihaylova', u'nadezhdamihaylova'],
    u'MOHÁCSI, Viktória': [u'Bernáthné Mohácsi', u'bernáthnémohácsi', u'bernathnemohacsi'],
    u'WOJCIECHOWSKI, Bernard': [u'Wojciechowski Bernard Piotr', u'wojciechowskibernardpiotr'],
    u'GARCÍA-MARGALLO Y MARFIL, José Manuel': [u'García-MarGállo y Marfil', u'garcía-margálloymarfil', u'García-Margallo', u'garcía-margallo'],
    u'ROGALSKI, Bogusław': [u'RoGálski', u'rogalski'],
    u'ROMEVA i RUEDA, Raül': [u'Romeva Rueda', u'romevarueda', u'Raьl Romeva i Rueda', u'raьlromevairueda'],
    u'JØRGENSEN, Dan': [u'Dan Jшrgensen', u'danjшrgensen', u'dan jшrgensen'],
    u'HÄFNER, Gerald': [u'Haefner', u'haefner', u'Gerald Haefner', u'geraldhaefner',u'gerald haefner'],
    u'EVANS, Robert': [u'Evans Robert J.E.', u'evansrobertj.e.'],
    u'LAMBSDORFF, Alexander Graf': [u'Lambsdorff Graf', u'lambsdorffgraf'],
    u'STARKEVIČIŪTĖ, Margarita': [u'Starkeviciūtė', u'starkeviciūtė'],
    u'KUŠĶIS, Aldis': [u'Kuškis', u'kuškis'],
    u'ŠŤASTNÝ, Peter': [u'Štastný', u'štastný'],
    u'FLAŠÍKOVÁ BEŇOVÁ, Monika': [u'Beňová', u'beňová'],
    u'ŢÎRLE, Radu': [u'Tîrle', u'tîrle'],
    u'HYUSMENOVA, Filiz Hakaeva': [u'Husmenova', u'husmenova'],
    u'LØKKEGAARD, Morten': [u'Morten Lokkegaard', u'mortenlokkegaard'],
    u"GOMES, Ana": [u'Ana Maria Gomes', u'ana maria gomes', u'anamariagomes'],
    u'(The Earl of) DARTMOUTH, William': [u'WilliAmendment (The Earl of) Dartmouth', u'williamendment (the earl of) dartmouth', u'williamendment(theearlof)dartmouth'],
    u'ESTARÀS FERRAGUT, Rosa': [u'Estarŕs Ferragut', u'estarŕs ferragut', u'estarŕsferragut'],
    u'GROSSETÊTE, Françoise': [u'Grossetęte', u'grossetęte'],
    u'SAVISAAR-TOOMAST, Vilja': [u'Vilja Savisaar', u'vilja savisaar', u'viljasavisaar'],
    u'HEDKVIST PETERSEN, Ewa' : [u'Hedkvist Pedersen', u'hedkvist pedersen', u'hedkvistpedersen'],
    u'JĘDRZEJEWSKA, Sidonia Elżbieta': [u'Sidonia Elżbieta Jędrzejewska', u'sidonia elżbieta jędrzejewska',u'sidoniaelżbietajędrzejewska',],
    u'TRAKATELLIS, Antonios': [u'M Trakatellis', u'm trakatellis', u'mtrakatellis'],
    u'FAVA, Claudio': [u'Giovanni Claudio Fava', u'giovanni claudio fava', u'giovanniclaudiofava'],
    u'TOMCZAK, Witold': [u'W. Tomczak', u'w. tomczak', u'w.tomczak'],
    u'PĘCZAK, Andrzej Lech': [u'A. Peczak', u'a. peczak', u'a.peczak'],
    u'SAKELLARIOU, Jannis': [u'Janis Sakellariou', u'janis sakellariou', u'janissakellariou'],
    u'GOROSTIAGA ATXALANDABASO, Koldo': [u'Koldo Gorostiaga', u'koldo gorostiaga', u'koldogorostiaga'],
    }

Titles=['Sir',
        'Lady',
        'Baroness',
        'Baron',
        'Lord',
        'Gräfin von',
        'Earl',
        'Duke',
        'The Earl of',
        '(The Earl of)',
        'The Lord',
        'Professor Sir']

def save(data, stats):
    res=db.ep_meps2.find_one({ 'UserID' : data['UserID'] }) or {}
    d=diff(dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]),
           dict([(k,v) for k,v in data.items() if not k in ['_id', 'meta', 'changes',]]))
    if d:
        now=datetime.utcnow().replace(microsecond=0)
        if not res:
            logger.info(('adding %s' % (data['Name']['full'])).encode('utf8'))
            data['meta']['created']=now
            if stats: stats[0]+=1
        else:
            logger.info(('updating %s' % (data['Name']['full'])).encode('utf8'))
            logger.warn(jdump(d))
            data['meta']['updated']=now
            if stats: stats[1]+=1
            data['_id']=res['_id']
        data['changes']=res.get('changes',{})
        data['changes'][now.isoformat()]=d
        db.ep_meps2.save(data)
    if stats: return stats
    else: return data

unlisted=[ 1018, 26833, 1040, 1002, 2046, 23286, 28384, 1866, 28386,
           1275, 2187, 34004, 28309, 1490, 28169, 28289, 28841, 1566,
           2174, 4281, 28147, 28302, ]
meplists={
    'in':       'http://www.europarl.europa.eu/meps/en/xml.html?query=inout&type=in',
    'out':      'http://www.europarl.europa.eu/meps/en/xml.html?query=inout&type=out',
    'observer': 'http://www.europarl.europa.eu/meps/en/xml.html?query=observer',
    #'all':      'http://www.europarl.europa.eu/meps/en/xml.html?query=full&filter=&leg=0', # returns limited to only 80 records per default :/
    'all':      'http://www.europarl.europa.eu/meps/en/xml.html?query=full&filter=%s&leg=0', # we have to page by starting letters :/
    #'current':  'http://www.europarl.europa.eu/meps/en/xml.html?query=full&filter=&leg=%s' % current_term,
    'current':  'http://www.europarl.europa.eu/meps/en/xml.html?leg=0', # automatically returns the latest
    'unlisted': None,
}

def getmeps(query='current'):
    if query=='unlisted':
        for mep in unlisted:
            yield mep
    elif query=='all':
        for letter in xrange(26):
            tmp=meplists[query]
            a=ord('A')
            root=fetch(tmp%chr(a+letter), ignore=[500])
            for meplm in root.xpath('//id/text()'):
                yield int(meplm)
    else:
        root=fetch(meplists[query], ignore=[500])
        for meplm in root.xpath('//id/text()'):
            yield int(meplm)

def crawler(meps,saver=jdump,threads=4):
    m=Multiplexer(scrape,saver,threads=threads)
    m.start()
    [m.addjob(mepid) for mepid in meps]
    m.finish()
    logger.info('end of crawl')

def seqcrawl(meps, term=current_term,saver=jdump, scraper=scrape, null=False):
    return [saver(scraper(mepid),None)
            for mepid in meps
            if (null and db.ep_meps2.find_one({'UserID': mepid},['_id'])==None) or not null]

if __name__ == "__main__":
    if len(sys.argv)<2:
        print "%s full|test|mepid <mepid> [<seq>] [<dry>]" % (sys.argv[0])
    args=set(sys.argv[1:])
    saver=save
    null=False
    if 'dry' in args:
        saver=jdump
    if 'null' in args:
        null=True

    if sys.argv[1]=="test":
        print jdump(scrape('28215')).encode('utf8')
        print jdump(scrape('113959')).encode('utf8')

        #print jdump(scrape('108570')).encode('utf8')
        #print jdump(scrape('1934')).encode('utf8')
        #print jdump(scrape('96919')).encode('utf8')
        #import code; code.interact(local=locals());
        sys.exit(0)
        print jdump(scrape("http://www.europarl.europa.eu/meps/en/1934/get.html"),None)
        print jdump(scrape("http://www.europarl.europa.eu/meps/en/28576/get.html"), None)
        print jdump(scrape("http://www.europarl.europa.eu/meps/en/1263/Elmar_BROK.html"), None)
        print jdump(scrape("http://www.europarl.europa.eu/meps/en/96739/Reinhard_B%C3%9CTIKOFER.html"), None)
        print jdump(scrape("http://www.europarl.europa.eu/meps/en/28269/Jerzy_BUZEK.html"), None)
        print jdump(scrape("http://www.europarl.europa.eu/meps/en/1186/Astrid_LULLING.html"), None)
    elif sys.argv[1]=='mepid' and sys.argv[2]:
        print saver(scrape(int(sys.argv[2]))).encode('utf8')
        sys.exit(0)

    elif sys.argv[1] in meplists.keys():
        logger.info('\n\tsaver: %s\n\tseq: %s' % (saver, 'seq' in args))
        meps=getmeps(sys.argv[1])
        if 'seq' in args:
            res=seqcrawl(meps,saver=saver, null=null)
            if 'dry' in args:
                print "[%s]" % ',\n'.join(res).encode('utf8')
        else:
            crawler(meps,saver=saver)
