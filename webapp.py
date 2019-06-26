#----------------------------------------------------------------------------#
# Imports
#----------------------------------------------------------------------------#

import logging
import os

import config
import notification_model as notif

import diff_match_patch

from math import ceil, floor
from datetime import datetime, date
from flask import Flask, render_template, request
from flask import Flask, render_template, request, redirect
from flask.json import jsonify
from flask_mail import Message, Mail
from hashlib import sha1
from jinja2 import escape
from logging import Formatter, FileHandler
from pprint import pprint
from random import shuffle, randrange, randint, choice
from sys import version_info
from urllib.parse import unquote
from utils.utils import asDate, clean_lb, jdump
from utils.devents import merge_events
from utils.objchanges import getitem
from utils.mappings import (
    SEIRTNUOC as COUNTRIES,
    COUNTRIES as COUNTRY_ABBRS,
    COMMITTEE_MAP,
    stage2percent,
)

from db import Client

db = Client()

if version_info[0] == 3:
    unicode = str

ep_wtf_dossiers = {
    '2012/2039(INI)': "This dossier is a true EPWTF and you need to consider it together with <a href='/dossier/2012/2039(INL)'>2012/2039(INL)</a>",
    '2012/2039(INL)': "This dossier is a true EPWTF and you need to consider it together with <a href='/dossier/2012/2039(INI)'>2012/2039(INI)</a>"
}

mepnames = db.names_by_mepids(db.keys('ep_meps', None))

def highlight(q, s):
    s = str(escape(s))
    q = set(q.lower().split())
    for w in set(s.split()):
        if w.lower() in q:
            s = s.replace(w, '<span class="highlight">'+w+'</span>')
    return s

#----------------------------------------------------------------------------#
# App Config.
#----------------------------------------------------------------------------#

app = Flask(__name__)
app.config.from_object('config')
mail = Mail()
mail.init_app(app)

def get_changes(obj, path):
    ret = []
    for date, changelog in obj['changes'].items():
        for c in changelog:
            if c['path'][:len(path)] == path:
                ret.append({'date': date, 'type': c['type'], 'data': c['data']})
    return getitem(obj, path), ret


def render(template, **kwargs):
    if request.args.get('format') == 'json':
        if 'exclude_from_json' in kwargs:
            for v in set(kwargs['exclude_from_json']):
                del(kwargs[v])
            del(kwargs['exclude_from_json'])
        return jsonify(kwargs)
    if request.args.get('q'):
        kwargs['q'] = request.args['q']
    if request.args.get('party'):
        display_mode = request.args['party']
    else:
        display_mode = ''
    kwargs['highlight'] = highlight
    kwargs['display_mode'] = display_mode
    kwargs['committee_map'] = COMMITTEE_MAP
    kwargs['today'] = date.today().strftime("%Y-%m-%d")
    kwargs['countries'] = COUNTRIES
    kwargs['country_abbrs'] = COUNTRY_ABBRS
    kwargs['get_changes'] = get_changes
    return render_template(template, **kwargs)


#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#


@app.route('/')
def home():
    date = getDate()
    meps = db.count('ep_meps', None) or 0
    dossiers = db.count('ep_dossiers', None) or 0
    active_meps = db.count('meps_by_activity', "active") or 0
    votes = db.count('ep_votes', None) or 0
    amendments = db.count('ep_amendments', None) or 0
    return render(
        'index.html',
        mep_count="{:,}".format(meps),
        dossier_count="{:,}".format(dossiers),
        active_mep_count="{:,}".format(active_meps),
        votes="{:,}".format(votes),
        amendments="{:,}".format(amendments),
    )


@app.route('/about')
def about():
    return render('about.html')


@app.route('/dumps')
def dumps():
    return render('dumps.html')

