#!/usr/bin/env python

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

# (C) 2011 by Adam Tauber, <asciimoo@gmail.com>, Stefan Marsiske <stefan.marsiske@gmail.com>

import os, re, copy, csv, cStringIO, json, sys, itertools
from pymongo import Connection
from flaskext.mail import Mail, Message
from flaskext.cache import Cache
from flask import Flask, render_template, request, jsonify, abort, redirect, Response
from datetime import datetime, date, timedelta
from random import randint, choice, shuffle, randrange
from hashlib import sha1
from werkzeug import ImmutableDict
from bson.objectid import ObjectId
from bson.code import Code
from operator import itemgetter
from itertools import chain
from collections import defaultdict
from parltrack import default_settings

Flask.jinja_options = ImmutableDict({'extensions': ['jinja2.ext.autoescape', 'jinja2.ext.with_', 'jinja2.ext.loopcontrols']})
app = Flask(__name__)
app.config.from_object(default_settings)
app.config.from_envvar('PARLTRACK_SETTINGS', silent=True)
cache = Cache(app)
mail = Mail(app)

#@app.context_processor

def connect_db():
    conn = Connection(app.config.get('MONGODB_HOST'))
    return conn[app.config.get('MONGODB_DB')]

def get_data_dir():
    data_dir = app.config.get('DATA_DIR', '/tmp/parltrack')
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir)
    return data_dir

@app.context_processor
def inject_data():
    return dict(now_date=datetime(*date.today().timetuple()[:3]+(23,59)),
                committees=COMMITTEES,
                committee_map=COMMITTEE_MAP,
                countries=SEIRTNUOC,
                )

@cache.cached()
@app.route('/')
def index():
    db = connect_db()
    #tmp=dict([(x[u'procedure.stage_reached'],int(x['count'])) for x in db.dossiers.group({'procedure.stage_reached': True},
    #                                                                              {},
    #                                                                              {'count': 0},
    #                                                                              Code('function(doc, out){ out.count++ }'))])
    #stages=[(k,tmp[k]) for k in ALL_STAGES if tmp.get(k)]
    cutoff=datetime.now()-timedelta(days=int(request.args.get('days','2')))

    cdocs=db.dossiers2.find      ({'meta.updated': {'$gt': cutoff}}).sort([('procedure.reference', 1)])
    cmeps=db.ep_meps2.find       ({'meta.updated': {'$gt': cutoff}}).sort([('Name.family', 1)])
    ccoms=db.ep_comagendas.find  ({'meta.updated': {'$gt': cutoff}}).sort([('commmittee', 1)])
    newdocs=db.dossiers2.find    ({'meta.created': {'$gt': cutoff}}).sort([('procedure.reference', 1)])
    newmeps=db.ep_meps2.find     ({'meta.created': {'$gt': cutoff}}).sort([('Name.family', 1)])
    newcoms=db.ep_comagendas.find({'meta.created': {'$gt': cutoff}}).sort([('commmittee', 1)])

    return render_template('index.html',
                           #stages=stages,
                           dossiers_num=db.dossiers2.find().count(),
                           votes_num=db.ep_votes.find().count(),
                           meps_num=db.ep_meps2.find().count()+db.ep_meps.find({"Constituencies.start": {'$lt': datetime(2009,07,14)}}).count(),
                           newdocs=newdocs,
                           newmeps=newmeps,
                           newcoms=newcoms,
                           cdocs=cdocs,
                           cmeps=cmeps,
                           ccoms=ccoms,
                           )



#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Search
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

