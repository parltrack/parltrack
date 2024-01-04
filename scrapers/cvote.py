#!/usr/bin/python3

from db import db
from utils.utils import fetch, jdump, junws, unws
from utils.log import log
from utils.process import process
from utils.process import publish_logs

from datetime import datetime
from lxml.html import tostring
import re

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'abort_on_error': True,
    'table': 'ep_com_votes',
}

def extract_table(table, url, date=None):
    trs = table.xpath('.//tr')
    header = trs[0]
    tds = header.xpath('.//td')
    if len(tds)<2:
        log(1, "vote table has less than two columns in the header: %s %s" % (url, tostring(trs[0])))
        raise ValueError
    type = junws(tds[1])
    if type=='–': type='-'
    if type not in {"+","-","0","Corrections to vote", "Corrections to votes", 'Corrections to final vote and voting intentions'}:
        if url in ['http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2017-0072&language=EN',
                   'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2017-0009&language=EN']:
            type='CORRECTIONS TO VOTES AND VOTING INTENTIONS'
        elif url in ['http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0115&language=EN',
                     'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0064&language=EN',
                     ]:
            return # the "procedure committee responsible" table is a direct sibling of the vote result tables. :/
        else:
            log(1, "vote header type is unexpected value %s in %s" % (repr(type), url))
            raise ValueError
    try:
        total = int(junws(tds[0]).replace(' ', '')) if len(type)==1 else -1
    except:
        if url in ['http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0353&language=EN',
                   'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2016-0336&language=EN',
                   'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2016-0333&language=EN',
                   'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2017-0246&language=EN',
                   'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0313&language=EN',
                   'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2017-0406&language=EN',
                   'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2016-0335&language=EN']:
            total = 0
        elif url == 'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0444&language=EN':
            total=34
        else:
            log(1,url)
            raise
    res = { 'total' : total,
            'type' : type,
            'meps': []}
    for tr in trs[1:]:
        tds = tr.xpath('.//td')
        if len(tds)<2:
            log(1, "vote table has less than two columns in the body: %s %s" % (url, tostring(tr)))
            raise ValueError
        if type == "Corrections to vote":
            vtype=junws(tds[0])
            if not 'corrections' in res: res['corrections']={}
            res['corrections'][vtype]=[]
        for meps in tds[1].xpath(".//p"):
            meps = junws(meps)
            if not meps: continue
            for m in meps.split(','):
                m = unws(m)
                if not m: continue
                mepid = db.getMep(m, date=date)
                if not mepid:
                    log(2, "could not resolve MEP name: %s" % m)
                if type == "Corrections to vote":
                    res['corrections'][vtype].append(mepid or m)
                else:
                    res['meps'].append(mepid or m)
    if res['total']==-1 and res['type']=="Corrections to vote":
        res['total']=len(res['meps'])
    return res

