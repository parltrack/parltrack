#!/usr/bin/env python3

import socket
import sys
import traceback
import os, json, sys, atexit, msgpack, struct
from datetime import datetime
from threading import Thread
from utils.log import log
from tempfile import mkstemp
from utils.utils import dateJSONhandler

PIDFILE='db.pid'

DBS = {}
IDXs = {}

def cleanup_singleton():
    log(3,"cleaning up {}".format(PIDFILE))
    os.unlink(PIDFILE)

def singleton():
    # ensure we are a singleton
    if os.path.exists(PIDFILE):
        # uhoh, there is a db.pid file, check if there is a process with this pid
        with open(PIDFILE, 'r') as fd:
            pid = int(fd.read())
        try:
            with open('/proc/{}/cmdline'.format(pid),'r') as fd:
                cmd = fd.read()
        except(FileNotFoundError):
            # ok, it seems the pid does not exist anymore, we can delete and continue
            log(2,"found a stale db.pid file, removing and continuing")
        except:
            raise
        else:
            # the pid is a running process, check if it is a python3 db.py process
            cmd = cmd.split('\0')
            if cmd[0].endswith('python3') and cmd[1].endswith('db.py'):
                log(1, "[!] another db process is already running at pid: {}".format(pid))
                sys.exit(1)
            # pid has been recycled and is some other unrelated process
        os.unlink(PIDFILE)

    with open(PIDFILE, 'x') as fd:
        fd.write(str(os.getpid()))
    atexit.register(cleanup_singleton)

def reindex(table):
    for idx in TABLES[table]['indexes']:
        IDXs[idx['name']]=idx['fn']()

def reindex_all():
    for table in TABLES.keys():
        reindex(table)

def genkey(table):
    key = random.randrange(2**32)
    while key in table.keys():
        key = random.randrange(2**32)
    return key

def init(data_dir):
    log(3,"initializing")
    singleton()

    global DBDIR
    DBDIR = data_dir

    # load json dumps int global DBS dict
    for table in TABLES.keys():
        with open("{}/{}.json".format(data_dir, table), 'rt') as fd:
            log(3,"loading table {}".format(table))
            DBS[table]={item[TABLES[table]['key']]: item for item in json.load(fd)}

    # initialize indexes
    log(3,"indexing tables")
    reindex_all()
    log(3,"init done")

def read_req(sock):
    size = sock.recv(4)
    log(5, "req size is {!r}".format(size))
    size = struct.unpack("I", size)[0]
    if size > 1024 * 1024 * 50: # arbitrary upper limit for request 50MB
        log(1, "request is too big: {}MB".format(size / (1024*1024)))
        return {}
    log(3, 'receiving {} bytes request'.format(size))
    res = []
    while size>0:
        rsize=65535 if size >= 65535 else size
        res.append(sock.recv(rsize))
        size -= rsize
    req = msgpack.loads(b''.join(res), raw = False)
    log(3, 'received {!r}'.format(req))
    return req

def mainloop():
    from IPython import embed
    Thread(target=embed).start()

    # Create a TCP/IP socket
    #sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Bind the socket to the port
    #server_address = ('localhost', 10000)
    #log(2, 'starting up on {} port {}'.format(*server_address))

    # create a unix domain socket
    server_address = '/tmp/pt-db.sock'
    # Make sure the socket does not already exist
    try:
        os.unlink(server_address)
    except OSError:
        if os.path.exists(server_address):
            raise

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    log(2, 'starting up on {}'.format(server_address))
    sock.bind(server_address)

    # Listen for incoming connections
    sock.listen(1)

    while True:
        # Wait for a connection
        log(3,'waiting for a connection')
        connection, client_address = sock.accept()
        try:
            log(3, 'connection from {}'.format(client_address))
            query = read_req(connection)
            if query.get('cmd', '') == 'get':
                res = get(**query.get('params', [])) or None
            elif query.get('cmd', '') == 'put':
                res = put(**query.get('params', [])) or None
            elif query.get('cmd', '') == 'commit':
                res = commit(**query.get('params', [])) or None
            else:
                log(2,'invalid or missing cmd')
                continue
            log(3,"responding with {} records".format(len(res) if res else res))
            fd = connection.makefile(mode = 'wb', buffering = 65535)
            msgpack.dump(res, fd, use_bin_type = True)
            log(3,'sent data back to the client')
            fd.close()
        except:
            log(1, "connection error")
            traceback.print_exc()
        finally:
            # Clean up the connection
            connection.close()

def get(source, key):
    # TODO error handling
    log(3,'getting src: "{}" key: "{}"'.format(source,key))
    if isinstance(key, list):
        if source in IDXs:
            return [IDXs[source].get(x) for x in key]
        if source in DBS:
            return [DBS[source].get(x) for x in key]
    else:
        if source in IDXs:
            return IDXs[source].get(key)
        if source in DBS:
            return DBS[source].get(key)
    log(1, 'source not found in db nor in index')
    return None

