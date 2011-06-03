
SECRET_KEY = 'biene maya'

MONGODB_HOST = 'localhost'
MONGODB_DB = 'parltrack'

SOLR_URL = 'http://localhost:8983/solr/parlament'
SOLR_USER = None
SOLR_PASS = None

try:
    from parltrack.local_settings import *
except:
    pass
