#!/usr/bin/env python
# -*- coding: utf-8 -*-
#    This file is part of parltrack

#    parltrack is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    parltrack is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with parltrack  If not, see <http://www.gnu.org/licenses/>.

# (C) 2011 by Stefan Marsiske, <stefan.marsiske@gmail.com>, Asciimoo

from datetime import datetime
from utils.mappings import COMMITTEE_MAP
from utils.log import log, set_level
from utils.process import process
import json, re, sys
from db import db
from config import ROOT_URL
import notification_model as notif
import requests
from utils.utils import fetch_raw, jdump, unws, textdiff
from utils.notif_mail import send_html_mail

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'table': 'ep_comagendas',
    'abort_on_error': True,
}
set_level(3)

seen=set()
skip={'INTA(2023)0918_2P', 'BUDG(2023)0426_1P', 'AGRI(2022)0110_1', 'PECH(2021)0114_1'}

# '***I 2023/0266(COD) COM(2023)0441 - C9-0305/2023'
instdocre=re.compile(u'(?:(\**)(I*))?\s*([0-9A-Z/()]{12,16})?\s*([0-9A-Z/()]{12,16})?\s*(?:\[[0-9]*\])?\s*(?:[-–]\s([-0-9A-Z/()]{12,16}))?$')
refre=re.compile(r'([0-9]{4}/[0-9]{4}[A-Z]?\((?:ACI|APP|AVC|BUD|CNS|COD|COS|DCE|DEA|DEC|IMM|INI|INL|INS|NLE|REG|RPS|RSO|RSP|SYN)\))')
def getdocs(line):
    issue={}
    m=instdocre.search(unws(line))
    if m.group(1):
        issue[u'procedure_type']=m.group(1)
    if m.group(2):
        issue[u'reading']=m.group(2)
    if m.group(3):
        issue[u'epdoc']=m.group(3)
        dossier=db.dossier(m.group(3))
        if dossier:
            issue[u'docref']=dossier['procedure']['reference']
    else:
        for frag in line.split("\t"):
            frag=unws(frag)
            if refre.match(frag):
                indb=frag in db.dossier_refs()
                if indb:
                    issue['epdoc'] = frag
    if m.group(4):
        if not 'docref' in issue:
            dossiers=db.get('dossiers_by_doc', m.group(4)) or []
            if dossier and len(dossier)==1:
                issue[u'docref']=dossier[0]['procedure']['reference']
        issue[u'comdoc']=m.group(4)
    if m.group(5):
        issue[u'otherdoc']=m.group(5)
    return issue

