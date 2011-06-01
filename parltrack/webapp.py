import os
from pymongo import Connection
from flaskext.mail import Mail
from flask import Flask, render_template
from parltrack import default_settings


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


@app.route('/')
def index():
    db = connect_db()
    return render_template('index.html', dossiers_num=db.dossiers.find().count(), votes_num=db.ep_votes.find().count(), meps_num=db.ep_meps.find().count())

@app.route('/ranking/mep/<path:date>')
def ranking(date):
    from parltrack.views.views import mepRanking
    return render_template('mep_ranking.html', rankings=mepRanking(date), d=date)

@app.route('/dossier/<path:d_id>')
def view_dossier(d_id):
    from parltrack.views.views import dossier
    return dossier(d_id)

if __name__ == '__main__':
    app.run()
