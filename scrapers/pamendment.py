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
from scrapers.amendment import isfooter, parse_block, strip
from utils.mappings import COMMITTEE_MAP

pere = re.compile(r'(?P<PE>PE(?:TXTNRPE)? ?[0-9]{3,4}\.?[0-9]{3}(?:v[0-9]{2}(?:[-./][0-9]{1,2})?)?)')

headerre=re.compile(r'\s*(?P<date>\d{1,2}\.\d{1,2}\.\d{4})\s*(?P<Aref>A[789]-\d{4}/ ?\d{1,4})')
def isheader(line):
   return headerre.match(line)

def unpaginate(text, url):
    #print(text)
    lines = [l.rstrip('\n\t ') for l in text.split('\n')]
    ## find end of 1st page
    #eo1p = 0
    PE = None
    date = None
    aref = []
    #while not lines[eo1p].startswith('\x0c') and eo1p<len(lines):
    #    eo1p+=1
    #if eo1p == len(lines):
    #    log(1, "could not find end of 1st page in %s" % url)
    #    raise ValueError("eo1p not found: %s" % url)

    i = len(lines)
    while i>=0:
       if i != len(lines):
          if not lines[i].startswith('\x0c'):
             i -= 1
             continue

       # we found a line starting with pagebreak
       if i != len(lines):
          lines[i]=lines[i][1:]
       i -= 1
       fstart = i

       if i != len(lines) - 1:
          header = isheader(lines[fstart+1])
          if header:
             date1 = header.group("date")
             if date:
                if date1 != date:
                   log(1, f"date found, but is not consistent: {date} != {date1}")
             else:
                date = date1
             aref1 = header.group('Aref')
             if aref1:
                aref.append(aref1)
             del lines[fstart+1]

       # skip empty lines before pagebreak
       while i>=0 and unws(lines[i])=='':
           i-=1

       # we expect i>0 and lines[i] == 'EN' (or variations)
       if i<=0:
           log(1, "could not find non-empty line above pagebreak in %s" % url)
           raise ValueError("no EN marker found: %s" % url)

       tmp = unws(lines[i])
       if tmp not in ["EN", "EN EN", "EN United in diversity EN",
                      "United in diversity",
                      "EN Unity in diversity EN",
                      "EN Unie dans la diversité EN",
                      "EN In Vielfalt geeint EN",
                      "ENEN United in diversity EN",
                      "XM United in diversity XM",
                      "XT United in diversity EN",
                      "XM", "XM XM", "XT", "XT XT"]:
           if tmp in ["FR",'NL','HU']:
               log(2,'Document has non-english language marker: "%s" %s' % (tmp, url))
               return [], None
           if tmp=="Or. en":
               # no footer in this page
               continue
           if tmp in ['AM_Com_NonLegCompr', 'AM_Com_NonLegReport','AM_Com_NonLegOpinion']:
               # no footer on this page (and probably neither on the previous one which should be the first)
               continue
           log(2, 'could not find EN marker above pagebreak: %d/%d "%s"' % (i, len(lines), tmp))
           #raise ValueError('no EN marker found "%s" in %s' % (tmp,url))
       else:
          i-=1
          if tmp == "United in diversity" and unws(lines[i]) in {'EN', 'EN EN'}:
             i-=1

       # find the next non-empty line above the EN marker
       while i>0 and unws(lines[i])=='':
           i-=1
       if i<=0:
           log(1, "could not find non-empty line above EN marker: %s" % url)
           raise ValueError("no next line above EN marker found: %s" % url)

       if i<len(lines) and lines[i].startswith('\x0c'): # we found a ^LEN^L
           # we found an empty page.
           while fstart > i:
               del lines[fstart]
               fstart -= 1
           #lines[i]="\x0c"

       footer = isfooter(lines[i])
       if footer:
          if PE is None:
             m = pere.search(unws(lines[i]))
             if m: PE = m.group(0)
          if lines[i].startswith('\x0c'):
             lines[i]="\x0c"
             continue
          i-=1

       while i>0 and unws(lines[i])=='':
           i-=1
       if i<=0:
           log(1, "could not find non-empty line above footer: %s" % url)
           raise ValueError("no content found above footer: %s" % url)

       # delete all lines between fstart and i
       while fstart > i:
           del lines[fstart]
           fstart -= 1

    while unws(lines[0]) == '':
       del lines[0]
    header = isheader(lines[0])
    if header:
       date1 = header.group("date")
       if date:
          if date1 != date:
             log(1, f"date found, but is not consistent: {date} != {date1}")
       else:
          date = date1
       aref1 = header.group('Aref')
       if aref:
          aref.append(aref1)
       del lines[0]

    # clear left margin
    margin = 1
    while margin<max(len(l) for l in lines):
       if set([' '*margin])     != set([(l[1:margin+1] if l[0]=='\f' else l[:margin]) for l in lines if unws(l)]):
          margin = margin - 1
          break
       margin+=1
    lines = [l[margin:] if not l.startswith('\f') else '\f' + l[margin+1:] for l in lines]

    return lines, PE, date, aref, margin

