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

import sys, unicodedata
from datetime import datetime
try:
    from parltrack.webapp import connect_db
    db = connect_db()
except:
    import pymongo
    db=pymongo.Connection().parltrack

db.oeil.ensure_index([('reference.procedure', 1)])

def mepsInGroups(group, date):
    date=datetime.strptime(date, "%d/%m/%Y")
    query={"Constituencies.start" : {'$lt': date},
           "Constituencies.end" : {'$gt': date},
           "Groups.groupid": group,
           }
    meps=db.ep_meps.find(query)
    return meps.count()
    return [x for x in meps]

group_positions={u'Chair': 10,
                 u'Co-Chair': 8,
                 u'Vice-Chair': 6,
                 u'Deputy Chair': 5,
                 u'Chair of the Bureau': 4,
                 u'Vice-Chair/Member of the Bureau': 3,
                 u'Member of the Bureau': 2,
                 u'Treasurer': 2,
                 u'Co-treasurer': 1,
                 u'Member': 0,
                 }
com_positions={"Chair": 4,
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
    date=datetime.strptime(date, "%d/%m/%Y")
    query.update({"Constituencies.start" : {'$lt': date},
                  "Constituencies.end" : {'$gt': date},
                  })
    meps=db.ep_meps.find(query)
    rankedMeps=[]
    for mep in meps:
        score=0
        ranks=[]
        # get group rank
        for i, group in enumerate(mep['Groups']):
            if group['start']<date and group['end']>date:
                score=group_positions[group['role']]
                if type(group['groupid'])==list:
                    group['groupid']=group['groupid'][0]
                ranks.append((group_positions[group['role']],group['role'],group['groupid']))
                break
            else:
                del mep['Groups'][i]
        # get committee ranks
        for i,com in enumerate(mep['Committees']):
            if com['start']<date and com['end']>date:
                score+=com_positions[com['role']]
                ranks.append((com_positions[com['role']],com['role'],com['Organization']))
            else:
                del mep['Committees'][i]
        # get ep staff ranks
        for i,staff in enumerate(mep.get('Staff',[])):
            if staff['start']<date and staff['end']>date:
                score+=staff_positions[staff['role']]
                ranks.append((staff_positions[staff['role']],staff['role'],staff['Organization']))
            else:
                del mep['Staff'][i]
        rankedMeps.append((score,sorted(ranks, reverse=True),mep))
    return [x for x in sorted(rankedMeps,reverse=True)]

def dossier(id):
    dossier_idqueries=[{'procedure.reference': id },
                       {'procedure.docs.title': id },
                       {'activites.documents.title': id },
                       ]
    for query in dossier_idqueries:
        dossier=db.dossiers.find_one(query)
        if dossier:
            break
    if not dossier:
        return 404
    del dossier['changes']
    # find related votes
    votes=list(db.ep_votes.find({'dossierid': dossier['_id']}))
    for vote in votes:
        groups=[]
        for dec, new in [('+','For'),
                         ('-','Against'),
                         ('0','Abstain')]:
            vote[new]=vote[dec]
            del vote[dec]
            groups.extend([x for x in vote[new].keys() if x!='total'])
        vote['groups']=sorted(set(groups))
        for dec in ['For','Against','Abstain']:
            for g in groups:
                if g not in vote[dec]:
                    vote[dec][g]=[]
    dossier['votes']=votes
    dossier['comeets']=[]
    for item in db.ep_com_meets.find({'comref': dossier['_id']}):
        item['Committees']={}
        if 'Rapporteur' in item:
            item['Rapporteur']['rapporteurs']=[db.ep_meps.find_one({'_id': x}) for x in item['Rapporteur']['rapporteurs']]
            item['Committees'][item['committee']]=item['Rapporteur']['rapporteurs']
        for com in item['Opinions']:
            com['rapporteurs']=[db.ep_meps.find_one({'_id': x}) for x in com['rapporteurs']]
            item['Committees'][com['committee']]=com['rapporteurs']
        dossier['comeets'].append(item)
    return dossier

def getMep(text):
    name=''.join(unicodedata.normalize('NFKD', unicode(text.replace(',','').strip())).encode('ascii','ignore').split()).lower()

    if not name: return
    # TODO add date constraints based on groups.start/end
    mep=db.ep_meps.find_one({'Name.aliases': name})
    if not mep and u'ß' in text:
        name=''.join(unicodedata.normalize('NFKD', unicode(text.replace(u'ß','ss').strip())).encode('ascii','ignore').split()).lower()
        mep=db.ep_meps.find_one({'Name.aliases': name})
    if not mep:
        print >>sys.stderr, '[$] lookup oops:', text.encode('utf8')
    else:
        return mep

def mep(id):
    mep=getMep(id)
    if not mep:
        return 404
    #print mep
    # find related votes
    #votes=list(db.ep_votes.find({'mepid': dossier['_id']}))
    #ep['votes']=votes
    return mep

if __name__ == "__main__":
    dossier('COD/2007/0247')
    date='24/11/2010'
    #date='02/06/2011'
    #groups=['PPE','S&D','ALDE','Verts/ALE','GUE/NGL','NI','EFD','ECR']
    #groupstrengths=[mepsInGroups(x,date) for x in groups]
    #print groupstrengths, sum(groupstrengths)
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