celexre=re.compile(r'(directive\s+)?(19[89][0-9]|20[01][0-9])/([0-9]{1,4})/EC\s*$',re.I)
@app.route('/search')
def search():
    db = connect_db()
    if not request.args.get('q'):
        return ''
    q = request.args.get('q')
    ret = []
    if request.args.get('s_meps'):
        ret.extend(db.ep_meps2.find({'Name.full': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}))
        ret.extend(db.ep_meps.find({'Name.full': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}))
    if request.args.get('s_dossiers'):
        m=celexre.match(q)
        if m:
            ret.extend(db.dossiers2.find({'activities.docs.title': "3%sL%04d" % (m.group(2),int(m.group(3)))}))
        ret.extend(db.dossiers2.find({'procedure.title': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}))
        ret.extend(db.dossiers2.find({'activities.docs.title': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}))
    if request.args.get('format')=='json' or request.headers.get('X-Requested-With') or request.headers.get('Accept')=='text/json':
        return jsonify(count=len(ret), items=tojson(ret))
    if len(ret)==1:
        if 'procedure' in ret[0]:
            return redirect('/dossier/%s' % ret[0]['procedure']['reference'])
            #return view_dossier(ret[0]['procedure']['reference'])
        if 'Name' in ret[0]:
            return redirect('/mep/%s' % (ret[0]['Name']['full']))
            #return view_mep(ret[0]['Name']['full'])
    return render_template('search_results.html', query=q,
                           results=sorted(ret, reverse=True))


#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Notifications
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/notification')
def gen_notif_id():
    db = connect_db()
    while True:
        nid = ''.join([chr(randint(97, 122)) if randint(0, 5) else choice("_-.") for x in range(10)])
        if not db.notifications.find({'id': nid}).count():
            break
    return '/notification/'+nid

def listdossiers(d):
    for act in d['activities']:
        if act.get('type') in ['Non-legislative initial document',
                               'Commission/Council: initial legislative document',
                               "Legislative proposal",
                               "Legislative proposal published"]:
            if 'title' in act['docs'][0]:
                d['comdoc']={'title': act['docs'][0]['title'],
                             'url': act['docs'][0].get('url'), }
    if 'legal_basis' in d.get('procedure', {}):
        clean_lb(d)
    db = connect_db()
    for item in db.ep_comagendas.find({'epdoc': d['procedure']['reference']}):
        if 'tabling_deadline' in item and item['tabling_deadline']>=datetime.now():
            d['activities'].insert(0,{'type': '(%s) Tabling Deadline' % item['committee'], 'body': 'EP', 'date': item['tabling_deadline']})
    return d

@cache.cached()
@app.route('/notification/<string:g_id>')
def notification_view_or_create(g_id):
    db = connect_db()
    # TODO g_id validation
    group = db.notifications.find_one({'id': g_id})
    if not group:
        group = {'id': g_id, 'active_emails': [], 'dossiers': [], 'restricted': False, 'actions' :[]}
        db.notifications.save(group)
    ds=[]
    if len(group['dossiers']):
        ds=[listdossiers(d) for d in db.dossiers2.find({'procedure.reference': { '$in' : group['dossiers'] } })]
    return render_template('view_notif_group.html',
                           dossiers=ds,
                           date=datetime.now(),
                           group=group)

@app.route('/notification/<string:g_id>/add/<any(dossiers, emails):item>/<path:value>')
def notification_add_detail(g_id, item, value):
    db = connect_db()
    group = db.notifications.find_one({'id': g_id})
    if not group:
        return 'unknown group '+g_id
    # TODO handle restricted groups
    #if group.restricted:
    #    return 'restricted group'
    if item == 'emails':
        if value in group['active_emails']:
            return 'already subscribed to this group'
        item = 'actions'
        # TODO validation
        addr = db.notifications.find_one({'actions.address': value, 'id': g_id})
        if addr:
            # or just return with OK?! -> more privacy but harder debug
            return 'Already subscribed'
        i = {'address': value, 'type': 'subscription', 'token': sha1(''.join([chr(randint(32, 122)) for x in range(12)])).hexdigest(), 'date': datetime.now()}
        msg = Message("Parltrack Notification Subscription Verification",
                sender = "parltrack@parltrack.euwiki.org",
                recipients = [value])
        msg.body = "Your verification key is %sactivate?key=%s\nNotification group url: %snotification/%s" % (request.url_root, i['token'], request.url_root, g_id)
        mail.send(msg)

    else:
        #if db.notifications.find({'dossiers': value}).count():
        #    return 'OK'
        i = db.dossiers2.find_one({'procedure.reference': value})
        if not i:
            return 'unknown dossier - '+value
        i = i['procedure']['reference']

    group[item].append(i)
    db.notifications.save(group)
    return 'OK'

