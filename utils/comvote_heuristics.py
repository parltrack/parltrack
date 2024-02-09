#!/usr/bin/env python

import json, os, re, datetime, unicodedata
from urllib.parse import unquote
from utils.utils import unws, jdump
from utils.log import set_level
from db import db

set_level(3)

daymonth=r'(?P<day>\d{1,2})\s+(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)|Nov(?:ember)?|Dec(?:ember)?)'

dedatere4y = re.compile(r'(?P<match>(?P<day>\d{2})[-./](?P<month>\d{2})[-./](?P<year>20\d{2}))(?:\D|$)')
dedatere2y = re.compile(r'(?P<match>(?P<day>\d{2})[-./](?P<month>\d{2})[-./](?P<year>\d{2}))(?:\D|$)')
endatere4y = re.compile(r'(?P<match>(?P<year>20[12]\d)[-./](?P<month>\d{2})[-./](?P<day>\d{2}))')
endatere2y = re.compile(r'(?P<match>(?P<year>[12]\d)[-./](?P<month>\d{2})[-./](?P<day>\d{2}))')
fulldatere = re.compile(r'(?P<match>'+daymonth+r'\s+(?P<year>20\d{2})'+r')(?:\D|$)', re.I)
noyearre = re.compile(r'(?P<match>'+daymonth+r')', re.I)
yearre = re.compile(r'\D(?P<year>20[12]\d)(?:\D|$)')

monthmap = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}

def find_date(txt, year_c=None):
    txt = unicodedata.normalize('NFKD', txt).encode('ascii','ignore').decode('utf8')
    for (exp, conf) in [(fulldatere, 10), (noyearre, 5), (endatere4y, 8), (dedatere4y, 8), (dedatere2y, 5), (endatere2y, 5)]:
        if exp == noyearre and not year_c: continue
        m = exp.search(txt)
        if m:
            day = int(m.group('day'))
            month = monthmap.get(m.group('month').lower()[:3]) or int(m.group('month'))
            if exp == noyearre:
                year = year_c
            else:
                year = int(m.group('year'))
            if year > 2000: year -= 2000
            if (year < 12 or
                year > datetime.datetime.now().year or
                day < 1 or
                day > 31 or
                month < 1 or
                month > 12):
                continue
            return (conf, datetime.datetime(2000+year, month, day, 0, 0), m.group('match'))

def update_s(dates, match, type):
   if match:
      date = dates.get(match[1], {'conf': 0,
                                  'matches': {}})
      date['conf']+=match[0]
      date['matches'][type]=match[2]
      dates[match[1]]=date
   return dates

def extract_dates(doc, com_dates, debug=True):
   dates = {}
   year = None
   date_t=find_date(doc['title'], year)
   dates = update_s(dates,date_t, 'title')
   if not date_t:
      y = yearre.search(doc['title'])
      if y:
          year = int(y.group('year'))
   date_lt=find_date(doc["link_text"], year)
   dates = update_s(dates,date_lt, 'link_text')
   date_u=find_date(doc["url_fname"], year)
   dates = update_s(dates,date_u, 'url_fname')
   if "subtitle" in doc:
      date_s=find_date(doc["subtitle"], year)
      dates = update_s(dates,date_s, 'subtitle')

   i = 0
   if debug:
       frags = []
   for frag in doc['pdfdata']:
       if isinstance(frag, dict) or isinstance(frag, list): continue
       date_f=find_date(frag, year)
       dates = update_s(dates,date_f, f'frag {i}')
       if debug and date_f:
          frag = ' '.join([l for l in frag.split('\n') if date_f[2] in l])
          frags.append(f'frag {i}\t{date_f}\t{frag}')
       i+=1

   # sanity check dates
   dominators = set()
   for date, meta in dates.items():
       for field in ['title','link_text', 'url_fname']:
           if field in meta['matches'].keys():
               dominators.add(date)

   if dominators:
      refdate = list(sorted(dominators))[0]
      for dominator in list(sorted(dominators))[1:]:
          keys = list(dates.keys())
          for date in keys:
              if (dominator - date) > datetime.timedelta(days=1) or (date - dominator) > datetime.timedelta(days=1):
                 if date in dominators:
                    if date != dominator:
                       print(f"conflicting dominators: {dominator.isoformat()[:10]} vs {date.isoformat()[:10]} is {abs((date-dominator).days)} apart")
                 else:
                     print(f"dominated date to far: {dominator.isoformat()[:10]} vs {date.isoformat()[:10]} is {abs((date-dominator).days)} apart")
                     print(f"deleting date: {date}: {dates[date]}")
                     del dates[date]

      keys = list(dates.keys())
      for date in keys:
          if date.isoformat()[:10] not in com_dates.keys():
              print(f"{date} is not on a day when there was a meeting for {doc['committee']}")
              del dates[date]

   if debug:
      if year:
         print("year", year)
      else:
         print("no year")
      print('lt\t', date_lt, doc["link_text"])
      print('url\t', date_u, doc["url_fname"], doc["url"])
      if "subtitle" in doc:
         print('st\t', date_s, doc["subtitle"])
      for frag in frags:
          print(frag)

   return dates