group_positions={u'Chair': 10,
                 u'Treasurer/Vice-Chair/Member of the Bureau': 10,
                 u'Co-Chair': 8,
                 u'First Vice-Chair/Member of the Bureau': 8,
                 u'Vice-Chair': 6,
                 u"Vice-President": 6,
                 u'Deputy Chair': 5,
                 u'Chair of the Bureau': 4,
                 u'Vice-Chair/Member of the Bureau': 8,
                 u'Secretary to the Bureau': 4,
                 u'Member of the Bureau': 2,
                 u'Treasurer': 2,
                 u'Co-treasurer': 1,
                 u'Deputy Treasurer': 1,
                 u'Member': 0,
                 u'Observer': 0,
                 u'': 0,
                 }
com_positions={"Chair": 4,
               "Vice-President": 3,
               "Vice-Chair": 3,
               "Member": 2,
               "Substitute": 1,
               'Observer': 0,
               }
staff_positions={"President": 7,
                 "Chair": 6,
                 "Vice-President": 6,
                 "Quaestor": 5,
                 "Member": 4,
                 'Observer': 0,
                 }

@app.route('/meps')
def meps():
    # TODO date handling
    date = asdate(datetime.now())
    meps = db.meps_by_activity(True)
    rankedMeps=[]
    for mep in meps:
        score=0
        ranks=[]
        # get group rank
        for group in mep.get('Groups',[]):
            if not 'end' in group or (group['start']<=date and group['end']>=date):
                if not 'role' in group:
                    group['role']='Member'
                score=group_positions.get(group['role'], 1)
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
            if not 'end' in com or (com['start']<=date and com['end']>=date):
                score+=com_positions[com['role']]
                ranks.append((com_positions[com['role']],com['role'],com['Organization']))
                tmp.append(com)
        mep['Committees']=tmp
        # get ep staff ranks
        tmp=[]
        for staff in mep.get('Staff',[]):
            if not 'end' in staff or (staff['start']<=date and staff['end']>=date):
                score+=staff_positions[staff['role']]
                ranks.append((staff_positions[staff['role']],staff['role'],staff['Organization']))
                tmp.append(staff)
        if len(tmp):
            mep['Staff']=tmp
        rankedMeps.append((score,sorted(ranks, reverse=True),mep))
    return render('meps.html', date=date, meps=[x for x in sorted(rankedMeps,key=lambda x: x[0], reverse=True)])


@app.route('/mep/<int:mep_id>/<string:mep_name>')
def mep(mep_id, mep_name):
    mep = db.mep(mep_id)
    if not mep:
        return not_found_error(None)
    amendments = db.get("ams_by_mep", mep_id) or []
    activities = db.activities(mep_id) or []
    acts = {'types':{}, 'dossiers':{}}
    acts['types']['amendments'] = len(amendments)
    for a in amendments:
        if not a['reference'] in acts['dossiers']:
            acts['dossiers'][a['reference']] = 1
        else:
            acts['dossiers'][a['reference']] += 1

    for a,v in activities.items():
        if a in ('meta', 'changes') or not isinstance(v, list):
            continue
        acts['types'][a] = len(v)
        for e in v:
            if not 'dossiers' in e:
                continue
            for d in e['dossiers']:
                if not d in acts['dossiers']:
                    acts['dossiers'][d] = 1
                else:
                    acts['dossiers'][d] += 1

    acts['types']={k: v for k,v in sorted(acts['types'].items(), key=lambda x:asactivity(x[0]))}
    acts['dossiers']={k: v for k,v in sorted(acts['dossiers'].items(), key=lambda x: x[1], reverse=True)}
    mep['activities'] = acts

    if isinstance(mep.get('CV'),list):
        mep['CV']={'': mep['CV']}
    mep['dossiers'] = sorted(db.get('dossiers_by_mep',mep_id) or [], reverse=True)
    return render(
        'mep.html',
        mep=mep,
        d=mep_id,
        group_cutoff=datetime(2004,7,20).strftime("%Y-%m-%d"),
        # TODO
        committees={},
        exclude_from_json=('d', 'group_cutoff', 'committees'),
    )


