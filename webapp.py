#----------------------------------------------------------------------------#
# Imports
#----------------------------------------------------------------------------#

import logging
import os

import config
import model

from flask import Flask, render_template, request
from logging import Formatter, FileHandler

#----------------------------------------------------------------------------#
# App Config.
#----------------------------------------------------------------------------#

app = Flask(__name__)
app.config.from_object('config')


#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/dumps')
def dumps():
    return render_template('dumps.html')


@app.route('/meps')
def meps():
    return render_template('meps.html')


@app.route('/dossiers')
def dossiers():
    return render_template('dossiers.html')


# Error handlers.

@app.errorhandler(500)
def internal_error(error):
    #db_session.rollback()
    return render_template('errors/500.html'), 500


@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404


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
