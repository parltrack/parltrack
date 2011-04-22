# -*- coding: utf-8 -*-
from parltrack.environment import connect_db, get_data_dir
import logging
import re, string, os
import urllib2, urllib
import cookielib
from datetime import datetime
from hashlib import sha1
from threading import Lock
from time import sleep
from lxml import etree
from hashlib import sha1
from pprint import pprint
from itertools import count
from urlparse import urlparse, urljoin, parse_qs
from StringIO import StringIO

MAKE_SESSION_URL = "http://dipbt.bundestag.de/dip21.web/bt"
BASE_URL = "http://dipbt.bundestag.de/dip21.web/searchProcedures/simple_search.do?method=Suchen&offset=%s&anzahl=100"
DETAIL_VP_URL = "http://dipbt.bundestag.de/dip21.web/searchProcedures/simple_search_detail_vp.do?vorgangId=%s"

FACTION_MAPS = {
        u"BÜNDNIS 90/DIE GRÜNEN": u"B90/Die Grünen",
        u"DIE LINKE.": u"Die LINKE.",
        u"Bündnis 90/Die Grünen": u"B90/Die Grünen",
        u"Die Linke": "Die LINKE."
        }

DIP_GREMIUM_TO_KEY = {
    u"Ausschuss für Bildung, Forschung und Technikfolgenabschätzung": "a18",
    u"Ausschuss für Ernährung, Landwirtschaft und Verbraucherschutz": "a10",
    u"Ausschuss für Tourismus": "a20",
    u"Ausschuss für Umwelt, Naturschutz und Reaktorsicherheit": "a16",
    u"Ausschuss für Verkehr, Bau und Stadtentwicklung": "a15",
    u"Ausschuss für Arbeit und Soziales": "a11",
    u"Ausschuss für Familie, Senioren, Frauen und Jugend": "a13",
    u"Ausschuss für Wirtschaft und Technologie": "a09",
    u"Finanzausschuss": "a07",
    u"Haushaltsausschuss": "a08",
    u"Ausschuss für die Angelegenheiten der Europäischen Union": "a21",
    u"Ausschuss für Agrarpolitik und Verbraucherschutz": "a10",
    u"Ausschuss für Innere Angelegenheiten": "a04",
    u"Wirtschaftsausschuss": "a09",
    u"Ausschuss für Gesundheit": "a14",
    u"Ausschuss für Wahlprüfung, Immunität und Geschäftsordnung": "a01",
    u"Rechtsausschuss": "a06",
    u"Ausschuss für Fragen der Europäischen Union": "a21",
    u"Ausschuss für Kulturfragen": "a22",
    u"Gesundheitsausschuss": "a14",
    u"Ausschuss für Menschenrechte und humanitäre Hilfe": "a17",
    u"Ausschuss für wirtschaftliche Zusammenarbeit und Entwicklung": "a19",
    u"Ausschuss für Auswärtige Angelegenheiten": "a03",
    u"Ausschuss für Kultur und Medien": "a22",
    u"Sportausschuss": "a05",
    u"Auswärtiger Ausschuss": "a03",
    u"Ausschuss für Arbeit und Sozialpolitik": "a11",
    u"Ausschuss für Frauen und Jugend": "a13",
    u"Ausschuss für Städtebau, Wohnungswesen und Raumordnung": "a15",
    u"Innenausschuss": "a04",
    u"Verkehrsausschuss": "a15",
    u"Verteidigungsausschuss": "a12",
    u"Ausschuss für Familie und Senioren": "a13",
    u"Petitionsausschuss": "a02",
    u"Ausschuss für Verteidigung": "a12",
    u"Ältestenrat": "002"
    }