@app.route('/activities/<int:mep_id>', defaults={'d_id':None, 't':None})
@app.route('/activities/<int:mep_id>/type/<string:t>', defaults={'d_id':None})
@app.route('/activities/<int:mep_id>/dossier/<path:d_id>', defaults={'t':None})
@app.route('/activities/<int:mep_id>/<string:t>/<path:d_id>')
def activities(mep_id, t, d_id):
    if mep_id not in mepnames:
        return render('errors/404.html'), 404
    a = db.activities(mep_id, t, d_id) or {}
    if t == 'amendment' or t is None:
        ams = db.get('ams_by_mep',mep_id)
        print(len(ams))
        if d_id is not None:
            ams = [a for a in ams if a['reference']==d_id]
        a['amendments'] = sorted(ams, key=lambda x: (x['reference'], -x['seq']), reverse=True)
    return render(
        'activities.html',
        activities=a,
        mep_name=mepnames.get(mep_id),
        mep_id=mep_id,
        type=t,
        dossier_id=d_id,
    )



@app.route('/mep/<int:mep_id>')
def mep_id(mep_id):
    mep = db.mep(mep_id)
    if not mep:
        return not_found_error(None)
    return redirect('/mep/{0}/{1}'.format(mep_id, mep['Name']['full']))


@app.route('/mep/<string:mep_name>')
def mep_name(mep_name):
    meps = db.meps_by_name(mep_name)

    if not meps:
        return not_found_error(None)
    if len(meps) == 1:
        return redirect('/mep/{0}/{1}'.format(meps[0]['UserID'], meps[0]['Name']['full']))
    return render("mep_select.html", meps=meps)


@app.route('/dossiers')
def dossiers():
    date = getDate()
    dossiers = db.dossiers_by_activity(True)
    ds = []
    for d in dossiers:
        lead_c = [x['committee'] for x in d.get('committees', []) if x.get('type') == "Responsible Committee"]
        ds.append({
            'reference': d['procedure']['reference'],
            'title': d['procedure']['title'],
            'stage_reached': d['procedure']['stage_reached'],
            'lead_committee': '' if not lead_c else lead_c[0],
        })
    return render('dossiers.html', dossiers=ds, date=date)

