from lxml import etree
from pprint import pprint

from parltrack.environment import connect_db

MDB_INDEX_URL = "http://www.bundestag.de/xml/mdb/index.xml"
AUSSCHUSS_INDEX_URL = "http://www.bundestag.de/xml/ausschuesse/index.xml"
AKTUELL_URL = "http://www.bundestag.de/xml/aktuell/index.xml"

RSS_FEEDS = {
        "a11": "http://www.bundestag.de/rss_feeds/arbeitsoziales.rss",
        "a03": "http://www.bundestag.de/rss_feeds/auswaertiges.rss",
        "a18": "http://www.bundestag.de/rss_feeds/bildung.rss",
        "a10": "http://www.bundestag.de/rss_feeds/landwirtschaftverbraucher.rss",
        "a21": "http://www.bundestag.de/rss_feeds/eu.rss",
        "a13": "http://www.bundestag.de/rss_feeds/familie.rss",
        "a07": "http://www.bundestag.de/rss_feeds/finanzen.rss",
        "a14": "http://www.bundestag.de/rss_feeds/gesundheit.rss",
        "a08": "http://www.bundestag.de/rss_feeds/haushalt.rss",
        "a04": "http://www.bundestag.de/rss_feeds/inneres.rss",
        "a22": "http://www.bundestag.de/rss_feeds/kultur.rss",
        "a17": "http://www.bundestag.de/rss_feeds/menschenrechte.rss",
        "a02": "http://www.bundestag.de/rss_feeds/petitionen.rss",
        "a06": "http://www.bundestag.de/rss_feeds/recht.rss",
        "a05": "http://www.bundestag.de/rss_feeds/sport.rss",
        "a20": "http://www.bundestag.de/rss_feeds/tourismus.rss",
        "a16": "http://www.bundestag.de/rss_feeds/umwelt.rss",
        "a15": "http://www.bundestag.de/rss_feeds/verkehr.rss",
        "a14": "http://www.bundestag.de/rss_feeds/verteidigung.rss",
        "a09": "http://www.bundestag.de/rss_feeds/wirtschaft.rss",
        "a19": "http://www.bundestag.de/rss_feeds/entwicklung.rss",
        "eig": "http://www.bundestag.de/rss_feeds/internetenquete.rss"
    }

KEY_NAMES = {
        "aufgabe": "task",
        "iD": "id",
        "austrittsdatum": "exit_date",
        "zuname": "lastname",
        "vorname": "firstname",
        "adelstitel": "nobility",
        "akademischerTitel": "degree",
        "ortszusatz": "consituency",
        "geburtsdatum": "birthday",
        "religionKonfession": "religion",
        "schulOderBerufsabschluss": "qualification",
        "hochschulbildung": "higher_education",
        "beruf": "profession",
        "geschlecht": "sex",
        "familienstand": "martial_status",
        "anzahlKinder": "children",
        "fraktion": "group",
        "partei": "party",
        "land": "state",
        "wahlkreis": "constituency",
        "wahlkreisNummer": "number",
        "wahlkreisName": "name",
        "wahlkreisURL": "url",
        "gewaehlt": "elected",
        "bioURL": "bio_url",
        "biografischeInformationen": "bio", 
        "wissenswertes": "trivia", 
        "homepageURL": "homepage",
        "sonstigeWebsites": "websites", 
        "telefon": "tel",
        "mitgliedschaften": "memberships",
        "veroeffentlichungspflichtigeAngaben": "additional_income",
        "medien": "media",
        "fotoURL": "foto_url",
        "fotoCopyright": "foto_copyright",
        "redenVorPlenumURL": "plenary_speeches_url",
        "redenVorPlenumRSS": "plenary_speeches_rss"
    }

def elem_to_dict(elem):
    out = dict(elem.attrib.items())
    tag = elem.tag
    if tag.startswith('mdb'):
        tag = tag[3:]
        tag = tag[:1].lower() + tag[1:]
    if tag.startswith('ausschuss'):
        tag = tag[9:]
        tag = tag[:1].lower() + tag[1:]
    tag = KEY_NAMES.get(tag, tag)
    out[tag] = elem.text.strip() if elem.text else None
    #print tag
    if len(elem):
        out[tag] = {}
        for child in elem: 
            out[tag].update(elem_to_dict(child))
    return out

def rename_key(d, old, new):
    if old in d: 
        d[new] = d[old]
        del d[old]

def load_mdb_index(db): 
    doc = etree.parse(MDB_INDEX_URL)
    for info_url in doc.findall("//mdbInfoXMLURL"):
        load_mdb(db, info_url.text)

