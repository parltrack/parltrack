from pprint import pprint
from parltrack.environment import connect_db, connect_solr

def index_actor(procedure, db, solr):
    entry = {'_collection': 'actor', 'key': actor.get('key')}
    entry['_id'] = str(actor['_id'])
    entry['title'] = actor.get('name')
    if actor.get('department'):
        entry['department'] = actor.get('department')
    if actor.get('group'):
        entry['group'] = actor.get('group')
    if actor.get('function'):
        entry['function'] = actor.get('function')
    if actor.get('party'):
        entry['party'] = actor.get('party')
    if actor.get('state'):
        entry['state'] = actor.get('state')
    if actor.get('constituency'):
        entry['constituency'] = actor.get('constituency', {}).get('name')
    if 'bio' in actor:
        entry['description'] = actor['bio']
    solr.add(**entry)
    solr.commit()

def index_actors(db, solr):
    for actor in db.actor.find():
        index_actor(actor, db, solr)

if __name__ == '__main__':
    index_actors(connect_db(), connect_solr())

