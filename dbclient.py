#!/usr/bin/env python3

import socket, sys, msgpack, struct
from utils.log import log

class DB:
    def get(self, source, key):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_address = '/tmp/pt-db.sock'
        log(3,'connecting to db on {}'.format(server_address))
        sock.connect(server_address)
        try:
            # Send request
            cmd = {"cmd": "get", "params": {"key": key, "source": source}}
            self.send_req(sock, cmd)
            # make the sock a file object
            fd = sock.makefile(mode = 'rb', buffering = 65535)
            # unmarshall response
            res = msgpack.load(fd, raw = False)
        finally:
            log(3,'closing socket')
            sock.close()
            fd.close()
            return res

    def send_req(self, sock, cmd):
        log(3,'sending {!r}'.format(cmd))
        req = msgpack.dumps(cmd, use_bin_type = True)
        sock.sendall(struct.pack("I", len(req)))
        sock.sendall(req)
        log(3,'sent {} bytes'.format(len(req)+4))

    def meps_by_activity(self,key=True):
        return db.get('meps_by_activity', "active" if key else "inactive")

    def mep(self,id):
        return db.get('ep_meps', id)

db = DB()

if __name__ == '__main__':
    log(3,len(db.meps_by_activity(True)))