# these dossiers have been scraped by us in v1, but are not existing anymore as
# of 20190605, we keep them and display them using the old v1 template.
v1dossiers = {
    '1991/2118(INS)', '1992/2223(INS)', '1994/2195(INI)', '1995/2078(INI)', '1995/2189(INI)', '1996/2143(INI)', '1997/2015(INI)', '1997/2044(INI)', '1998/2041(INI)',
    '1998/2077(INI)', '1998/2078(INI)', '1998/2101(INI)', '1998/2165(INI)', '1999/2010(INS)', '1999/2184(INI)', '2000/2126(INI)', '2000/2323(INI)', '2001/2061(INI)',
    '2001/2069(INI)', '2002/2264(INI)', '2003/2004(INI)', '2003/2057(INI)', '2003/2107(INI)', '2004/2125(INI)', '2005/2122(INI)', '2005/2138(IMM)', '2005/2148(INI)',
    '2005/2176(IMM)', '2006/2013(INI)', '2006/2014(INI)', '2006/2015(INI)', '2006/2059(INI)', '2007/0181(CNS)', '2008/2093(IMM)', '2008/2117(INI)', '2008/2121(INI)',
    '2009/2029(REG)', '2009/2134(INL)', '2009/2170(INI)', '2009/2239(INI)', '2009/2816(RSP)', '2010/2073(INI)', '2011/0341(COD)', '2011/0901(COD)', '2011/2176(INI)',
    '2011/2184(INI)', '2011/2257(REG)', '2011/2304(IMM)', '2012/0033(NLE)', '2012/0219(NLE)', '2012/2012(REG)', '2012/2024(INI)', '2012/2061(INI)', '2012/2146(IMM)',
    '2012/2241(IMM)', '2012/2260(INI)', '2012/2274(IMM)', '2012/2303(INI)', '2012/2309(INI)', '2012/2317(INI)', '2012/2324(INI)', '2012/2686(RSP)', '2012/2807(RSP)',
    '2012/2817(RSP)', '2012/2863(RSP)', '2012/2899(RSP)', '2013/0120(NLE)', '2013/0151(NLE)', '2013/0267(NLE)', '2013/2046(INI)', '2013/2089(INI)', '2013/2102(INI)',
    '2013/2129(INI)', '2013/2167(INI)', '2013/2171(INI)', '2013/2184(INI)', '2013/2191(IMM)', '2013/2271(IMM)', '2013/2280(IMM)', '2013/2692(RSP)', '2013/2739(RSP)',
    '2013/2847(RPS)', '2013/2887(RSP)', '2014/2009(INI)', '2014/2034(IMM)', '2014/2227(IMM)', '2014/2536(RSP)', '2014/2557(RSO)', '2014/2604(RSP)', '2014/3015(RSP)',
    '2015/2009(INI)', '2015/2073(IMM)', '2015/2081(INI)', '2015/2594(RSP)', '2015/2600(RSP)', '2015/2659(RSP)', '2015/2901(RSP)', '2015/2996(RSP)', '2015/3029(RSP)',
    '2016/0357(COD)', '2016/0360(COD)', '2016/2031(INI)', '2016/2040(IMM)', '2016/2069(IMM)', '2016/2205(DEC)', '2016/2661(RSP)', '2017/2034(IMM)', '2017/2062(IMM)',
    '2017/2205(INL)', '2017/2207(INI)', '2017/2264(REG)', '2017/2595(RSP)', '2017/2657(RSP)', '2017/2836(RSP)', '2017/2872(RSP)', '2017/2902(RSP)', '2018/0330(COD)',
    '2018/2002(INL)', '2018/2027(IMM)', '2018/2033(INI)', '2018/2087(INI)', '2018/2154(INI)', '2018/2917(RSP)', '2018/2921(RSP)'
}

@app.route('/dossier/<path:d_id>')
def dossier(d_id):
    d = db.dossier(d_id)
    if not d:
        return not_found_error(None)
    d['amendments'] = db.get("ams_by_dossier", d_id) or []
    d['vmatrix'] = votematrices(db.get('votes_by_dossier',d_id) or [])
    if d_id in v1dossiers:
        template = "v1dossier.html"
    else:
        template = "dossier.html"
    d['activities'] = merge_events(d)

    # get activities by meps
    meps={}
    for act, type, mepid, mepname in (db.activities_by_dossier(d_id) or []):
        if type in ["REPORT", "REPORT-SHADOW", "COMPARL"]: continue
        if type == 'COMPARL-SHADOW':
            continue
        #    pass # todo add this to the committee info
        #else:
        if not mepid in meps: meps[mepid]={'name': mepname, 'types': {}}
        if not type in meps[mepid]['types']: meps[mepid]['types'][type]=[]
        meps[mepid]['types'][type].append(act)
    # todo sort meps by number of activities
    d['activities']=sorted(meps.items(), key=lambda x: sum(len(y) for y in x[1]['types'].values()), reverse=True)
    types = {
        'CRE': 'Plenary Speeches',
        "MOTION": 'Institutional Motions',
        "OQ": 'Oral Questions',
        'WEXP': 'Written Explanations',
        'MINT': 'Major Interpellations',
        "WQ": 'Written Questions',
        "IMOTION": 'Individiual Motions',
        "WDECL": 'Written Declarations',
    }

    progress = 0
    for a in d.get('events',[]):
        if a.get('type') in stage2percent:
            progress = stage2percent[a['type']]
            break
    stage_progress = stage2percent.get(d['procedure'].get('stage_reached'), 0)
    progress = max(progress, stage_progress)
    return render(
        template,
        dossier=d,
        d=d_id,
        url=request.base_url,
        now_date=date.today().strftime("%Y-%m-%d"),
        progress=progress,
        TYPES=types,
        msg=ep_wtf_dossiers.get(d_id),
        exclude_from_json=('now_date', 'url', 'd', 'progress', 'TYPES'),
    )


