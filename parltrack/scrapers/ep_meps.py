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
from parltrack.environment import connect_db
from mappings import COMMITTEE_MAP, buildings, group_map
from urlparse import urlparse, urljoin
import unicodedata, traceback, json, urllib2, sys
from parltrack.utils import diff, htmldiff, fetch, dateJSONhandler, unws, Multiplexer, logger

BASE_URL = 'http://www.europarl.europa.eu'
db = connect_db()
db.ep_meps2.ensure_index([('UserID', 1)])
db.ep_meps2.ensure_index([('Name.full', 1)])
db.ep_meps2.ensure_index([('Name.aliases', 1)])

def getAddress(root):
    res={}
    for div in root.xpath('//div[@id="contextzone"]//div[@class="ep_title"]'):
        # getAddress(map(strip, div.xpath("../..//div[@class='ep_elementcontact']/ul")))
        key=unws(''.join(div.xpath('.//text()')))
        if key not in ['Bruxelles', 'Strasbourg', 'Postal address', 'Luxembourg']:
            continue
        res[key]={}
        if key in ['Bruxelles', 'Strasbourg', 'Luxembourg']:
            tmp=div.xpath('../..//li[@class="ep_phone"]/div/text()')
            if tmp:
                res[key]['Phone'] = unws(tmp[0]).replace('(0)','')
            tmp=div.xpath('../..//li[@class="ep_fax"]/div/text()')
            if tmp:
                res[key]['Fax'] = unws(tmp[0]).replace('(0)','')
        tmp=[unws(x) for x in div.xpath('../..//li[@class="ep_address"]/div/text()') if len(unws(x))]
        if key=='Strasbourg':
            res[key].update(dict(zip(['Organization','Building', 'Office', 'Street','Zip1', 'Zip2'],tmp)))
            res[key]['City']=res[key]['Zip2'].split()[1]
            res[key]['Zip2']=res[key]['Zip2'].split()[0]
            res[key]['building_code']=buildings[res[key]['Building']]
        elif key=='Bruxelles':
            res[key].update(dict(zip(['Organization','Building', 'Office', 'Street','Zip'],tmp)))
            res[key]['City']=res[key]['Zip'].split()[1]
            res[key]['Zip']=res[key]['Zip'].split()[0]
            res[key]['building_code']=buildings[res[key]['Building']]
        elif key=='Luxembourg':
            res[key]['Address']=tmp
        elif key=='Postal address':
            res[key]=tmp
        else:
            logger.error("wtf %s" % key)
    return res

def getMEPGender(id):
    try:
        mepraw=fetch("http://www.europarl.europa.eu/meps/fr/%s/get.html" % (id))
    except Exception, e:
        logger.error("mepgender %s" % e)
        return 'n/a'
    hint=mepraw.xpath('//div[@class="ep_elementtext"]/p/text()')[0].replace(u"\u00A0",' ').split()[0]
    if hint==u"Née":
        return "F"
    elif hint==u"Né":
        return "M"
    return 'n/a'

