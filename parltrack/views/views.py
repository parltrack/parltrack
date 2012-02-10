#!/usr/bin/env python
# -*- coding: utf-8 -*-
#    This file is part of parltrack

#    parltrack is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    parltrack is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with parltrack  If not, see <http://www.gnu.org/licenses/>.

# (C) 2011 by Stefan Marsiske, <stefan.marsiske@gmail.com>

SHORTCUTMAP={'L': 'Directive',
             'R': 'Regulation',
             'D': 'Decision'}
group_positions={u'Chair': 10,
                 u'Co-Chair': 8,
                 u'Vice-Chair': 6,
                 u'Deputy Chair': 5,
                 u'Chair of the Bureau': 4,
                 u'Vice-Chair/Member of the Bureau': 8,
                 u'Secretary to the Bureau': 4,
                 u'Member of the Bureau': 2,
                 u'Treasurer': 2,
                 u'Co-treasurer': 1,
                 u'Deputy Treasurer': 1,
                 u'Member': 0,
                 }
com_positions={"Chair": 4,
               "Vice-President": 3,
               "Vice-Chair": 3,
               "Member": 2,
               "Substitute": 1,
               }
staff_positions={"President": 7,
                 "Chair": 6,
                 "Vice-President": 6,
                 "Quaestor": 5,
                 "Member": 4,
                 }
def mepRanking(date,query={}):
    meps=db.ep_meps2.find(query)
    tmp=[]
    for m in meps:
        for c in m['Constituencies']:
            if c['start']<=date and c['end']>=date:
                tmp.append(m)
                break
    rankedMeps=[]
    for mep in tmp:
        score=0
        ranks=[]
        # get group rank
        for group in mep['Groups']:
            if group['start']<=date and group['end']>=date:
                score=group_positions[group['role']]
                if not 'groupid' in group:
                    group['groupid']=group['Organization']
                elif type(group.get('groupid'))==list:
                    group['groupid']=group['groupid'][0]
                ranks.append((group_positions[group['role']],group['role'],group.get('groupid',group['Organization'])))
                mep['Groups']=[group]
                break
        # get committee ranks
        tmp=[]
        for com in mep.get('Committees',[]):
            if com['start']<=date and com['end']>=date:
                score+=com_positions[com['role']]
                ranks.append((com_positions[com['role']],com['role'],com['Organization']))
                tmp.append(com)
        mep['Committees']=tmp
        # get ep staff ranks
        tmp=[]
        for staff in mep.get('Staff',[]):
            if staff['start']<=date and staff['end']>=date:
                score+=staff_positions[staff['role']]
                ranks.append((staff_positions[staff['role']],staff['role'],staff['Organization']))
                tmp.append(staff)
        if len(tmp):
            mep['Staff']=tmp
        rankedMeps.append((score,sorted(ranks, reverse=True),mep))
    return [x for x in sorted(rankedMeps,reverse=True)]

