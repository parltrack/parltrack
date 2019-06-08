#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import atexit
import json
import msgpack
import os
import re
import socket
import stat
import struct
import sys
import traceback
import unicodedata

from datetime import datetime, date, timedelta
from random import randrange
from tempfile import mkstemp
from threading import Thread
from utils.log import log, set_logfile
from utils.utils import dateJSONhandler, create_search_regex, dossier_search, end_of_term


PIDFILE='/tmp/db.pid'

DBS = {}
IDXs = {}


def normalize_name(t):
    return ''.join(unicodedata.normalize('NFKD', t.replace(u'ß','ss')).encode('ascii','ignore').decode('utf8').split()).lower()


class Client:
    mepCache={}
    def commit(self, table):
        cmd = {"cmd": "commit", "params": {"table": table}}
        return self.send_req(cmd)

    def put(self, table, value):
        cmd = {"cmd": "put", "params": {"table": table, "value": value}}
        return self.send_req(cmd)

    def get(self, source, key):
        cmd = {"cmd": "get", "params": {"key": key, "source": source}}
        return self.send_req(cmd)

    def keys(self, source, count=False):
        cmd = {"cmd": "keys", "params": {"source": source, 'count': count}}
        return self.send_req(cmd)

    def search(self, source, query):
        cmd = {"cmd": "search", "params": {"source": source, "query": query}}
        return self.send_req(cmd)

    def count(self, source, key):
        cmd = {"cmd": "count", "params": {"source": source, "key": key}}
        return self.send_req(cmd)

    def reindex(self, table):
        cmd = {"cmd": "reindex", "params": {"table": table}}
        return self.send_req(cmd)

    def mepid_by_name(self, name, date=None, group=None, gabbr=None):
        # normalize name
        name = normalize_name(name)
        cmd = {"cmd": "mepid_by_name", "params": {"name": name, "group": group, "date": date, 'gabbr': gabbr}}
        return self.send_req(cmd)

    def countries_for_meps(self, meps, date):
        cmd = {"cmd": "countries_for_meps", "params": {"mepids": meps, "date": date}}
        return self.send_req(cmd)

    def names_by_mepids(self, mepids):
        cmd = {"cmd": "names_by_mepids", "params": {"mepids": mepids}}
        return self.send_req(cmd)

    def meps_by_name(self, name):
        name = normalize_name(name)
        cmd = {"cmd": "get", "params": {"source": "meps_by_name", "key": name}}
        return self.send_req(cmd)

    def send_req(self, cmd):
        server_address = '/tmp/pt-db.sock'
        req = msgpack.dumps(cmd, default=dateJSONhandler, use_bin_type = True)

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            log(4,'connecting to db on {}'.format(server_address))
            sock.connect(server_address)

            log(4,'sending {} bytes: {}...'.format(len(req), repr(cmd)[:120]))
            sock.sendall(struct.pack("I", len(req)))
            sock.sendall(req)
            log(4,'sent {} bytes'.format(len(req)+4))

            # Send request
            # make the sock a file object
            fd = sock.makefile(mode = 'rb', buffering = 65535)
            # unmarshall response
            res = msgpack.load(fd, raw = False)
            fd.close()
        except:
            log(1, "error during processing request {}".format(cmd))
            raise
        else:
            log(4,'closing socket')
            sock.close()
            return res

    def meps_by_activity(self,key=True):
        return self.get('meps_by_activity', "active" if key else "inactive")

    def mep(self,id):
        return self.get('ep_meps', id)

    def dossier(self,id):
        return self.get('ep_dossiers', id)

    def activities(self,id):
        return self.get('ep_mep_activities', id)

    def vote(self,id):
        return self.get('ep_votes', id)

    def amendment(self,id):
        return self.get('ep_amendments', id)

    def dossiers_by_activity(self,key=True):
        return self.get('active_dossiers', "active" if key else "inactive")

    def dossier_refs(self):
        return self.get('dossier_refs', None)

    def getMep(self, name, date=None,group=None, abbr=None):
        if date and (name, (date.year,date.month)) in self.mepCache:
            # we only cache if there is also a date, and then we cache only year/month
            # this might lead to confusion if there is two different meps
            # with the same name in the same month.
            return self.mepCache[(name, (date.year,date.month))]
        if not name: return

        mepid = self.mepid_by_name(name, date=date, group=group, gabbr=abbr)
        if mepid:
            if date:
                self.mepCache[(name,(date.year,date.month))]=mepid
            return mepid
        log(2,'no mepid found for "%s"' % name)
        if date:
            self.mepCache[(name,(date.year,date.month))]=None

