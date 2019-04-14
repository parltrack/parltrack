import os

CURRENT_TERM=8

USER_AGENT='parltrack/0.8'
PROXY='http://localhost:8123/'

ROOT_URL = '/'

# Grabs the folder where the script runs.
basedir = os.path.abspath(os.path.dirname(__file__))

# Enable debug mode.
DEBUG = True
DB_DEBUG = False

# Webapp config

WEBSERVER_PORT = 6776
