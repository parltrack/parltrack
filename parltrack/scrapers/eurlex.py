#!/usr/bin/env python
#    This file is part of parltrack.

#    parltrack is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    parltrack is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with parltrack.  If not, see <http://www.gnu.org/licenses/>.

# (C) 2012 by Stefan Marsiske, <stefan.marsiske@gmail.com>

import re, sys, time
from parltrack.utils import fetch as _fetch, unws, jdump, diff, logger
from mappings import CELEXCODES
from datetime import datetime
try:
    from parltrack.environment import connect_db
    db = connect_db()
except:
    import pymongo
    db=pymongo.Connection().parltrack

db.eurlex.ensure_index([('id.celexid', 1)])

def fetch(url, **kwargs):
    timer=8
    while True:
        root=_fetch(url, **kwargs)
        fail=root.xpath('//h1[text()="The system could not serve your request in time because of a temporary problem; please try again shortly."]')
        if not len(fail):
            timer=8
            break
        logger.info('[i] getting "pls wait" msg, sleeping for %ss' % timer)
        time.sleep(timer)
        timer=timer*2
    return root

EURLEXURL="http://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri="
GENERIC_FIELDS = [("Classifications",
                   ["Subject matter:","Directory code:","EUROVOC descriptor:","Directory code:"]),
                  ("Miscellaneous information",
                   ["Author:","Form:","Addressee:","Additional information:"]),
                  ("Procedure",
                   ["Procedure number:","Legislative history:"]),
                  ("Relationship between documents",
                   ["Treaty:",
                    "Legal basis:",
                    "Amendment to:",
                    "Amended by:",
                    "Consolidated versions:",
                    "Subsequent related instruments:",
                    "Affected by case:",
                    "Instruments cited:"])]

def scrape(celexid, path):
    logger.info("scraping %s%s:NOT" % (EURLEXURL,celexid))
    path.reverse()
    (code,lang)=celexid.split(":")[1:3]
    st=6
    if len(code)>6:
        if code[6].isalpha(): st=7
        eurlex={'id': {u'celexid': celexid,
                       u'sector': code[0],
                       u'year': code[1:5],
                       u'doctype': code[5:st],
                       u'refno': code[st:],
                       u'lang': lang,
                       u'chapter': path,
                       }}
    else:
        eurlex={'id': {u'celexid': celexid,
                       u'sector': code[0],
                       u'year': code[1:5],
                       u'doctype': code[5:6],
                       u'lang': lang,
                       u'chapter': path,
                       }}

    try:
        eurlex['id'][u'typeDesc']= CELEXCODES[code[0]]['Document Types'][code[5:st]] if code[5:st] != 'C' else CELEXCODES[code[0]]['Sector']
    except:
        eurlex['id'][u'typeDesc']= u"Unknown"
        logger.warn("[!] unknown typedesc %s" % celexid)
    eurlex['meta']={u'src': "%s%s:NOT" % (EURLEXURL,celexid)}

    root = fetch("%s%s:NOT" % (EURLEXURL,celexid))
    if len(root.xpath('//h1[text()="No documents matching criteria."]'))>0:
        logger.warn('[!] nothing to scrape here: %s', "%s%s:NOT" % (EURLEXURL,celexid))
        return
    eurlex[u'title'] = root.xpath('//h2[text()="Title and reference"]/following-sibling::p/text()')[0]
    # dates
    dates=root.xpath('//h2[text()="Dates"]/following-sibling::ul/text()')
    for y in dates:
        if not unws(y): continue
        title, rest=unws(y).split(": ",1)
        item={u'type': title}
        date=rest[:10]
        tail=rest[10:]
        if tail.startswith('; '):
            tail=tail[2:]
        if date=='99/99/9999': item[u'date']= datetime(9999,12,31)
        elif date=='00/00/0000': item[u'date']= datetime(0001,01,01)
        elif date=='//': continue
        else:
            try: item[u'date']= datetime.strptime(date, u"%d/%m/%Y")
            except ValueError:
                try: item[u'date']= datetime.strptime(date, u"%m/%d/%Y")
                except: pass
        if len(tail):
            item['note']=tail
        try:
            eurlex['dates'].append(item)
        except:
            eurlex['dates']=[item]

    for t,l in GENERIC_FIELDS:
        try:
            s=root.xpath('//h2[text()="%s"]/following-sibling::ul' % t)[0]
        except:
            continue
        if not len(s): continue
        tmp=dict([(field, [unws(x) if x.getparent().tag!='a' else {u'text': unws(x),
                                                                   u'url': x.getparent().get('href')}
                           for x in s.xpath('./li/strong[text()="%s"]/..//text()' % field)
                           if unws(x) and unws(x)!='/'][1:])
                  for field in l])

        # merge multi-text items into one dict
        for k in ['Amended by:', "Legal basis:", 'Amendment to:']:
            tmp1={}
            for v in tmp.get(k,[]):
                if type(v)==type(dict()):
                    if not v['url'] in tmp1: tmp1[v['url']]={u'url': v['url'],
                                                             u'text': [v['text']]}
                    elif not v['text'] in tmp1[v['url']]['text']:
                        tmp1[v['url']]['text'].append(v['text'])
            if tmp1:
                tmp[k]=tmp1.values()

        if len(tmp.keys()):
            eurlex[t]=tmp
    return eurlex