#delchars = ''.join(c for c in map(chr, range(1114111)) if not c.isalnum())
delchars = ''.join(c for c in map(chr, range(128)) if not c.isalnum())
del_map = str.maketrans('', '', delchars)
def normalize(txt):
    return unicodedata.normalize('NFKD', txt).encode('ascii','ignore').decode('utf8').translate(del_map).lower()

def match_titles(com, dates, frag, label, com_dates):
   #print("title matching", unws(frag))
   #if normalize('European Semester for economic policy coordination') in normalize(frag):
   #    print("asdf", doc['committee'])
   #    print(normalize(frag))
   for d in dates.keys():
      d = d.isoformat()[:10]
      #print('date', d)
      for item in com_dates.get(d, []):
         #print("check", item['item']['title'])
         #if normalize('European Semester for economic policy coordination') in normalize(frag):
         #print("asdf")
         #print(normalize(item['item']['title']))
         #print(frag)
         if normalize(item['item']['title']) in frag:
             #print('dossierT', item['docref'], label, ' '.join([l for l in frag.split('\n') if item['item']['title'] in l]))
             return item['docref'], item['item']['title'], item
   return None

def update_dossiers(dossiers, match, type):
   if match:
      dossier = dossiers.get(match[1], {'conf':0, 'matches': {}})

      dossier['conf']+=match[0]
      dossier['matches'][type]=match[2]
      if len(match)==4:
          dates=dossier.get('dates',[])
          dates.append(match[3])
          dossier['dates']=dates
      dossiers[match[1]]=dossier
   return dossiers

types = {normalize('Vote on the decision to enter into interinstitutional negotiations'),
		 normalize('Decision to enter into interinstitutional negotiations'),
		 normalize('Vote on the provisional agreement resulting from interinstitutional negotiations'),
		 normalize('Vote on the recommendation for an early non-objection'),
		 normalize('Final vote on the resolution'),
		 normalize('Final vote on Motion for a Resolution'),
		 normalize('Vote on Mandate'),
		 normalize('Mandate to negotiate'),
		 normalize('Vote on the text as amended'),
		 normalize('FINAL VOTE BY ROLL CALL IN COMMITTEE ASKED FOR OPINION'),
		 normalize('FINAL VOTE BY ROLL CALL IN COMMITTEE RESPONSIBLE')}
def txt_extract(dossiers, dates, txt, label, com, com_dates, debug = True):
   txt = unws(txt)
   for legend in ['Key: + : in favour - : against 0 : abstentions',
                  'Key to symbols: + : in favour - : against 0 : abstention',
                  'Key to symbols: + (in favour), - (against), 0 (abstention)',
                  'Key to symbols: + : refuses discharge - : grants discharge 0 : abstention',
                  ]:
       txt = txt.replace(legend, '')
   for date, meta in dates.items():
      if label in meta['matches']:
         txt = txt.replace(meta['matches'][label], '')
   if len(unws(txt)) < 13: return

   found=False
   while ''.join(txt.split()):
      m = refre.search(txt)
      if not m:
          break
      found=True
      dossiers = update_dossiers(dossiers,
                                 (10,
                                  m.group(1).replace(' ',''),
                                  ' '.join([l for l in txt.split('\n') if m.group(1).replace(' ','') in l.replace(' ', '')])),
                                 label)
      txt=txt.replace(m.group(1),'')

   frag = normalize(txt)
   while ''.join(txt.split()):
      m = match_titles(com, dates, frag, label, com_dates)
      if not m:
         if not found and frag not in types and debug:
             print("not matched", com, f"{label:<14}", unws(txt))
         break
      found=True
      dossiers = update_dossiers(dossiers, (11, m[0], m[1], m[2]['item'].get('start', m[2]['meeting']['time']['date'])), label)
      frag=frag.replace(normalize(m[1]), '')