@app.route('/committees')
def committees():
    r = db.keys('dossiers_by_committee', count=True) or {}
    s = sorted(x for x in r.keys())
    return render('committees.html', committees=s, dossier_count=r)


@app.route('/committee/<string:c_id>')
def committee(c_id):
    c = db.get('com_votes_by_committee', c_id) or None
    return render('committee.html', committee=c)


@app.route('/subjects')
def subjects():
    r = db.keys('dossiers_by_subject', count=True) or {}
    s = sorted(x for x in r.keys())
    sm = db.get('subject_map',None)
    return render('subjects.html', subjects=s, dossier_count=r, subjectmap=sm, exclude_from_json=('subjects','subjectmap'))


@app.route('/subject/<path:subject>')
def subject(subject):
    r = sorted(db.get('dossiers_by_subject', subject) or [], key=lambda x: x['procedure']['reference'], reverse=True)
    sm = db.get('subject_map',None)
    if not r:
        return not_found_error(None)
    return render('subject.html', dossiers=r, subject=subject, subjectmap=sm, exclude_from_json=('subjectmap'))


def dossier_sort_key(d):
    if not 'activities' in d:
        return ''
    return d['activities'][-1]['date']


def mep_sort_key(m):
    return m['Name']['full']


@app.route('/search')
def search():
    q = request.args.get('q')
    if not q:
        return redirect('/')
    dossiers = db.search('ep_dossiers', q) or []
    meps = db.meps_by_name(q) or db.search('ep_meps', q) or []
    res = {
        'meps': sorted(meps, key=mep_sort_key),
        'dossiers': sorted(dossiers, key=dossier_sort_key, reverse=True),
    }
    result_count = 0
    for k in res:
        result_count += len(res[k])
    return render(
        'results.html',
        res=res,
        result_count=result_count,
        countries=COUNTRIES,
    )


#-[+++++++++++++++++++++++++++++++++++++++++++++++|
#               Notifications
#-[+++++++++++++++++++++++++++++++++++++++++++++++|

@app.route('/notification')
def gen_notif_id():
    while True:
        nid = ''.join(chr(randint(97, 122)) if randint(0, 10) else choice("_-") for x in range(16))
        if not notif.session.query(notif.Group).filter(notif.Group.name==nid).first():
            break
    return '/notification/'+nid

def listdossiers(d):
    for act in d['activities']:
        if act.get('type') in ['Non-legislative initial document',
                               'Commission/Council: initial legislative document',
                               "Legislative proposal",
                               "Legislative proposal published"]:
            if 'title' in act.get('docs',[{}])[0]:
                d['comdoc']={'title': act['docs'][0]['title'],
                             'url': act['docs'][0].get('url'), }
        if 'date' not in act:
            print('removing [%s] %s' % (d['activities'].index(act), act))
            del d['activities'][d['activities'].index(act)]
    if 'legal_basis' in d.get('procedure', {}):
        clean_lb(d)
    # TODO
    #db = connect_db()
    #for item in db.ep_comagendas.find({'epdoc': d['procedure']['reference']}):
    #    if 'tabling_deadline' in item and item['tabling_deadline']>=datetime.now():
    #        d['activities'].insert(0,{'type': '(%s) Tabling Deadline' % item['committee'], 'body': 'EP', 'date': item['tabling_deadline']})
    return d