@app.route('/notification/<string:g_id>/del/<any(dossiers, emails):item>/<path:value>')
def notification_del_detail(g_id, item, value):
    db = connect_db()
    group = db.notifications.find_one({'id': g_id})
    if not group:
        return 'unknown group '+g_id
    # TODO handle restricted groups
    #if group.restricted:
    #    return 'restricted group'
    if item == 'emails':
        print value
        print group['active_emails']
        if value not in group['active_emails']:
            return 'Cannot complete this action'
        i = {'address': value, 'type': 'unsubscription', 'token': sha1(''.join([chr(randint(32, 122)) for x in range(12)])).hexdigest(),'date': datetime.now()}
        group['actions'].append(i)
        msg = Message("Parltrack Notification Unsubscription Verification",
                sender = "parltrack@parltrack.euwiki.org",
                recipients = [value])
        msg.body = "Your verification key is %sactivate?key=%s\nNotification group url: %snotification/%s" % (request.url_root, i['token'], request.url_root, g_id)
        mail.send(msg)
        db.notifications.save(group)
    return 'OK'

@app.route('/activate')
def activate():
    db = connect_db()
    k = request.args.get('key')
    if not k:
        return 'Missing key'
    notif = db.notifications.find_one({'actions.token': k})
    if not notif:
        return 'wrong key'
    for action in notif['actions']:
        if action.get('token') == k:
            if action['type'] == 'subscription':
                if not action['address'] in notif['active_emails']:
                    notif['active_emails'].append(action['address'])
                notif['actions'].remove(action)
                db.notifications.save(notif)
                # TODO activation method
                return 'activated'

            if action['type'] == 'unsubscription':
                notif['actions'].remove(action)
                notif['active_emails'].remove(action['address'])
                db.notifications.save(notif)
                # TODO activation method
                return 'deactivated'

#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Meps
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

def getDate():
    date=datetime.now()
    if request.args.get('date'):
        try:
            date=datetime.strptime(request.args['date'], "%d/%m/%Y")
        except ValueError:
            try:
                date=datetime.strptime(request.args['date'], "%Y-%m-%d")
            except ValueError:
                date=datetime.strptime(request.args['date'], "%Y/%m/%d")
    return date

def render_meps(query={},kwargs={}):
    date=getDate()
    rankings=mepRanking(date,query)
    if not rankings:
        abort(404)
    if request.args.get('format','')=='json' or request.headers.get('X-Requested-With') or request.headers.get('Accept')=='text/json':
        return jsonify(count=len(rankings), meps=tojson([z for x,y,z in rankings]))
    return render_template('mep_ranking.html',
                           rankings=rankings,
                           d=date,
                           groupids=groupids,
                           url=request.base_url,
                           **kwargs)

@cache.cached()
@app.route('/meps/<string:country>/<path:group>')
def mepfilter(country, group):
    query={}
    args={}
    date=getDate()
    if country.upper() in COUNTRIES.keys():
        query["Constituencies"]={'$elemMatch' :
                                 {'start' : {'$lte': date},
                                  'country': COUNTRIES[country.upper()],
                                  "end" : {'$gte': date},}}
        args['country']=COUNTRIES[country.upper()]
    else:
        query["Constituencies"]={'$elemMatch' :
                                 {'start' : {'$lte': date},
                                  "end" : {'$gte': date},}}
        group="%s/%s" % (country, group)
    if group in groupids:
        query['Groups']={'$elemMatch' :
                         {'groupid': group,
                          'start' : {'$lte': date},
                          "end" : {'$gte': date},}}
        args['group']=group
    if not args:
        abort(404)
    return render_meps(query, args)

