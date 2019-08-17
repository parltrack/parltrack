#!/usr/bin/env python3

import sys
from os.path import exists
from datetime import datetime
from utils.log import LEVELS

def usage():
    print("%s <debug|info|warn(ing)|err(or)> <logfile")
    sys.exit(0)

def parse(line):
    tokens = line.split()
    if len(tokens)<4: return line
    try:
        date = datetime.fromisoformat(tokens[0])
    except:
        return line
    if tokens[1] not in ['db','dossier','dossiers','mep','meps','mgr','pvote','pvotes', 'amendment', 'amendments', 'comagenda', 'comagendas', 'mep_activities', 'mep_activity', '_findecl']:
        return line
    module = tokens[1]
    if tokens[2] not in LEVELS:
        return line
    level = LEVELS.index(tokens[2])
    msg = ' '.join(tokens[3:])
    return (date, module, level, tokens[2], msg)

def dump(date, module, level, levelz, msg):
    color = (lambda x: x,
             lambda x: "\033[41m\033[93m%s\033[0m" % x, # error
             lambda x: "\033[43m\033[90m%s\033[0m" % x, # warning
             lambda x: "%s" % x, # info
             lambda x: "\033[38;2;127;127;127m%s\033[0m" % x) # debug
    cmod = {
        'db': "db",
        '_findecl': "findecl",
        "mgr": "mgr",
        "mep": "mep",
        "meps": "\033[38;2;127;127;127mmeps\033[0m",
        "dossier": "dossier",
        "dossiers": "\033[38;2;127;127;127mpvotes\033[0m",
        "pvote": "pvote",
        "pvotes": "\033[38;2;127;127;127mpvotes\033[0m",
        "amendment": "amendment",
        "amendments": "\033[38;2;127;127;127mamendments\033[0m",
        "comagenda": "comagenda",
        "comagendas": "\033[38;2;127;127;127mcomagendas\033[0m",
        "mep_activity": "mep_activity",
        "mep_activities": "\033[38;2;127;127;127mmep_activities\033[0m",
    }
    if dlevel<level:
        return
    print("%s %s %s %s" % (date.isoformat(), cmod[module], color[level](levelz), msg))

def dump_html(date, module, level, levelz, msg):
    if dlevel<level:
        return
    output.append('<tr class="log_entry %s %s"><td class="collapsing">%s</td><td class="collapsing log_module %s">%s</td><td class="collapsing log_level %s">%s</td><td>%s</td></tr>' % (module, levelz, date.isoformat(), module, module, levelz, levelz, msg))

def handle_buffer(dlevel, plev, buffer, html):
    if buffer:
        # handle buffer
        if dlevel>=plev:
                t = '\n'.join(buffer).strip()
                if t:
                    if html:
                        output.append('<tr class="log_buffer %s"><td colspan="4"><pre>%s</pre></td></tr>\n' % (plev,t))
                    else:
                        print("%s\n" % t)
        buffer=[]
    return buffer

html=False
output = []
dlevel = 0
fname = None
for arg in sys.argv[1:]:
    if arg == 'help':
        usage()
    elif arg == 'html':
        html=True
        output.append('<table id="logentries" class="ui table small compact"><thead><tr><th>Time</th><th data-filter="ddl">Module</th><th data-filter="ddl">Level</th><th>Message</th></tr></thead><tbody>')
    elif arg == 'debug':
        dlevel=4
    elif arg == 'info':
        dlevel=3
    elif arg in ['warn', 'warning']:
        dlevel=2
    elif arg in ['err', 'error']:
        dlevel=1
    else:
        print('unknown parameter "%s"' % repr(arg))
        usage()

stats = {l:0 for l in LEVELS}
changes = {}
nobody = {}
nomep = {}
plev = 0
insummary = False
exceptions=0

