#!/usr/bin/python3

from db import db
from utils.utils import fetch, jdump, junws, unws
from utils.log import log
from utils.process import process
from utils.process import publish_logs
from datetime import datetime

from datetime import datetime
from lxml.html import tostring

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
    if type not in {"+","-","0"}:
        log(1, "vote header type is unexpected value %s in %s" % (repr(type), url))
        raise ValueError
    res = { 'total' : int(junws(tds[0])),
            'type' : type,
            'meps': []}
    for tr in trs[1:]:
        tds = tr.xpath('.//td')
        if len(tds)<2:
            log(1, "vote table has less than two columns in the body: %s %s" % (url, tostring(tr)))
            raise ValueError
        #grp = junws(tds[0]).split()
        for meps in tds[1].xpath(".//p"):
            meps = junws(meps)
            if not meps: continue
            for m in meps.split(','):
                m = unws(m)
                if not m: continue
                mepid = db.getMep(m, date=date)
                if not mepid:
                    log(2, "could not resolve MEP name: %s" % m)
                res['meps'].append(mepid or m)
    return res

def extract_proc(table, url):
    res = {}
    if len(table)<1:
        log(1, "could not find procedure table in %s", url)
        raise ValueError
    for tr in table[0].xpath('.//tr'):
        tds = tr.xpath('.//td')
        title = junws(tds[0])
        val = junws(tds[1])
        if not title or not val: continue
        res[title] = val
    return res

def scrape(url):
    log(4, "scraping %s" % url)
    root = fetch(url)
    res = {'responsible': [],
            'opinions': []}
    for opinion in root.xpath('//p/span[contains(text(),"FINAL VOTE BY ROLL CALL IN COMMITTEE ASKED FOR OPINION")]'):
        procedure = opinion.xpath('../../p/span[contains(text(),"PROCEDURE – COMMITTEE ASKED FOR OPINION")]')
        if len(procedure)!=1:
            log(1, "found %s procedures for opinion in %s" % (len(procedure),url))
            raise ValueError
        proc_table = procedure[0].xpath('../following-sibling::p/table')
        proc = extract_proc(proc_table , url)
        date = datetime.strptime(proc['Date adopted'], "%d.%m.%Y")
        cmte = proc['Opinion by Date announced in plenary'].split()[0]
        res_op = {
                'proc': proc,
                'date': date,
                'committee': cmte,
                'votes': {}
                }
        res['opinions'].append(res_op)
        for table in opinion.xpath('../following-sibling::p/table'):
            if table==proc_table[0]: continue
            vote = extract_table(table, url, date)
            res_op['votes'][vote['type']]=vote
            del(vote['type'])
    responsible = root.xpath('//tr[@class="doc_title"]//span[contains(text(),"FINAL VOTE BY ROLL CALL IN COMMITTEE RESPONSIBLE")]')
    if len(responsible)!=1:
        log(1, "number of responsible rc votes is not 1: %s" % url)
        raise ValueError
    responsible=responsible[0]
    proc = root.xpath('//tr[@class="doc_title"]//span[contains(text(),"PROCEDURE – COMMITTEE RESPONSIBLE")]')
    if len(proc)!=1:
        log(1, "could not find exactly one procedure for the responsible committee in %s" % url)
        raise ValueError
    proc = extract_proc(proc[0].xpath('../../following-sibling::tr/td/p/table'), url)
    cmte = proc['Committee responsible Date announced in plenary'].split()[0]
    date = datetime.strptime(proc['Date adopted'], "%d.%m.%Y")
    res_resp = {
            'proc': proc,
            'date': date,
            'committee': cmte,
            'votes': {},
            }
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
    print(jdump(scrape(url)))