DIP_ABLAUF_STATES_FINISHED = {
    u'Beantwortet': True,
    u'Abgeschlossen': True,
    u'Abgelehnt': True,
    u'In der Beratung (Einzelheiten siehe Vorgangsablauf)': False,
    u'Verkündet': True,
    u'Angenommen': True,
    u'Keine parlamentarische Behandlung': False,
    u'Überwiesen': False,
    u'Beschlussempfehlung liegt vor': False,
    u'Noch nicht beraten': False,
    u'Für erledigt erklärt': True,
    u'Noch nicht beantwortet': False,
    u'Zurückgezogen': True,
    u'Dem Bundestag zugeleitet - Noch nicht beraten': False,
    u'Nicht beantwortet wegen Nichtanwesenheit des Fragestellers': True,
    u'Zustimmung erteilt': True,
    u'Keine parlamentarische Behandlung': True,
    u'Aufhebung nicht verlangt': False,
    u'Den Ausschüssen zugewiesen': False,
    u'Zusammengeführt mit... (siehe Vorgangsablauf)': True,
    u'Dem Bundesrat zugeleitet - Noch nicht beraten': False,
    u'Zustimmung (mit Änderungen) erteilt': True,
    u'Bundesrat hat Vermittlungsausschuss nicht angerufen': False,
    u'Bundesrat hat zugestimmt': False,
    u'1. Durchgang im Bundesrat abgeschlossen': False,
    u'Einbringung abgelehnt': True,
    u'Verabschiedet': True,
    u'Entlastung erteilt': True,
    u'Abschlussbericht liegt vor': True,
    u'Erledigt durch Ende der Wahlperiode (§ 125 GOBT)': True,
    u'Zuleitung beschlossen': False,
    u'Zuleitung in geänderter Fassung beschlossen': False,
    u'Für gegenstandslos erklärt': False,
    u'Nicht ausgefertigt wegen Zustimmungsverweigerung des Bundespräsidenten': False,
    u'Im Vermittlungsverfahren': False,
    u'Zustimmung versagt': True,
    u'Einbringung in geänderter Fassung beschlossen': False,
    u'Bundesrat hat keinen Einspruch eingelegt': False,
    u'Bundesrat hat Einspruch eingelegt': False,
    u'Zuleitung in Neufassung beschlossen': True,
    u'Untersuchungsausschuss eingesetzt': False
}

jar = None
lock = Lock()

inline_re = re.compile(r"<!--(.*?)-->", re.M + re.S)
inline_comments_re = re.compile(r"<-.*->", re.M + re.S)

def inline_xml_from_page(page):
    for comment in inline_re.findall(page):
        comment = comment.strip()
        if comment.startswith("<?xml"):
            comment = inline_comments_re.sub('', comment)
            return etree.parse(StringIO(comment))

def get_dip_with_cookie(url, method='GET', data={}):
    class _Request(urllib2.Request):
        def get_method(self):
            return method

    lock.acquire()
    try:
        def _req(url, jar, data={}):
            _data = urllib.urlencode(data)
            req = _Request(url, _data)
            jar.add_cookie_header(req)
            fp = urllib2.urlopen(req)
            jar.extract_cookies(fp, req)
            return fp
        global jar
        if jar is None:
            jar = cookielib.CookieJar()
            fp = _req(MAKE_SESSION_URL, jar)
            fp.read()
            fp.close()
        return _req(url, jar, data=data)
    finally:
        lock.release()


def _get_document(db, publisher, typ, id, **kwargs):
    q = {"publisher": publisher, "typ": typ, "key": id}
    data = {'publisher': publisher}
    for k, v in kwargs.items():
        if v:
            data[k] = v
    db.document.update(q, {"$set": data}, upsert=True)
    if data.get('link'):
        fetch_document(data.get('link'))
    return db.document.find_one(q).get('_id')

def document_by_id(db, publisher, typ, id, **kwargs):
    if '/' in id:
        section, id = id.split("/", 1)
        id = id.lstrip("0")
        id = section + "/" + id
    return _get_document(db, publisher, typ, id, **kwargs)

def document_by_url(db, url, **kwargs):
    if url is None or not url:
        return
    if '#' in url:
        url, fragment = url.split('#', 1)
    name, file_ext = url.rsplit('.', 1)
    base = name.split('/', 4)[-1].split("/")
    publisher, typ = {"btd": ("BT", "drs"),
                 "btp": ("BT", "plpr"),
                 "brd": ("BR", "drs"),
                 "brp": ("BR", "plpr")
                }.get(base[0])
    if publisher == 'BR' and typ == 'plpr':
        id = base[1]
    elif publisher == 'BR' and typ == 'drs':
        id = "/".join(base[-1].split("-"))
    elif publisher == 'BT':
        s = base[1]
        id = base[-1][len(s):].lstrip("0")
        id = s + "/" + id
    return _get_document(db, publisher, typ, id, link=url, **kwargs)

