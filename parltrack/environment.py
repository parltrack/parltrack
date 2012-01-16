import os
from pymongo import Connection
from flask import Flask, g
from flaskext.mail import Mail
from parltrack import default_settings

app = Flask(__name__)
app.config.from_object(default_settings)
app.config.from_envvar('PARLTRACK_SETTINGS', silent=True)
mail = Mail(app)

def connect_db():
    conn = Connection(app.config.get('MONGODB_HOST'))
    return conn[app.config.get('MONGODB_DB')]

def connect_solr():
    return SolrConnection(app.config.get('SOLR_URL'), 
            http_user=app.config.get('SOLR_USER'),
            http_pass=app.config.get('SOLR_PASS'))

def get_data_dir():
    data_dir = app.config.get('DATA_DIR', '/tmp/parltrack')
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir)
    return data_dir