def extract_proc(table, url):
    res = {}
    if len(table)<1:
        log(1, "could not find procedure table in %s" % url)
        raise ValueError
    for tr in table[0].xpath('.//tr'):
        tds = tr.xpath('.//td')
        title = junws(tds[0])
        if title in ('Title', 'References'):
            val = junws(tds[1])
        elif title in ("Committee responsible Date announced in plenary", "Committees asked for opinions Date announced in plenary", "Not delivering opinions Date of decision",
                       'Opinion by Date announced in plenary'):
            val = []
            for t in tds[1:]:
                if not junws(t): continue
                ps = t.xpath('.//p')
                if len(ps)!=2:
                    log(2, 'not 2 #p# found in "%s" "%s" %s' % (title, junws(t), url))
                    continue
                if junws(ps[1]):
                    val.append({'committee': junws(ps[0]), 'date': datetime.strptime(junws(ps[1]), "%d.%m.%Y")})
                else:
                    val.append({'committee': junws(ps[0])})
        elif title in ["Rapporteurs Date appointed", "Rapporteur Date appointed"]:
            val = []
            for t in tds[1:]:
                if not junws(t): continue
                ps = t.xpath('.//p')
                if len(ps)!=2:
                    log(2, 'not 2 #p# found in "%s" "%s" %s' % (title, junws(t), url))
                    continue
                date=datetime.strptime(junws(ps[1]), "%d.%m.%Y")
                val.append({'mep': db.getMep(junws(ps[0]), date=date), 'date': date})
        elif title == "Result of final vote":
            val = [{junws(a):junws(b) for a, b in  zip(tds[1].xpath('.//p'), tds[2].xpath('.//p'))}]
        else:
            val = [x for x in [[y for y in [junws(p) for p in t.xpath('.//p')] if y] for t in tds[1:]] if x]
        if not title or not val: continue
        res[title] = val

    for type in ["Date of consulting Parliament", "Discussed in committee", "Date tabled",'Date adopted']:
        if not type in res: continue
        res[type] = [datetime.strptime(d[0], "%d.%m.%Y") for d in res[type]]

    if not 'Date adopted' in res:
        if url == 'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0169&language=EN':
            res['Date adopted']=[datetime(2019,2,10,0,0)] # guessed
        elif url == 'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0471&language=EN':
            res['Date adopted']=[datetime(2018,11,21,0,0)] # guessed
        elif url == 'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0078&language=EN':
            res['Date adopted']=[datetime(2019,1,23,0,0)] # guessed
        elif url == 'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0163&language=EN':
            res['Date adopted']=[datetime(2018,4,24,0,0)] # guessed
        elif url == 'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0093&language=EN':
            res['Date adopted']=[datetime(2019,1,25,0,0)] # guessed
        else:
            log(2, "no Date adopted in proc for %s" % url)
            raise ValueError
    date = res['Date adopted'][0]
    for type in ["Substitutes present for the final vote", "Substitutes under Rule 200(2) present for the final vote", "Members present for the final vote"]:
        if not type in res: continue
        meps=[]
        for m in res[type][0][0].split(','):
            m = unws(m)
            if not m: continue
            mepid = db.getMep(m, date=date)
            if not mepid:
                log(2, "could not resolve MEP name: %s" % m)
            meps.append(mepid or m)
        res[type]=meps

    return res

cont = { # most of these are cont docs from 2018
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0066&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0067&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0068&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0076&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0077&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0078&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0079&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0080&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0081&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0083&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0084&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0085&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0086&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0087&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0088&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0090&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0091&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0092&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0093&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0098&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0099&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0101&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0103&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0106&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0107&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0108&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0109&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0111&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0113&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0122&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0123&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0128&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0064&language=EN',  # again cont, still 8th term though
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0098&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0107&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0109&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0110&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0116&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0118&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0119&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0120&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0121&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0122&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0123&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0124&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0125&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0127&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0128&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0130&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0131&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0133&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0134&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0135&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0136&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0137&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0138&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0139&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0141&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0143&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0145&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0150&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0153&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0154&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0155&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0158&language=EN',
          'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0163&language=EN',
          }
fucked = { 'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0170&language=EN',  # this is the final (and only report) of taxe3 it has it's own special format
          }