@app.route('/notification/<string:g_id>')
def notification_view_or_create(g_id):
    # TODO g_id validation
    group = notif.session.query(notif.Group).filter(notif.Group.name==g_id).first()
    if not group:
        group = notif.Group(name=g_id, activation_key=gen_token())
        notif.session.add(group)
        notif.session.commit()
    ds=[]
    ids=[]
    active_items = [d for d in group.items if not d.activation_key]
    inactive_items = [d for d in group.items if d.activation_key]
    if len(active_items):
        ds=[listdossiers(db.dossier(d.name)) for d in active_items if d.type=='dossiers']
    if len(inactive_items):
        ids=[listdossiers(db.dossier(d.name)) for d in inactive_items if d.type=='dossiers']
    if ds and request.args.get('format','')=='json' or request.headers.get('X-Requested-With'):
        return jsonify(count=len(ds), dossiers=tojson(ds))
    return render('view_notif_group.html',
                           dossiers=ds,
                           active_dossiers=len(ds),
                           inactive_dossiers=len(ids),
                           date=datetime.now(),
                           group=group)


@app.route('/notification/<string:g_id>/add/<any(dossiers, emails, subject):item>/<path:value>')
def notification_add_detail(g_id, item, value):
    group = notif.session.query(notif.Group).filter(notif.Group.name==g_id).first()
    if not group:
        return 'unknown group '+g_id
    # TODO handle restricted groups
    #if group.restricted:
    #    return 'restricted group'
    email = group.subscribers[0].email
    if item == 'emails':
        email = value
        emails = [s.email for s in group.subscribers]
        active_emails = [s.email for s in group.subscribers if not s.activation_key]
        if value in emails:
            return 'already subscribed to this group'
        i = notif.Subscriber(email=value, activation_key=gen_token())
        group.subscribers.append(i)

    elif item == 'dossiers':
        d = db.dossier_by_id(value)
        if not d:
            return 'unknown dossier - '+value
        i = notif.Item(name=value, type='dossier', activation_key=gen_token())
        group.items.append(i)
    elif item == 'subject':
        i = notif.Item(name=value, type='subject', activation_key=gen_token())
        group.items.append(i)
    msg = Message("Parltrack Notification Subscription Verification",
            sender = "parltrack@parltrack.euwiki.org",
            recipients = [email])
    msg.body = "Your verification key is %sactivate?key=%s\nNotification group url: %snotification/%s" % (request.url_root, i.activation_key, request.url_root, g_id)
    mail.send(msg)

    notif.session.add(i)
    notif.session.commit()
    return 'OK'


@app.route('/notification/<string:g_id>/del/<any(dossiers, emails):item>/<path:value>')
def notification_del_detail(g_id, item, value):
    group = notif.session.query(notif.Group).filter(notif.Group.name==g_id).first()
    if not group:
        return 'unknown group '+g_id
    # TODO handle restricted groups
    #if group.restricted:
    #    return 'restricted group'
    if item == 'emails':
        active_emails = [s.email for s in group.subscribers if not s.activation_key]
        if value not in 'active_emails':
            return 'Cannot complete this action'
        sub = None
        for x in group.subscribers:
            if x.email == value:
                sub = x
                break
        if not sub:
            return 'Cannot complete this action'
        sub.activation_key = gen_token()
        notif.session.commit()
        msg = Message("Parltrack Notification Unsubscription Verification",
                sender = "parltrack@parltrack.euwiki.org",
                recipients = [value])
        msg.body = "Your verification key is %sactivate?key=%s&?delete=1\nNotification group url: %snotification/%s" % (request.url_root, sub.activation_key, request.url_root, g_id)
        mail.send(msg)
        db.notifications.save(group)
    # TODO items
    return 'OK'


@app.route('/activate')
def activate():
    db = connect_db()
    k = request.args.get('key')
    delete = True if request.args.get('delete') else False
    if not k:
        return 'Missing key'
    i = notif.session.query(notif.Group).filter(notif.Group.activation_key==k).first()
    if not i:
        i = notif.session.query(notif.Subscriber).filter(notif.Subscriber.activation_key==k).first()
        if not i:
            i = notif.session.query(notif.Item).filter(notif.Item.activation_key==k).first()
            if not i:
                return 'invalid item'
    if delete:
        notif.session.delete(i)
        notif.session.commit()
        return 'deactivated'
    i.activation_key = ''
    notif.session.commit()
    return 'activated'



