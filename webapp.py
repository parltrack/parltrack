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
from utils.utils import asDate, clean_lb, jdump, file_size
from utils.devents import merge_events
from utils.objchanges import getitem, revert
from utils.mappings import (
    SEIRTNUOC as COUNTRIES,
    COUNTRIES as COUNTRY_ABBRS,
    SPLIT_DOSSIERS as v1dossiers,
    COMMITTEE_MAP,
    GROUPIDS,
    ACTIVITY_MAP,
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
dossier_titles = db.dossier_titles()

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
    kwargs['dossier_titles'] = dossier_titles
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
    TABLE_NAMES=['ep_amendments', 'ep_comagendas',  'ep_dossiers',  'ep_mep_activities',  'ep_meps',  'ep_votes']
    arch = {}
    for file in os.listdir('/var/www/parltrack/dumps/arch'):
        table,rest = file.split('-',1)
        _date,_ = rest.split('.',1)
        if not table in arch: arch[table]=[]
        arch[table].append((file,_date))
    stats = {}
    for table in TABLE_NAMES:
        try:
            s = os.stat("/var/www/parltrack/dumps/%s.json.lz" % table)
        except:
            continue
        stats[table]={
                'size': file_size(s.st_size),
                'updated': date.fromtimestamp(s.st_mtime).isoformat()
                }
    first=True
    for file in sorted(os.listdir('/var/www/parltrack/logs'), reverse=True):
        if not file.endswith(".log.lz"): continue
        s = os.stat("/var/www/parltrack/logs/%s" % file)
        if first:
            stats['scraper_logs']={
                    'size': file_size(s.st_size),
                    'updated': date.fromtimestamp(s.st_mtime).isoformat()
                    }
            first=False
            continue
        if not 'scraper_logs' in arch: arch['scraper_logs']=[]
        arch['scraper_logs'].append((file, date.fromtimestamp(s.st_mtime).isoformat()))
    return render('dumps.html', stats=stats, arch=arch)


@app.route('/log/<string:date>')
@app.route('/log')
def logs(date=date.today().strftime("%Y-%m-%d")):
    lf = {f for f in os.listdir("/var/www/parltrack/logs") if f.endswith('.html')}
    if ('%s.html' % date) not in lf:
        print(date, lf)
        return render('errors/404.html'), 404
    with open('/var/www/parltrack/logs/%s.html' % date, 'r') as f:
        log = f.read()
    return render('log_summary.html', date=date, log=log)

group_positions={u'Chair': 10,
                 u'Treasurer/Vice-Chair/Member of the Bureau': 10,
                 u'Co-President': 9,
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

@app.route('/meps/<string:filter1>/<string:filter2>')
@app.route('/meps/<string:filter1>')
@app.route('/meps')
def meps(filter1=None, filter2=None):
    # TODO date handling
    group_filter = None
    country_filter = None
    print(repr(filter1),repr(filter2))
    if filter1 is not None:
        if filter1 in GROUPIDS:
            group_filter = filter1
        elif filter1 in COUNTRY_ABBRS:
            country_filter = filter1
        else:
            return render('errors/404.html'), 404
    if filter2 is not None:
        if country_filter is None and filter2 in COUNTRY_ABBRS:
            country_filter = filter2
        elif group_filter is None and filter2 in GROUPIDS:
            group_filter = filter2
        else:
            return render('errors/404.html'), 404
    date = asdate(datetime.now())
    meps = db.meps_by_activity(True)
    rankedMeps=[]
    for mep in meps:
        score=-1
        ranks=[]
        if country_filter is not None:
            from_country = False
            for c in mep.get('Constituencies',[]):
                if not 'end' in c or (c['start']<=date and c['end']>=date):
                    if country_filter and c.get('country')!= COUNTRY_ABBRS[country_filter]: continue
                    from_country = True
                    break
            if not from_country: continue
        in_group=False
        # get group rank
        for group in mep.get('Groups',[]):
            if not 'end' in group or (group['start']<=date and group['end']>=date):
                if group_filter and group.get('groupid')!= group_filter: continue
                if not 'role' in group:
                    group['role']='Member'
                score=group_positions.get(group['role'], 1)
                if not 'groupid' in group:
                    group['groupid']=group['Organization']
                elif type(group.get('groupid'))==list:
                    group['groupid']=group['groupid'][0]
                ranks.append((group_positions[group['role']],group['role'],group.get('groupid',group['Organization'])))
                mep['Groups']=[group]
                in_group = True
                break
        if group_filter and not in_group: continue
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
    return render('meps.html',
                  date=date,
                  group=group_filter,
                  country=country_filter,
                  meps=[x for x in sorted(rankedMeps,key=lambda x: x[0], reverse=True)])


@app.route('/mep/<int:mep_id>/<string:mep_name>')
def mep(mep_id, mep_name):
    mep = db.mep(mep_id)
    if not mep:
        return not_found_error(None)
    mep, changes, date = timetravel(mep)
    amendments = db.get("ams_by_mep", mep_id) or []
    activities = db.activities(mep_id) or {}
    acts = {'types':{}, 'dossiers':{}}
    if len(amendments):
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
                    acts['dossiers'][d] = 0
                acts['dossiers'][d] += 1

    acts['types']={k: v for k,v in sorted(acts['types'].items(), key=lambda x:asactivity(x[0]))}
    acts['dossiers']={k: v for k,v in sorted(acts['dossiers'].items(), key=lambda x: x[1], reverse=True)}
    mep['activities'] = acts

    if isinstance(mep.get('CV'),list):
        mep['CV']={'': mep['CV']}
    mep['dossiers'] = sorted(db.get('dossiers_by_mep',mep_id) or [], reverse=True)
    # add legal opinions to activities
    comparl_count = 0
    for (ref, title, type, committee) in mep['dossiers']:
        if type.endswith("Committee Legal Basis Opinion"):
            comparl_count+=1
            if not ref in acts['dossiers']:
                acts['dossiers'][ref] = 0
            acts['dossiers'][ref] += 1
    if comparl_count>0: acts['types']['COMPARL-LEG'] = comparl_count

    return render(
        'mep.html',
        mep=mep,
        d=mep_id,
        change_dates=changes,
        group_cutoff=datetime(2004,7,20).strftime("%Y-%m-%d"),
        date=date,
        exclude_from_json=('d', 'group_cutoff'),
    )

@app.route('/activities/<int:mep_id>', defaults={'d_id':None, 't':None})
@app.route('/activities/<int:mep_id>/type/<string:t>', defaults={'d_id':None})
@app.route('/activities/<int:mep_id>/dossier/<path:d_id>', defaults={'t':None})
@app.route('/activities/<int:mep_id>/<string:t>/<path:d_id>')
def activities(mep_id, t, d_id):
    if mep_id not in mepnames:
        return render('errors/404.html'), 404
    if t and t not in ACTIVITY_MAP.keys():
        return render('errors/404.html'), 404
    a = db.activities(mep_id, t, d_id) or {}
    if t in {'COMPARL-LEG', None}:
        # add legal opinions to activities
        for (ref, title, type, committee) in sorted(db.get('dossiers_by_mep',mep_id) or [], reverse=True):
            if not type.endswith("Committee Legal Basis Opinion"): continue
            if not 'COMPARL-LEG' in a: a['COMPARL-LEG']=[]
            if d_id is not None:
                if d_id == ref:
                    a['COMPARL-LEG'].append({'reference': ref, 'url': '/dossier/%s' % ref, 'title': title, 'committee': committee})
            else:
                a['COMPARL-LEG'].append({'reference': ref, 'url': '/dossier/%s' % ref, 'title': title, 'committee': committee})

    if t in {'amendments', None}:
        ams = db.get('ams_by_mep',mep_id) or []
        if d_id is not None:
            ams = [a for a in ams if a['reference']==d_id]
        if ams:
            a['amendments'] = sorted(ams, key=lambda x: (x['reference'], -(x['seq'] if isinstance(x['seq'], int) else ord(x['seq'][0]))), reverse=True)

    for k in ['mep_id', 'changes', 'meta']:
        if k in a: del a[k]
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

@app.route('/dossier/<path:d_id>')
def dossier(d_id):
    d = db.dossier(d_id)
    if not d:
        return not_found_error(None)
    d, changes, date = timetravel(d)

    clean_lb(d)

    d['amendments'] = [a for a in (db.get("ams_by_dossier", d_id) or []) if a.get('date',"0") < date] # filter amendments by timetravel
    # some amendments have letters as seq numbers m(
    for a in d['amendments']:
        a['seq']=str(a['seq'])
    progress = 0

    if d_id in v1dossiers or 'activities' in d:
        template = "v1dossier.html"
        types = None
        # todo add d['votes'] in v1 expected format
        #votes = db.get('votes_by_dossier',d_id) or []
        #for vote in votes:
        #    groups=[x['group']
        #            for new in ['For','Against','Abstain']
        #            if new in vote
        #            for x in vote[new]['groups']]
        #    vote['groups']=sorted(set(groups))
        #    t,r=vote.get('title'),vote.get('report')
        #    if t and r:
        #        i=t.index(r)
        #        if i>=0:
        #            tmp=r.replace('/','-').split('-')
        #            rid='-'.join((tmp[0],tmp[2],tmp[1]))
        #            if rid[0] == 'A':
        #                type = 'REPORT'
        #            elif rid[0] == 'B':
        #                type = 'MOTION'
        #            else:
        #                print >>sys.stderr, '[$] unkown vote reference type:', r
        #            vote['linkedtitle']='%s<a href="http://www.europarl.europa.eu/sides/getDoc.do?type=%s&amp;mode=XML&amp;reference=%s&amp;language=EN">%s</a>%s' \
        #                                 % (t[:i], type, rid, r, t[i+len(r):])
        #    for dec in [x for x in ['For','Against','Abstain'] if x in vote]:
        #        for g in groups:
        #            if g not in [x['group'] for x in vote[dec]['groups']]:
        #                vote[dec]['groups'].append({'group':g, 'votes': []})
        #        vote[dec]['groups'].sort(key=itemgetter('group'))
        #d['votes']=votes
    else:
        template = "dossier.html"
        d['events'] = merge_events(d)
        d['vmatrix'] = votematrices([v for v in (db.get('votes_by_dossier',d_id) or []) if v.get('ts','0') < date ]) # filter votes by timetravel date

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
            if act.get('date','0') < date: # filter for timetravel
                meps[mepid]['types'][type].append(act)
        # todo sort meps by number of activities
        d['mep_activities']=sorted(meps.items(), key=lambda x: sum(len(y) for y in x[1]['types'].values()), reverse=True)
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
        now_date=date,
        change_dates=changes,
        progress=progress,
        TYPES=types,
        msg=ep_wtf_dossiers.get(d_id),
        exclude_from_json=('now_date', 'url', 'd', 'progress', 'TYPES'),
    )


@app.route('/committees')
def committees():
    s = db.committees()
    s = dict(sorted(s.items(), key=lambda x: x[1]['active'], reverse=True))
    return render('committees.html', committees=s)


@app.route('/committee/<string:c_id>')
def committee(c_id):
    c = {}
    c['votes'] = db.get('com_votes_by_committee', c_id) or None
    c['agendas'] = db.get('comagenda_by_committee', c_id) or []
    c['shortname'] = c_id
    c['name'] = COMMITTEE_MAP.get(c_id, "Unknown committee")
    if c['agendas']:
        for a in c['agendas']:
            if 'time' in a and a['time']:
                a['date'] = a['time']['date']
            if 'date' not in a:
                a['date'] = ''

    rankedMeps=[]
    for mep in (db.get('meps_by_committee', c_id) or []):
        for com in reversed(mep['Committees']):
            if com.get('abbr')==c_id:
                score=com_positions[com['role']]
                mep['crole']=com['role']
                if com.get('end')=='9999-12-31T00:00:00':
                    rankedMeps.append((score,mep,True))
                else:
                    rankedMeps.append((score,mep,False))
                break
    c['meps'] = sorted(rankedMeps,key=lambda x: (x[2],x[0],x[1]['Name']['full']), reverse=True) or None

    c['dossiers'] = db.get('dossiers_by_committee', c_id) or []
    if c['dossiers']:
        for d in c['dossiers']:
            clean_lb(d)
            del d['changes']
            tmp=[c for c in d['committees'] if c['committee']==c_id]
            if len(tmp)>0:
                d['crole']=tmp[0].get('type') or ("Responsible" if tmp[0].get('responsible') else "Opinion")
                d['rapporteur']=list({m['name']: m for c in d['committees'] if c.get('type')=="Responsible Committee" or c.get('responsible') for m in c.get('rapporteur',[])}.values())
                d['rapporteur_groups'] = sorted({'IND/DEM' if k['abbr'][0]=='ID' else 'NA' if k['abbr'][0]=='NA' else k['abbr'] for k in d['rapporteur'] if k.get('abbr')})
                for event in d.get('events',[]):
                    if event.get('type') in ['Non-legislative initial document',
                                             "Non-legislative basic document published",
                                             'Commission/Council: initial legislative document',
                                             "Legislative proposal",
                                             "Legislative proposal published"] and 'docs' in event and len(event['docs'])>0:
                        if 'title' in event['docs'][0]:
                            d['comdoc']={'title': event['docs'][0]['title'],
                                         'url': event['docs'][0].get('url'), }
                            break

    return render(
        'committee.html',
        committee=c,
        now_date=date.today().strftime("%Y-%m-%d"),
        exclude_from_json=('now_date',)
    )


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
    for act in d.get('activities', []):
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
        ds=[listdossiers(db.dossier(d.name)) for d in active_items if d.type=='dossier']
    if len(inactive_items):
        ids=[listdossiers(db.dossier(d.name)) for d in inactive_items if d.type=='dossier']
    if ds and request.headers.get('X-Requested-With'):
        return jsonify(count=len(ds), dossiers=ds)
    return render('view_notif_group.html',
                           dossiers=ds,
                           active_dossiers=len(ds),
                           inactive_dossiers=len(ids),
                           date=datetime.now(),
                           group={
                               'name': group.name,
                               'id': group.id,
                               'items': [{'name': i.name, 'type': i.type} for i in group.items if not i.activation_key],
                               'subscribers': [{'email': s.email} for s in group.subscribers if not s.activation_key],
                               'pending_subscribers': [{'email': s.email} for s in group.subscribers if s.activation_key],
                               'inactive_items': [{'name': i.name, 'type': i.type} for i in group.items if i.activation_key],
                           })


@app.route('/notification/<string:g_id>/add/<any(dossiers, emails, subject):item>/<path:value>')
def notification_add_detail(g_id, item, value):
    group = notif.session.query(notif.Group).filter(notif.Group.name==g_id).first()
    if not group:
        return 'unknown group '+g_id, 500
    email = ''
    if group.subscribers:
        email = [x.email for x in group.subscribers if not x.activation_key]
    if item == 'emails':
        email = [value]
        emails = [s.email for s in group.subscribers]
        if value in emails:
            return 'already subscribed to this group'
        i = notif.Subscriber(email=value, activation_key=gen_token())
        group.subscribers.append(i)

    elif item == 'dossiers':
        d = db.dossier(value)
        if not d:
            return 'unknown dossier - '+value
        i = notif.Item(name=value, type='dossier', activation_key=gen_token())
        group.items.append(i)
    elif item == 'subject':
        i = notif.Item(name=value, type='subject', activation_key=gen_token())
        group.items.append(i)
    if not email:
        return 'unknown email', 500
    msg = Message("Parltrack Notification Subscription Verification",
            sender = "parltrack@parltrack.org",
            recipients = email)

    notif.session.add(i)
    notif.session.commit()
    print("activation_key %s" % i.activation_key)
    msg.body = "Your verification key is %sactivate?key=%s\nNotification group url: %snotification/%s" % (request.url_root, i.activation_key, request.url_root, g_id)
    mail.send(msg)
    return 'OK'


@app.route('/notification/<string:g_id>/del/<any(dossiers, emails, subscribers):item>/<path:value>')
def notification_del_detail(g_id, item, value):
    group = notif.session.query(notif.Group).filter(notif.Group.name==g_id).first()
    if not group:
        return 'unknown group '+g_id
    active_emails = [s.email for s in group.subscribers if not s.activation_key]
    msg = Message("Parltrack Notification Unsubscription Verification",
            sender = "parltrack@parltrack.org",
            recipients = active_emails)
    if item == 'emails':
        if value not in active_emails:
            return 'Cannot complete this action'
        sub = None
        for x in group.subscribers:
            if x.email == value:
                sub = x
                break
        if not sub:
            return 'Cannot complete this action'
        sub.activation_key = gen_token()
        notif.session.add(sub)
        notif.session.commit()
        msg.body = "Your verification key is %sactivate?key=%s&?delete=1\nNotification group url: %snotification/%s" % (request.url_root, sub.activation_key, request.url_root, g_id)
        mail.send(msg)
    else:
        item = notif.session.query(notif.Item).filter(notif.Item.name==g_id).first()
        if not item:
            return 'Cannot complete this action'
        item.activation_key = gen_token()
        notif.session.add(item)
        notif.session.commit()
        msg.body = "Your verification key is %sactivate?key=%s&?delete=1\nNotification group url: %snotification/%s" % (request.url_root, item.activation_key, request.url_root, g_id)
        mail.send(msg)
    return 'OK'


@app.route('/activate')
def activate():
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
    obj = unquote(obj)
    if 'www.europarl.europa.eu/sides/getDoc.do?pubRef=-//EP//NONSGML' in obj:
        # old style nonsgml urls
        #http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-//EP//NONSGML+COMPARL+PE-595.712+02+DOC+PDF+V0//EN&language=EN
        return obj.split('+')[2]
    elif 'www.europarl.europa.eu/doceo/document/' in obj and obj.endswith('_EN.pdf'):
        # new doceo style urls
        #http://www.europarl.europa.eu/doceo/document/JURI-AM-597416_EN.pdf
        tmp = obj.split('/')[-1][:-len('_EN.pdf')].split('-')[-1]
        return "%s.%s" % (tmp[:3], tmp[3:])
    else:
        print("bad doceo style url for asPE(): %s" % repr(obj))
        return "Unknown"


@app.template_filter()
def asmep(value):
    #if isinstance(value, int):
    #    value = str(value)
    #if isinstance(value, str):
    #    value = int(value)
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
    return ACTIVITY_MAP.get(value,"unknown").capitalize()


def getDate():
    date=datetime.now()
    if request.args.get('date'):
        date = asDate(request.args['date'])
    return date

def gen_token():
    return sha1(''.join([chr(randint(1, 128)) for x in range(128)]).encode()).hexdigest()

def votematrices(votes):
    res = []
    for vote in votes: # can have multiple votes
        if not 'votes' in vote:
            continue
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


def timetravel(obj):
    date = getDate().isoformat()
    changes = []
    for d,c in sorted(obj.get('changes', {}).items(), key=lambda x: x[0], reverse=True):
        if date > d:
            break
        if not c:
            del(obj['changes'][d])
            continue
        if len(changes) and changes[-1][0] in obj['changes']:
            del(obj['changes'][changes[-1][0]])
        try:
            obj = revert(obj, c)
        except:
            print('failed to revert obj', d, c)
            break
        changes.append((d, ', '.join(set('.'.join([y for y in x['path'] if isinstance(y, str)]).replace(' ', '_') for x in c))))
    return obj, changes, date

if not config.DEBUG:
    app.logger.setLevel(logging.INFO)

#----------------------------------------------------------------------------#
# Launch.
#----------------------------------------------------------------------------#

if __name__ == '__main__':
    #dossier('2016/0279(COD)')
    app.run(host='0.0.0.0', port=config.WEBSERVER_PORT, threaded=False)
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