END_ID = re.compile("[,\n]")
def document_by_name(db, name, **kwargs):
    if name is None or not name:
        return
    print name.encode("utf-8")
    if ' - ' in name:
        date, name = name.split(" - ", 1)
    else:
        print "WARNING NO DATE", name.encode('utf-8')
    if ',' in name or '\n' in name:
        name, remainder = END_ID.split(name, 1)
    typ, id = name.strip().split(" ")
    publisher, typ = {
            "BT-Plenarprotokoll": ("BT", "plpr"),
            "BT-Drucksache": ("BT", "drs"),
            "BR-Plenarprotokoll": ("BR", "plpr"),
            "BR-Drucksache": ("BR", "drs")
            }.get(typ)
    if publisher == 'BT' and typ == 'drs':
        f, s = id.split("/")
        s = s.zfill(5)
        kwargs['link'] = "http://dipbt.bundestag.de:80/dip21/btd/%s/%s/%s%s.pdf" % (f, s[:3], f, s)
    return _get_document(db, publisher, typ, id, title=name, **kwargs)



# EU Links
COM_LINK = re.compile('.*Kom.\s\((\d{1,4})\)\s(\d{1,6}).*')
SEC_LINK = re.compile('.*Sek.\s\((\d{1,4})\)\s(\d{1,6}).*')
RAT_LINK = re.compile('.*Ratsdok.\s*([\d\/]*).*')
EUR_LEX_RECH = "http://eur-lex.europa.eu/Result.do?T1=%s&T2=%s&T3=%s&RechType=RECH_naturel"
LEX_URI = "http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=%s:%s:%s:FIN:DE:%s"
CONS = "http://register.consilium.europa.eu/servlet/driver?lang=DE&typ=Advanced&cmsid=639&ff_COTE_DOCUMENT=%s&fc=REGAISDE&md=100&rc=1&nr=1&page=Detail"
def expand_eu_reference(ablauf):
    eu_dok_nr = ablauf.get('eu_dok_nr')
    if not eu_dok_nr:
        return ablauf
    com_match = COM_LINK.match(eu_dok_nr)
    if com_match:
        year, process = com_match.groups()
        ablauf['eur_lex_url'] = EUR_LEX_RECH % ("V5", year, process)
        ablauf['eur_lex_pg'] = LEX_URI % ("COM", year, process.zfill(4), "PDF")
    sec_match = SEC_LINK.match(eu_dok_nr)
    if sec_match:
        year, process = sec_match.groups()
        ablauf['eur_lex_url'] = EUR_LEX_RECH % ("V7", year, process)
        ablauf['eur_lex_pg'] = LEX_URI % ("SEC", year, process.zfill(4), "PDF")
    rat_match = RAT_LINK.match(eu_dok_nr)
    if rat_match:
        id, = rat_match.groups()
        ablauf['consilium_url'] = CONS % urllib.quote(id)
    return ablauf

def fetch_document(link):
    file_id = sha1(link).hexdigest()
    path = os.path.join(get_data_dir(), file_id)
    if os.path.isfile(path):
        return
    try:
        urllib.urlretrieve(link, path)
    except Exception, e:
        logging.exception(e)



def activity_person_merge(db, actor):
    actor = actor.copy()
    if actor.get('firstname') == 'Wolfgang' and actor.get('lastname') == 'Neskovic':
        actor['lastname'] = u'Nešković'
    if actor.get('firstname') == 'Eva' and actor.get('lastname') == 'Klamt':
        actor['firstname'] = 'Ewa'
    if actor.get('firstname') == 'Daniela' and actor.get('lastname') == 'Raab':
        # data mining and marriage: not a good fit.
        actor['lastname'] = 'Ludwig'
    candidates = list(db.actor.find(
        {"firstname": actor.get('firstname'),
         "lastname": actor.get('lastname')}))
    if len(candidates) == 0:
        #print _namesub(actor.get('firstname'))
        candidates = list(db.actor.find(
            {"firstname": {"$regex": actor.get('firstname') + ".*"},
             "lastname": actor.get('lastname')}))
    if actor.get('funktion') == 'MdB' or len(candidates) == 1:
        if len(candidates) == 0:
            def _namesub(name):
                s = '.*'
                for c in name:
                    if c in string.letters:
                        s += c
                    else:
                        s += '.'
                return s + '.*'
            candidates = list(db.actor.find(
                {"firstname": {"$regex": _namesub(actor.get('firstname'))},
                 "lastname": {"$regex": _namesub(actor.get('lastname'))}}))
        if len(candidates) == 0:
            candidates = list(db.actor.find({"$or": [
                {"firstname": actor.get('firstname')},
                {"lastname": actor.get('lastname')}]}))
        if len(candidates) == 1:
            a = candidates[0]
            db.actor.update({'_id': a.get('_id')},
                {"$set": {"funktion": actor.get("funktion"),
                          "ressort": actor.get("ressort"),
                          "ortszusatz": actor.get("ortszusatz"),
                          "state": actor.get("state")}})
            return a.get('_id')
        pprint(actor)
        print "HAS", len(candidates), "CANDIDATES"
        pprint(candidates)
        return None
    a = actor.copy()
    if 'seite' in a:
        del a['seite']
    if 'aktivitaet' in a:
        del a['aktivitaet']
    a['key'] = sha1(repr(a).encode("ascii", "ignore")).hexdigest()[:10]
    db.actor.update({"key": a['key']}, a, upsert=True)
    return db.actor.find_one({"key": a['key']}).get('_id')

