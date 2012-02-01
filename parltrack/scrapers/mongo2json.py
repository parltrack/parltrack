#!/usr/bin/env python
import pymongo, json, sys
from datetime import datetime, date
from parltrack.utils import dateJSONhandler
conn = pymongo.Connection()
db=conn.parltrack

#print '\n'.join(["%s %s" % ((x.get('Mail') or [None])[0],x['Name']['full']) for x in
#         db.ep_meps2.find({},['Name.full','Mail','UserID'])]).encode('utf8')

#print json.dumps(list(db.dossiers2.find({})),
#      indent=1, default=dateJSONhandler, ensure_ascii=False).encode('utf8')

def jdump(obj):
   return json.dumps(obj,
         indent=1, default=dateJSONhandler, ensure_ascii=False).encode('utf8')

dbmap={'meps': db.ep_meps2,
      'oeil': db.dossiers2,
      'com': db.ep_comagendas,
      'votes': db.ep_votes,
      'eurlex': db.eurlex,
      }

all=dbmap[sys.argv[1]].find({})
print "[%s" % jdump(all[0])
for item in all[1:]:
   print ",\n%s" % jdump(item)
print "]"
