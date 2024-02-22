#!/usr/bin/env python

import sys
from datetime import datetime
from db import db
from utils.log import log, set_level
from utils.utils import jdump
from config import CURRENT_TERM
from scrapers import plenary

set_level(3)

def scrape(years):
   res = []
   for ref in db.keys('ep_dossiers'):
       url, dossier, date  = plenary.ref_to_url(ref)
       if url is None: continue
       if date[:4] not in years: continue
       log(3,f"adding job {url}")
       try:
           res.append(plenary.scrape(url, dossier))
       except:
           print(jdump(res))
           raise
   print(jdump(res))

if __name__ == '__main__':
    if len(sys.argv)==1:
        scrape([str(datetime.now().year)])
    elif sys.argv[1] == 'all':
        scrape(str(d) for d in range(2014,CURRENT_TERM+1))
    else:
        scrape({sys.argv[1]})
