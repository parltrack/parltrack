import urllib 
from lxml import html
from pprint import pprint
from parltrack.environment import connect_db

RESOLVER = "http://www.bundestag.de/cgibin/wkreis2009neu.pl"

def load_wahlkreise(db):
    for i in xrange(10000, 100000):
        q = urllib.urlencode([("PLZ", str(i)), ("ORT", "")])
        urlfh = urllib.urlopen(RESOLVER, q)
        doc = html.parse(urlfh)
        urlfh.close()
        result = doc.find('//tr[@class="alternativ"]')
        if result is None: 
            continue
        plz_e, ort_e, wk_e = result.findall("td")
        plz = plz_e.xpath("string()").strip()
        ort = ort_e.xpath("string()").strip()
        wk_url = wk_e.find("a").get('href')
        wk_name = wk_e.find(".//strong").text
        wk_id = wk_url.rsplit("=",1)[-1]
        actore = db.actor.find({"constituency_data.number": wk_id})
        actore = [a.get('_id') for a in actore]
        db.wahlkreis.update({"key": wk_id}, {
            "$set": {
                "title": wk_name,
                "actors": actors,
                "url": wk_url},
            "$addToSet": {
                "cities": ort,
                "postal": plz}
            }, upsert=True)

if __name__ == '__main__':
    db = connect_db()
    load_wahlkreise(db)

