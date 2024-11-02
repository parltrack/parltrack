#!/usr/bin/env python

import sys, re
from datetime import datetime
from db import db
from utils.log import log, set_level
from utils.utils import jdump
from config import CURRENT_TERM
from scrapers import plenary

set_level(3)

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 1,
    'error_handler': None,
}

docre=re.compile(r'(?:[AB]|RC-B)[3456789]-\d{4}/ ?\d{1,4}')
def motions(ref):
   dossier = db.dossier(ref)
   if dossier is None: return []
   url = None
   date = None
   res = []
   for doc in dossier.get('docs',[]):
      if doc.get('type') not in {'Motion for a resolution',
                                 'Joint motion for resolution'
                                 }: continue
      if 'docs' not in doc:
          log(3, f"{ref} has no doc in {doc}")
          continue
      for d in doc['docs']:
          if not docre.match(d['title']):
              continue
          url = d.get('url')
          if url is None:
              log(2,f"no url in {ref} {doc}")
              continue
          date = doc['date']
          res.append((url, {k:v for k,v in dossier.items() if k in {'procedure','committees', 'events'}}, date))
   return res


def scrape(years=None, test=False, save=True, **kwargs):
   if years is None:
      years = [str(datetime.now().year)]
   res = []
   for ref in db.keys('ep_dossiers'):
       tmp = plenary.ref_to_url(ref)
       l=[tmp] if tmp is not None else []
       l.extend(motions(ref))
       for tmp in l:
           url, dossier, date  = tmp
           if url is None: continue
           if isinstance(date,str):
                if date[:4] not in years: continue
           elif isinstance(date,datetime.datetime):
               if date.year not in years: continue
           else: continue
           log(3,f"adding job {url}")
           if test:
              try:
                  res.append(plenary.scrape(url, dossier['procedure']['reference'], test=test, save=save))
              except:
                  print(jdump(res))
                  raise
           else:
              add_job('plenary', payload={'url': url, 'dossier': dossier['procedure']['reference'], 'test': test, 'save': save})

   if test:
      print(jdump(res))

if __name__ == '__main__':
    if len(sys.argv)==1:
        scrape([str(datetime.now().year)])
    elif sys.argv[1] == 'all':
        scrape([str(d) for d in range(2019,datetime.now().year+1)], save=True, test=True)
    else:
        scrape({sys.argv[1]}, save=False, test=True)