# Error handlers.

@app.errorhandler(500)
def internal_error(error):
    #db_session.rollback()
    return render('errors/500.html'), 500


@app.errorhandler(404)
def not_found_error(error):
    return render('errors/404.html'), 404


# Helpers

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
def asdate(value):
    if not value:
        return 'unknown date'
    if isinstance(value, int):
        value=datetime.fromtimestamp(value)
    if hasattr(value, 'strftime'):
        return value.strftime('%Y/%m/%d')
    d = asDate(value)
    if d.year == 9999:
        return ''
    return d.strftime('%Y/%m/%d')


@app.template_filter()
def asdiff(obj): # should have a new and old item
    de=diff_match_patch.diff_match_patch()
    diffs=de.diff_main(' '.join (obj.get('old','')),' '.join (obj.get('new','')))
    de.diff_cleanupSemantic(diffs)
    return de.diff_prettyHtml(diffs)


@app.template_filter()
def asPE(obj): # should have a new and old item
    return unquote(obj).split('+')[2]


@app.template_filter()
def asmep(value):
    #if isinstance(value, int):
    #    value = str(value)
    if value not in mepnames:
        return '<b>Unknown MEP</b>'
    return u'<a href="/mep/%d/%s">%s</a>' % (value, mepnames[value], mepnames[value])


@app.template_filter()
def asdossier(value):
    #doc=db.get('ep_dossiers', value)
    #if not doc:
    #    return value
    return (u'<a href="/dossier/%s">%s</a>' % (value, value))


@app.template_filter()
def isodate(value):
    if type(value)==type(datetime(1,1,1)):
        return value.isoformat()
    return datetime.strptime(value[:10],'%Y-%m-%d').isoformat()


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

    for a in email_address:
        cipher_text += key[ character_set.find(a) ]

    return '<span class="protected_address" data-key="'+key+'" data-ctext="'+cipher_text+'">[javascript protected email address]</span>'


@app.template_filter()
def reftopath(ref):
    return "%s/%s" % (ref[-4:-1], ref[:9])


@app.template_filter()
def group_icon(value):
    if not value: return ''
    if type(value)==type(list()): value=value[0]
    if value=='NA': value='NI'
    return "static/images/%s.gif" % value.lower().replace('/','_')

@app.template_filter()
def asactivity(value):
    return {'CRE': 'plenary speeches',
            "REPORT": 'reports',
            "REPORT-SHADOW": 'shadow reports',
            "COMPARL": 'opinions',
            "COMPARL-SHADOW": 'shadow opinions',
            "MOTION": 'institutional motions',
            "OQ": 'oral questions',
            'WEXP': 'written explanations',
            'MINT': 'major interpellations',
            "WQ": 'written questions',
            "IMOTION": 'individual motions',
            "amendments": 'amendments',
            "WDECL": 'written declarations'}.get(value,"unknown").capitalize()


def getDate():
    date=datetime.now()
    if request.args.get('date'):
        date = asDate(request.args['date'])
    return date

def gen_token():
    return sha1(''.join([chr(randint(1, 128)) for x in range(128)]).encode()).hexdigest()


def tojson(data):
    #if type(data)==type(ObjectId()):
    #    return
    #if type(data)==type(dict()):
    #    return dict([(k,tojson(v)) for k,v in data.items() if not type(ObjectId()) in [type(k), type(v)]])
    #if '__iter__' in dir(data):
    #    return [tojson(x) for x in data if type(x)!=type(ObjectId())]
    #if hasattr(data, 'isoformat'):
    #    return data.isoformat()
    return data

