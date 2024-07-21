#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

# (C) 2024 by Stefan Marsiske, <parltrack@parltrack.eu>


import os, re, sys, unicodedata
from itertools import permutations
from tempfile import mkstemp
from sh import pdftotext
from dateutil.parser import parse
from utils.utils import fetch_raw, unws, jdump
from utils.log import log
from db import db
from scrapers.amendment import isfooter, parse_block, strip, splitNames, getraw
from utils.mappings import COMMITTEE_MAP
from tempfile import NamedTemporaryFile
import pdfplumber

pere = re.compile(r'(?P<PE>PE(?:TXTNRPE)? ?[0-9]{3,4}\.?[0-9]{3}(?:v[0-9]{2}(?:[-./][0-9]{1,2})?)?)(?: })?')


def strip(block):
    while len(block) and not unws(block[0]):
        del block[0]
    while len(block) and not unws(block[-1]):
        del block[-1]

refre=re.compile(r'(.*)([0-9]{4}/[0-9]{4}[A-Z]?\((?:ACI|APP|AVC|BUD|CNS|COD|COS|DCE|DEA|DEC|IMM|INI|INL|INS|NLE|REG|RPS|RSO|RSP|SYN)\))')
amstart=re.compile(r'\s*(:?Emendamenti|Amende?ment)\s*([0-9A-Z]+(:?/rev1?)?)\s*$')

dossier1stline_re = re.compile(r'(.*)\s*((?:[AB]|RC-B)[6789]-\d{4}/\d{4})$')
def parse_dossier(lines, date):
   m1 = dossier1stline_re.match(lines[0])
   if not m1:
      log(1, f"dossier block line 0 has no '(RC-)?[AB][6789]-' postfix. {repr(lines[0])}")
      return
   dossier = {
      'type' : unws(m1.group(1)),
      'aref' : m1.group(2)
      }
   if len(lines)<2:
      log(3,f"parse_dossier only got 1 line in block to parse: {repr(lines[0])}")
      return dossier

   for text in filter(None,splitNames(lines[1])):
       mepid=db.getMep(text,date)
       if mepid:
           try: dossier['meps'].append(mepid)
           except KeyError: dossier['meps']=[mepid]
       else:
           log(3, "fix %s" % text)

   mr = refre.search(unws(' '.join(lines[2:])))
   if not mr:
      log(3, "could not find dossier reference in rest of dossier block")
      return dossier
   ref=mr.group(2)
   d = db.dossier(ref)
   if not d:
       if ref.endswith('INL)'):
           d = db.dossier(ref[:-2]+"I)")
           if not d:
               log(2, f"could not find dossier for ref '{ref}'")
               return dossier
   dossier['dossier']=ref
   return dossier