refre=re.compile(r'([0-9]{4}/[0-9]{4}[A-Z]? ?\((?:ACI|APP|AVC|BUD|CNS|COD|COS|DCE|DEA|DEC|IMM|INI|INL|INS|NLE|REG|RPS|RSO|RSP|SYN)\))')
def doc_extract(doc, com_dates, dates=None, debug=True):
   votes=0
   unknown=0
   dossiers = {}
   if dates is None: dates = {}

   for field in ['title', 'link_text', 'subtitle', 'url_fname']:
       if field not in  doc: continue
       txt_extract(dossiers, dates, doc[field], field, doc['committee'], com_dates, False)

   i = 0
   for frag in doc['pdfdata']:
      if isinstance(frag, dict):
         votes+=1
         continue
      if isinstance(frag, list):
          unknown+=1
          continue
      txt_extract(dossiers, dates, frag, f"frag {i}", doc['committee'], com_dates)
      i+=1
   return dossiers, votes, unknown

def extract_dossiers(frag, fragno, committee, com_dates, dates=None):
    ret = {}
    txt_extract(ret, dates, frag, f"frag {fragno}", committee, com_dates)
    return ret

def extract_dossiers_from_metadata(doc, com_dates, dates=None, debug=True):
    dossiers = {}
    if dates is None: dates = {}

    for field in ['title', 'link_text', 'subtitle', 'url_fname']:
        if field not in doc:
            continue
        txt_extract(dossiers, dates, doc[field], field, doc['committee'], com_dates, False)
    return dossiers

def process(debug):
   docs = {}
   for fname in os.listdir():
      if not fname.endswith('.json'): continue
      with open(fname,'r') as fd:
         doc=json.load(fd)
         l = sum(1 for f in doc["pdfdata"] if isinstance(f, list))
         d = sum(1 for f in doc["pdfdata"] if isinstance(f, dict))
         if l>0 and d==0: continue # doc has no recognized votes
         docs[fname]=doc

   total_dates=0
   total_dossiers=0
   perfects=0
   partials=0
   lost = 0
   unexpecteds = 0
   for fname, doc in docs.items():
      doc['url_fname']=unquote(doc["url"]).split('/')[-1]
      com_dates = db.committee_votes_by_date(doc['committee'])
      dates = extract_dates(doc, com_dates, debug)
      for date, meta in dates.items():
          print(f"{date.strftime('%Y-%m-%d')}\tconf: {meta['conf']},\tmatches: {meta['matches']}")
          total_dates+=1
      if not dates:
          print(f"no date for {fname}")
          print('t', doc['title'])
          print('l', doc["link_text"])
          print('u', doc["url"])
          print(doc['url'])

      dossiers, votes, unknown = doc_extract(doc, com_dates, dates)
      for dossier, meta in dossiers.items():
          print(f"{dossier}\tconf: {meta['conf']},\tmatches: {meta['matches']}")
          total_dossiers+=1

      expected = {item['docref'] for d in dates.keys() for item in com_dates.get(d.isoformat()[:10], [])}
      missing = expected - set(dossiers.keys())
      if missing == set():
          perfects+=1
      elif votes == len(dossiers) and unknown==0:
          partials+=1
      else:
          print("expected not found", ', '.join(sorted(missing)))
          lost+=1

      extras = set(dossiers.keys()) - expected
      if extras:
          print("found unexpected", ', '.join(sorted(extras)))
          unexpecteds+=1

      if not dossiers:
          print(f"no dossiers for {fname}")
          print(doc['url'])
      print()
   print(f"total dates: {total_dates}, total dossiers: {total_dossiers}, perfects: {perfects}, partials: {partials}, missing: {lost}, unexpecteds {unexpecteds}")

if __name__ == "__main__":
    process(False)
    #print(jdump(load_com('AFET')))
