import os

CURRENT_TERM=8

USER_AGENT='parltrack/0.8'
PROXY='http://localhost:8123/'

ROOT_URL = '/'

# Base directory
basedir = os.path.abspath(os.path.dirname(__file__))

# Debug
DEBUG = True
DB_DEBUG = False

# DB
NOTIF_DB_URI = 'sqlite:///notifications.sqlite3'

# Webapp
WEBSERVER_PORT = 6776
