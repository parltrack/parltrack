#!/usr/bin/env python3

from db import db
from utils.log import log
from utils.utils import fetch, junws, unws, jdump, getpdf
from utils.process import process
from config import CURRENT_TERM

from scrapers import pamendment
from scrapers.amendment import locstarts, types

import re
from itertools import zip_longest
from lxml.etree import tostring

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'abort_on_error': True,
    'table': 'ep_plenary_amendments',
}

base='https://www.europarl.europa.eu'

AM_RE = re.compile('Am (\d+(?:[sS=, ]{1,2}\d+)*)')
#AM_RE = re.compile('Am ([sS=, ])*')
DATE_RE = re.compile(' \d{2}/\d{2}/\d{4}.+')
SEP_RE = re.compile('[sS=, ]+')

CVOTE_TITLES = {
    'opinion': "FINAL VOTE BY ROLL CALL IN COMMITTEE ASKED FOR OPINION",
    'responsible': "FINAL VOTE BY ROLL CALL IN COMMITTEE RESPONSIBLE",
}


def html_full(root):
   res={'amendments': [], 'text': []}
   for node in root.xpath('//div[@class="red:section_MainContent"]//h2[@id="_section1"]/following-sibling::*'):
      if node.get('id') == "_section2": break
      #print(junws(node))
      res['text'].append(junws(node))

   deletes = root.xpath("//div[@class='red:section_MainContent']//*[contains(text(),'▌')]")
   if not deletes: return res
   # todo handle inline amendments
   #print("todo handle inline diffs")
   return res

def skip_empty_lines(node):
   node=node.getnext()
   while node is not None:
      tmp = junws(node)
      if tmp != '':
         return node
      node=node.getnext()


def parse_sequential(line, end):
   line=line.getnext()
   old = []
   new = []
   justification = []

   while line is not None and junws(line)!="Amendment" and line!=end:
      old.append(junws(line))
      line=line.getnext()

   if junws(line)=="Amendment":
      line=line.getnext()

      while line is not None and junws(line)!="Justification" and line!=end:
         new.append(junws(line))
         line=line.getnext()

   if junws(line)=="Justification":
      line=line.getnext()

      if line is None or (end is not None and line==end):
         return old, new, []

      while line is not None and (end is None or line!=end):
         justification.append(junws(line))
         line=line.getnext()

   return old, new, justification

blist = { ('https://www.europarl.europa.eu/doceo/document/A-9-2023-0048_EN.html', '145'),
          #('', ''),
         }
def html_ams(amendment_titles, url):
   res=[]
   for n, amendment_title in enumerate(amendment_titles):
      number = unws(''.join(amendment_title.xpath('./following-sibling::span/text()')))
      if (url, number) in blist:
         log(2, f"skipping am {number} in {url} due to it being blacklisted")
         res.append({'seq': number})
         continue
      am={'seq': number}
      line = amendment_title.getparent()
      line = skip_empty_lines(line)

      tmp = junws(line)
      # compromise section, see am 5 in https://www.europarl.europa.eu/doceo/document/A-9-2023-0364_EN.html
      if tmp.startswith("Compromise "):
         am['compromise'] = tmp[11:]
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
      am['location']=[tmp]
      line = skip_empty_lines(line)

      end = None
      if n+1 < len(amendment_titles):
         end = amendment_titles[n+1].getparent()

      # EP personal does a lot of stupid stuff
      # we complain about it and then ignore the shit out of it...
      bail = False
      while line.tag != 'div':
         if junws(line) != '':
            if junws(line) == "Text proposed by the Commission":
               old, new, justification = parse_sequential(line, end)
               if old: am['old']=old
               if new: am['new']=new
               if justification: am['justification']=justification
               res.append(am)
               bail = True
               break
            #log(4,f"amendment {number} table expected, instead: {junws(line)}")
            #log(4,f"adding to location, location was {repr(am['location'])}")
            am['location'].append(junws(line))
         line = line.getnext()
      if bail == True:
         continue

      if line.get('class') != "table-responsive":
         log(2,f"amendment {number} table expected, instead: {tostring(line)}")
         continue

      #parse table
      rows = line.xpath('./table/tr')
      if len(rows)<3:
         log(2, f"amendment {number} table has less than 3 rows {url}")
         res.append(am)
         continue

      tmp = junws(rows[0])
      if tmp == '':
         del rows[0]
      #else:
      #   log(3, f"first row of amendment table has unexpected content: {repr(tmp)}")
      tmp = rows[0].xpath('./td')
      if len(tmp) != 2:
         log(2,f"found row with other than two columns {len(tmp)}, in am {number} {url}")
         res.append(am)
         continue
      col1, col2 = tmp

      tmp = junws(col1)
      if tmp not in {'Text proposed by the Commission', 'Present text'}:
         log(2, f'am {number} heading of first column has unexpected content: {repr(tmp)}')
      tmp = junws(col2)
      if tmp not in {'Amendment', 'Unchanged text included in the compromise'}:
         log(2, f'am {number} heading of second column has unexpected content: {repr(tmp)}')

      old = []
      new = []

      bail = False
      for row in rows[1:]:
         tmp = row.xpath('./td')
         if len(tmp) != 2:
            log(2,f"found row with other than two columns {len(tmp)}, in am {number} {url}")
            res.append(am)
            bail = True
            break
         col1, col2 = tmp
         old.append(junws(col1))
         new.append(junws(col2))

      if bail:
         continue

      if [x for x in old if x]: am['old']=old
      if [x for x in new if x]: am['new']=new

      # TODO/FIXME conflates (comments) and justifications
      line = line.getnext()
      justification = []
      while line is not None and (end is None or line!=end):
         justification.append(junws(line))
         line=line.getnext()
      justification = '\n'.join([x for x in justification if x])
      if justification:
         am['justification']=justification

      res.append(am)

   return res