def cleanup_singleton():
    log(3,"cleaning up {}".format(PIDFILE))
    os.unlink(PIDFILE)
    sys.exit(0)


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
    key = randrange(2**32)
    while key in DBS[table].keys():
        key = randrange(2**32)
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
            DBS[table]={TABLES[table]['key'](item): item for item in json.load(fd)}

    # initialize indexes
    log(3,"indexing tables")
    reindex_all()
    log(3,"init done")

def read_req(sock):
    size = sock.recv(4)
    log(4, "req size is {!r}".format(size))
    size = struct.unpack("I", size)[0]
    if size > 1024 * 1024 * 50: # arbitrary upper limit for request 50MB
        log(1, "request is too big: {}MB".format(size / (1024*1024)))
        return {}
    log(4, 'receiving {} bytes request'.format(size))
    res = []
    while size>0:
        rsize=65535 if size >= 65535 else size
        res.append(sock.recv(rsize, socket.MSG_WAITALL))
        size -= rsize
    res = b''.join(res)
    log(4,"size received {}".format(len(res)))
    req = msgpack.loads(res, raw = False)
    log(4, 'received ({}B) {}'.format(len(req),repr(req)[:120]))
    return req

def mainloop():
    from IPython import start_ipython
    Thread(target=start_ipython, kwargs={'user_ns':globals()}).start()

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
            log(3, 'incoming connection')
            query = read_req(connection)
            if query.get('cmd', '') == 'get':
                res = get(**query.get('params', {})) or None
            elif query.get('cmd', '') == 'keys':
                res = keys(**query.get('params', {})) or None
            elif query.get('cmd', '') == 'put':
                res = put(**query.get('params', {})) or None
            elif query.get('cmd', '') == 'commit':
                res = commit(**query.get('params', {})) or None
            elif query.get('cmd', '') == 'search':
                res = search(**query.get('params', {})) or None
            elif query.get('cmd', '') == 'count':
                res = count(**query.get('params', {})) or None
            elif query.get('cmd', '') == 'reindex':
                res = reindex(**query.get('params', {})) or None
            elif query.get('cmd', '') == 'mepid_by_name':
                res = mepid_by_name(**query.get('params', {})) or None
            elif query.get('cmd', '') == 'countries_for_meps':
                res = countries_for_meps(**query.get('params', {})) or None
            elif query.get('cmd', '') == 'names_by_mepids':
                res = names_by_mepids(**query.get('params', {})) or None
            else:
                log(2,'invalid or missing cmd')
                continue
            log(3,"responding with {} records".format(len(res) if hasattr(res,'__len__') else res))
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
    elif key == None:
        if source in IDXs:
            return IDXs[source]
        if source in DBS:
            return DBS[source]
    else:
        if source in IDXs:
            return IDXs[source].get(key)
        if source in DBS:
            return DBS[source].get(key)
    log(1, 'source not found in db nor in index')
    return None


def keys(source, count=False):
    if count:
        s = None
        if source in IDXs:
            s = IDXs
        if source in DBS:
            s = DBS
        if s:
            return {x:len(s[source][x]) for x in s[source].keys()}
    else:
        if source in IDXs:
            return list(IDXs[source].keys())
        if source in DBS:
            return list(DBS[source].keys())
    log(1, 'source not found in db nor in index')
    return None


def put(table, value):
    # TODO error handling
    if not table in DBS:
        log(1, 'table not found in db')
        return False
    key = TABLES[table]['key'](value) or genkey(table)
    log(3,'storing into src: "{}" key: {!r}'.format(table,key))
    DBS[table][key]=value
    #reindex(table)
    return True


def count(source, key):
    ret = get(source, key)
    if not ret:
        return 0
    return len(ret)


def search(source, query):
    res = []
    search_re = create_search_regex(query)
    if source == 'ep_dossiers':
        for d in DBS[source].values():
            if dossier_search(search_re, d):
                res.append(d)
    return res


