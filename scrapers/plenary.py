#!/usr/bin/env python3

from db import db
from utils.log import log
from utils.utils import fetch, junws, unws, jdump, getpdf
from utils.process import process
from config import CURRENT_TERM

import pamendment
from amendment import locstarts, types

from lxml.etree import tostring

base='https://www.europarl.europa.eu'

def crawl():
   dossiers = db.dossiers_by_activity()
   #print(len(dossiers))
   for dossier in dossiers:
       scrape(dossier)

def html_full(root):
   res={'amendments': [], 'text': []}
   for node in root.xpath('//div[@class="red:section_MainContent"]//h2[@id="_section1"]/following-sibling::*'):
      if node.get('id') == "_section2": break
      #print(junws(node))
      res['text'].append(junws(node))

   deletes = root.xpath("//div[@class='red:section_MainContent']//*[contains(text(),'▌')]")
   if not deletes: return res
   # todo handle inline amendments
   print("handle inline diffs")
   return res

def skip_empty_lines(node):
   node=node.getnext()
   while node is not None:
      tmp = junws(node)
      if tmp != '':
         return node
      node=node.getnext()

def html_ams(amendment_titles):
   res={'amendments': [], 'text': []}
   for amendment_title in amendment_titles:
      number = ''.join(amendment_title.xpath('./following-sibling::span/text()'))
      am={'seqno': number}
      line = amendment_title.getparent()
      line = skip_empty_lines(line)

      tmp = junws(line)
      if tmp not in types:
         log(2,f"amendment {number} not of expected draft/proposal type: {tostring(line)}")
         continue
      line=line.getnext()

      tmp = junws(line)
      if tmp.split()[0] not in locstarts:
         log(2,f"invalid amendment {number} location: {tostring(line)}")
         continue
      am['location']=tmp
      line = skip_empty_lines(line)

      # EP personal does a lot of stupid stuff
      # we complain about it and then ignore the shit out of it...
      while line.tag != 'div':
         if junws(line) != '':
            log(2,f"amendment {number} table expected, instead: {junws(line)}")
            log(2,f"location was {repr(am['location'])}")
         line = line.getnext()

      if line.get('class') != "table-responsive":
         log(2,f"amendment {number} table expected, instead: {tostring(line)}")
         continue

      #parse table
      rows = line.xpath('./table/tr')
      tmp = junws(rows[0]) 
      if tmp != '':
         log(2, f"first row of amendment table has unexpected content: {repr(tmp)}")
         #continue
      col1, col2 = rows[1].xpath('./td')
      tmp = junws(col1)
      if tmp != 'Text proposed by the Commission':
         log(2, f'heading of first column has unexpected content: {repr(tmp)}')
      tmp = junws(col2)
      if tmp != 'Amendment':
         log(2, f'heading of second column has unexpected content: {repr(tmp)}')

      old = []
      new = []

      for row in rows[2:]:
         col1, col2 = row.xpath('./td')
         old.append(junws(col1))
         new.append(junws(col2))

      if [x for x in old if x]: am['old']=old
      if [x for x in new if x]: am['new']=new

      res['amendments'].append(am)

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

   res={'amendments': [], 'text': []}
   if len(amendment_titles)>0 and len(tables)>0:
      res = html_ams(amendment_titles)
   elif len(amendment_titles)==0 and len(tables)==0:
      res = html_full(root)
   else:
      log(1, f"inconistent am titles and tables in {url}")
      return

   for pdf_url in root.xpath('//div[@id="amdData"]//a[@aria-label="pdf"]/@href'):
     print(base+pdf_url)
     # todo pass also dossier id
     res['amendments'].append(pamendment.scrape(base+pdf_url, dossier))


   # todo link up amendments with text...

   #from IPython import embed; embed()
   print(jdump(res))

   return(res)

if __name__ == '__main__':
   # whole doc - inline amendments
   #scrape(db.dossier('2022/0272(COD)'))
   # pure amendments
   scrape(db.dossier('2021/0106(COD)'))

   # pamendment test-cases
   #scrape(db.dossier('2022/2048(INI)'))
   #scrape(db.dossier('2021/0201(COD)'))
   #scrape(db.dossier('2022/0272(COD)'))
   #scrape(db.dossier('2021/0106(COD)'))
   #scrape(db.dossier('2022/0118(COD)'))
   #scrape(db.dossier('2020/0036(COD)'))

