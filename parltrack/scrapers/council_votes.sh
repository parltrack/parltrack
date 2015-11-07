#!/usr/bin/bash

zipfile=$(mktemp)
dumpfile=$(mktemp)
wget -q -O $zipfile 'http://data.consilium.europa.eu/data/public-voting/council-votes-on-legislative-acts.zip' || exit 1
unzip -p $zipfile turtle-dump.ttl >$dumpfile || exit 1
rm $zipfile
./council_votes.py csv $dumpfile >"council-votes-$(date --rfc-3339=date).csv"
#xz -c $dumpfile >../../dumps/council-votes-$(date --rfc-3339=date).ttl.xz
rm $dumpfile
