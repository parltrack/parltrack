#!/usr/bin/env python3

import socket, sys, msgpack, struct
from utils.log import log

class DB:
    def commit(self, table):
        cmd = {"cmd": "get", "params": {"table": table}}
        return self.send_req(sock, cmd)

    def put(self, table, value):
        cmd = {"cmd": "get", "params": {"table": table, "value": value}}
        return self.send_req(sock, cmd)

    def get(self, source, key):
        cmd = {"cmd": "get", "params": {"key": key, "source": source}}
        return self.send_req(sock, cmd)

    def send_req(self, cmd):
        server_address = '/tmp/pt-db.sock'
        req = msgpack.dumps(cmd, use_bin_type = True)

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            log(3,'connecting to db on {}'.format(server_address))
            sock.connect(server_address)

            log(3,'sending {!r}'.format(cmd))
            sock.sendall(struct.pack("I", len(req)))
            sock.sendall(req)
            log(3,'sent {} bytes'.format(len(req)+4))

            # Send request
            # make the sock a file object
            fd = sock.makefile(mode = 'rb', buffering = 65535)
            # unmarshall response
            res = msgpack.load(fd, raw = False)
            fd.close()
        finally:
            log(3,'closing socket')
            sock.close()
            return res

    def meps_by_activity(self,key=True):
        return db.get('meps_by_activity', "active" if key else "inactive")

    def mep(self,id):
        return db.get('ep_meps', id)

db = DB()

if __name__ == '__main__':
    log(3,len(db.meps_by_activity(True)))
