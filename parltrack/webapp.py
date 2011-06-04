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
from flask import Flask, render_template, request, jsonify
from parltrack import default_settings
from datetime import datetime
from random import randint
from hashlib import sha1
from werkzeug import ImmutableDict
from bson.objectid import ObjectId

Flask.jinja_options = ImmutableDict({'extensions': ['jinja2.ext.autoescape', 'jinja2.ext.with_', 'jinja2.ext.loopcontrols']})
app = Flask(__name__)
app.config.from_object(default_settings)
app.config.from_envvar('PARLTRACK_SETTINGS', silent=True)
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
def inject_date():
    return dict(now_date=datetime.now())

@app.route('/')
def index():
    db = connect_db()
    return render_template('index.html', dossiers_num=db.dossiers.find().count(), votes_num=db.ep_votes.find().count(), meps_num=db.ep_meps.find().count())

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
        ret.extend(db.dossiers.find({'procedure.reference': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}))
    '''
    if request.headers.get('X-Requested-With'):
        return json.dumps(ret)
    '''
    if len(ret)==1:
        if 'procedure' in ret[0]:
            return view_dossier(ret[0]['procedure']['reference'])
        if 'Name' in ret[0]:
            return view_mep(ret[0]['Name']['full'])
    return render_template('search_results.html', query=q, results=ret)


#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Notifications
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/notifications/<string:g_id>')
def notification_view_or_create(g_id):
    db = connect_db()
    # TODO g_id validation
    group = db.notifications.find_one({'id': g_id})
    if not group:
        group = {'id': g_id, 'active_emails': [], 'dossiers': [], 'pending_emails': [], 'restricted': False}
        db.notifications.save(group)
    return render_template('view_notif_group.html', group=group)

@app.route('/notifications/<string:g_id>/add/<any(dossiers, pending_emails):item>/<path:value>')
def notification_add_detail(g_id, item, value):
    db = connect_db()
    group = db.notifications.find_one({'id': g_id})
    if not group:
        return 'unknown group '+g_id
    # TODO handle restricted groups
    #if group.restricted:
    #    return 'restricted group'
    if item == 'pending_emails':
        # TODO validation, mail sending
        addr = db.notifications.find_one({'pending_emails.address': value})
        if addr:
            # or just return with OK?! -> more privacy but harder debug
            return 'Already subscribed'
        i = {'address': value, 'token': sha1(''.join([chr(randint(32, 122)) for x in range(12)])).hexdigest(), 'date': datetime.now()}
        msg = Message("Parltrack Notification Subscription Verification",
                sender = "asdf@localhost",
                recipients = [value])
        msg.body = "your verification key is %sactivate?key=%s" % (request.url_root, i['token'])
        mail.send(msg)

    else:
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
    if not request.args.get('key'):
        return 'Missing key'
    k = request.args.get('key')
    if db.notifications.find({'pending_emails.token': k}).count():
        # TODO activation method
        return 'activated'
    elif db.notifications.find({'actions.token': k}).count():
        # TODO
        return 'action activation'
    return 'wrong key'

#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Meps
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/meps/<path:date>')
def ranking(date):
    from parltrack.views.views import mepRanking
    rankings=mepRanking(date)
    if request.args.get('format','')=='json':
        return jsonify(count=len(rankings), meps=tojson([z for x,y,z in rankings]))
    return render_template('mep_ranking.html', rankings=rankings, d=date)

@app.route('/group/<string:g_id>/<path:date>')
def bygroup(g_id, date):
    from parltrack.views.views import mepRanking
    query={'Groups.groupid': g_id}
    rankings=mepRanking(date,query)
    if request.args.get('format','')=='json':
        return jsonify(count=len(rankings), meps=tojson([z for x,y,z in rankings]))
    return render_template('mep_ranking.html', rankings=rankings, d=date, group=g_id)

@app.route('/mep/<string:d_id>')
def view_mep(d_id):
    from parltrack.views.views import mep
    m=mep(d_id)
    if request.args.get('format','')=='json':
        return jsonify(tojson(m))
    return render_template('mep.html', mep=m, d=d_id, today=datetime.now())


#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Dossiers
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/dossier/<path:d_id>')
def view_dossier(d_id):
    from parltrack.views.views import dossier
    d=dossier(d_id)
    if request.args.get('format','')=='json':
        return jsonify(tojson(d))
    return render_template('dossier.html', dossier=d, d=d_id)

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
