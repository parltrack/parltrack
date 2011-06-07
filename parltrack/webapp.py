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

# (C) 2011 by Adam Tauber, <asciimoo@gmail.com>

import os
import re
from pymongo import Connection
from flaskext.mail import Mail, Message
from flaskext.cache import Cache
from flask import Flask, render_template, request, jsonify, abort, redirect
from parltrack import default_settings
from datetime import datetime
from random import randint
from hashlib import sha1
from werkzeug import ImmutableDict
from bson.objectid import ObjectId
from parltrack.scrapers.ep_meps import groupids, COUNTRIES
from parltrack.scrapers.ep_com_meets import COMMITTEES, COMMITTEE_MAP
from parltrack.scrapers.mappings import ALL_STAGES as STAGES
from bson.code import Code

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
    return dict(now_date=datetime.now(),
                committees=COMMITTEES,
                committee_map=COMMITTEE_MAP,
                )

@app.route('/')
@cache.cached()
def index():
    db = connect_db()
    tmp=dict([(x[u'procedure.stage_reached'],int(x['count'])) for x in db.dossiers.group({'procedure.stage_reached': True},
                                                                                  {},
                                                                                  {'count': 0},
                                                                                  Code('function(doc, out){ out.count++ }'))])
    stages=[(k,tmp[k]) for k in STAGES if tmp.get(k)]
    return render_template('index.html',
                           stages=stages,
                           dossiers_num=db.dossiers.find().count(),
                           votes_num=db.ep_votes.find().count(),
                           meps_num=db.ep_meps.find().count())

#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Search
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/search')
def search():
    db = connect_db()
    if not request.args.get('q'):
        return ''
    q = request.args.get('q')
    ret = []
    if request.args.get('s_meps'):
        ret.extend(db.ep_meps.find({'Name.full': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}))
    if request.args.get('s_dossiers'):
        print q
        ret.extend(db.dossiers.find({'procedure.title': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}))
    '''
    if request.headers.get('X-Requested-With'):
        return json.dumps(ret)
    '''
    if len(ret)==1:
        if 'procedure' in ret[0]:
            return view_dossier(ret[0]['procedure']['reference'])
        if 'Name' in ret[0]:
            return view_mep(ret[0]['Name']['full'])
    return render_template('search_results.html', query=q,
                           results=ret)


#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Notifications
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/notification')
def gen_notif_id():
    from random import choice
    db = connect_db()
    while True:
        nid = ''.join([chr(randint(97, 122)) if randint(0, 5) else choice("_-.") for x in range(10)])
        if not db.notifications.find({'id': nid}).count():
            break
    return '/notification/'+nid

@app.route('/notification/<string:g_id>')
def notification_view_or_create(g_id):
    db = connect_db()
    # TODO g_id validation
    group = db.notifications.find_one({'id': g_id})
    if not group:
        group = {'id': g_id, 'active_emails': [], 'dossiers': [], 'restricted': False, 'actions' :[]}
        db.notifications.save(group)
    return render_template('view_notif_group.html',
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
        if db.notifications.find({'active_emails': value}).count():
            return 'already subscribed to this group'
        item = 'actions'
        # TODO validation
        addr = db.notifications.find_one({'actions.address': value})
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
        if db.notifications.find({'dossiers': value}).count():
            return 'OK'
        i = db.dossiers.find_one({'procedure.reference': value})
        if not i:
            return 'unknown dossier - '+value
        i = i['procedure']['reference']

    group[item].append(i)
    db.notifications.save(group)
    return 'OK'

@app.route('/activate')
def activate():
    db = connect_db()
    k = request.args.get('key')
    if not k:
        return 'Missing key'
    notif = db.notifications.find_one({'actions.token': k})
    if notif:
        for action in notif['actions']:
            if action.get('token') == k:
                if not action['address'] in notif['active_emails']:
                    notif['active_emails'].append(action['address'])
                notif['actions'].remove(action)
                db.notifications.save(notif)
                break
        # TODO activation method
        return 'activated'
    return 'wrong key'

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
    from parltrack.views.views import mepRanking
    date=getDate()
    rankings=mepRanking(date,query)
    if not rankings:
        abort(404)
    if request.args.get('format','')=='json':
        return jsonify(count=len(rankings), meps=tojson([z for x,y,z in rankings]))
    return render_template('mep_ranking.html',
                           rankings=rankings,
                           d=date,
                           url=request.base_url,
                           **kwargs)

@app.route('/meps/<string:country>/<path:group>')
def mepfilter(country, group):
    query={}
    args={}
    date=getDate()
    if country.upper() in COUNTRIES.keys():
        query["Constituencies"]={'$elemMatch' :
                                 {'start' : {'$lt': date},
                                  'country': COUNTRIES[country.upper()],
                                  "end" : {'$gt': date},}}
        args['country']=COUNTRIES[country.upper()]
    else:
        query["Constituencies"]={'$elemMatch' :
                                 {'start' : {'$lt': date},
                                  "end" : {'$gt': date},}}
        group="%s/%s" % (country, group)
    if group in groupids:
        query['Groups']={'$elemMatch' :
                         {'groupid': group,
                          'start' : {'$lt': date},
                          "end" : {'$gt': date},}}
        args['group']=group
    if not args:
        abort(404)
    return render_meps(query, args)

@app.route('/meps/<path:p1>')
def mepsbygroup(p1):
    query={}
    args={}
    date=getDate()
    if p1 in groupids:
        query['Groups']={'$elemMatch' :
                         {'groupid': p1,
                          'start' : {'$lt': date},
                          "end" : {'$gt': date},}}
        args['group']=p1
    elif p1.upper() in COUNTRIES.keys():
        query["Constituencies"]={'$elemMatch' :
                                 {'start' : {'$lt': date},
                                  'country': COUNTRIES[p1.upper()],
                                  "end" : {'$gt': date},}}
        args['country']=COUNTRIES[p1.upper()]
    else:
        abort(404)
    return render_meps(query, args)

@app.route('/meps/')
def ranking():
    query={}
    date=getDate()
    query={"Constituencies": {'$elemMatch' :
                             {'start' : {'$lt': date},
                              'end' : {'$gt': date},}}}
    return render_meps(query)

@app.route('/mep/<string:d_id>')
def view_mep(d_id):
    from parltrack.views.views import mep
    m=mep(d_id)
    if not m:
        abort(404)
    if request.args.get('format','')=='json':
        return jsonify(tojson(m))
    return render_template('mep.html',
                           mep=m,
                           d=d_id,
                           today=datetime.now(),
                           url=request.base_url)

#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Dossiers
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/dossier/<path:d_id>')
def view_dossier(d_id):
    from parltrack.views.views import dossier
    d=dossier(d_id)
    if not d:
        abort(404)
    #print d
    if request.args.get('format','')=='json':
        return jsonify(tojson(d))
    return render_template('dossier.html',
                           dossier=d,
                           d=d_id,
                           url=request.base_url)

#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#              Committees
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/committee/<string:c_id>')
def view_committee(c_id):
    from parltrack.views.views import committee
    c=committee(c_id)
    if not c:
        abort(404)
    if request.args.get('format','')=='json':
        return jsonify(tojson(c))
    return render_template('committee.html',
                           committee=c,
                           Committee=COMMITTEE_MAP[c_id],
                           c=c_id,
                           url=request.base_url)

@app.template_filter()
def asdate(value):
    return value.strftime('%Y/%m/%d')

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

if __name__ == '__main__':
    app.run(debug=True)