def test_activiy_person_merge(db):
    aktivitaeten = db.aktivitaet.find()
    for aktivitaet in aktivitaeten:
        for akteur in aktivitaet.get('akteure', []):
            activity_person_merge(db, akteur)



def scrape_stages(db, db_id, id, session):
    urlfp = get_dip_with_cookie(DETAIL_VP_URL % id)
    xml = inline_xml_from_page(urlfp.read())
    urlfp.close()
    if xml is None:
        return {}
    stages = []
    for position in xml.findall(".//VORGANGSPOSITION"):
        pos = {
            'procedure': db_id,
            'session': session,
            'body': position.findtext("ZUORDNUNG"),
            'creator': position.findtext("URHEBER"),
            'source': position.findtext("FUNDSTELLE"),
            'source_link':  position.findtext("FUNDSTELLE_LINK"),
        }
        dt, rest = pos.get('source').split("-", 1)
        pos['date'] = datetime.strptime(dt.strip(), "%d.%m.%Y")
        key = sha1(pos.get('source').encode("ascii", "ignore") \
                + pos.get('creator').encode("ascii", "ignore")).hexdigest()[:10]
        pos['key'] = key
        typ = pos.get('creator', '')
        if ',' in typ:
            typ, quelle = typ.split(',', 1)
            pos['source_name'] = re.sub("^.*Urheber.*:", "", quelle).strip()
        else:
            pos['source_name'] = None
        pos['typ'] = typ.strip()
        try:
            pos['document'] = document_by_url(db, pos.get('source_link'))
            assert pos['document'] is not None
        except:
            try:
                pos['document'] = document_by_name(db, pos.get('source'))
            except Exception, e:
                logging.exception(e)

        for creator in position.findall("PERSOENLICHER_URHEBER"):
            c = {
                'firstname': creator.findtext("VORNAME"),
                'lastname': creator.findtext("NACHNAME"),
                'function': creator.findtext("FUNKTION"),
                'constituency': creator.findtext('WAHLKREISZUSATZ'),
                'group': creator.findtext("FRstageION"),
                'department': creator.findtext("RESSORT"),
                'state': creator.findtext("BUNDESLAND"),
                'activity': creator.findtext("stageIVITAETSART"),
                'page': creator.findtext("SEITE"),
            }
            c['group'] = FACTION_MAPS.get(c['group'], c['group'])
            c['id'] = activity_person_merge(db, c)
            #if c['function'] != "MdB":
            pos['participants'] = pos.get('participants', []) + [c]
        for delegation in position.findall("ZUWEISUNG"):
            z = {
                'committee': delegation.findtext("AUSSCHUSS_KLARTEXT"),
                'responsible': delegation.find("FEDERFUEHRUNG") is not None,
            }
            key = DIP_GREMIUM_TO_KEY.get(z['committee'])
            if key is None:
                print "TODO: Ausschuss %s" % z['committee'].encode('utf-8')
            else:
                z['key'] = key
                committee = db.committee.find_one({"key": key})
                z['id'] = committee.get('_id')
            pos['committees'] = pos.get('committees', []) + [z]
        for decision in position.findall("BESCHLUSS"):
            d = {
                'page': decision.findtext("BESCHLUSSSEITE"),
                'document': decision.findtext("BEZUGSDOKUMENT"),
                'result': decision.findtext("BESCHLUSSTENOR")
            }
            pos['decisions'] = pos.get('decisions', []) + [d]
        if len(pos.get('decisions', [])) > 1:
            logging.warn("More than one decision on activity: %s: %s", id, len(pos.get('decisions')))
        q = {"procedure": db_id, "key": key}
        db.stage.update(q, {"$set": pos}, upsert=True)
        stage = db.stage.find_one(q)
        stages.append(stage)
    return stages