@cache.cached()
@app.route('/meps/<path:p1>')
def mepsbygroup(p1):
    query={}
    args={}
    date=getDate()
    if p1 in groupids:
        query['Groups']={'$elemMatch' :
                         {'groupid': p1,
                          'start' : {'$lte': date},
                          "end" : {'$gte': date},}}
        args['group']=p1
    elif p1.upper() in COUNTRIES.keys():
        query["Constituencies"]={'$elemMatch' :
                                 {'start' : {'$lte': date},
                                  'country': COUNTRIES[p1.upper()],
                                  "end" : {'$gte': date},}}
        args['country']=COUNTRIES[p1.upper()]
    else:
        abort(404)
    return render_meps(query, args)

@cache.cached()
@app.route('/meps/')
def ranking():
    query={}
    date=getDate()
    if date<datetime(2009,7,14):
        query={"Constituencies": {'$elemMatch' :
                                 {'start' : {'$lte': date},
                                  'end' : {'$gte': date},}}}
    else:
        query={"Constituencies.start": {'$lte': date} }
    return render_meps(query)

@cache.cached()
@app.route('/mep/<string:d_id>/atom')
def mep_changes(d_id):
    c=mep(d_id,None)
    if not c:
        abort(404)
    changes=[(date, change)
             for date,change
             in c['changes'].items()]
    updated=max(changes, key=itemgetter(0))[0]
    changes=[{'changes': {date: change}} for date, change in sorted(changes, key=itemgetter(0), reverse=True)]
    return render_template('changes_atom.xml', updated=updated, changes=changes, path='/mep/%s' % d_id)

@cache.cached()
@app.route('/mep/<string:d_id>')
def view_mep(d_id):
    date=None
    if request.args.get('date'):
        date=getDate()
    m=mep(d_id,date)
    if not m:
        abort(404)
    if request.args.get('format','')=='json' or request.headers.get('X-Requested-With') or request.headers.get('Accept')=='text/json':
        return jsonify(tojson(m))
    return render_template('mep.html',
                           mep=m,
                           d=d_id,
                           group_cutoff=datetime(2004,7,20),
                           today=datetime.now(),
                           url=request.base_url)

def toJit(tree, name):
    if type(tree)==type(dict()):
        res=[toJit(v,k) for k, v in tree.items()]
    if type(tree)==type(list()):
        return {"name": name,
                "id": name,
                "data": {"$area": len(tree), 'meta': tree}}
    w=sum([x['data']['$area'] for x in res])
    return {"id": name,
            "name": name,
            "data": { "$area": w},
            "children": res}

@cache.cached()
@app.route('/datasets/imm/')
def immunity_view():
    res=immunity()
    if request.args.get('format','')=='tree':
        tree={}
        for item in res:
            if item['country'] not in tree:
                tree[item['country']]={}
            if item['party'] not in tree[item['country']]:
                tree[item['country']][item['party']]={}
            if item['mep'] not in tree[item['country']][item['party']]:
                tree[item['country']][item['party']][item['mep']]=[]
            tree[item['country']][item['party']][item['mep']].append({'year': item['year'],
                                                                      'status': item['status'],
                                                                      'dossier': item['dossier']})
        return jsonify(tojson(toJit(tree,'Immunity Procedures by Country/Party')))
    if request.args.get('format','')=='json' or request.headers.get('X-Requested-With') or request.headers.get('Accept')=='text/json':
        return jsonify(tojson({'count': len(res), 'data': res}))
    if request.args.get('format','')=='csv':
        fd = cStringIO.StringIO()
        writer = csv.writer(fd,dialect='excel')
        writer.writerow(['status', 'procedure','country','name','year','party'])
        writer.writerows([[v.encode('utf8') for k,v in row.items()] for row in sorted(res,key=itemgetter('year'),reverse=True)])
        fd.seek(0)
        return Response( response=fd.read(), mimetype="text/csv" )
    return render_template('immunity.html',
                           data=res,
                           url=request.base_url)