def parseMember(userid):
    url='http://www.europarl.europa.eu/meps/en/%s/get.html' % userid
    logger.info("scraping %s" % url)
    root = fetch(url)
    data = {u'active': True, 'meta': {u'url': url}} # return {'active': False}
    mepdiv=root.xpath('//div[@class="ep_elementpeople2"]')
    if len(mepdiv) == 1:
        mepdiv = mepdiv[0]
    else:
        logger.error("len(mepdiv) not 1: %s" % str(list(mepdiv)))
    data[u'Name'] = mangleName(unws(mepdiv.xpath('.//span[@class="ep_title"]/text()')[0]))
    data[u'Photo'] = unicode(urljoin(BASE_URL,mepdiv.xpath('.//span[@class="ep_img"]/img')[0].get('src')),'utf8')
    (d, p) = mepdiv.xpath('.//div[@class="ep_elementtext"]/p/text()')[0].split(',', 1)
    try:
        data[u'Birth'] = { u'date': datetime.strptime(unws(d), "Born on %d %B %Y"),
                           u'place': unws(p) }
    except ValueError:
        logger.warn('[!] failed to scrape birth data %s' % url)
        logger.warn(traceback.format_exc())
    const={u'country': unws(mepdiv.xpath('.//span[@class="ep_country"]/text()')[0])}
    data[u'Constituencies']=[const]
    try:
        const[u'party']=unws(mepdiv.xpath('.//span[@class="ep_group"]/text()')[1]),
    except IndexError:
        data[u'active']=False
    else:
        group=unws(mepdiv.xpath('.//span[@class="ep_group"]/text()')[0])
        data[u'Groups'] = [{ u'role': unws(mepdiv.xpath('.//span[@class="ep_title"]/text()')[1]),
                             u'group': group,
                             u'groupid': group_map[group]}]
    cdiv=root.xpath('//div[@class="ep_elementcontact"]')
    if len(cdiv):
        addif(data,u'RSS',[unicode(urljoin(BASE_URL,x.get('href')),'utf8') for x in cdiv[0].xpath('.//li[@class="ep_rss"]//a')])
        addif(data,u'Homepage',[unicode(x.get('href'),'utf8') for x in cdiv[0].xpath('.//li[@class="ep_website"]//a')])
        addif(data,u'Mail',[decodemail(unws(unicode(x,'utf8'))) for x in cdiv[0].xpath('.//li[@class="ep_email"]//text()') if len(unws(x))])
    for span in root.xpath('//div[@id="contextzone"]//span[@class="ep_title"]'):
        title=unws(''.join(span.xpath('.//text()')))
        if title in ['Accredited assistants', 'Local assistants']:
            addif(data,title,[unws(x) for x in span.xpath('../../..//li/div/text()')])
    addif(data,u'Addresses',getAddress(root))
    for div in root.xpath('//div[@class="ep_content"]'):
        key=unws(u''.join(div.xpath('.//span[@class="ep_title"]/text()')))
        if not len(key):
            continue
        elif key.lower()=='curriculum vitae':
            data[u'CV'] = [unws(x) for x in div.xpath('.//div[@class="ep_elementtext"]//li/div/text()')]
        elif key in ['Member', 'Substitute', 'Chair', 'Vice-Chair', 'Co-President', 'President', 'Vice-President']:
            for span in div.xpath('.//span[@class="commission_label"]'):
                item={u'role': key,
                      u'abbr': unws(''.join(span.xpath('text()'))),
                      u'Organization': unws(span.tail)}
                for start, field in orgmaps:
                    if item['Organization'].startswith(start):
                        if not field in data: data[field]=[]
                        if field=='Committees' and item['Organization'] in COMMITTEE_MAP:
                            item[u'committee_id']=COMMITTEE_MAP[item['Organization']]
                        data[field].append(item)
                        break
        else:
            logger.error('[!] unknown field %s' % key)
    return data

def addif(target, key, val):
    if val:
        target[key]=val

def decodemail(txt):
    return txt.replace('[dot]','.').replace('[at]','@')[::-1]

def mangleName(name):
    sur=[]
    family=[]
    tmp=name.split(' ')
    for i,token in enumerate(tmp):
        if token.isupper():
            family=tmp[i:]
            break
        else:
            sur.append(token)
    sur=' '.join(sur)
    family=' '.join(family)
    title=None
    for t in Titles:
        if family.startswith(t):
            family=family[len(t)+1:]
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
                                u''.join(("%s%s%s" % (family, sur, title)).split()).lower().strip(),
                                u''.join(("%s%s%s" % (family, title, sur)).split()).lower().strip(),
                                u''.join(("%s%s%s" % (title, family, sur)).split()).lower().strip(),
                                u''.join(("%s%s%s" % (title, sur, family)).split()).lower().strip(),
                                ])
    if  u'ß' in unicode(name):
        res[u'aliases'].extend([x.replace(u'ß','ss') for x in res['aliases']])
    if unicodedata.normalize('NFKD', unicode(name)).encode('ascii','ignore')!=name:
        res[u'aliases'].extend([unicodedata.normalize('NFKD', x).encode('ascii','ignore') for x in res['aliases']])
    if "'" in name:
        res[u'aliases'].extend([x.replace("'","") for x in res['aliases']])
    if name in meps_aliases:
           res[u'aliases'].extend(meps_aliases[name])
    return res

newbies={}
def scrape(url, data={}):
    urlseq=urlparse(url)
    userid=int(urlseq.path.split('/')[3])
    if userid in newbies:
        data=newbies[userid]
    name=urlseq.path.split('/')[4][:-5].replace('_',' ')
    data['UserID']=userid
    ret=parseMember(userid)
    for k in ['Constituencies', 'Groups']:
        if k in ret and k in data:
            # currently data is better than ret - might change later
            del ret[k]
    data.update(ret)
    data['Gender'] = getMEPGender(userid)
    return data

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
        'Earl',
        'Duke',
        'The Earl of',
        'The Lord',
        'Professor Sir']

def get_meps(term='7'):
    i=0
    page=fetch("http://www.europarl.europa.eu/meps/en/performsearch.html?webCountry=&webTermId=%s&name=&politicalGroup=&bodyType=ALL&bodyValue=&type=&filter=&search=Show+result" % (term))
    last=None
    while True:
        meps=[(x.get('href'), unws(x.xpath('text()')[0])) for x in page.xpath('//div[@class="ep_elementpeople1"]//a[@class="ep_title"]')]
        if meps==last:
            break
        for url,name in meps:
            yield (urljoin(urljoin(BASE_URL,url),'get.html'), name)
        last=meps
        i+=1
        page=fetch("http://www.europarl.europa.eu/meps/en/performsearch.html?action=%s&webCountry=&webTermId=%s&name=&politicalGroup=&bodyType=ALL&bodyValue=&type=&filter=" % (i, term))

