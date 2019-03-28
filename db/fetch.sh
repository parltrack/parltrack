#!/bin/sh 

for a in ep_dossiers ep_meps_current ep_comagendas ep_votes ep_amendments ep_com_votes; do
   curl -L http://parltrack.euwiki.org/dumps/$a.json.xz | xz -dc >$a.json
done
mv ep_meps_current.json ep_meps.json

echo "do not forget to run uniq.py on ep_dossiers!"