import unicodedata
import diff_match_patch as dmp_module
dmp = dmp_module.diff_match_patch()
# todo move normalize to utils
delchars = ''.join(c for c in map(chr, range(128)) if not c.isalnum())
del_map = str.maketrans('', '', delchars)
def normalize(txt):
    return unicodedata.normalize('NFKD', txt).encode('ascii','ignore').decode('utf8').translate(del_map).lower()
def difftxt(t1, t2):
    res = []
    d = dmp.diff_main(t1,t2)
    dmp.diff_cleanupSemantic(d)
    for op, data in d or []:
        if op == dmp.DIFF_INSERT:
            if data == ' ':
               res.append(' ')
               continue
            res.append(f"\033[48;5;40m{data}\033[0m")
        elif op == dmp.DIFF_DELETE:
            if data == ' ':
               res.append(' ')
               continue
            res.append(f"\033[48;5;197m{data}\033[0m")
        elif op == dmp.DIFF_EQUAL:
            res.append(f"{data}")
    return ''.join(res)


def parse_votes(root, aref, resp_committee, url, save=True, test=False):
    for vtype, vtitle in CVOTE_TITLES.items():
        anchor_xp = f'//div[@class="red:section_MainContent_Second"]//span[text()="{vtitle}"]//ancestor::div[@class="red:section_MainContent_Second"]'
        nodes = root.xpath(anchor_xp)
        for a in nodes:
            if vtype == 'opinion':
                try:
                    metadata = a.xpath('./preceding-sibling::div[@class="red:section_MainContent_Second"]//table')[-1]
                except:
                    log(1,f"failed to parse opinion vote for {url}")
                    continue
                try:
                    committee = metadata.xpath('.//td//*[contains(text(), "Opinion by")]//ancestor::tr/td[last()]//text()')[0]
                except:
                    try:
                        metadata = a.xpath(f'.//span[text()="{vtitle}"]/ancestor::p/preceding-sibling::div[@class="table-responsive"]//table')[-1]
                    except:
                        log(1,f"failed to parse opinion vote for {url}")
                        continue
                    committee = metadata.xpath('.//td//*[contains(text(), "Opinion by")]//ancestor::tr/td[last()]//text()')[0]
            else:
                committee = resp_committee
            vtables = a.xpath(f'.//span[text()="{vtitle}"]/../following-sibling::div[@class="table-responsive"]//table')
            payload = {
                'committee': committee,
                'vote_tables': vtables,
                'aref': aref,
                'save': save,
                'test': test,
                'vote_type': vtype,
            }
            if test:
                from scrapers.comvote import scrape as cscrape
                cscrape(**payload)
            else:
                add_job('comvote', payload=payload)