oheaderre=re.compile(r'opinion of the committee on (.*) \(([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4}) ?\)$', re.I)
def scrape(url,ref):
    if url in fucked: 
        log(3,"skipping damaged %s" % url)
        return
    log(4, "scraping %s" % url)
    root = fetch(url)
    res = {'dossier': ref,
           'responsible': [],
           'opinions': []}
    for opinion in root.xpath('//p/span[contains(text(),"FINAL VOTE BY ROLL CALL IN COMMITTEE ASKED FOR OPINION")]'):
        procedure = opinion.xpath('../../p/span[contains(text(),"PROCEDURE – COMMITTEE ASKED FOR OPINION") or contains(text(),"INFORMATION ON ADOPTION IN COMMITTEE ASKED FOR OPINION")]')
        if len(procedure)!=1:
            log(2, "found %s procedures for opinion in %s" % (len(procedure),url))
            continue
            raise ValueError
        proc_table = procedure[0].xpath('../following-sibling::p/table')
        proc = extract_proc(proc_table , url)
        date = proc['Date adopted'][0]
        res_op = {
                'proc': proc,
                'date': date,
                'votes': {}
                }
        if 'Opinion by Date announced in plenary' in proc:
            res_op['committee'] = [x['committee'] for x in proc['Opinion by Date announced in plenary']]
        # added to fucked instead
        #elif url == 'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2018-0099&language=EN':
        #    header = opinion.xpath('../../../../tr[@class="doc_title"]')
        #    res_op['committee']=['Committee on Civil Liberties, Justice and Home Affairs']
        else:
            header = opinion.xpath('../../../../tr[@class="doc_title"]')
            if len(header)==1:
                header = junws(header[0])
                if not header.lower().startswith("opinion of the committee on"):
                    log(2,'opinion header does not start with expected prefix: "%s" %s' % (header, url))
                    raise ValueError
                    continue
                m = oheaderre.match(header)
                if not m:
                    log(2,'opinion header does not match regex: "%s" %s' % (header, url))
                    raise ValueError
                    continue
                cmte=[m.groups(1)]
                # TODO resolve cmte and set res_op['committee']
            else:
                log(2, "opinion table has not 1 doc_title tr: %s" % url)
                continue
        res['opinions'].append(res_op)
        for table in opinion.xpath('../following-sibling::p/table'):
            if table==proc_table[0]: continue
            if table.get('class')=="inpage_annotation_doc": continue
            vote = extract_table(table, url, date)
            if vote:
                res_op['votes'][vote['type']]=vote
                del(vote['type'])
    responsible = root.xpath('//tr[@class="doc_title"]//span[contains(text(),"FINAL VOTE BY ROLL CALL IN COMMITTEE RESPONSIBLE")]')
    if len(responsible)!=1:
        log(1, "number of responsible rc votes is not 1 (is %s): %s" % (len(responsible),url))
        #raise ValueError
        return
    responsible=responsible[0]
    proc = root.xpath('//tr[@class="doc_title"]//span[contains(text(),"PROCEDURE – COMMITTEE RESPONSIBLE") or contains(text(),"INFORMATION ON ADOPTION IN COMMITTEE RESPONSIBLE")]')
    if len(proc)!=1:
        log(1, "could not find exactly one procedure for the responsible committee in %s" % url)
        #raise ValueError
        return
    t = proc[0].xpath('../../following-sibling::tr/td/p/table')
    if not t:
        if url in ['http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0115&language=EN',
                         'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0190&language=EN',
                         'http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2019-0174&language=EN']:
            t = proc[0].xpath('../../../following-sibling::p/table')
        elif url in ['http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&mode=XML&reference=A8-2016-0244&language=EN']:
            t = proc[0].xpath('../../../following-sibling::tr/td/p/table')
    proc = extract_proc(t, url)
    date = proc['Date adopted'][0]
    res_resp = {
            'proc': proc,
            'date': date,
            'votes': {},
            }
    if 'Committee responsible Date announced in plenary' in proc:
        res_resp['committee'] = [x['committee'] for x in proc['Committee responsible Date announced in plenary']]
    else:
        pass # no idea how to recover this. but it might be ok, the parent dossier has this info anyway

    res['responsible'].append(res_resp)
    for table in responsible.xpath('../../following-sibling::tr/td/p/table'):
        vote = extract_table(table, url, date)
        res_resp['votes'][vote['type']]=vote
        del(vote['type'])
    return res

def onfinished(daisy=True):
    publish_logs(get_all_jobs)

if __name__ == '__main__':
    import sys
    url = sys.argv[1]
    from utils.log import set_level
    set_level(1)
    print(jdump(scrape(url, "asdf")))
