#!/usr/bin/env python3

from db import db
from utils.log import log
from utils.utils import fetch, junws, unws, jdump, getpdf
from utils.process import process
from config import CURRENT_TERM

import pamendment

from lxml.etree import tostring

base='https://www.europarl.europa.eu'

def crawl():
   dossiers = db.dossiers_by_activity()
   #print(len(dossiers))
   for dossier in dossiers:
       scrape(dossier)

def html_full(root):
   # todo handle inline amendments
   res={'amendments': [], 'text': []}
   for node in root.xpath('//h2[@id="_section1"]/following-sibling::*'):
      if node.get('id') == "_section2": break
      #print(junws(node))
      res['text'].append(junws(node))

   return res

def html_ams(amendment_titles):
   res={'amendments': [], 'text': []}
   for amendment_title in amendment_titles:
      number = ''.join(amendment_title.xpath('./following-sibling::span/text()'))
      print(number)
   return res

def scrape(dossier):
   url = None
   for ev in dossier.get('events',[]):
      if ev.get('type') not in {'Committee report tabled for plenary',
                                'Committee report tabled for plenary, 1st reading'}: continue
      if len(ev.get('docs',[])) > 1:
         log(1,f"too many tabled reports in plenary {len(ev.get('docs',[]))} {dossier['procedure']['reference']}")
         raise ValueError(f"{dossier['procedure']['reference']} has multiple reports tabled")
      url = ev['docs'][0]['url']
      break
   if url is None: return
   print(url)
   root = fetch(url)

   amendment_titles = root.xpath('//div[@class="red:section_MainContent"]//p[@class="text-center"]/span[text()="Amendment"]')
   tables = root.xpath('//div[@class="red:section_MainContent"]//div[@class="table-responsive"]/table/tr/td/p/span[text()="Text proposed by the Commission"]')

   if len(amendment_titles)>0 and len(tables)>0:
      res = html_ams(root)
   elif len(amendment_titles)==0 and len(tables)==0:
      res = html_full(amendment_titles)
   else:
      log(1, f"inconistent am titles and tables in {url}")
      return

   for pdf_url in root.xpath('//div[@id="amdData"]//a[@aria-label="pdf"]/@href'):
     print(base+pdf_url)
     # todo pass also dossier id
     res['amendments'].append(pamendment.scrape(base+pdf_url))


   # todo link up amendments with text...

   #from IPython import embed; embed()
   print(jdump(res))

   return(res)

if __name__ == '__main__':
    #scrape(db.dossier('2022/2048(INI)'))
    scrape(db.dossier('2021/0201(COD)'))
