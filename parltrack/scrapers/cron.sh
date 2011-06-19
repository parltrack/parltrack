#!/usr/bin/ksh

dumpsdir=${0%/*}/dumps
logdir=${0%/*}/logs

mkdir -p "$dumpsdir"
mkdir -p "$logdir"

source ${0%/*}/../../env/bin/activate

filename="com-$(date '+%Y-%m-%d-%H:%M')"
comlog="$logdir/$filename.log"
${0%/*}/ep_com_meets.py 2>"$comlog" | bzip2 -c >"$dumpsdir/$filename.json.bz2"

filename="votes-$(date '+%Y-%m-%d-%H:%M')"
voteslog="$logdir/$filename.log"
${0%/*}/ep_votes_by_year.py 2011 2>"$voteslog" | bzip2 -c >"$dumpsdir/$filename.json.bz2"

filename="dossiers-$(date '+%Y-%m-%d-%H:%M')"
dossierlog="$logdir/$filename.log"
${0%/*}/new_dossiers.py 2>"$dossierlog" | bzip2 -c >"$dumpsdir/$filename.json.bz2"
