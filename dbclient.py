#!/usr/bin/env python3

import socket, sys, msgpack, struct
from utils.log import log
from utils.utils import dateJSONhandler

class DB:
    def commit(self, table):
        cmd = {"cmd": "commit", "params": {"table": table}}
        return self.send_req(cmd)

    def put(self, table, value):
        cmd = {"cmd": "put", "params": {"table": table, "value": value}}
        return self.send_req(cmd)

    def get(self, source, key):
        cmd = {"cmd": "get", "params": {"key": key, "source": source}}
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
        return db.get('meps_by_activity', "active" if key else "inactive")

    def mep(self,id):
        return db.get('ep_meps', id)

db = DB()

if __name__ == '__main__':
    log(3,len(db.meps_by_activity(True)))
