#!/usr/bin/env python3

from db import db
from utils.log import log
from utils.utils import fetch, junws, unws, jdump, getpdf
from utils.process import process
from config import CURRENT_TERM

import pammendment

from lxml.etree import tostring

base='https://www.europarl.europa.eu'

def crawl():
   dossiers = db.dossiers_by_activity()
   #print(len(dossiers))
   for dossier in dossiers:
       scrape(dossier)

def scrape(dossier):
    url = None
    for ev in dossier.get('events',[]):
        if ev.get('type') != 'Committee report tabled for plenary': continue
        if len(ev.get('docs',[])) > 1:
            log(1,f"too many tabled reports in plenary {len(ev.get('docs',[]))} {dossier['procedure']['reference']}")
            raise ValueError(f"{dossier['procedure']['reference']} has multiple reports tabled")
        url = ev['docs'][0]['url']
        break
    if url is None: return
    #print(url)
    res={'ammendments': [], 'text': []}
    root = fetch(url) 
    for pdf_url in root.xpath('//div[@id="amdData"]//a[@aria-label="pdf"]/@href'):
        #print(base+pdf_url)
        # todo pass also dossier id
        res['ammendments'].append(pammends.scrape(base+pdf_url))

    for node in  root.xpath('//h2[@id="_section1"]/following-sibling::*'):
        if node.get('id') == "_section2": break
        #print(junws(node))
        res['text'].append(junws(node))
    #from IPython import embed; embed()
    print(jdump(res))

    # todo link up amendments with text...

    return(res)

if __name__ == '__main__':
    scrape(db.dossier('2022/2048(INI)'))