amsre=re.compile(r'^Amendments?\s*([0-9]{1,})(?:\s?-\s?(\d{1,}))?\s*$', re.I)
dividerre=re.compile(r'^\s*[__]*\s*$')
def parse_cover(lines, reference, dossier, aref):
   #print('asdf', '\n'.join(lines))
   rapporteurs_tmp = []
   for r in [r
             for c in dossier.get('committees',[]) if c['type'] in {'Responsible Committee', 'Joint Responsible Committee'}
             for r in c.get('rapporteur',[])]:

      rapporteur=[]
      rapporteur.append(r['name']+r"\s*\(?"+r['group']+r"\)?")
      rapporteur.append(r['name']+r"\s*\(?"+r['abbr'] +r"\)?")
      name = db.mep(r['mepref'])['Name']
      rapporteur.append(name['sur']+r'\s*'+name['family']+r"\s*\(?"+r['abbr'] +r"\)?")
      rapporteur.append(name['sur']+r'\s*'+name['family']+r"\s*\(?"+r['group']+r"\)?")
      rapporteur.append(name['sur']+r'\s*'+name['family'])
      rapporteur.append(r['name'])
      rapporteurs_tmp.append(rapporteur)
   #print('asdf','|'.join([r'(?:'+', '.join(p)+r')' for r in zip(*rapporteurs_tmp) for p in permutations(r)]))
   rapporteurs = re.compile('|'.join([r'(?:'+', '.join(p)+r')' for r in zip(*rapporteurs_tmp) for p in permutations(r)]),re.I)

   comid = set([d['title']
                for e in dossier.get('events',[])
                if e['type']=='Legislative proposal published'
                for d in e.get('docs',[])
                if d['title'].startswith('COM(')])
   if len(comid)==1:
      ids = re.compile(r'\(?'+list(comid)[0].replace('(','\\(').replace(')','\\)')
                       + r'\W{1,}C\d[--]\d{4}/20\d{2}\W{1,}'
                       + reference.replace('(','\\(').replace(')','\\)')
                       +r'\)?')
   else:
      if len(comid) > 2:
         log(2,f"{reference} has more than one COM(*) doc in leg prop published event entry")
      ids = re.compile(r'\(?'
                       + reference.replace('(','\\(').replace(')','\\)')
                       +r'\)?')
   res = {}
   # delete rapporteur, dossier title, aref, dossier ref from block
   # extract amendment number/range
   i=0
   while i < len(lines):
      # remove stuff
      lines[i]=dividerre.sub('', lines[i])
      lines[i]=ids.sub('',lines[i])
      lines[i]=lines[i].replace(reference, '')
      lines[i]=rapporteurs.sub('',lines[i],re.I)
      lines[i]=lines[i].replace(aref, '')
      lines[i]=lines[i].replace(dossier['procedure']['title'],'')
      if unws(lines[i]) in {'Report',
                            'Proposal for a regulation'}:
         lines[i]=''
      # extract and remove stuff
      if lines[i].startswith('by the Committee'):
         for k in COMMITTEE_MAP.keys():
            if lines[i][7:].startswith(k):
               if len(k)!=4:
                  res['committee']=COMMITTEE_MAP[k]
               else:
                  res['committee']=k
               lines[i].replace("by the "+k,'')
               break
         lines[i]=''
      m = amsre.match(lines[i])
      if m:
         #if m.group(2):
         #   res['amendments']={'start': int(m.group(1)),
         #                      'end': int(m.group(2))}
         #else:
         #   res['amendments']=int(m.group(1))
         lines[i]=''

      i+=1
   strip(lines)
   if(lines):
      log(4, "leftover after cover extraction\n\t|"+'\n\t|'.join(lines))
   return res

fuxups = {
   "https://www.europarl.europa.eu/doceo/document/A-8-2019-0115-AM-001-154_EN.pdf": [
      ('  Amendment             50Proposal for a regulation',
       ['  Amendment             50',
        '',
        '  Proposal for a regulation']),
      ('  Amendment             37Proposal for a regulation',
       ['  Amendment             37',
        '',
        '  Proposal for a regulation'])
   ],
   "https://www.europarl.europa.eu/doceo/document/A-9-2021-0016-AM-001-305_EN.pdf": [
      ('        https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02009R1224-',
       ['       (https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02009R1224-']),

      ('        https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02009R1224-',
       ['       (https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02009R1224-']),
      ('                                                 20190814&qid=1582016726712',
       ['                                                20190814&qid=1582016726712)']),
      # same as prev, happens twice
      ('        https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02009R1224-',
       ['       (https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02009R1224-']),
      ('                                                 20190814&qid=1582016726712',
       ['                                                20190814&qid=1582016726712)']),
   ],
   "https://www.europarl.europa.eu/doceo/document/A-8-2019-0190-AM-001-488_EN.pdf": [
      # these are all the same, but not centered but left-justified
      # and the last line is very short as can be seen.
      ('Commission’s proposal.)',
       ['                                                    Commission’s proposal.)'
       ]),

      ('the Commission’s proposal.)',
       ['                                               the Commission’s proposal.)'
       ]),

      ('Commission’s proposal.)',
       ['                                                  Commission’s proposal.)'
       ]),

      ('Commission’s proposal.)',
       ['                                                  Commission’s proposal.)'
       ]),

      ('Commission’s proposal.)',
       ['                                                  Commission’s proposal.)'
       ]),

      ('Commission’s proposal.)',
       ['                                                  Commission’s proposal.)'
       ]),

      ('in the column ‘Comment’.)',
       ['                                                  in the column ‘Comment’.)'
       ]),
      ],

   "https://www.europarl.europa.eu/doceo/document/A-9-2020-0101-AM-001-122_EN.pdf": [
      ('         https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32013R1306',
       ['       (https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32013R1306)'])],
   }
