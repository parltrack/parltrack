#!/usr/bin/env python3

from db import db
from utils.log import log
from utils.utils import jdump
from utils.objchanges import diff, patch
from datetime import datetime

def process(obj, id, getter, table, name, nopreserve=None, nodiff=False, nostore=False, onchanged=None):
    if nopreserve is None: nopreserve=[]
    # clear out empty values
    obj = {k:v for k,v in obj.items() if v or v==False}

    if nodiff:
        now=datetime.utcnow().replace(microsecond=0)
        if not 'meta' in obj: obj['meta']={}
        log(3,'adding %s (%s)' % (name, id))
        obj['meta']['created']=now
        obj['changes']={}
        if not nostore and not db.put(table, obj):
            log(1,"failed to store updated obj {}".format(id))
            raise ValueError
        if onchanged is not None:
            onchanged(obj, d)
        return

    # generate diff
    prev = getter(id)
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
                raise ValueError("diff between new and patched old is not empty")

        now=datetime.utcnow().replace(microsecond=0)
        if not 'meta' in obj: obj['meta']={}
        if not prev or nodiff:
            log(3,'adding %s (%s)' % (name, id))
            obj['meta']['created']=now
            obj['changes']={}
        else:
            log(3,'updating %s (%s)' % (name, id))
            log(4,"changes for %s\n%s" % (id, jdump(d)))
            obj['meta']['updated']=now
            obj['changes']=prev.get('changes',{})
            obj['changes'][now.isoformat()]=d
        if not nostore and not db.put(table, obj):
            log(1,"failed to store updated obj {}".format(id))
            raise ValueError
        if onchanged is not None:
            onchanged(obj, d)
    del prev
    if __name__ == '__main__':
        print(jdump(obj))
    return obj


from subprocess import Popen
def publish_logs(get_all_jobs):
    jobs=get_all_jobs()
    log(4,"publish_logs, jobs: %s" % jobs)
    log(4, "publish_logs conds: %s %s %s" % (not any(jobs['queues'].values()),  not any(jobs['job_counts'].values()), not any(jobs['queues'].values()) and not any(jobs['job_counts'].values())))
    if not any(jobs['queues'].values()) and not any(jobs['job_counts'].values()):
        Popen(['/bin/sh','./publish-log.sh'])