def put(table, value):
    # TODO error handling
    log(3,'storing into src: "{}" key: "{}"'.format(table,key))
    if not table in DBS:
        log(1, 'table not found in db')
        return False
    key = value[TABLES[table].get('key', genkey(table))]
    DBS[table][key]=value
    reindex(table)
    return True

def commit(table):
    if not table in DBS:
        log(1, 'table not found in db')
        return False
    def jdump(obj):
        return json.dumps(obj, default=dateJSONhandler, ensure_ascii=False).encode('utf8')
    (fd, name) = mkstemp(dir=DBDIR)
    items = DBS[table].values()
    fd.write(b"[{}".format(jdump(items[0])))
    for rec in DBS[table].values()[1:]:
        fd.write(b'\n,{}'.format(jdump(rec)))
    fd.write(b'\n]')
    fd.close()
    os.rename(name, "{}/{}.json".format(DBDIR, table))

######  indexes ######

def idx_meps_by_activity():
    res = {'active':[], 'inactive':[]}
    for mep in DBS['ep_meps'].values():
        if mep['active']: res['active'].append({k:v for k,v in mep.items() if k not in ['changes', 'activities']})
        else: res['inactive'].append({k:v for k,v in mep.items() if k not in ['changes', 'activities']})
    return res

def idx_meps_by_country():
    res = {}
    for mep in DBS['ep_meps'].values():
        countries = set([constituency.get('country')
                         for constituency in mep.get('Constituencies',[])
                         if constituency])
        for country in countries:
            if not country in res: res[country] = []
            res[country].append({k:v for k,v in mep.items() if k not in ['changes', 'activities']})
    return res

def idx_meps_by_group():
    res = {}
    for mep in DBS['ep_meps'].values():
        groups = set([group.get('Organization')
                         for group in mep.get('Groups',[])
                         if group])
        for group in groups:
            if not group in res: res[group] = []
            res[group].append({k:v for k,v in mep.items() if k not in ['changes', 'activities']})
    return res

def idx_ams_by_mep():
    res = {}
    for am in DBS['ep_amendments'].values():
        meps = set(am.get('meps', []))
        for mep in meps:
            if not mep in res: res[mep] = []
            res[mep].append(am)
    return res

def idx_ams_by_dossier():
    res = {}
    for am in DBS['ep_amendments'].values():
        dossier = am.get('reference', '')
        if not dossier:
            #log(1,"amendment has no reference {}".format(am))
            continue
        if not dossier in res: res[dossier] = []
        res[dossier].append(am)
    return res

def idx_com_votes_by_dossier():
    res = {}
    for vote in DBS['ep_com_votes'].values():
        dossier = vote.get('ep_ref', '')
        if not dossier:
            log(1,"com_vote has no reference {}".format(vote))
        if not dossier in res: res[dossier] = []
        res[dossier].append(vote)
    return res

def idx_com_votes_by_committee():
    res = {}
    for vote in DBS['ep_com_votes'].values():
        committee = vote.get('committee', '')
        if not committee:
            log(1,"com_vote has no committee {}".format(vote))
        if not committee in res: res[committee] = []
        res[committee].append(vote)
    return res

def idx_votes_by_dossier():
    res = {}
    for vote in DBS['ep_votes'].values():
        dossier = vote.get('ep_ref', '')
        if not dossier:
            continue
        if not dossier in res: res[dossier] = []
        res[dossier].append(vote)
    return res

def idx_dossiers_by_reference():
    res = {}
    for dossier in DBS['ep_dossiers'].values():
        reference = dossier['procedure']['reference']
        if not reference in res: res[reference] = []
        res[reference].append(dossier)
    return res
# todo indexes for dossiers by committees, rapporteur, subject, stage_reached
# todo indexes for meps by name(alias)

TABLES = {'ep_amendments': {'indexes': [{"fn": idx_ams_by_dossier, "name": "ams_by_dossier"},
                                        {"fn": idx_ams_by_mep, "name": "ams_by_mep"}],
                            'key': '_id'},

          'ep_comagendas': {"indexes": [],
                            'key': '_id'},

          'ep_com_votes': {'indexes': [{"fn": idx_com_votes_by_dossier, "name": "com_votes_by_dossier"},
                                       {"fn": idx_com_votes_by_committee, "name": "com_votes_by_committee"}],
                           'key': '_id'},

          'ep_dossiers': {'indexes': [{"fn": idx_dossiers_by_reference, "name": "idx_dossiers_by_reference"}],
                          'key': '_id'},

          'ep_meps': {'indexes': [{"fn": idx_meps_by_activity, "name": "meps_by_activity"},
                                  {"fn": idx_meps_by_country, "name": "meps_by_country"},
                                  {"fn": idx_meps_by_group, "name": "meps_by_group"}],
                      'key': 'UserID'},

          'ep_votes': {'indexes': [{"fn": idx_votes_by_dossier, "name": "votes_by_dossier"}],
                       'key': '_id'},
}

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'dev':
        init('dev_dumps')
    else:
        init('db')
    mainloop()