@cache.cached()
@app.route('/datasets/subjects/')
def subjects_view():
    (res,tree)=subjects() or ([],{})
    if request.args.get('format','')=='json' or request.headers.get('X-Requested-With') or request.headers.get('Accept')=='text/json':
        return jsonify(tojson({'count': len(res), 'data': res}))
    if request.args.get('format','')=='csv' or request.headers.get('Accept')=='text/csv':
        fd = cStringIO.StringIO()
        writer = csv.writer(fd,dialect='excel')
        writer.writerow(['count', 'subj_id','party','subj_title','group','country'])
        writer.writerows([[row[0]]+[v.encode('utf8') for v in row[1:]] for row in sorted(res,reverse=True)])
        fd.seek(0)
        return Response( response=fd.read(), mimetype="text/csv" )
    if request.args.get('format','')=='tree':
        return jsonify(tojson(tree))
    return render_template('subjects.html',
                           data=res,
                           url=request.base_url)
#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Dossiers
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/dossier/<string:d>/<string:y>/<string:ctr>')
def dossier_path(d, y, ctr):
    return redirect('/dossier/%s/%s(%s)' % (y,ctr,d))

@cache.cached()
@app.route('/dossier/<path:d_id>/atom')
def dossier_changes(d_id):
    c=dossier(d_id, without_changes=False)
    if not c:
        abort(404)
    changes=[(date, change)
             for date,change
             in c['changes'].items()]
    updated=max(changes, key=itemgetter(0))[0]
    changes=[{'changes': {date: change}} for date, change in sorted(changes, key=itemgetter(0), reverse=True)]
    return render_template('changes_atom.xml', updated=updated, changes=changes, path='/dossier/%s' % d_id)

@cache.cached()
@app.route('/dossier/<path:d_id>')
def view_dossier(d_id):
    d=dossier(d_id, without_changes=False)
    if not d:
        abort(404)
    #print d
    if request.args.get('format','')=='json' or request.headers.get('X-Requested-With') or request.headers.get('Accept')=='text/json':
        return jsonify(tojson(d))
    return render_template('dossier.html',
                           dossier=d,
                           d=d_id,
                           url=request.base_url)

def atom(db, order, tpl, path):
    d=db.find().sort([(order, -1)]).limit(30)
    if request.args.get('format','')=='json' or request.headers.get('X-Requested-With') or request.headers.get('Accept')=='text/json':
        return jsonify(tojson(d))
    return render_template(tpl, dossiers=list(d), path=path)

@cache.cached()
@app.route('/new/')
def new_docs():
    return atom(connect_db().dossiers2, 'meta.created', 'atom.xml', 'new')

@cache.cached()
@app.route('/changed/')
def changed():
    return atom(connect_db().dossiers2, 'meta.updated', 'atom.xml', 'changed')

@cache.cached()
@app.route('/meps/new/')
def new_meps():
    return atom(connect_db().ep_meps2, 'meta.created', 'mep_atom.xml', 'new')

@cache.cached()
@app.route('/meps/changed/')
def changed_meps():
    return atom(connect_db().ep_meps2, 'meta.updated', 'mep_atom.xml', 'changed')

@cache.cached()
@app.route('/committees/new/')
def new_coms():
    return atom(connect_db().ep_comagendas, 'meta.created', 'com_atom.xml', 'new')

@cache.cached()
@app.route('/committees/changed/')
def changed_com():
    return atom(connect_db().ep_comagendas, 'meta.updated', 'com_atom.xml', 'changed')

@cache.cached()
@app.route('/atom/<path:nid>')
def rss(nid):
    db = connect_db()
    ng=db.notifications.find_one({'id': nid})
    if not ng:
        abort(404)
    timelimit=datetime.now()-timedelta(weeks=3)
    d=db.dossiers2.find({'procedure.reference': { '$in': ng['dossiers']},
                        'meta.updated' : {'$gt': timelimit}}).sort([('meta.updated', -1)])
    res=[]
    for doc in d:
        for k,c in doc['changes'].items():
            k=datetime.strptime(k, "%Y-%m-%dT%H:%M:%S")
            if k>timelimit:
               d=copy.deepcopy(doc)
               d['changes']={k:c}
               res.append((k,d))
    res=[x[1] for x in sorted(res,reverse=True)]
    if request.args.get('format','')=='json' or request.headers.get('X-Requested-With') or request.headers.get('Accept')=='text/json':
        return jsonify(tojson(res))
    return render_template('atom.xml', dossiers=res, path="changed")

