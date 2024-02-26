import os

CURRENT_TERM=9

USER_AGENT='parltrack/0.8'
PROXY='http://localhost:8123/'

ROOT_URL = 'https://parltrack.org/'

# Base directory
basedir = os.path.abspath(os.path.dirname(__file__))

# Debug
DEBUG = False
DB_DEBUG = False

# DB
NOTIF_DB_URI = 'sqlite:///notifications.sqlite3'

# Webapp
WEBSERVER_PORT = 6776

CACHE_DIR='/tmp/ptcache'