from tempfile import NamedTemporaryFile
import pdfplumber
def getraw(url):
   try:
      pdf_doc = fetch_raw(url, binary=True)
   except:
      log(1, f'Failed to download pdf from {url}')
      return
   doc = []
   with NamedTemporaryFile() as tmp:
      tmp.write(pdf_doc)
      with pdfplumber.open(tmp.name) as pdf:
         for page in pdf.pages:
            lines = page.extract_text(layout=True, x_density=3, y_density=13.8, y_tolerance=6.9, keep_blank_chars=True).split('\n')
            # strip leading empty lines on a page
            while unws(lines[0]) == '':
               del[lines[0]]
            # strip trailing empty lines on a page
            i=len(lines)-1
            while unws(lines[i])=='':
               del lines[i]
               i-=1
            doc.append('\n'.join(lines))
   return unpaginate('\n\f'.join(doc), url)

refre=re.compile(r'(.*)([0-9]{4}/[0-9]{4}[A-Z]?\((?:ACI|APP|AVC|BUD|CNS|COD|COS|DCE|DEA|DEC|IMM|INI|INL|INS|NLE|REG|RPS|RSO|RSP|SYN)\))')
amstart=re.compile(r'\s*(:?Emendamenti|Amende?ment)\s*([0-9A-Z]+(:?/rev1?)?)\s*$')

dossier1stline_re = re.compile(r'(.*)\s*(A[6789]-\d{4}/\d{4})$')
def parse_dossier(lines, date):
   m1 = dossier1stline_re.match(lines[0])
   if not m1:
      log(1, f"dossier block line 0 has no 'A[6789]-' postfix. {repr(lines[0])}")
      return
   dossier = {
      'type' : unws(m1.group(1)),
      'aref' : m1.group(2)
      }
   if len(lines)<2:
      log(2,f"parse_dossier only got 1 line in block to parse: {repr(lines)}")
      return dossier
   mepid=db.getMep(unws(lines[1]),date)
   if mepid:
      try: dossier['meps'].append(mepid)
      except KeyError: dossier['meps']=[mepid]

   mr = refre.search(unws(' '.join(lines[2:])))
   if not mr:
      log(3, "could not find dossier reference in rest of dossier block")
      return dossier
   ref=mr.group(2)
   d = db.dossier(ref)
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
             for c in dossier['committees'] if c['type'] in {'Responsible Committee', 'Joint Responsible Committee'}
             for r in c['rapporteur']]:
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
                for e in dossier['events']
                if e['type']=='Legislative proposal published'
                for d in e['docs']
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
         if m.group(2):
            res['amendments']={'start': int(m.group(1)),
                               'end': int(m.group(2))}
         else:
            res['amendments']=int(m.group(1))
         lines[i]=''

      i+=1
   strip(lines)
   if(lines):
      log(4, "leftover after cover extraction\n\t|"+'\n\t|'.join(lines))
   return res

blisted = {'https://www.europarl.europa.eu/doceo/document/A-9-2023-0033-AM-001-001_EN.pdf'}
def scrape(url, dossier, aref=None, save = False):
   res=[]
   if url in blisted:
      log(3,f"skipping blacklisted {url}")
      return res
   if aref is None:
      aref = url_to_aref(url)
   reference = dossier['procedure']['reference']
   lines, PE, date, _, margin = getraw(url)
   #print(PE, date, aref)
   #print('\n'.join(lines[:30]))
   tmp = '\n'.join(lines)
   #print(tmp)
   pagewidth = max(len(line) for line in lines) + margin
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
   fname = url.split('/')[-1][:13]
   return f'A{fname[2]}-{fname[9:13]}/{fname[4:8]}'

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