def clean(obj, key=None):
    if isinstance(obj, dict):
        return {k: clean(v,k) for k,v  in obj.items() if v and k != "documentLinks"}
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    if key in ['date','start','end','time'] and isinstance(obj, int):
        return datetime.fromtimestamp(obj // 1000)
    return obj

    {k:v if not isinstance(v, dict) else {K:V for K,V in v.items() if V} for k,v  in elem.items() if v}

def scrape(payload, save=True, **kwargs):
    url=f"https://emeeting.europarl.europa.eu/emeeting/ecomback/ws/EMeetingRESTService/oj?language=en&reference={payload['meeting']['meetingReference']}&securedContext=false"
    if url in seen: return
    seen.add(url)
    log(3,f'scraping {payload["meeting"]["meetingReference"]} {url}')
    try:
        agenda_items=fetch_raw(url, res=True).json()
    except requests.exceptions.HTTPError as e:
        #if e.response.status_code == 500:
        log(3, "failed to get list of draft agendas for %s, month: %s %s, http error code: %s, %s" %
            (com, year, month, e.response.status_code, url))
    except:
        if payload['meeting']['meetingReference'] in skip:
            log(3,f"skipping {payload['meeting']['meetingReference']}")
            return
        log(1, f"error in fetching json from '{payload['meeting']['meetingReference']}' {url}")
        raise
    meeting={'committee': payload['committee'],
             'src': url,
             'id' : payload['meeting']["meetingReference"],
             'time': { 'date': datetime.fromtimestamp(payload['meeting']['start'] // 1000),
                       'end': datetime.fromtimestamp(payload['meeting']['end'] // 1000) },
             'type': payload['meeting']["title"],
             'city': payload['meeting']["venue"],
             'room': payload['meeting']["roomName"],
             'items': [],
            }
    if payload['meeting']["meetingCategory"] is not None:
        meeting['type']=payload['meeting']["meetingCategory"]
    items = {}
    electronic_vote = False
    for elem in agenda_items['items']:
        meeting['items'].append(clean(elem))
        if unws(elem['title']) in ['* * *', '***']:
            if electronic_vote:
                electronic_vote=False
            continue # skip end of schedule block
        #todo also handle these, see
        # https://emeeting.europarl.europa.eu/emeeting/ecomback/ws/EMeetingRESTService/oj?language=en&reference=CONT(2023)1214_1&securedContext=false
        # https://emeeting.europarl.europa.eu/emeeting/committee/en/agenda/202312/CONT?meeting=CONT-2023-1214_1&session=12-14-08-30
        if unws(elem['title']) in {'*** Electronic vote ***', "*** Voting time ***"}:
            if electronic_vote:
                if payload['meeting']['meetingReference'] in {'AFET(2017)0130_1'}:
                   electronic_vote = False
                   continue
                log(1,"scraper is already in electronic vote state in %s" % url)
            else:
                electronic_vote = True
                continue
        if unws(elem['title']) in {"*** End of electronic vote ***", "*** End of vote ***"}:
            if not electronic_vote:
                log(1,"scraper is not in electronic vote state in %s" % url)
            else:
                electronic_vote = False
                continue

        if elem['procedure'] is None:
            continue

        #print(jdump({k:v if not isinstance(v, dict) else {K:V for K,V in v.items() if V} for k,v  in elem.items() if v}))

        item = meeting['items'][-1]
        item['RCV']= electronic_vote

        # dossier references
        tmp = getdocs(elem['procedure']['reference'])
        if tmp:
            item.update(tmp)
        else:
            log(1, f"{elem['uid']} does not have an ep dossier in it's procedure: {elem['procedure']}")
            continue

        # activities - mostly tabling deadlines
        for act in elem['activities'] or []:
            if act.get("description","").startswith("Deadline for tabling amendments:"):
                tmp = act["description"]
                try:
                    item[u'tabling_deadline']=datetime.strptime(tmp.split(':')[1].strip(),"%d %B %Y, %H.%M")
                except ValueError:
                    try:
                        item[u'tabling_deadline']=datetime.strptime(tmp.split(':')[1].strip(),"%d.%m.%Y at %H.%M")
                    except:
                        log(2, '[$] unknown tabling deadline format %s' % unws(tmp))
            else:
                item["activity"]=act['description']

    id = meeting['id']
    if save:
        print(id,' - ', payload['meeting']["title"])
        print(payload['meeting'])
        process(meeting, id, db.comagenda, 'ep_comagendas', id+' - '+(payload['meeting']["title"] or "unnamed meeting"), onchanged=onchanged)
    return meeting

def onchanged(doc, diff):
    if not 'epdoc' in doc: return
    id = doc['epdoc']
    dossiers = notif.session.query(notif.Item).filter(notif.Item.name==id).all()
    recipients = set()
    for i in dossiers:
        for s in i.group.subscribers:
            recipients.add(s.email)
    if not recipients:
        return
    log(3, "sending comagenda changes to " + ', '.join(recipients))
    #(recepients, subject, change, date, url)
    send_html_mail(
        recipients=list(recipients),
        subject="[PT-Com] %s: %s" % (doc['committee'],doc['title']),
        obj = doc,
        change=diff,
        date=(sorted(doc['changes'].keys()) or ['unknown'])[-1],
        url='%scommittee/%s' % (ROOT_URL, doc['committee']),
        text=''.join((u"Parltrack has detected %s%s on the schedule of %s \n"
                    u"\n  on %s"
                    u"\n%s"
                    u"%s"
                    u"\nsee the details here: %s\n"
                    u"\nYour Parltrack team" %
                    (u"a change on " if diff else u'',
                     doc['epdoc'],
                     doc['committee'],
                     doc['date'] if 'date' in doc else 'unknown date',
                     ("\n  - %s" % u'\n  - '.join(doc['list'])) if 'list' in doc and len(doc['list'])>0 else u"",
                     "\n %s" % (textdiff(diff) if diff else ''),
                     "%sdossier/%s" % (ROOT_URL, doc['epdoc']),
                    )))
    )

from utils.process import publish_logs
def onfinished(daisy=True):
    publish_logs(get_all_jobs)

def test(meetids):
    from comagendas import topayload
    for com, month, year, id in meetids:
        payload = [m for m in topayload(com, year, month) if m['meeting']['meetingReference']==id][0]
        print(jdump(scrape(payload, save=False)))

if __name__ == "__main__":
    if len(sys.argv)>1:
        #if sys.argv[1]=='url' and len(sys.argv)==4:
        #    print(jdump(scrape(sys.argv[2], sys.argv[3])))
        #    sys.exit(0)
        #elif sys.argv[1]=="url":
        #    print('-'*30)
        #    print(jdump(scrape(sys.argv[2], 'XXXX')))
        #    print('-'*30)
        #    sys.exit(0)
        if sys.argv[1]=="test":
            test([('AFET',  1, 2017, 'AFET(2017)0130_1'),
                  ('TRAN', 12, 2023, 'TRAN(2023)1207_1'),
                  ('IMCO', 12, 2023, 'IMCO(2023)1204_1'),
                  ('EMPL', 11, 2023, 'CJ21(2023)1107_1'),
                  ]);
        #elif sys.argv[1]=='url' and len(sys.argv)==4:
        #    print(jdump(scrape(sys.argv[2], sys.argv[3])))
        #    sys.exit(0)

    # handle opts
    #args=set(sys.argv[1:])
    #saver=jdump
    #if 'save' in args:
    #    saver=save
    #if 'seq' in args:
    #    res=seqcrawler(saver=saver)
    #else:
    #    crawler(saver=saver)
