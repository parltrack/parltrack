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
from flaskext.mail import Mail
from flask import Flask, render_template, request
from parltrack import default_settings
from datetime import datetime
from random import randint
from hashlib import sha1


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
        for res in db.ep_meps.find({'Name.full': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}):
            ret.append('mep: '+res['Name']['full'])
    if request.args.get('s_dossiers'):
        for res in db.dossiers.find({'procedure.reference': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}):
            ret.append('dossier: '+res['procedure']['reference'])
    '''
    if request.headers.get('X-Requested-With'):
        return json.dumps(ret)
    '''
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
        # TODO validation and mail sending
        i = {'address': value, 'token': sha1(''.join([chr(randint(32, 122)) for x in range(12)])).hexdigest(), 'date': datetime.now()}
    else:
        i = db.dossiers.find_one({'procedure.reference': value})
        if not i:
            return 'unknown dossier - '+value
        i = i['procedure']['reference']

    group[item].append(i)
    db.notifications.save(group)
    return 'OK'


#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Meps
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/meps/<path:date>')
def ranking(date):
    from parltrack.views.views import mepRanking
    rankings=mepRanking(date)
    return render_template('mep_ranking.html', rankings=rankings, d=date)

@app.route('/mep/<string:d_id>')
def view_mep(d_id):
    from parltrack.views.views import mep
    return render_template('mep.html', mep=mep(d_id), d=d_id, today=datetime.now())


#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Dossiers
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/dossier/<path:d_id>')
def view_dossier(d_id):
    from parltrack.views.views import dossier
    return render_template('dossier.html', dossier=dossier(d_id), d=d_id)

if __name__ == '__main__':
    app.run(debug=True)
