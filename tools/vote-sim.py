#!/usr/bin/env python

from datetime import datetime, timedelta
import itertools
#from numpy import dot
#from numpy.linalg import norm
from scipy import spatial

def prepare(interval):
  print("[1] creating indexes by date and mep")
  parties_by_date_and_mep={}
  countries_by_date_and_mep={}
  for m in DBS['ep_meps'].values():
    for c in m.get('Constituencies',[]):
      if not c or c['end'] < interval[0] or c['start'] > interval[1]: continue
      if c['end'] != '9999-12-31T00:00:00':
        end=datetime.fromisoformat(c['end']).date()
      else:
        end=datetime.now().date()
      delta = timedelta(days=1)
      cur = datetime.fromisoformat(c['start']).date()
      while cur <= end:
        if 'party' in c:
          parties_by_date_and_mep[(cur,m['UserID'])]=c['party']
        countries_by_date_and_mep[(cur,m['UserID'])]=c['country']
        cur += delta

  parties = {}
  countries = {}
  tc_cache = {}
  tp_cache = {}
  print("[2] aggregating party and country votes")
  for v in DBS['ep_votes'].values():
    if v['ts'] < interval[0] or v['ts'] > interval[1]: continue
    ts = datetime.fromisoformat(v['ts']).date()
    pv = {}
    cv = {}
    for k, t in v.get('votes',{}).items():
      if k not in '-+': continue
      for g in t['groups'].values():
        for mv in g:
          party = parties_by_date_and_mep.get((ts,mv['mepid']))
          if not party:
            print(f"no party for {mv['mepid']} at {ts}")
            continue
          if party not in pv:
            pv[party]={'+': [], '-': []}
          country = countries_by_date_and_mep.get((ts,mv['mepid']))
          if not country:
            print(f"no country for {mv['mepid']} at {ts}")
            continue
          if country not in cv:
            cv[country]={'+': [], '-': []}
          pv[party][k].append(mv['mepid'])
          cv[country][k].append(mv['mepid'])

    for c in cv.keys():
      if c not in countries:
        countries[c]={}
      if (c,ts) not in tc_cache:
        tc = len(set([m1 for (d1,m1), v1 in countries_by_date_and_mep.items() if v1==c and d1 == ts]))
        tc_cache[(c,ts)] = tc
      else:
        tc = tc_cache[(c,ts)]
      countries[c][v['voteid']]={'t': (len(cv[c]['+']) - len(cv[c]['-'])) / tc, 'tc': tc, 'votes': cv[c] }

    for p in pv.keys():
      if p not in parties:
        parties[p]={}
      if (p,ts) not in tp_cache:
        tp = len(set([m1 for (d1,m1), v1 in parties_by_date_and_mep.items() if v1==p and d1 == ts]))
        tp_cache[(p,ts)]=tp
      else:
        tp=tp_cache[(p,ts)]
      parties[p][v['voteid']]={'t': (len(pv[p]['+']) - len(pv[p]['-'])) / tp, 'tp': tp, 'votes': pv[p] }

  return parties, countries

def compare(parties, countries):
  print("[3] pairwise comparison")
  psims={}
  for p1, p2 in itertools.combinations(parties.keys(),2):
    pv1 = set(parties[p1].keys())
    pv2 = set(parties[p2].keys())
    commonvotes = sorted(pv1 & pv2, key=str)
    v1 = [parties[p1][voteid]['t'] for voteid in commonvotes]
    v2 = [parties[p2][voteid]['t'] for voteid in commonvotes]
    psims[tuple(sorted([p1,p2]))] = {'sim': 1 - float(spatial.distance.cosine(v1, v2)), 'cv': commonvotes, p1: parties[p1], p2: parties[p2]}

  csims={}
  for c1, c2 in itertools.combinations(countries.keys(),2):
    cv1 = set(countries[c1].keys())
    cv2 = set(countries[c2].keys())
    commonvotes = sorted(cv1 & cv2, key=str)
    v1 = [countries[c1][voteid]['t'] for voteid in commonvotes]
    v2 = [countries[c2][voteid]['t'] for voteid in commonvotes]
    csims[tuple(sorted([c1,c2]))] = {'sim': 1 - float(spatial.distance.cosine(v1, v2)), 'cv': commonvotes, c1: countries[c1], c2: countries[c2]}
  return psims, csims

now = datetime.now()
p,c = prepare(('2019-07-02T00:00:00','9999-12-31T00:00:00'))
print("running time", datetime.now() - now)
now = datetime.now()
psims, csims = compare(p,c)
print("running time", datetime.now() - now)

with open('country-vote-similarity.tsv','w') as fd:
  for score, votes, (c1, c2) in list(sorted([(v['sim'], len(v['cv']), k) for k,v in csims.items()])): fd.write(f"{score}\t{votes}\t{c1}\t{c2}\n")

with open('party-vote-similarity.tsv','w') as fd:
  for score, votes, (p1, p2) in list(sorted([(v['sim'], len(v['cv']), k) for k,v in psims.items() if len(v['cv'])>0])): fd.write(f"{score}\t{votes}\t{p1}\t{p2}\n")
