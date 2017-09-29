DUMPDIR="/var/www/parltrack/dumps/"
exec  >${DUMPDIR}/full-$(date '+%s').log 2>&1

. /var/www/parltrack/env/bin/activate

/var/www/parltrack/parltrack/scrapers/ep_meps.py in seq null
/var/www/parltrack/parltrack/scrapers/ep_meps.py out seq 
/var/www/parltrack/parltrack/scrapers/ep_meps.py current seq
# defer dumping of meps after acts update

/var/www/parltrack/parltrack/scrapers/oeil.py newseq
/var/www/parltrack/parltrack/scrapers/oeil.py updateseq  && { 
   /bin/rm -f /tmp/parltrack/* 
   for a in 'http://parltrack.euwiki.org/dossier/2011/0195%28COD%29' 'http://parltrack.euwiki.org/dossier/2012%2F0011%28COD%29#ams' ; do 
       curl -qs "$a" >/dev/null; 
   done 
}
/var/www/parltrack/parltrack/scrapers/mongo2json.py oeil | xz >/tmp/3edcsxc && mv /tmp/3edcsxc ${DUMPDIR}/ep_dossiers.json.xz

/var/www/parltrack/parltrack/scrapers/acts.py
/var/www/parltrack/parltrack/scrapers/mongo2json.py meps | xz >/tmp/3edcsxc && mv /tmp/3edcsxc ${DUMPDIR}/ep_meps_current.json.xz

/var/www/parltrack/parltrack/scrapers/ep_comagendas.py save seq
/var/www/parltrack/parltrack/scrapers/mongo2json.py com | xz >/tmp/3edcsxc && mv /tmp/3edcsxc ${DUMPDIR}/ep_comagendas.json.xz

/var/www/parltrack/parltrack/scrapers/ep_votes.py $(date '+%Y')
/var/www/parltrack/parltrack/scrapers/mongo2json.py votes | xz >/tmp/3edcsxc && mv /tmp/3edcsxc ${DUMPDIR}/ep_votes.json.xz

/var/www/parltrack/parltrack/scrapers/amendments.py update
/var/www/parltrack/parltrack/scrapers/mongo2json.py ams | xz >/tmp/3edcsxc && mv /tmp/3edcsxc ${DUMPDIR}/ep_amendments.json.xz

/var/www/parltrack/parltrack/scrapers/ep_com_votes.py
/var/www/parltrack/parltrack/scrapers/mongo2json.py comvotes | xz >/tmp/3edcsxc && mv /tmp/3edcsxc ${DUMPDIR}/ep_com_votes.json.xz

/var/www/parltrack/parltrack/filters/attendance.py > /var/www/parltrack/dumps/attendance.csv.new && {
   mv /var/www/parltrack/dumps/attendance.csv.new /var/www/parltrack/dumps/attendance.csv
}
rm /var/www/parltrack/dumps/attendance.csv.new 2>/dev/null

#/var/www/parltrack/parltrack/scrapers/mongo2json.py eurlex | xz >/tmp/3edcsxc && mv /tmp/3edcsxc ${DUMPDIR}/eurlex.json.xz

zipfile=$(mktemp)
dumpfile=$(mktemp)
wget -q -O $zipfile 'http://data.consilium.europa.eu/data/public-voting/council-votes-on-legislative-acts.zip' || exit 1
unzip -p $zipfile turtle-dump.ttl >$dumpfile || exit 1
rm $zipfile
/var/www/parltrack/parltrack/scrapers/council_votes.py csv $dumpfile | xz >"/var/www/parltrack/dumps/council-votes.csv.xz"
/var/www/parltrack/parltrack/scrapers/council_votes.py json $dumpfile | xz >"/var/www/parltrack/dumps/council-votes.json.xz"
rm $dumpfile
