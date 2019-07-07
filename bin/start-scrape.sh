#!/bin/sh

echo -n '{"command": "setlog", "path": "/tmp/'$(date -Idate)'.log"}' | nc -N 127.0.0.1 7676
echo -n '{"command": "call", "scraper": "meps", "payload":{"all": false, "onfinished": {"daisy": true}}}' | nc -N 127.0.0.1 7676