def dossier(id, without_changes=True):
    dossier_idqueries=[{'procedure.reference': id },
                       {'activites.docs.title': id },
                       {'procedure.docs.title': id },
                       ]
    for query in dossier_idqueries:
        dossier=db.dossiers2.find_one(query)
        if dossier:
            break
    if not dossier:
        return
    if 'dossier_of_the_committee' in dossier['procedure']:
        dossier['procedure']['committee']=dossier['procedure']['dossier_of_the_committee'].split('/')[0]
    if 'changes' in dossier and without_changes: del dossier['changes']
    for act in dossier['activities']:
        if act.get('type') in ['Non-legislative initial document', 'Commission/Council: initial legislative document']:
            if 'comdoc' in dossier:
                print 'WTF? there is already a comdoc'
                raise
            dossier['comdoc']={'title': act['docs'][0]['title'], 'url': act['docs'][0].get('url'), }
        if act.get('type')=='Final legislative act':
            cid=act['docs'][0].get('title','')
            dossier['celexid']="CELEX:%s:EN" % cid
            st=7 if cid[6].isalpha() else 6
            doctype = cid[5:st]
            doctypename=SHORTCUTMAP.get(doctype)
            #print doctype, doctypename
            if doctypename:
                dossier['finalref']="%s %s/%d/EC" % (doctypename,
                                                     cid[1:5],
                                                     int(cid[st:]))
    if 'ipex' in dossier:
        dossier['ipex']['Rapporteur']=[[db.ep_meps2.find_one({'_id': id}),group] for id,group,name in dossier['ipex'].get('Rapporteur',[])]
        dossier['ipex']['Shadows']=[[db.ep_meps2.find_one({'_id': id}), group] for id,group,name in dossier['ipex'].get('Shadows',[])]
    # find related votes
    votes=list(db.ep_votes.find({'epref': dossier['procedure']['reference']}))
    for vote in votes:
        groups=[x['group'] for new in ['For','Against','Abstain'] if new in vote for x in vote[new]['groups']]
        vote['groups']=sorted(set(groups))
        t,r=vote.get('title'),vote.get('report')
        if t and r:
            i=t.index(r)
            if i>=0:
                tmp=r.replace('/','-').split('-')
                rid='-'.join((tmp[0],tmp[2],tmp[1]))
                vote['linkedtitle']='%s<a href="http://www.europarl.europa.eu/sides/getDoc.do?type=REPORT&amp;mode=XML&amp;reference=%s&amp;language=EN">%s</a>%s' \
                                     % (t[:i], rid, r, t[i+len(r):])
        for dec in [x for x in ['For','Against','Abstain'] if x in vote]:
            for g in groups:
                if g not in [x['group'] for x in vote[dec]['groups']]:
                    vote[dec]['groups'].append({'group':g, 'votes': []})
            vote[dec]['groups'].sort(key=itemgetter('group'))
    dossier['votes']=votes
    dossier['comeets']=[]
    for item in db.ep_comagendas.find({'epdoc': dossier['procedure']['reference']}):
        item['Committees']={}
        if 'Rapporteur' in item:
            item['Rapporteur']['rapporteurs']=[db.ep_meps2.find_one({'_id': x}) for x in item['Rapporteur']['rapporteurs']]
            item['Rapporteur']['rapporteurs'].extend([db.ep_meps.find_one({'_id': x}) for x in item['Rapporteur']['rapporteurs']])
            item['Committees'][item['committee']]=item['Rapporteur']['rapporteurs']
        for com in item.get('Opinions',[]):
            if 'committees' in com and 'committee' not in com:
                for c in com['committees']:
                    c['rapporteurs']=[]
                    item['Committees'][c['committee']]=c
            else:
                com['rapporteurs']=[db.ep_meps2.find_one({'_id': x}) for x in com['rapporteurs']]
                com['rapporteurs'].extend([db.ep_meps.find_one({'_id': x}) for x in com['rapporteurs']])
                item['Committees'][com['committee']]=com['rapporteurs']
        if 'tabling_deadline' in item and item['tabling_deadline']>=datetime.now():
            deadline={'type': '(%s) Tabling Deadline' % item['committee'],
                      'body': 'EP',
                      'date': item['tabling_deadline']}
            if deadline not in dossier['activities']:
                dossier['activities'].insert(0,deadline)
        item['resp']=item['committee'] in [x['committee'] for x in item.get('Responsible',[])]
        dossier['comeets'].append(item)

    agents=set()
    for c in dossier.get('committees',[]):
        agents.update([tuple(x.items()+
                             [('responsible', c.get('responsible',False)),
                              ('committee',c['committee'])])
                       for x in c.get('rapporteur',[])])
    dossier['procedure']['agents']=sorted([dict(x) for x in agents],key=itemgetter('name'))

    return dossier

def getMep(text, date):
    name=''.join(unicodedata.normalize('NFKD', unicode(text.replace(',','').strip())).encode('ascii','ignore').split()).lower()

    if not name: return
    if date:
        query={'Name.aliases': name,
               "Constituencies": {'$elemMatch' :
                                  {'start' : {'$lte': date},
                                   "end" : {'$gte': date},
                                   }}}
    else:
        query={'Name.aliases': name}
    mep=db.ep_meps2.find_one(query)
    mep5=None
    if not mep:
        mep5=db.ep_meps.find_one(query)
    if not (mep or mep5):
        if u'ß' in text:
            query['Name.aliases']=''.join(unicodedata.normalize('NFKD', unicode(text.replace(u'ß','ss').strip())).encode('ascii','ignore').split()).lower()
            mep=db.ep_meps2.find_one(query)
            if not mep:
                mep5=db.ep_meps.find_one(query)
        else:
            query={'Name.aliases': re.compile(''.join([x if ord(x)<128 else '.' for x in name]),re.I)}
            mep=db.ep_meps2.find_one(query,retfields)
            if not mep:
                mep5=db.ep_meps.find_one(query,retfields)
    if not (mep or mep5):
        print >>sys.stderr, '[$] lookup oops:', text.encode('utf8')
        print >>sys.stderr, query, '\n', mep
        return

    # merge with v5 mep db
    if mep:
        mep5=db.ep_meps.find_one({'UserID': str(mep['UserID'])})
        if not mep5:
            return mep
    for field in [u'Constituencies', u'Groups', u'Delegations', u'Committees', u'Staff']:
        for item in sorted(mep5.get(field,[]),key=itemgetter('start')):
            if item['start']>=datetime(2009,7,13):
                continue
            else:
                if not field in mep: mep[field]=[]
                mep[field].append(item)
    return mep