def fixup(url, lines):
  for old, new in fuxups.get(url, []):
     idx = lines.index(old)
     #print(f"fixing up in location {idx}")
     #print('\t|', '\n\t|'.join(lines[idx-40:idx+1]))
     del lines[idx]
     for p in reversed(new):
        lines.insert(idx, p)
  return lines

blisted = {'https://www.europarl.europa.eu/doceo/document/A-9-2023-0033-AM-001-001_EN.pdf'}
def scrape(url, dossier, aref=None, save = False):
   res=[]
   if url in blisted:
      log(3,f"skipping blacklisted {url}")
      return res
   if aref is None:
      aref = url_to_aref(url)
   reference = dossier['procedure']['reference']
   try:
       lines, PE, date, pagewidth, margin = getraw(url)
   except:
       log(1, f'failed to fetch and convert {url}')
       raise
   if pagewidth>200:
      log(1,f"pagewidth is {pagewidth} > 200")
   if pagewidth >= 245:
      log(3, f"since pagewidth is {pagewidth} >= 245 we are clobbering it to 199 and margin to 24")
      margin = 24
      pagewidth = 199
   if PE is None:
      PE = aref
   #print(PE, date, aref)
   #print('\n'.join(lines[:30]))
   lines = fixup(url, lines)
   tmp = '\n'.join(lines)
   #print(tmp)
   #log(3,f"page width is {pagewidth}")
   if 'new or amended text is highlighted in bold' in tmp or '▌' in tmp:
      log(1, f"inline diff format for {reference} / {aref} in {url}")
      # todo return one item
      return res
   block=[]
   prolog = True
   committee = []
   meps = None
   meta = None
   if date is not None:
      if date == '78.3.2023': date = '8.3.2023'
      date = parse(date, dayfirst=True)

   for line in lines:
      if amstart.match(line):
         if prolog:
            meta = parse_cover(block, reference, dossier, aref)
            prolog = False
            block=[line]
            continue

         am=parse_block(block, url, reference, date, meps, PE, pagewidth=pagewidth, parse_dossier=parse_dossier, top_of_diff=1, margin=margin)
         if am is not None:
            if meta: am.update(meta)
            if save:
               process(am, am['id'], db.amendment, 'ep_amendments', am['reference']+' '+am['id'], nodiff=True)
            res.append(am)
         block=[line]
         continue
      if block is not None: block.append(line)

   if block and filter(None,block):
      am=parse_block(block, url, reference, date, meps, PE, pagewidth=pagewidth, parse_dossier=parse_dossier, top_of_diff=1, margin=margin)
      if am is not None:
         if meta: am.update(meta)
         if save:
            process(am, am['id'], db.amendment, 'ep_amendments', am['reference']+' '+am['id'], nodiff=True)
         res.append(am)
   log(3,"total amendments %d in %s" % (len(res),url))
   return res

def url_to_aref(url):
   fname = url.split('/')[-1]
   if fname.startswith('RC-'):
       #fname = fname[:14]
       return f'RC-B{fname[3]}-{fname[10:14]}/{fname[5:9]}'
   return f'{fname[0]}{fname[2]}-{fname[9:13]}/{fname[4:8]}'

def dossier_from_url(url):
   # url ~ https://www.europarl.europa.eu/doceo/document/A-9-2022-0292-AM-001-001_EN.pdf
   #  or ~ https://www.europarl.europa.eu/doceo/document/A-9-2023-0233_EN.html
   aref = url_to_aref(url)
   return aref, db.get("dossiers_by_doc", aref)[0]

if __name__ == '__main__':
   aref, dossier = dossier_from_url(sys.argv[1])
   ams = scrape	(sys.argv[1],dossier, aref)
   print(jdump(ams))
   print(len(ams))
   for am in ams:
      if 'location' not in am:
         print(f"am {am['seq']} has no location")
