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

import os, re
from pymongo import Connection
from flaskext.mail import Mail, Message
from flaskext.cache import Cache
from flask import Flask, render_template, request, jsonify, abort, redirect
from parltrack import default_settings
from datetime import datetime, date
from random import randint, choice, shuffle, randrange
from hashlib import sha1
from werkzeug import ImmutableDict
from bson.objectid import ObjectId
from parltrack.scrapers.ep_meps import groupids, COUNTRIES, SEIRTNUOC
from parltrack.scrapers.ep_com_meets import COMMITTEES, COMMITTEE_MAP
from parltrack.scrapers.mappings import ALL_STAGES, STAGES
from bson.code import Code
from operator import itemgetter

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

#@cache.cached()
@app.route('/')
def index():
    db = connect_db()
    tmp=dict([(x[u'procedure.stage_reached'],int(x['count'])) for x in db.dossiers.group({'procedure.stage_reached': True},
                                                                                  {},
                                                                                  {'count': 0},
                                                                                  Code('function(doc, out){ out.count++ }'))])
    stages=[(k,tmp[k]) for k in ALL_STAGES if tmp.get(k)]
    return render_template('index.html',
                           stages=stages,
                           dossiers_num=db.dossiers.find().count(),
                           votes_num=db.ep_votes.find().count(),
                           meps_num=db.ep_meps.find().count())

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
        ret.extend(db.ep_meps.find({'Name.full': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}))
    if request.args.get('s_dossiers'):
        m=celexre.match(q)
        if m:
            ret.extend(db.dossiers.find({'activities.documents.title': "3%sL%04d" % (m.group(2),int(m.group(3)))}))
        ret.extend(db.dossiers.find({'procedure.title': {'$regex': re.compile('.*'+re.escape(q)+'.*', re.I | re.U)}}))
    #if request.headers.get('X-Requested-With'):
    if request.args.get('format')=='json':
        return jsonify(count=len(ret), items=tojson(ret))
    if len(ret)==1:
        if 'procedure' in ret[0]:
            return redirect('/dossier/%s' % ret[0]['procedure']['reference'])
            #return view_dossier(ret[0]['procedure']['reference'])
        if 'Name' in ret[0]:
            return redirect('/mep/%s' % (ret[0]['Name']['full']))
            #return view_mep(ret[0]['Name']['full'])
    return render_template('search_results.html', query=q,
                           results=ret)


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
    db = connect_db()
    if 'agents' in d['procedure']:
        d['rapporteur']=[dict(y)
                         for y
                         in set([(('name', x['name']), ('grp', x['group']))
                                 for x in d['procedure']['agents']
                                 if x.get('responsible') and x.get('name')])]
    forecasts=[]
    for act in d['activities']:
        if act['type']=='Forecast':
            forecasts.append({'date':datetime.strptime(act['date'], "%Y-%m-%d"),
                              'title': ' '.join(act['title'].split())})
        if act['type'] in ['Non-legislative initial document',
                           'Commission/Council: initial legislative document']:
            if 'comdoc' in d:
                print 'WTF? there is already a comdoc'
                raise
            d['comdoc']={'title': act['documents'][0]['title'],
                         'url': act['documents'][0].get('url'), }
    for item in db.ep_com_meets.find({'docref': d['_id']}):
        d['activities'].insert(0,{'type': 'Forecast',
                                  'body': 'EP',
                                  'date': item['meeting_date'],
                                  'title': 'EP: on %s agenda' % item['committee']})
        forecasts.append({'date': item['meeting_date'],
                          'title': 'EP: on %s agenda' % item['committee']})
        if 'tabling_deadline' in item and item['tabling_deadline']>=datetime.now():
            d['activities'].insert(0,{'type': 'Forecast',
                                      'body': 'EP',
                                      'date': item['tabling_deadline'],
                                      'title': 'EP %s Deadline for tabling ammendments' % item['committee']})
            forecasts.append({'date': item['tabling_deadline'],
                              'title': 'EP: %s Deadline for tabling ammendments' % item['committee']})
    d['forecasts']=sorted(forecasts, key=itemgetter('date'))
    return d

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
        ds=[listdossiers(d) for d in db.dossiers.find({'procedure.reference': { '$in' : group['dossiers'] } })]
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
        i = db.dossiers.find_one({'procedure.reference': value})
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
                           groupids=groupids,
                           url=request.base_url,
                           **kwargs)

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

@app.route('/meps/')
def ranking():
    query={}
    date=getDate()
    query={"Constituencies": {'$elemMatch' :
                             {'start' : {'$lte': date},
                              'end' : {'$gte': date},}}}
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
                           group_cutoff=datetime(2004,7,20),
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

@app.route('/new/')
def new_docs():
    db = connect_db()
    d=db.dossiers.find().sort([('meta.created', -1)]).limit(30)
    if request.args.get('format','')=='json':
        return jsonify(tojson(d))
    #if request.args.get('format','')=='atom':
    return render_template('atom.xml', dossiers=list(d), path="new")

@app.route('/changed/')
def changed():
    db = connect_db()
    d=db.dossiers.find().sort([('meta.updated', -1)]).limit(30)
    if request.args.get('format','')=='json':
        return jsonify(tojson(d))
    #if request.args.get('format','')=='atom':
    return render_template('atom.xml', dossiers=list(d), path="changed")

@app.route('/dossiers')
def active_dossiers():
    db = connect_db()
    query={'procedure.stage_reached': { "$in": STAGES } }
    ds=[listdossiers(d) for d in db.dossiers.find(query)]
    return render_template('active_dossiers.html',
                           dossiers=ds,
                           date=datetime.now())

#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#              Committees
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/committee/<string:c_id>')
def view_committee(c_id):
    from parltrack.views.views import committee
    c=committee(c_id)
    c['dossiers']=[listdossiers(d) for d in c['dossiers']]
    if not c:
        abort(404)
    if request.args.get('format','')=='json':
        return jsonify(tojson(c))
    return render_template('committee.html',
                           committee=c,
                           Committee=COMMITTEE_MAP[c_id],
                           today=datetime.now(),
                           groupids=groupids,
                           c=c_id,
                           url=request.base_url)

@app.template_filter()
def asdate(value):
    date=value.strftime('%Y/%m/%d %H:%M')
    if not date.endswith(" 00:00"):
        return date
    else: return date[:-len(" 00:00")]

@app.template_filter()
def isodate(value):
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

if __name__ == '__main__':
    app.run(debug=True)