def getActive():
    for elem in db.ep_meps2.find({ 'active' : True},['meta.url']):
        yield (elem['meta']['url'], elem['Name']['full'])

def getIncomming(term=7):
    # returns dict of new incoming meps. this is being checked when
    # crawling, to set more accurate groups and constituency info
    i=0
    page=fetch('http://www.europarl.europa.eu/meps/en/incoming-outgoing.html?type=in')
    last=None
    res={}
    while True:
        meps=[((u'name', unws(x.xpath('text()')[0])),
               (u'meta', {u'url': urljoin(urljoin(BASE_URL,x.get('href')),'get.html')}),
               (u'Constituencies', {u'start': datetime.strptime(unws((x.xpath('../span[@class="meps_date_inout"]/text()') or [''])[0]), "%B %d, %Y"),
                                    u'country': unws((x.xpath('..//span[@class="ep_country"]/text()') or [''])[0])}),
               (u'Groups', {u'start': datetime.strptime(unws((x.xpath('../span[@class="meps_date_inout"]/text()') or [''])[0]), "%B %d, %Y"),
                            u'group': unws((x.xpath('..//span[@class="ep_group"]/text()') or [''])[0]),
                            u'groupid': group_map[unws((x.xpath('..//span[@class="ep_group"]/text()') or [''])[0])],
                            u'role': unws((x.xpath('..//span[@class="ep_group"]/span[@class="ep_title"]/text()') or [''])[0])}),
               )
              for x in page.xpath('//div[@class="ep_elementpeople1"]//a[@class="ep_title"]')]
        if meps==last:
            break
        last=meps
        for mep in meps:
            res[int(mep[1][1]['url'].split('/')[-2])]=dict(mep[1:])
        i+=1
        page=fetch('http://www.europarl.europa.eu/meps/en/incoming-outgoing.html?action=%s&webCountry=&webTermId=%s&name=&politicalGroup=&bodyType=&bodyValue=&type=in&filter=' % (i, term))
    return res

def getOutgoing(term=7):
    # returns an iter over ex meps from the current term, these are
    # missing from the get_meps result
    i=0
    page=fetch('http://www.europarl.europa.eu/meps/en/incoming-outgoing.html?type=out')
    last=None
    while True:
        meps=[((u'url', urljoin(BASE_URL,x.get('href'))),
               (u'name', unws(x.xpath('text()')[0])),
               ('dates', unws((x.xpath('../span[@class="meps_date_inout"]/text()') or [''])[0])),
               ('country', unws((x.xpath('../span[@class="ep_country"]/text()') or [''])[0])),
               ('group', unws((x.xpath('..//span[@class="ep_group"]/text()') or [''])[0])),
               ('role', unws((x.xpath('..//span[@class="ep_group"]/span[@class="ep_title"]/text()') or [''])[0])),
               )
              for x in page.xpath('//div[@class="ep_elementpeople1"]//a[@class="ep_title"]')]
        if meps==last:
            break
        last=meps
        for mep in meps:
            mep=dict(mep)
            tmp=mep['dates'].split(' - ')
            if tmp:
                mep[u'Constituencies']={u'start': datetime.strptime(tmp[0], "%B %d, %Y"),
                                       u'end': datetime.strptime(tmp[1], "%B %d, %Y"),
                                       u'country': mep['country']}
                mep[u'Groups']={u'start': datetime.strptime(tmp[0], "%B %d, %Y"),
                               u'end': datetime.strptime(tmp[1], "%B %d, %Y"),
                               u'group': mep['group'],
                               u'role': mep['role']}
                del mep['dates']
                del mep['country']
                del mep['group']
                del mep['role']
                yield (urljoin(urljoin(BASE_URL,mep['url']),'get.html'), mep)
        i+=1
        page=fetch('http://www.europarl.europa.eu/meps/en/incoming-outgoing.html?action=%s&webCountry=&webTermId=%s&name=&politicalGroup=&bodyType=&bodyValue=&type=out&filter=' % (i, term))

def jdump(d, tmp=None):
    # simple json dumper default for saver (multiplexer related)
    logger.info(json.dumps(d, indent=1, default=dateJSONhandler, ensure_ascii=False).encode('utf-8'))
    return json.dumps(d, indent=1, default=dateJSONhandler, ensure_ascii=False)

