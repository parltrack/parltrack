#----------------------------------------------------------------------------#
# Imports
#----------------------------------------------------------------------------#

import logging
import os

import config

from pprint import pprint
from datetime import datetime, date
from flask import Flask, render_template, request
from logging import Formatter, FileHandler
from random import shuffle, randrange
from sys import version_info
from urllib.parse import unquote
import diff_match_patch

from flask import Flask, render_template, request, redirect
from utils.utils import asDate
from utils.mappings import (
    SEIRTNUOC as COUNTRIES,
    COMMITTEE_MAP,
)

from db import Client

if version_info[0] == 3:
    unicode = str

#----------------------------------------------------------------------------#
# App Config.
#----------------------------------------------------------------------------#

app = Flask(__name__)
app.config.from_object('config')

db = Client()


def render(template, **kwargs):
    return render_template(template, **kwargs)


#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#


@app.route('/')
def home():
    meps = 0
    dossiers = 0
    date = getDate()
    active_meps = 0
    return render_template(
        'index.html',
        mep_count=meps,
        dossier_count=dossiers,
        active_mep_count=active_meps,
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
    return render_template('meps.html', date=date, meps=meps)


@app.route('/mep/<int:mep_id>')
def mep(mep_id):
    mep = db.mep(mep_id)
    if not mep:
        return not_found_error(None)
    mep['amendments'] = db.get("ams_by_mep", mep_id) or []
    return render_template(
        'mep.html',
        mep=mep,
        today=date.today().strftime("%Y-%m-%d"),
        countries=COUNTRIES,
        d=mep_id,
        group_cutoff=datetime(2004,7,20).strftime("%Y-%m-%d"),
        # TODO
        committees={},
        committee_map=COMMITTEE_MAP,
    )


@app.route('/mep/<string:mep_name>')
def mep_name(mep_name):
    meps = db.mepid_by_name(mep_name)
    if meps:
        return redirect('/mep/{0}'.format(meps[0]))


@app.route('/dossiers')
def dossiers(d_id):
    return render('dossiers.html')


@app.route('/dossier/<path:d_id>')
def view_dossier(d_id):
    d = db.dossier(d_id)
    if not d:
        return not_found_error(None)
    d['amendments'] = db.get("ams_by_dossier", d_id) or []
    return render(
        'dossier.html',
        dossier=d,
        d=d_id,
        url=request.base_url,
        now_date=date.today().strftime("%Y-%m-%d"),
    )


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
    if type(value)==type(int()):
        value=datetime.fromtimestamp(value)
    if type(value) not in [str, bytes]:
        return value.strftime('%Y/%m/%d')
    return value.split(' ')[0]


@app.template_filter()
def asdate(value):
    if isinstance(value, int):
        value=datetime.fromtimestamp(value)
    if type(value) not in [str, unicode]:
        return value.strftime('%Y/%m/%d')
    return value.split(' ')[0]


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
    return u'<a href="/mep/%s">%s</a>' % (mep['Name']['full'],mep['Name']['full'])


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


def getDate():
    date=datetime.now()
    if request.args.get('date'):
        date = asDate(request.args['date'])
    return date

if not config.DEBUG:
    app.logger.setLevel(logging.INFO)

#----------------------------------------------------------------------------#
# Launch.
#----------------------------------------------------------------------------#

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config.WEBSERVER_PORT)
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