def commit(table):
    if not table in DBS:
        log(1, 'table not found in db')
        return False
    def jdump(obj):
        return json.dumps(obj, default=dateJSONhandler, ensure_ascii=False).encode('utf8')
    (_fd, name) = mkstemp(dir=DBDIR)
    fd = os.fdopen(_fd,"wb")
    items = tuple(DBS[table].values())
    fd.write(b"["+jdump(items[0]))
    for rec in items[1:]:
        fd.write(b'\n,'+jdump(rec))
    fd.write(b'\n]')
    fd.close()
    tname = "{}/{}.json".format(DBDIR, table)
    os.rename(name, tname)
    os.chmod(tname,stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
    return True


def mepid_by_name(name=None, date=None, group=None, gabbr=None):
    log(3,'getting mepid for name: "{}" group: "{}", date: {}'.format(name,group, date))
    meps = IDXs["meps_by_name"].get(name,[])
    lmeps = len(meps)
    if lmeps == 0:
        log(1, 'mep "{}" not found'.format(name))
        return None # not found
    if lmeps == 1: return meps[0]['UserID'] # lucky us
    # ambigous, more than one mep found
    if date==None:
        log(1, 'mep "{}" not found'.format(name))
        return None
    # filter by constituency
    cmeps = [mep for mep in meps if matchInterval(mep['Constituencies'], date)]
    lcmeps = len(cmeps)
    if lcmeps == 0:
        log(1, 'mep "{}" not found'.format(name))
        return None # not found
    if lcmeps == 1: return cmeps[0]['UserID'] # lucky us

    # filter by group abbrev
    if gabbr is not  None:
        gmeps = [mep for mep in meps if matchInterval(mep['Groups'], date).get('Organization')==gabbr]
        if len(gmeps) == 1: return gmeps[0]['UserID'] # lucky us

    # filter by groups
    if group is not None:
        gmeps = [mep for mep in meps if matchInterval(mep['Groups'], date).get('Organization')==group]
        if len(gmeps) == 1: return gmeps[0]['UserID'] # lucky us

    log(1, 'mep "{}" not found'.format(name))
    return None


def matchInterval(items,tdate):
    for item in items:
        start = item['start']
        end = date.today().isoformat() if item['end'] in ['9999-12-31T00:00:00', '31-12-9999T00:00:00'] else item['end']
        if start <= tdate <=end: return item
    return {}

def countries_for_meps(mepids,date):
    res = {}
    for mepid in mepids:
        mep = DBS['ep_meps'][mepid]
        constituency = matchInterval(mep['Constituencies'], date)
        if constituency:
            res[mepid]=constituency
    return res

def names_by_mepids(mepids):
    res = {}
    for mepid in mepids:
        mep = DBS['ep_meps'][mepid]
        res[mepid]=mep['Name']['full']
    return res


######  indexes ######


def idx_meps_by_activity():
    res = {'active':[], 'inactive':[]}
    for mep in DBS['ep_meps'].values():
        if mep.get('active'): res['active'].append({k:v for k,v in mep.items() if k not in ['changes', 'activities']})
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

def idx_meps_by_name():
    res={}
    for mep in DBS['ep_meps'].values():
        for name in mep['Name']['aliases']:
            name = normalize_name(name)
            if not name in res: res[name]=[mep]
            elif mep not in res[name]: res[name].append(mep)
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

def idx_dossiers_by_subject():
    res = {}
    for d in DBS['ep_dossiers'].values():
        for s in d['procedure'].get('subject',[]):
            if not s in res: res[s] = []
            res[s].append(d)
    return res

def idx_dossiers_by_committee():
    res = {}
    for d in DBS['ep_dossiers'].values():
        for c in d.get('committees',[]):
            if not 'date' in c:
                continue
            d = c['date']
            if isinstance(d, list):
                if not d:
                    continue
                d = d[0]
            if d < end_of_term(4):
                continue
            n = c['committee_full']
            if not n in res: res[n] = []
            res[n].append(d)
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
        dossiers = vote.get('epref', [])
        if not dossiers:
            continue
        for dossier in set(dossiers):
            if not dossier in res: res[dossier] = []
            res[dossier].append(vote)
    return res

def idx_dossiers_by_doc():
    # "activities.docs.title"
    res = {}
    for dossier in DBS['ep_dossiers'].values():
        for d in dossier.get('docs', []):
            for doc in d.get('docs',[]):
                if not doc['title'] in res: res[doc['title']]=[]
                if dossier not in res[doc['title']]: res[doc['title']].append(dossier)
        for e in dossier.get('events', []):
            for doc in e.get('docs',[]):
                if not doc['title'] in res: res[doc['title']]=[]
                if dossier not in res[doc['title']]: res[doc['title']].append(dossier)
    return res

def idx_dossiers_by_mep():
    res = {}
    for dossier in DBS['ep_dossiers'].values():
        ref = dossier['procedure']['reference']
        title = dossier['procedure']['title']
        for committee in dossier.get('committees',[]):
            if 'type' not in committee and 'responsible' not in committee:
                log(2, "warning committee in %s has neither type nor responsible" % ref)
                continue
            type=committee.get('type') or ('Responsible Committee' if committee['responsible'] else "Committee Opinion")
            for rapporteur in committee.get('rapporteur',[]):
                if not 'mepref' in rapporteur:
                    log(2,"no mepref for rapporteur in %s %s" % (ref,rapporteur))
                    continue
                if rapporteur['mepref'] not in DBS['ep_meps']:
                    log(2,"idx_dossiers_by_mep: mepref %s for %s is not in ep_meps" % (rapporteur['mepref'], ref))
                    continue
                if not rapporteur['mepref'] in res:
                    res[rapporteur['mepref']]=[]
                res[rapporteur['mepref']].append((ref,title,type))
            type="%s Shadow" % type
            for shadow in committee.get('shadows',[]):
                if not 'mepref' in shadow:
                    log(2,"no mepref for shadow in %s %s" % (ref,shadow))
                    continue
                if shadow['mepref'] not in DBS['ep_meps']:
                    log(2,"idx_dossiers_by_mep: mepref %s for %s is not in ep_meps" % (shadow['mepref'], ref))
                    continue
                if not shadow['mepref'] in res:
                    res[shadow['mepref']]=[]
                res[shadow['mepref']].append((ref,title,type))
    return res

def idx_active_dossiers():
    # procedure.stage_reached not in [ "Procedure completed", "Procedure rejected", "Procedure lapsed or withdrawn"]
    res = {'active': [], 'inactive': []}
    for dossier in DBS['ep_dossiers'].values():
        if not 'stage_reached' in dossier['procedure']:
            log(1, "no stage_reached in %s" % dossier['procedure']['reference'])
            continue
        if dossier['procedure']['stage_reached'] in [ "Procedure completed", "Procedure rejected", "Procedure lapsed or withdrawn"]:
            res['inactive'].append(dossier)
        else:
            res['active'].append(dossier)
    return res

def idx_activities_by_mep():
    res = {}
    for act in DBS['ep_mep_activities'].values():
        mep_id = act['mep_id']
        if not mep_id in res: res[mep_id] = []
        res[mep_id].append(act)
    return res

def idx_dossier_refs():
    res = []
    for doc in DBS['ep_dossiers'].values():
        res.append(doc['procedure']['reference'])
    return res

TABLES = {'ep_amendments': {'indexes': [{"fn": idx_ams_by_dossier, "name": "ams_by_dossier"},
                                        {"fn": idx_ams_by_mep, "name": "ams_by_mep"}],
                            'key': lambda x: x.get('id')},

          'ep_comagendas': {"indexes": [],
                            'key': lambda x: x.get('_id')},

          'ep_com_votes': {'indexes': [{"fn": idx_com_votes_by_dossier, "name": "com_votes_by_dossier"},
                                       {"fn": idx_com_votes_by_committee, "name": "com_votes_by_committee"}],
                           'key': lambda x: x.get('_id')},

          'ep_dossiers': {'indexes': [{"fn": idx_active_dossiers, "name": "active_dossiers"},
                                      {"fn": idx_dossiers_by_doc, "name": "dossiers_by_doc"},
                                      {"fn": idx_dossiers_by_mep, "name": "dossiers_by_mep"},
                                      {"fn": idx_dossier_refs, "name": "dossier_refs"},
                                      {"fn": idx_dossiers_by_subject, "name": "dossiers_by_subject"},
                                      {"fn": idx_dossiers_by_committee, "name": "dossiers_by_committee"}],
                          'key': lambda x: x['procedure']['reference']},

          'ep_meps': {'indexes': [{"fn": idx_meps_by_activity, "name": "meps_by_activity"},
                                  {"fn": idx_meps_by_country, "name": "meps_by_country"},
                                  {"fn": idx_meps_by_group, "name": "meps_by_group"},
                                  {"fn": idx_meps_by_name, "name": "meps_by_name"}],
                      'key': lambda x: x['UserID']},

          'ep_mep_activities': {'indexes': [{"fn": idx_activities_by_mep, "name": "activities_by_mep"},],
                                'key': lambda x: x['mep_id']},

          'ep_votes': {'indexes': [{"fn": idx_votes_by_dossier, "name": "votes_by_dossier"}],
                       'key': lambda x: x['voteid']},
}

db = Client()

if __name__ == '__main__':
    set_logfile("/tmp/db.log")
    if len(sys.argv) > 1 and sys.argv[1] == 'dev':
        init('dev_dumps')
    else:
        init('db')
    mainloop()
