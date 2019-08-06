#!/usr/bin/env python3

import re
from datetime import datetime
from db import db
from utils.log import log
from utils.utils import fetch, unws, jdump, getpdf
from utils.process import process

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'table': 'ep_mep_activities',
    'abort_on_error': True,
}

def scrape(id, terms, mepname, **kwargs):
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
                               log(4, "fetching primary activity page %s" % item['url'])
                               try:
                                   refroot = fetch(item['url'])
                               except:
                                   refroot = None
                               if refroot is not None:
                                   if '/doceo/' in item['url']: # stupid new EP site removed the span with the procedure, bastards.
                                       fulla = refroot.xpath('//table[@class="buttondocwin"]//a/img[@src="/doceo/data/img/navi_moredetails.gif"]/..')
                                       if fulla:
                                           fullurl = fulla[0].get('href')
                                           if fullurl.endswith('.html'):
                                               if fullurl[-7:-5]!='EN':
                                                   fullurl=fullurl[:-7]+'EN.html'
                                               log(4,'loading activity full text page %s' % fullurl)
                                               refroot = fetch(fullurl)
                                       else:
                                           log(4,'no fulla for %s' % item['url'])
                                   anchor = refroot.xpath('//span[@class="contents" and text()="Procedure : " and not(ancestor::div[@style="display:none"])]')
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
    if len(activities.keys())>1:
        process(activities, id, db.activities, 'ep_mep_activities', mepname, nodiff=True)
        return activities
    return {}

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

def onfinished(daisy=True):
    from utils.process import publish_logs
    publish_logs(get_all_jobs)

if __name__ == '__main__':
    #print(jdump(scrape(1275)))
    #scrape(28390)
    #scrape(96779)
    #scrape(96674)
    #scrape(28469)
    #scrape(96843)
    #scrape(1393) # 1-3rd term
    #scrape(96992)
    #scrape(1275)
    import sys
    print(jdump(scrape(int(sys.argv[1]))))