def save(data, stats):
    res=db.ep_meps2.find_one({ 'UserID' : data['UserID'] }) or {}
    d=diff(dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]),
           dict([(k,v) for k,v in data.items() if not k in ['_id', 'meta', 'changes',]]))
    if d:
        now=unicode(datetime.utcnow().replace(microsecond=0).isoformat())
        if not res:
            logger.info(('adding %s' % (data['Name']['full'])).encode('utf8'))
            data['meta']['created']=now
            stats[0]+=1
        else:
            logger.info(('updating %s' % (data['Name']['full'])).encode('utf8'))
            logger.warn(d)
            data['meta']['updated']=now
            stats[1]+=1
            data['_id']=res['_id']
        data['changes']=res.get('changes',{})
        data['changes'][now]=d
        db.ep_meps2.save(data)
    return stats

def crawlseq(term='7',saver=jdump):
    for url, name in get_meps(term=term):
        saver(scrape(url))

def crawl_all(saver=jdump,threads=4):
    m=Multiplexer(scrape,saver,threads=threads)
    m.start()
    seen=[]
    for term in xrange(1,8):
        for url, name in get_meps(term=term):
            if not url in seen:
                m.addjob(url)
                seen.append(url)
    m.finish()
    logger.info('end of crawl')

def crawl_allseq(saver=jdump):
    seen=[]
    stats=[0,0]
    for term in xrange(1,8):
        for url, name in get_meps(term=term):
            if not url in seen:
                saver(scrape(url),stats)
    logger.info('end of crawl')

def crawl(saver=jdump,threads=4):
    m=Multiplexer(scrape,saver,threads=threads)
    m.start()
    [m.addjob(url) for url, name in get_meps()]
    m.finish()
    logger.info('end of crawl')

def crawler(targets,saver=jdump,threads=4, term='7'):
    m=Multiplexer(scrape,saver,threads=threads)
    m.start()
    [m.addjob(url, data) for url, data in targets(term=term)]
    m.finish()
    logger.info('end of crawl')

def seqcrawl(targets, term='7',saver=jdump, scraper=scrape):
    for url, data in targets(term=term):
        saver(scraper(url, data))

if __name__ == "__main__":
    if len(sys.argv)!=2:
        print "%s full|fullseq|current|currentdry|currentseq|currentdry|currentseqdry|outgoing|outgoingseq|outgoingdry|outgoingseqdry|test" % (sys.argv[0])
    if sys.argv[1]=="full":
        # outgoing and full (latest term, does not contain the
        # inactive meps, so outgoing is necessary to scrape as well
        crawl_all(saver=save,threads=8)
        crawler(getOutgoing, saver=save)
    if sys.argv[1]=="fullseq":
        # outgoing and full (latest term, does not contain the
        # inactive meps, so outgoing is necessary to scrape as well
        crawl_allseq(saver=save)
        crawler(getOutgoing, saver=save)

    elif sys.argv[1]=="current":
        newbies=getIncomming()
        crawl(saver=save)
    elif sys.argv[1]=="currentseq":
        newbies=getIncomming()
        crawlseq(saver=save)
    elif sys.argv[1]=="currentdry":
        newbies=getIncomming()
        crawl()
    elif sys.argv[1]=="currentseqdry":
        newbies=getIncomming()
        crawlseq()

    elif sys.argv[1]=="outgoing":
        crawler(getOutgoing, saver=save)
    elif sys.argv[1]=="outgoingseq":
        seqcrawl(getOutgoing, saver=save)
    elif sys.argv[1]=="outgoingdry":
        crawler(getOutgoing)
    elif sys.argv[1]=="outgoingseqdry":
        seqcrawl(getOutgoing)

    elif sys.argv[1]=="test":
        import pprint
        scrape('http://www.europarl.europa.eu/meps/en/950/get.html')
        #d=getIncomming()
        #d=list(getActive())
        #import code; code.interact(local=locals());
        #print len(d)
        #pprint.pprint(d)
        sys.exit(0)
        jdump(scrape("http://www.europarl.europa.eu/meps/en/1934/get.html"),None)
        jdump(scrape("http://www.europarl.europa.eu/meps/en/28576/get.html"), None)
        jdump(scrape("http://www.europarl.europa.eu/meps/en/1263/Elmar_BROK.html"), None)
        jdump(scrape("http://www.europarl.europa.eu/meps/en/96739/Reinhard_B%C3%9CTIKOFER.html"), None)
        jdump(scrape("http://www.europarl.europa.eu/meps/en/28269/Jerzy_BUZEK.html"), None)
        jdump(scrape("http://www.europarl.europa.eu/meps/en/1186/Astrid_LULLING.html"), None)
        d=list(getOutgoing())
        print len(d)
        pprint.pprint(d)
