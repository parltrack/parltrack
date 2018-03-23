import os

CURRENT_TERM=8

ROOT_URL = '/'

# Grabs the folder where the script runs.
basedir = os.path.abspath(os.path.dirname(__file__))

# Enable debug mode.
DEBUG = True
DB_DEBUG = False

#SECRET_KEY = os.environ.get('SECRET', 'my precious')
DB_USER = os.environ.get('DB_USER', '')
DB_PASS = os.environ.get('DB_PASS', '')
DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
DB_DATABASE = os.environ.get('DB_DATABASE', 'parltrack')
DB_PORT = os.environ.get('DB_PORT', '5432')

# Connect to the database
SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://{0}:{1}@{2}:{3}/{4}".format(
    DB_USER,
    DB_PASS,
    DB_HOST,
    DB_PORT,
    DB_DATABASE,
)