@cache.cached()
@app.route('/dossiers')
def active_dossiers():
    db = connect_db()
    query={'procedure.stage_reached': { "$in": STAGES } }
    sub=request.args.get('sub')
    filterby=None
    if sub:
        query['procedure.subject']=re.compile(sub,re.I)
        subtitle=request.args.get('subtitle')
        if request.args.get('subtitle'):
            filterby="Subtitle: %s" % subtitle
        else:
            filterby="Subtitle: %s" % sub
    ds=[]
    dstat=[]
    stages=defaultdict(lambda: defaultdict(int))
    for d in db.dossiers2.find(query):
        ds.append(listdossiers(d))
        if d['procedure']['reference'][-4:-1] in ['APP', 'COD', 'CNS'] and 'stage_reached' in d['procedure']:
            dstat.append((d['procedure']['reference'][-4:-1],
                          d['procedure']['stage_reached'],
                          d['procedure']['dossier_of_the_committee'].split('/')[0] if 'dossier_of_the_committee' in d['procedure'] else "",
                          )+tuple(max([x.get('date').strftime("%Y-%m-%d") if type(x.get('date'))==type(datetime.now()) else x.get('date')
                                       for x in d['activities']]).split('-')))
            stages[d['procedure']['stage_reached']][d['procedure']['reference'][-4:-1]]+=1
    stages={ 'label': ['APP', 'COD', 'CNS'],
             'values': [x[1] for x in
                        sorted([(STAGEMAP[stage][:3],
                                 {'label': STAGEMAP[stage][3:],
                                  'values': [types.get(t,0)
                                             for t in ['APP', 'COD', 'CNS']]})
                                for stage, types
                                in sorted(stages.items())
                                if stage in STAGEMAP])]}
    return render_template('active_dossiers.html',
                           stats=json.dumps(dstat),
                           dossiers=ds,
                           stages=json.dumps(stages),
                           filterby=filterby,
                           date=datetime.now())

#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#              Committees
#-[+++++++++++++++++++++++++++++++++++++++++++++++|


@cache.cached()
@app.route('/committee/<string:c_id>/atom')
def committee_changes(c_id):
    c=committee(c_id)
    if not c:
        abort(404)
    changes=[]
    for item in c['agendas']:
        for date,change in item['changes'].items():
            changes.append((date, change))
    updated=max(changes, key=itemgetter(0))[0]
    changes=[{'changes': {date: change}} for date, change in sorted(changes, key=itemgetter(0), reverse=True)]
    return render_template('changes_atom.xml', updated=updated, changes=changes, path='/committee/%s' % c_id)

@cache.cached()
@app.route('/committee/<string:c_id>')
def view_committee(c_id):
    c=committee(c_id)
    #c['dossiers']=[listdossiers(d) for d in c['dossiers']]
    if not c:
        abort(404)
    if request.args.get('format','')=='json' or request.headers.get('X-Requested-With') or request.headers.get('Accept')=='text/json':
        return jsonify(tojson(c))
    return render_template('committee.html',
                           committee=c,
                           Committee=COMMITTEE_MAP[c_id],
                           today=datetime.now().isoformat().split('T')[0],
                           groupids=groupids,
                           c=c_id,
                           url=request.base_url)

@app.template_filter()
def asdate(value):
    if type(value)==type(int()):
        value=datetime.fromtimestamp(value)
    if type(value) not in [type(str()), type(unicode())]:
        return value.strftime('%Y/%m/%d')
    return value.split(' ')[0]

@app.template_filter()
def isodate(value):
    if type(value)==type(datetime(1,1,1)):
        return value.isoformat()
    return datetime.strptime(value,'%Y-%m-%d').isoformat()

@app.template_filter()
def group_icon(value):
    if not value: return ''
    if type(value)==type(list()): value=value[0]
    if value=='NA': value='NI'
    return "static/images/%s.gif" % value.lower().replace('/','_')

