#----------------------------------------------------------------------------#
# Imports
#----------------------------------------------------------------------------#

import logging
import os

import config
import model

from pprint import pprint
from datetime import datetime
from flask import Flask, render_template, request
from logging import Formatter, FileHandler

#----------------------------------------------------------------------------#
# App Config.
#----------------------------------------------------------------------------#

app = Flask(__name__)
app.config.from_object('config')


def render(template, **kwargs):
    return render_template(template, **kwargs)


#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#


@app.route('/')
def home():
    return render('index.html')


@app.route('/about')
def about():
    return render('about.html')


@app.route('/dumps')
def dumps():
    return render('dumps.html')


@app.route('/meps')
def meps():
    date = getDate()
    meps = model.Mep.get_by_date(date)
    pprint(meps[0].data)
    return render('meps.html', meps=meps, date=date)


@app.route('/dossiers')
def dossiers():
    return render('dossiers.html')


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
def asdate(value):
    if type(value)==type(int()):
        value=datetime.fromtimestamp(value)
    if type(value) not in [str, bytes]:
        return value.strftime('%Y/%m/%d')
    return value.split(' ')[0]


if not app.debug:
    app.logger.setLevel(logging.INFO)

#----------------------------------------------------------------------------#
# Launch.
#----------------------------------------------------------------------------#

if __name__ == '__main__':
    app.run(port=config.WEBSERVER_PORT)
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