def scrape(url, dossier, save=True, test=False, **kwargs):
   #url, dossier, _ = ref_to_url(ref)
   dossier = db.dossier(dossier)
   if url is None: return
   log(3, f"scraping plenary: {url}")
   root = fetch(url)
   aref = pamendment.url_to_aref(url)
   try:
      resp_committee = [x['committee'] for x in dossier['committees'] if x['type'] == 'Responsible Committee'][0]
      parse_votes(root, aref, resp_committee, url, save=save, test=test)
   except Exception as e:
      log(1, f"failed to parse votes for {url} - {e}")
   votes = db.get('votes_by_dossier', dossier['procedure']['reference'])

   amendment_titles = root.xpath('//div[@class="red:section_MainContent"]//p[@class="text-center"]/span[text()="Amendment"]')
   tables = root.xpath('//div[@class="red:section_MainContent"]//div[@class="table-responsive"]/table/tr/td/p/span[text()="Text proposed by the Commission" or text()="Present text"]')

   ams = []
   res={'amendments': [], 'text': []}
   if len(amendment_titles)>0 and len(tables)>0:
      ams = html_ams(amendment_titles, url)
   elif len(amendment_titles)==0 and len(tables)==0:
      res = html_full(root)
   else:
      log(1, f"inconistent am titles and tables in {url}")
      return

   pdf_ams=[]
   for pdf_url in root.xpath('//div[@id="amdData"]//a[@aria-label="pdf"]/@href'):
     log(3,f"scraping plenary am pdf: {base+pdf_url}")
     pdf_ams.extend(pamendment.scrape(base+pdf_url, dossier))

   # merge pdf and html ams
   for h, p in zip_longest(ams, pdf_ams):
     if (h is not None and p is not None):
        try:
           tmp = int(h['seq'])
        except ValueError:
           tmp = None
        if tmp:
           if tmp != p['seq']:
              log(1, f"seq mismatch {h['seq']} != {p['seq']}, aborting "
                     f"{max(len(ams),len(pdf_ams))-len(res['amendments'])} unprocessed amendments in {url}")
              return res
           h['seq']=tmp
        else:
           log(2, f"seq is not an int {h['seq']}")

     if p is not None:
        am = p
        am['src_type']='pdf'
     elif h is not None:
        am = h
        am['src_type']='html'
        am['reference']=dossier['procedure']['reference']
     else:
        log(1,f'both pdf and html am are None, aborting processing'
              f"{max(len(ams),len(pdf_ams))-len(res['amendments'])} unprocessed amendments in {url}")
        return res
     am['adoc_src']=url

     if (h is not None and p is not None):
        # sanity-check if html==pdf am
        for t in ('old', 'new'):
          a = ''.join(h.get(t,[]))
          b = ''.join(p.get(t,[]))
          if normalize(a) != normalize(b):
             if 'inconsistent' not in am: am['inconsistent']=[]
             am['inconsistent'].append((t, difftxt(a,b)))
             if test:
                print(t, h['seq'], '\n', difftxt(a,b))
                print('html\n',jdump(h))
                print('pdf\n',jdump(p))

     if 'inconsistent' in am:
       am['html']=h
       del am['html']['seq']

     vids = am_ref_to_vote_id(votes, aref, am['seq'])
     if vids:
        am['vote_ids'] = vids
     res['amendments'].append(am)
   if save:
       for a in res['amendments']:
          aid = f"{aref}-{str(a['seq'])}"
          a['id'] = aid
          process(
              a,
              aid,
              db.plenary_amendment,
              'ep_plenary_amendments',
              aid,
              nodiff=True,
          )

   # todo link up amendments with text...

   return res

def ref_to_url(ref):
   dossier = db.dossier(ref)
   url = None
   date = None
   for ev in dossier.get('events',[]):
      if ev.get('type') not in {'Committee report tabled for plenary',
                                'Committee report tabled for plenary, 1st reading'}: continue
      if len(ev.get('docs',[])) > 1:
         log(1,f"too many tabled reports in plenary {len(ev.get('docs',[]))} {ref}")
         raise ValueError(f"{dossier['procedure']['reference']} has multiple reports tabled")
      if 'docs' not in ev:
          log(2, f"{ref} has no doc in {ev}")
          continue
      url = ev['docs'][0].get('url')
      if url is None:
          log(2,f"no url in {ref} {ev}")
          continue
      date = ev['date']
      break
   return url, {k:v for k,v in dossier.items() if k in {'procedure','committees', 'events'}}, date


def am_ref_to_vote_id(votes, aref, seq):
    if isinstance(seq, int):
        seq = str(seq)
    ret = []
    for vote in votes or []:
        if aref not in vote['title']:
            continue
        title = DATE_RE.sub('', vote['title'])
        am_res = AM_RE.search(title)
        if not am_res:
            continue
        ams = SEP_RE.split(am_res.group(1))
        if seq in ams:
            ret.append(vote['voteid'])
    return ret


from utils.process import publish_logs
def onfinished(daisy=True):
    publish_logs(get_all_jobs)


if __name__ == '__main__':
   import sys
   if len(sys.argv)==2:
      print(jdump(scrape(sys.argv[1], pamendment.dossier_from_url(sys.argv[1])[1]['procedure']['reference'], save=False, test=True)))
   # whole doc - inline amendments
   #scrape(*ref_to_url('2022/0272(COD)')[:2])
   # pure amendments
   #scrape(*ref_to_url('2021/0106(COD)')[:2])
   #scrape(*ref_to_url('2022/0118(COD)')[:2])
   #scrape(*ref_to_url('2022/0094(COD)')[:2])
   #scrape(*ref_to_url('2022/0118(COD)')[:2])

   # pamendment test-cases
   #scrape(*ref_to_url('2022/2048(INI)')[:2])
   #scrape(*ref_to_url('2021/0201(COD)')[:2])
   #scrape(*ref_to_url('2022/0272(COD)')[:2])
   #scrape(*ref_to_url('2021/0106(COD)')[:2])
   #scrape(*ref_to_url('2022/0118(COD)')[:2])
   #scrape(*ref_to_url('2020/0036(COD)')[:2])