@app.template_filter()
def protect_email(email_address):
    character_set = '+-.0123456789@ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz'
    char_list = list(character_set)
    shuffle(char_list)

    key = ''.join(char_list)

    cipher_text = ''
    id = 'e' + str(randrange(1,999999999))

    for a in email_address:
        cipher_text += key[ character_set.find(a) ]

    script = 'var a="'+key+'";var b=a.split("").sort().join("");var c="'+cipher_text+'";var d="";'
    script += 'for(var e=0;e<c.length;e++)d+=b.charAt(a.indexOf(c.charAt(e)));'
    script += 'document.getElementById("'+id+'").innerHTML="<a href=\\"mailto:"+d+"\\">"+d+"</a>"'


    script = "eval(\""+ script.replace("\\","\\\\").replace('"','\\"') + "\")"
    script = '<script type="text/javascript">/*<![CDATA[*/'+script+'/*]]>*/</script>'

    return '<span id="'+ id + '">[javascript protected email address]</span>'+ script

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

def tojson(data):
    if type(data)==type(ObjectId()):
        return
    if type(data)==type(dict()):
        return dict([(k,tojson(v)) for k,v in data.items() if not type(ObjectId()) in [type(k), type(v)]])
    if '__iter__' in dir(data):
        return [tojson(x) for x in data if type(x)!=type(ObjectId())]
    if hasattr(data, 'isoformat'):
        return data.isoformat()
    return data

@app.template_filter()
def printdict(d):
    if type(d)==type(list()):
        return u'<ul>%s</ul>' % '\n'.join(["<li>%s</li>" % printdict(v) for v in d])
    if type(d)==type(datetime(2000,1,1)):
        return "%s" % d.isoformat()[:10]
    elif not type(d)==type(dict()):
        return "%s" % unicode(d)
    res=['']
    for k,v in [(k,v) for k,v in d.items() if k not in ['mepref','comref']]:
        if type(v) == type(dict()) or (type(v)==type(list()) and len(v)>1):
            res.append(u"<dl><dt class='more'>%s</dt><dd class='hidden'>%s</dd></dl>" % (k,printdict(v)))
        else:
            res.append(u"<dl><dt>%s</dt><dd>%s</dd></dl>" % (k,printdict(v)))
    return '%s' % u'\n'.join(res)

@app.template_filter()
def formatdiff(dossier):
    if not dossier['changes']:
        return
    res=[]
    for di in sorted(sorted(dossier['changes'].items())[-1][1],key=itemgetter('path')):
        if 'text' in di['path'] or 'summary' in di['path']:
            res.append(u'<tr><td>summary changed</td><td>%s</td></tr>' % '/'.join([str(x) for x in di['path']]))
            continue
        if di['type']=='changed':
            res.append(u'<tr><td>change</td><td>%s</td><td>%s</td><td>%s</td></tr>' % ('/'.join([unicode(x) for x in di['path']]),printdict(di['data'][1]),printdict(di['data'][0])))
            continue
        if di['type']=='deleted':
            res.append(u"<tr><td>%s</td><td>%s</td><td></td><td>%s</td></tr>" % (di['type'], u'/'.join([unicode(x) for x in di['path']]), printdict(di['data'])))
        if di['type']=='added':
            res.append(u"<tr><td>%s</td><td>%s</td><td>%s</td><td></td></tr>" % (di['type'], u'/'.join([unicode(x) for x in di['path']]), printdict(di['data'])))

    return "<table border='1'><thead><tr width='90%%'><th>type</th><th>change in</th><th>new</th><th>old</th></tr></thead><tbody>%s</tbody></table>" % '\n'.join(res)


from parltrack.scrapers.mappings import ALL_STAGES, STAGES, STAGEMAP, groupids, COUNTRIES, SEIRTNUOC, COMMITTEE_MAP
from parltrack.views.views import mepRanking, mep, immunity, committee, subjects, dossier, clean_lb
COMMITTEES=[x for x in connect_db().ep_comagendas.distinct('committee') if x not in ['Security and Defence', 'SURE'] ]

if __name__ == '__main__':
    app.run(debug=True)