def scrape_procedure(db, url):
    id = parse_qs(urlparse(url).query).get('selId')[0]
    logging.info("Procedure %s", id)
    if db.procedure.find_one({"source_url": url, "finished": True}):
        print "%s - Skipping!" % id
        return {}
    urlfp = get_dip_with_cookie(url)
    xml = inline_xml_from_page(urlfp.read())
    urlfp.close()
    if xml is None:
        logging.warn("Could not find embedded XML in Ablauf: %s", id)
        return {}
    procedure = xml #.find("VORGANG")
    session = procedure.findtext("WAHLPERIODE")
    reference = session + '/' + id
    proc = {
        'parliament': 'de',
        'reference': reference,
        'ablauf_id': id,
        'session': session,
        'source_url': url,
        'type': procedure.findtext("VORGANGSTYP"),
        'title': procedure.findtext("TITEL"),
        'initiative': procedure.findtext("INITIATIVE"),
        'state': procedure.findtext("AKTUELLER_STAND"),
        'signature': procedure.findtext("SIGNATUR"),
        'gesta_id': procedure.findtext("GESTA_ORDNUNGSNUMMER"),
        'eu_reference': procedure.findtext("EU_DOK_NR"),
        'description': procedure.findtext("ABSTRAKT"),
        'legal_basis': procedure.findtext("ZUSTIMMUNGSBEDUERFTIGKEIT"),
        'tags': [t.text for t in procedure.findall("SCHLAGWORT")],
        'subjects': [procedure.findtext("SACHGEBIET")]
    }
    proc['title'] = proc['title'].strip().lstrip('.').strip()
    proc = expand_eu_reference(proc)
    #print proc['stand'].encode('utf-8')
    proc['finished'] = DIP_ABLAUF_STATES_FINISHED.get(proc.get('stand'), False)
    if 'Originaltext der Frage(n):' in proc['description']:
        _, proc['description'] = proc['description'].split('Originaltext der Frage(n):', 1)
    for document in procedure.findall("WICHTIGE_DRUCKSACHE"):
        c = {
            'type': 'drs',
            'publisher': document.findtext("DRS_HERAUSGEBER"),
            'key': document.findtext("DRS_NUMMER"),
            'text': document.findtext("DRS_TYP"),
            'link': document.findtext("DRS_LINK")
        }
        c['id'] = document_by_id(db, c['publisher'], c['type'], c['key'],
                link=c['link'])
        proc['references'] = proc.get('references', []) + [c]
    for reading in procedure.findall("PLENUM"):
        c = {
            'type': 'plpr',
            'publisher': reading.findtext("PLPR_HERAUSGEBER"),
            'key': reading.findtext("PLPR_NUMMER"),
            'text': reading.findtext("PLPR_KLARTEXT"),
            'pages': reading.findtext("PLPR_SEITEN"),
            'link': reading.findtext("PLPR_LINK")
        }
        c['id'] = document_by_id(db, c['publisher'], c['type'], c['key'],
                link=c['link'])
        proc['references'] = proc.get('references', []) + [c]
    proc['documents'] = [r.get('id') for r in proc.get('references', []) if
            r.get('id')]
    q = {"reference": reference, "parliament": 'de'}
    db.procedure.update(q, {"$set": proc}, upsert=True)
    db_id = db.procedure.find_one(q).get('_id')
    print "-> ", id
    for stage in scrape_stages(db, db_id, id, session):
        if stage is not None:
            db.procedure.update(q, {"$addToSet": {"stages": stage.get('_id')}})
            db.procedure.update(q, {"$addToSet": {"documents": stage.get('documents')}})
    return proc


def load_dip(db):
    for offset in count():
        urlfp = get_dip_with_cookie(BASE_URL % (offset*100))
        logging.info("Scraping: %s", urlfp.url)
        root = etree.parse(urlfp, etree.HTMLParser())
        urlfp.close()
        table = root.find(".//table[@summary='Ergebnisliste']")
        if table is None: return
        for result in table.findall(".//a[@class='linkIntern']"):
            url = urljoin(BASE_URL, result.get('href'))
            scrape_procedure(db, url)


if __name__ == '__main__':
    db = connect_db()
    #test_activiy_person_merge(db)
    load_dip(db)


