#!/usr/bin/env python3

from db import db
from utils.log import log
from utils.utils import jdump
from utils.objchanges import diff, patch # todo decide if to remove this sanity check?
from datetime import datetime

def process(obj, id, getter, table, name, nopreserve=[], nodiff=False, nostore=False):
    # clear out empty values
    obj = {k:v for k,v in obj.items() if v}

    if nodiff: # todo remove after first activities commit())
        now=datetime.utcnow().replace(microsecond=0)
        if not 'meta' in obj: obj['meta']={}
        log(3,'adding %s (%s)' % (name, id))
        obj['meta']['created']=now
        obj['changes']={}
        if not db.put(table, obj):
            log(1,"failed to store updated obj {}".format(id))
            raise ValueError
        return

    # generate diff
    prev = getter(id)
    if prev is not None and 'activities' in prev: del prev['activities'] # todo remove after first activity scrape
    if prev is not None:
        d=diff({k:v for k,v in prev.items() if not k in ['meta', 'changes', '_id']},
               {k:v for k,v in obj.items() if not k in ['meta', 'changes', '_id']})

        # preserve some top level items
        d1 = []
        for c in d:
            if c['type']!='deleted' or len(c['path']) != 1 or c['path'][0] in nopreserve:
                d1.append(c)
                continue
            if c['type']=='deleted' and len(c['path']) == 1 and c['data'] in ({},[]):
                d1.append(c)
                continue
            log(2,"preserving deleted path {} for obj id: {}".format(c['path'], id))
            obj[c['path'][0]]=prev[c['path'][0]]
        d = d1
    else:
        d=diff({}, {k:v for k,v in obj.items() if not k in ['meta', 'changes', '_id']})

    if d:
        # attempt to recreate current version by applying d to prev
        o2 = patch(prev or {}, d)
        if not o2:
            log(1,"failed to recreate {} record by patching previous version with diff".format(id))
            raise ValueError
        else:
            # make a diff between current record, an recreated one
            zero=diff({k:v for k,v in o2.items() if not k in ['meta', 'changes', '_id']},
                      {k:v for k,v in obj.items() if not k in ['meta', 'changes', '_id']})
            if zero != []:
                log(1,"id:{} diff between current record and patched previous one is not empty\n{!r}".format(id, zero))
                raise ValueError

        now=datetime.utcnow().replace(microsecond=0)
        if not 'meta' in obj: obj['meta']={}
        if not prev:
            log(3,'adding %s (%s)' % (name, id))
            obj['meta']['created']=now
            obj['changes']={}
        else:
            log(3,'updating %s (%s)' % (name, id))
            log(4,"changes for %d\n%s" % (id, jdump(d)))
            obj['meta']['updated']=now
            obj['changes']=prev.get('changes',{})
        obj['changes'][now.isoformat()]=d
        if not nostore and not db.put(table, obj):
            log(1,"failed to store updated obj {}".format(id))
            raise ValueError
    del prev
    if __name__ == '__main__':
        print(jdump(obj))
    return obj