def save(data, stats):
    if not data: return stats
    res=db.eurlex.find_one({ 'id.celexid' : data['id']['celexid'] }) or {}
    d=diff(dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]),
           dict([(k,v) for k,v in data.items() if not k in ['_id', 'meta', 'changes',]]))
    if d:
        now=unicode(datetime.utcnow().replace(microsecond=0).isoformat())
        if not res:
            logger.info(('adding %s' % (data['id']['celexid'])).encode('utf8'))
            data['meta']['created']=now
            if stats: stats[0]+=1
        else:
            logger.info(('updating %s' % (data['id']['celexid'])).encode('utf8'))
            logger.warn(d)
            data['meta']['updated']=now
            if stats: stats[1]+=1
            data['_id']=res['_id']
        data['changes']=res.get('changes',{})
        data['changes'][now]=d
        db.eurlex.save(data)
    if stats: return stats
    else: return data

crawlroot="http://eur-lex.europa.eu/en/legis/latest"
def sources(url, path):
    root=fetch(url)
    regexpNS = "http://exslt.org/regular-expressions"
    if path: logger.info("[i] crawler: %s" % path[-1])
    for doc in root.xpath("//a[re:test(@href, 'LexUriServ[.]do[?]uri=[0-9A-Z:]*:NOT', 'i')]",
                          namespaces={'re':regexpNS}):
        yield (doc.get('href').split('uri=')[1][:-4], path)
    for c in root.xpath("//div[@id='content']//a[re:test(@href, 'chap[0-9]*.htm', 'i')]",
                        namespaces={'re':regexpNS}):
        for res in sources("%s/%s" % (crawlroot,c.get('href')),
                           path+[tuple(c.text.split(' ',1))]):
            yield res

def crawl(saver=jdump, null=False):
    for celexid, data in sources("%s/index.htm" % crawlroot, []):
        if (null and db.eurlex.find_one({'id.celexid': celexid},['_id'])==None) or not null:
            yield saver(scrape(celexid, data),[0,0])

if __name__ == "__main__":
    if len(sys.argv)<2:
        print "%s [<chapter>] [<dry>] [<null>])" % (sys.argv[0])
    if sys.argv[1]=='url' and sys.argv[2]:
        print jdump(scrape(sys.argv[2],[]))
        sys.exit(0)
    args=set(sys.argv[1:])
    saver=save
    null=False
    if 'dry' in args:
        saver=jdump
    if 'null' in args:
        null=True
    iter=crawl(saver=saver, null=null)
    if 'dry' in args:
        print "[\n%s" % iter.next()
    for res in iter:
        if 'dry' in args:
            print ",\n%s" % res.encode('utf8')
            print ".oOo." * 35
    if 'dry' in args:
        print "]"
    #pprint.pprint(scrape("CELEX:32009L0140:EN:HTML"))
    #pprint.pprint(scrape("CELEX:31994D0006:EN:HTML"))
    #pprint.pprint(scrape("CELEX:31994L0006:EN:HTML"))
    #pprint.pprint(scrape("CELEX:51994XP006:EN:HTML"))
    #pprint.pprint(scrape("CELEX:32004L0048:EN:HTML"))