buffer = []
for line in sys.stdin:
    tmp = parse(line)
    if tmp==line:
        if dlevel>=plev: # only do stuff if we would print this out anyway
            if not insummary: # strip out summaries
                if line.strip() == '"summary": [':
                    buffer.append(line[:-1]+'...\033[48;2;127;127;127mstripped\033[0m...')
                    insummary=True
                    continue
            else:
                if line.strip() in [']', '],']:
                    insummary=False
                continue
            buffer.append(line[:-1])
    else:
        buffer = handle_buffer(dlevel, plev, buffer, html)
        (date, module, level, levelz, msg) = tmp
        if msg.strip()=='Traceback (most recent call last):':
            plev=0
            exceptions+=1
        stats[levelz]+=1
        if msg.startswith('no body mapping found for'):
            if msg[25:] not in nobody: nobody[msg[25:]]=0
            nobody[msg[25:]]+=1
        if msg.startswith('no mepid found for "'):
            mep = msg[len('no mepid found for "'):-1]
            if mep not in nomep: nomep[mep]=0
            nomep[mep]+=1
        if module in ['dossier','mep','pvote','amendment', 'comagenda', 'mep_activity'] and level==3 and msg.startswith("adding "):
            if module not in changes: changes[module]={'added':0, 'updated':0}
            changes[module]['added']+=1
        if module in ['dossier','mep','pvote','amendment', 'comagenda', 'mep_activity'] and level==3 and msg.startswith("updating "):
            if module not in changes: changes[module]={'added':0, 'updated':0}
            changes[module]['updated']+=1
        if html:
            dump_html(date, module, level, levelz, msg)
        else:
            dump(date, module, level, levelz, msg)
        plev = level

buffer = handle_buffer(dlevel, plev, buffer, html)
if html:
    output.append("</tbody></table>") # finish of the table containing all filtered msgs
    # print stats
    print('<h2>Summary of log messages</h2><table class="ui table definition"><thead><tr><th>Level</th><th>Count</th></tr></thead><tbody>')
    print('<tr><td class="log_level exception">Exceptions</td><td>%d</td></tr>' % exceptions)
    for l,v in stats.items():
        if l=='quiet': continue
        print('<tr><td class="l">%s</td><td>%d</td></tr>' % (l, v))
    print('</tbody></table>')

    print('<h2>Summary of changes</h2><table class="ui table definition"><thead><tr><th>Type</th><th>Added</th><th>Updated</th></tr></thead><tbody>')
    for mod, s in changes.items():
        print("<tr><td>%s</td>" % (mod))
        for l  in ['added','updated']:
            print("<td>%s</td>" % (s[l]))
        print("</tr>")
    print('</tbody></table>')

    if len(nobody)>0:
        print('<h2>Dossier events without known bodies</h2><table class="ui table definition"><thead><tr><th>Event</th><th>Count</th></tr></thead><tbody>')
        for l,v in sorted(nobody.items(),key=lambda x: x[1], reverse=True):
            print("<tr><td>%s</td><td>%d</td></tr>" % (l, v))
        print('</tbody></table>')

    if len(nomep)>0:
        print('<h2>Unknown MEPs</h2><table class="ui table definition"><thead><tr><th>Event</th><th>Count</th></tr></thead><tbody>')
        for l,v in sorted(nomep.items(),key=lambda x: x[1], reverse=True):
            print("<tr><td>%s</td><td>%d</td></tr>" % (l, v))
        print('</tbody></table><h2>Log Entries</h2>')

    print('\n'.join(output))
else:
    # print stats
    print("stats")
    for mod, s in changes.items():
        for l, v  in s.items():
            print("\t%s %s:%d" % (mod,l,v))
    print()
    print("\t%d exceptions" % exceptions)
    for l,v in stats.items():
        if l=='quiet': continue
        print("\t%d %s messages" % (v,l))
    print("nobodies")
    for l,v in sorted(nobody.items(),key=lambda x: x[1], reverse=True):
        print("\t%4d %s" % (v,l))
    print("nomeps")
    for l,v in sorted(nomep.items(),key=lambda x: x[1], reverse=True):
        print("\t%4d %s" % (v,l))
