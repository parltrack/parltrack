#!/usr/bin/bash

tmpdir='.'
zipfile=$(mktemp -p $tmpdir)
dumpfile=$(mktemp -p $tmpdir)
wget -q -o $zipfile 'http://data.consilium.europa.eu/data/public-voting/council-votes-on-legislative-acts.zip' || exit 1
unzip -p council-votes-on-legislative-acts.zip turtle-dump.ttl >$dumpfile || exit 1
rm $zipfile
./council_votes.py csv $dumpfile >"council-votes-$(date --rfc-3339).csv"
#xz -c $dumpfile >../../dumps/council-votes-$(date --rfc-3339).ttl.xz
rm $dumpfile