def load_mdb(db, info_url):
    doc = etree.parse(info_url)
    mdb = elem_to_dict(doc.find("/mdbInfo")).get('info')
    mdb.update(elem_to_dict(doc.find("/mdbMedien")).get('media'))
    mdb['bt_id'] = mdb['key'] = mdb.get('id')
    mdb['function'] = 'MdB'
    mdb['bio'] = mdb.get('bio', '').replace('<p>&nbsp;</p>', '')
    del mdb['id']
    print " -> AKTEUR", mdb.get('key')
    q = {'key': mdb.get('key')}
    db.akteur.update(q, {'$set': mdb}, upsert=True)
    mdb = db.akteur.find_one(q)
    id = mdb.get('_id')
    ms = mdb.get('memberships', {})
    for role, details in ms.items():
        # this section needs a comment so here goes: 
        # ignore it. 
        if role == 'bundestagspraesident':
            db.akteur.update(q, {"$set": {"president": True}})
            continue
        if role == 'bundestagsvizepraesident':
            db.akteur.update(q, {"$set": {"vicepresident": True}})
            continue
        key = details.get('id')
        qg = {"key": key}
        put_gremium = lambda m: db.gremium.update(qg, m, upsert=True)
        put_gremium({"$addToSet": {"akteure": id}})
        g = db.gremium.find_one(qg)
        gid = g.get('_id')
        put_mdb = lambda m: db.akteur.update(q, m, upsert=True)
        put_mdb({"$addToSet": {"gremien": gid}})
        data = {}
        if role == 'obleuteGremien':
            put_gremium({"$addToSet": {"umpires": id}})
            put_mdb({"$addToSet": {"umpire": gid}})
            data = details.get('obleuteGremium')
        if role == 'vorsitzGremien':
            put_gremium({"$set": {"chair": id}})
            put_gremium({"$addToSet": {"members": id}})
            put_mdb({"$addToSet": {"chair": gid}})
            data = details.get('vorsitzGremium')
            data['status'] = 'committee'
        if role == 'stellvertretenderVorsitzGremien':
            put_gremium({"$set": {"deputy_chair": id}})
            put_gremium({"$addToSet": {"members": id}})
            put_mdb({"$addToSet": {"stellvVorsitz": gid}})
            data = details.get('stellvertretenderVorsitzGremium')
            data['status'] = 'committee'
        if role == 'vorsitzSonstigeGremien':
            put_gremium({"$set": {"chair": id}})
            put_gremium({"$addToSet": {"members": id}})
            put_mdb({"$addToSet": {"chair": gid}})
            data = details.get('vorsitzSonstigesGremium')
            data['status'] = 'other'
        if role == 'stellvVorsitzSonstigeGremien':
            put_gremium({"$set": {"deputy_chair": id}})
            put_gremium({"$addToSet": {"members": id}})
            put_mdb({"$addToSet": {"deputy_chair": gid}})
            data = details.get('stellvVorsitzSonstigesGremium')
            data['status'] = 'other'
        if role == 'ordentlichesMitgliedGremien':
            put_gremium({"$addToSet": {"mitglieder": id}})
            put_mdb({"$addToSet": {"mitglied": gid}})
            data = details.get('ordentlichesMitgliedGremium')
            data['status'] = 'committee'
        if role == 'stellvertretendesMitgliedGremien':
            put_gremium({"$addToSet": {"deputies": id}})
            put_mdb({"$addToSet": {"deputy": gid}})
            data = details.get('stellvertretendesMitgliedGremium')
            data['status'] = 'committee'
        if role == 'ordentlichesMitgliedSonstigeGremien':
            put_gremium({"$addToSet": {"members": id}})
            put_mdb({"$addToSet": {"member": gid}})
            data = details.get('ordentlichesMitgliedSonstigesGremium')
            data['status'] = 'other'
        if role == 'stellvertretendesMitgliedSonstigeGremien':
            put_gremium({"$addToSet": {"deputies": id}})
            put_mdb({"$addToSet": {"deputy": gid}})
            data = details.get('stellvertretendesMitgliedSonstigesGremium')
            data['status'] = 'other'
        data['name'] = data['gremiumName']
        del data['gremiumName']
        data['url'] = data['gremiumURL']
        del data['gremiumURL']
        put_gremium({"$set": data})
    db.actor.update(q, {"$unset": {"memberships": 1}})
    #pprint(db.akteur.find_one(q))



def load_ausschuss_index(db):
    doc = etree.parse(AUSSCHUSS_INDEX_URL)
    for info_url in doc.findall("//ausschussDetailXML"):
        load_ausschuss(db, info_url.text)

def load_ausschuss(db, info_url):
    doc = etree.parse(info_url)
    ausschuss = elem_to_dict(doc.find(".")).get('detail')
    rename_key(ausschuss, 'id', 'key')
    if 'newslist' in ausschuss:
        del ausschuss['newslist']
    print " -> committee", ausschuss.get('key')
    ausschuss['rssURL'] = RSS_FEEDS.get(ausschuss.get('key'))
    q = {'key': ausschuss.get('key')}
    db.committee.update(q, {'$set': ausschuss}, upsert=True)
    committee_id = db.committee.find_one(q).get('_id')
    #for url in doc.findall("//news/detailsXML"):
    #    print url.text
    #    if url.text:
    #        load_news_item(db, url.text, committee_id=committee_id)

def load_news_item(db, url, committee_id=None):
    q = {"sourceURL": url}
    if db.news.find_one(q):
        if committee_id:
            db.news.update(q, {"$addToSet": {"committee": committee_id}})
        return
    doc = etree.parse(url)
    news = elem_to_dict(doc.find(".")).get("newsdetails")
    news['sourceURL'] = url
    db.news.update(q, {"$set": news}, upsert=True)
    prev = news.get('dokumentInfo', {}).get('previous')
    if 'dokumentInfo' in news:
        del news['dokumentInfo']
    if committee_id:
        db.news.update(q, {"$addToSet": {"committee": committee_id}})
    pprint(news)
    if prev is not None:
        load_news_item(db, prev)

def load_news_index(db):
    doc = etree.parse(AKTUELL_URL)
    for info_url in doc.findall("//detailsXML"):
        if not info_url.text or 'impressum' in info_url.text:
            continue
        load_news_item(db, info_url.text)





if __name__ == '__main__':
    db = connect_db()
    #load_news_index(db)
    load_ausschuss_index(db)
    load_mdb_index(db)
