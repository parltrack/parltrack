#----------------------------------------------------------------------------#
# Imports
#----------------------------------------------------------------------------#

import logging
import os

import config
import notification_model as notif

import diff_match_patch

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
from utils.utils import asDate, clean_lb
from utils.devents import merge_events
from utils.mappings import (
    SEIRTNUOC as COUNTRIES,
    COMMITTEE_MAP,
    stage2percent,
)

from db import Client

if version_info[0] == 3:
    unicode = str


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

db = Client()


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


@app.route('/meps')
def meps():
    # TODO date handling
    date = getDate()
    meps = db.meps_by_activity(True)
    return render('meps.html', date=date, meps=meps)


@app.route('/mep/<int:mep_id>/<string:mep_name>')
def mep(mep_id, mep_name):
    mep = db.mep(mep_id)
    if not mep:
        return not_found_error(None)
    #mep['amendments'] = db.get("ams_by_mep", mep_id) or []
    mep['amendments'] = []
    return render(
        'mep.html',
        mep=mep,
        d=mep_id,
        group_cutoff=datetime(2004,7,20).strftime("%Y-%m-%d"),
        # TODO
        committees={},
        exclude_from_json=('d', 'group_cutoff', 'committees'),
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
        ds.append({
            'name': d['procedure']['reference'],
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
    if d_id in v1dossiers:
        template = "v1dossier.html"
    else:
        template = "dossier.html"
    d['activities'] = merge_events(d)
    progress = 0
    for a in d['activities']:
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
        exclude_from_json=('now_date', 'url', 'd', 'progress'),
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
    return render('subjects.html', subjects=s, dossier_count=r, exclude_from_json=('subjects',))


@app.route('/subject/<path:subject>')
def subject(subject):
    r = db.get('dossiers_by_subject', subject) or []
    if not r:
        return not_found_error(None)
    return render('subject.html', dossiers=r, subject=subject)


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
    meps = db.meps_by_name(q) or []
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
    if isinstance(value, int):
        value=datetime.fromtimestamp(value)
    if type(value) not in [str, unicode]:
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
    #if not hasattr(request, 'meps'):
    #    request.meps = {}
    #if value in request.meps:
    #    mep = request.meps[value]
    #else:
    #    mep = db.get('ep_meps', value)
    #    request.meps[value] = mep
    mep = db.get('ep_meps', value)
    return u'<a href="/mep/%d/%s">%s</a>' % (mep['UserID'], mep['Name']['full'],mep['Name']['full'])


# TODO
@app.template_filter()
def asdossier(value):
    doc=db.get('ep_dossiers', value)
    if not doc:
        return value
    return (u'<a href="/dossier/%s">%s</a> %s' %
            (doc['procedure']['reference'],
             doc['procedure']['reference'],
             doc['procedure']['title']))


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
    id = 'e' + str(randrange(1,999999999))

    for a in email_address:
        cipher_text += key[ character_set.find(a) ]

    script = 'var a="'+key+'";var b=a.split("").sort().join("");var c="'+cipher_text+'";var d="";'
    script += 'for(var e=0;e<c.length;e++)d+=b.charAt(a.indexOf(c.charAt(e)));'
    script += 'document.getElementById("'+id+'").innerHTML="<a href=\\"mailto:"+d+"\\">"+d+"</a>"'


    script = "eval(\""+ script.replace("\\","\\\\").replace('"','\\"') + "\")"
    script = '<script type="text/javascript">/*<![CDATA[*/'+script+'/*]]>*/</script>'

    return '<span id="'+ id + '">[javascript protected email address]</span>'+ script


@app.template_filter()
def reftopath(ref):
    return "%s/%s" % (ref[-4:-1], ref[:9])


@app.template_filter()
def group_icon(value):
    if not value: return ''
    if type(value)==type(list()): value=value[0]
    if value=='NA': value='NI'
    return "static/images/%s.gif" % value.lower().replace('/','_')


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


if not config.DEBUG:
    app.logger.setLevel(logging.INFO)

#----------------------------------------------------------------------------#
# Launch.
#----------------------------------------------------------------------------#

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config.WEBSERVER_PORT, threaded=False)
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