def mep(id,date):
    mep=getMep(id,date)
    if not mep:
        return None

    # find related dossiers
    docs=[(x, True) for x in db.dossiers2.find({ 'activities.committees': { '$elemMatch': {'rapporteur.name': "%s %s" % (mep['Name']['family'],mep['Name']['sur']), 'responsible': True}}})]
    docs.extend([(x, False) for x in db.dossiers2.find({ 'activities.committees': { '$elemMatch': {'rapporteur.name': "%s %s" % (mep['Name']['family'],mep['Name']['sur']), 'responsible': False}}})])
    for c in mep['Constituencies']:
        # term 6 20.07.2004 / 13.07.2009
        if 'end' in c and c['start']>=datetime(2004,07,20) and c['end']<=datetime(2009,07,13):
            mep['term6']=True
        # term 7 started on 14.07.2009 / ...
        if c['start']>=datetime(2009,07,14):
            mep['term7']=True
    mep['dossiers']=docs
    return mep

def committee(id):
    # get agendas
    agendas=[]
    for entry in db.ep_comagendas.find({'committee': id,
                                        'date': { '$exists': True}}).sort([('date', pymongo.DESCENDING),
                                                                           ('seq_no', pymongo.ASCENDING)]):
        entry['date'], entry['time']=entry['date'].isoformat().split('T')
        agendas.append(entry)
    # get dossiers
    #comre=re.compile(COMMITTEE_MAP[id],re.I)
    dossiers=[]
    for d in db.dossiers2.find({'activities.committees.committee': id, 'procedure.stage_reached': {'$in': STAGES}}):
        tmp=[c for c in d['committees'] if c['committee']==id]
        if len(tmp)>0:
            d['crole']=0 if tmp[0]['responsible'] else 1
            d['rapporteur']=[m for c in d['committees'] if c['responsible'] for m in c.get('rapporteur',[])]
            for act in d['activities']:
                if act.get('type') in ['Non-legislative initial document',
                                       'Commission/Council: initial legislative document',
                                       "Legislative proposal",
                                       "Legislative proposal published"] and 'docs' in act and len(act['docs'])>0:
                    d['comdoc']={'title': act['docs'][0]['title'],
                                 'url': act['docs'][0].get('url'), }
                    break
            if d not in dossiers: dossiers.append(d)
    # get members of committee
    query={"Committees.abbr": id, "active": True}
    rankedMeps=[]
    for mep in db.ep_meps2.find(query):
        for c in mep['Committees']:
            if c['abbr']==id:
                score=com_positions[c['role']]
                mep['crole']=c['role']
                rankedMeps.append((score,mep))
                break
    return {'meps': [x for _,x in sorted(rankedMeps,reverse=True)],
            'dossiers': dossiers,
            'agendas': agendas}

def immunity():
    immre=re.compile(r'.*\(IMM\)$')
    mepre=re.compile(r"(?:.*Mr.? |.* of |)(.*?)(?:'[s]? .*(?:immunity|mandate|testimony)| to be waived|$)")
    res=[]
    for d in db.dossiers2.find({'procedure.reference': immre}):
        m=mepre.match(d['procedure']['title'])
        if not m:
            print 'pls improve mepre to handle', d['procedure']['title'].encode('utf8')
            continue
        name=''.join(unicodedata.normalize('NFKD', unicode(m.group(1).strip())).encode('ascii','ignore').split()).lower()
        mep=db.ep_meps2.find_one({'Name.aliases': name })
        if not mep:
            mep=db.ep_meps.find_one({'Name.aliases': name })
        if not mep and u'ß' in m.group(1):
            name=''.join(unicodedata.normalize('NFKD', unicode(text.replace(u'ß','ss').strip())).encode('ascii','ignore').split()).lower()
            mep=db.ep_meps2.find_one({'Name.aliases': name })
            if not mep:
                mep=db.ep_meps.find_one({'Name.aliases': name })
        if not mep:
            print '[0] not found', d['procedure']['reference'].split('/')[1], m.group(1).encode('utf8')
            continue
        year=d['procedure']['reference'].split('/')[0]
        for c in mep['Constituencies']:
            if c['start'].year<=int(year) and c['end'].year>=int(year):
                country=c['country']
                party=c['party']
                break
        if d['procedure']['stage_reached']=='Awaiting Parliament 1st reading / single reading / budget 1st stage':
            state='[1] in progress'
        elif d['procedure']['stage_reached']=='Procedure completed':
            state='[2] finished'
        else:
            state='[3] aborted'
        res.append({'status': state,
                    'year': year,
                    'mep': mep['Name']['full'],
                    'country': country,
                    'party': party,
                    'dossier': d['procedure']['reference']})
    return res