def votematrices(votes):
    res = []
    for vote in votes: # can have multiple votes
        matrix = { 'title': vote['title'],
                   'time': vote['ts'],
                   'totals': dict(sorted([(c,vote['votes'][c]['total']) for c in ['+','0','-'] if c in vote['votes']],key=lambda x: x[1], reverse=True)),
                   'max': 0,
                   'countries': {},
                   'groups': {},
                   'votes': {}}
        res.append(matrix)
        meps = []
        # we need two passes over the data, to collect all meps, so we can
        # query all their contries in one go, but we can already prepare some
        # stuff in the first pass
        for type in ['+','-','0']:
            for group, vs in vote['votes'].get(type,{'groups':{}})['groups'].items():
                if group not in matrix['groups'].keys():
                    matrix['groups'][group]={'0':0,'+':0,'-':0,'total':0}
                for mep in vs:
                    if not 'mepid' in mep: continue # we skip unresolvable meps
                    meps.append((mep['mepid'],group,type))
        # query countries for meps
        mepcountries = db.countries_for_meps([m[0] for m in meps], vote['ts'])
        mepnames = db.names_by_mepids([m[0] for m in meps])
        # second pass where we create a matrix: groups x countries, where each
        # cell contains a {'0':x,'+':y,'-':z,'total':t} dict.
        # and we also create aggregate totals for groups and countries, so
        # those can be displayed as well.
        for mepid, group, choice in meps:
            if mepid in mepcountries:
                country = COUNTRIES[mepcountries[mepid]['country']]
            else:
                country = '??'
            if not country in matrix['countries']:
                matrix['countries'][country]={'0':0,'+':0,'-':0,'total':0}
            if not group in matrix['votes']:
                matrix['votes'][group]={}
            if not country in matrix['votes'][group]:
                matrix['votes'][group][country]={'0':[],'+':[],'-':[],'total':0}
            matrix['votes'][group][country][choice].append((mepnames[mepid], mepid))
            matrix['votes'][group][country]['total']+=1
            matrix['countries'][country][choice]+=1
            matrix['countries'][country]['total']+=1
            matrix['groups'][group][choice]+=1
            matrix['groups'][group]['total']+=1
        def round(x):
            if x<0: return int(floor(x))
            else: return int(ceil(x))
        # lets precalc also color class in a 3rd pass
        cgmax = max(len(c['+'])-len(c['-'])
                    for cs in matrix['votes'].values()
                    for c in cs.values()) - min(len(c['+'])-len(c['-'])
                                                for cs in matrix['votes'].values()
                                                for c in cs.values())
        cmax = max(x.get('+',0)-x.get('-',0)
                   for x in matrix['countries'].values()) - min(x.get('+',0)-x.get('-',0)
                                                                for x in matrix['countries'].values())
        gmax = max(x.get('+',0)-x.get('-',0)
                   for x in matrix['groups'].values()) - min(x.get('+',0)-x.get('-',0)
                                                             for x in matrix['groups'].values())
        for k, v in matrix['countries'].items():
            v['class']=round((v['+']-v['-'])*10/cmax)
        for k, v in matrix['groups'].items():
            v['class']=round((v['+']-v['-'])*10/gmax)
        for g, cs in matrix['votes'].items():
            for c, v in cs.items():
                v['class']=round((len(v['+'])-len(v['-']))*10/cgmax)
                for type in ['+','-','0']:
                    if type not in v: continue
                    v[type]=sorted(v[type])

        # sort countries/groups in descending order
        matrix['countries']=sorted(matrix['countries'].items(),key=lambda x: x[1]['+']-x[1]['-'],reverse=True)
        matrix['groups']=sorted(matrix['groups'].items(),key=lambda x: x[1]['+']-x[1]['-'],reverse=True)
    return res


if not config.DEBUG:
    app.logger.setLevel(logging.INFO)

#----------------------------------------------------------------------------#
# Launch.
#----------------------------------------------------------------------------#

if __name__ == '__main__':
    dossier('2016/0279(COD)')
    #app.run(host='0.0.0.0', port=config.WEBSERVER_PORT, threaded=False)
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
