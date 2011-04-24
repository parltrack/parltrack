from pprint import pprint
from parltrack.environment import connect_db, connect_solr

def index_procedure(procedure, db, solr):
    pprint(procedure)
    entry = {'_id': procedure['_id'], '_collection': 'procedure'}
    entry['finished'] = procedure.get('finished')
    entry['state'] = procedure.get('state')
    entry['reference'] = procedure.get('reference')
    entry['title'] = procedure.get('title')
    entry['parliament'] = procedure.get('parliament')
    entry['session'] = procedure.get('session')
    entry['session'] = procedure.get('session')
    entry['subject'] = procedure.get('subjects')
    entry['tag'] = procedure.get('tags')
    entry['initiative'] = procedure.get('initiative')
    entry['description'] = procedure.get('description')
    solr.add(**entry)
    solr.commit()

def index_procedures(db, solr):
    for procedure in db.procedure.find():
        index_procedure(procedure, db, solr)

if __name__ == '__main__':
    index_procedures(connect_db(), connect_solr())