subjectscache={}
def fetchsubj(subj):
    (subject,title)=subj.split(' ',1)
    subject=tuple(map(int,subject.split('.')))
    if not subject in subjectscache:
        subjectscache[subject]={'title': []}
    if not title in subjectscache[subject]['title']:
        subjectscache[subject]['title'].append(title)
    return subject

def inc(dct,fld,sfl):
    if not fld in dct:
        dct[fld]={sfl:0}
    elif not sfl in dct[fld]:
        dct[fld][sfl]=0
    dct[fld][sfl]+=1

def getCountry(mep,date):
    if type(date) in [type(str()), type(unicode())]:
        date=datetime.strptime(date,"%Y-%m-%d")
    for c in mep:
        if type(c['start']) in [type(str()), type(unicode())]:
            start=datetime.strptime(c['start'],"%Y-%m-%d")
        else:
            start=c['start']
        if type(c['end']) in [type(str()), type(unicode())]:
            end=datetime.strptime(c['end'],"%Y-%m-%d")
        else:
            end=c['end']
        if end>=date and start<=date:
            return (c['country'],c['party'])
    if len(mep)==1:
        return (mep[0]['country'],mep[0]['party'])

def subjects():
    all={}
    fullmeps=dict([(x['_id'],(x['Constituencies'])) for x in db.ep_meps2.find({},['Constituencies'])])
    fullmeps.update(dict([(x['_id'],(x['Constituencies'])) for x in db.ep_meps.find({},['Constituencies'])]))
    tree={}
    for d in db.dossiers2.find():
        subs=[fetchsubj(x) for x in d['procedure'].get('subject',[]) if x]
        if not len(subs): continue
        buck=[]
        for actor, committee in [(a,committee)
                                 for committee in d['committees']
                                 for a in committee.get('rapporteur', [])
                                 if hasattr(a,'keys') and committee.get('responsible') and a.get('mepref')]:
            if actor in buck: continue
            buck.append(actor)
            if type(committee.get('date'))==type(list()):
                (country,party)=getCountry(fullmeps[actor['mepref']],
                                           committee.get('date')[committee['rapporteur'].index(actor)])
            else:
                (country,party)=getCountry(fullmeps[actor['mepref']],committee.get('date'))
            [inc(all,(party, actor['group'], country),sub) for sub in subs]
            inc(all,(party, actor['group'], country),'total')
            group=actor['group']
            if group not in tree:
                tree[group]={}
            if country not in tree[group]:
                tree[group][country]={}
            if party not in tree[group][country]:
                tree[group][country][party]={}
            [inc(tree[group][country],party,subjectscache[sub]['title'][0]) for sub in subs]
    csv = [(count, '.'.join([str(x) for x in subj]), k[0], subjectscache[subj]['title'][0], k[1], k[2])
           for k,v in all.items()
           for subj,count in v.items() if subj!='total']
    return (csv,tree)
    #print u'\n'.join([u'\t'.join([unicode(y) for y in x]) for x in sorted(csv,reverse=True)]).encode('utf8')

import sys, unicodedata
from datetime import datetime
import pymongo, re
from parltrack.scrapers.mappings import STAGES, COMMITTEE_MAP
try:
    from parltrack.webapp import connect_db
    db = connect_db()
except:
    db=pymongo.Connection().parltrack
from operator import itemgetter

if __name__ == "__main__":
    dossier('COD/2007/0247')
    date='24/11/2010'
    print committee('LIBE')
    #date='02/06/2011'
    #data=mepRanking(date)
    ## from bson.objectid import ObjectId
    ## import json
    ## def dateJSONhandler(obj):
    ##     if hasattr(obj, 'isoformat'):
    ##         return obj.isoformat()
    ##     elif type(obj)==ObjectId:
    ##         return str(obj)
    ##     else:
    ##         raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))
    #print json.dumps(data, default=dateJSONhandler, indent=1, ensure_ascii=False).encode('utf-8')
