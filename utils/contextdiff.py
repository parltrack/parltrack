#!/usr/bin/env python3

from sys import stderr
from utils.utils import jdump, diff_prettyHtml

ansi = {
    'added': "\033[32m%s\033[0m",    # bg \033[42m
    'deleted': "\033[31m%s\033[0m",  # bg \033[41m
    'changed': "\033[31m%s\033[32m%s\033[0m",
    'indent': "   ",
    'header': '',
    'footer': '',
    'objprefix': '',
    'objpostfix': '',
    'keyprefix': '',
    'keypostfix': ': ',
    'valprefix': '',
    'valpostfix': '',
    'keyheaderprefix': '',
    'keyheaderpostfix': '',
}


semantic = {
    'added': "<ins>%s</ins>",
    'deleted': "<del>%s</del>",
    'changed': "<del>%s</del><ins>%s</ins>",
    'indent': "",
    'header': '<div class="ui grid container padded diff">',
    'footer': "</div>",
    'objprefix': '<div class="ui grid container">',
    'objpostfix': '</div>',
    'keyprefix': '<div class="two wide column">',
    'keyheaderprefix': '<div class="sixteen wide column">\n',
    'keyheaderpostfix': '</div>',
    'keypostfix': '</div>',
    'valprefix': '<div class="fourteen wide column">',
    'valpostfix': '</div>',
}


table = {
    'added': "<ins>%s</ins>\n",
    'deleted': "<del>%s</del>\n",
    'changed': "<del>%s</del>\n<ins>%s</ins>\n",
    'indent': "",
    'header': '<div class="ui container diff">\n',
    'footer': "</div>\n",
    'objprefix': '<table class="ui table">\n',
    'objpostfix': '</table>\n',
    'keyprefix': '<tr>\n<td>\n',
    'keyheaderprefix': '<tr>\n<th colspan="2">\n',
    'keyheaderpostfix': '</th></tr>\n',
    'keypostfix': '</td>\n',
    'valprefix': '<td>\n',
    'valpostfix': '</td>\n</tr>\n',
}

mail = {
    'added': '<ins>%s</ins>\n',
    'deleted': '<del>%s</del>\n',
    'changed': '<div class="changed row"><del class="column">%s</del>\n<ins class="column">%s</ins></div>\n',
    'indent': "",
    'header': '<div class="wrapper">\n',
    'footer': "</div>\n",
    'objprefix': '<table class="table">\n',
    'objpostfix': '</table>\n',
    'keyprefix': '<tr class="key">\n<td class="td">\n',
    'keyheaderprefix': '<tr>\n<th colspan="2">\n',
    'keyheaderpostfix': '</th></tr>\n',
    'keypostfix': '</td>\n',
    'valprefix': '<td class="td">\n',
    'valpostfix': '</td>\n</tr>\n',
}

# helper for nesteddiff
def paths2tree(changes):
    res = {}
    for change in sorted(changes, key=lambda x: x['path']):
        path = change['path']
        node = res
        for seg in path:
            if not 'kids' in node:
                node['kids']={}
            if not seg in node['kids']:
                node['kids'][seg]={}
            node = node['kids'][seg]
        if not 'change' in node:
            node['change']=[]
        node['change'].append({'type':change['type'],
                               'data':change['data']})

    return res

from itertools import groupby, count
def lst2ints(l):
    l = [list(g) for _, g in groupby(sorted(set(l)), lambda n, c=count(): n-next(c))]
    return ','.join(['{}-{}'.format(u[0], u[-1]) if len(u) > 1 else str(u[0]) for u in l])

# helper for walk
def format_obj(obj, depth, tpl):
    iter = None
    if isinstance(obj, dict):
        return ('\n'+tpl['indent']*(depth)).join(['',tpl['objprefix']]+
                                                 [''.join((
                                                     tpl['keyprefix'],
                                                     str(k).title(),
                                                     tpl['keypostfix'],
                                                     tpl['valprefix'],
                                                     format_obj(v, depth+1,tpl),
                                                     tpl['valpostfix']))
                                                  for k,v in obj.items()]+[tpl['objpostfix']])
    if isinstance(obj,list):
        return ('\n'+tpl['indent']*(depth)).join(['',tpl['objprefix']]+
                                                 [''.join((
                                                     tpl['keyprefix'],
                                                     format_obj(v, depth+1,tpl),
                                                     tpl['valpostfix']))
                                                  for v in obj]+[tpl['objpostfix']])
    if iter is None:
        return str(obj)

import diff_match_patch

# helper for nesteddiff
def walk(node, changes, tpl, depth=0):
    ret = []
    if changes.get('change'):
        for change in changes['change']:
            if (change['type']) == 'changed':
                if [type(x) for x in change['data']] == [str,str]:
                    de=diff_match_patch.diff_match_patch()
                    diffs=de.diff_main(change['data'][0],change['data'][1])
                    de.diff_cleanupSemantic(diffs)
                    ret.append(diff_prettyHtml(de, diffs))
                else:
                    ret.append(tpl['changed'] % (format_obj(change['data'][0], depth, tpl), format_obj(change['data'][1], depth, tpl)))
            else:
                ret.append(tpl[change['type']] % format_obj(change['data'], depth, tpl))
    elif changes.get('kids'):
        if isinstance(node, dict):
            ret.append(tpl['objprefix'])
            #unchanged=[]
            for k,v in sorted(node.items(), key=lambda x: str(x[0]).upper()):
                if k in changes['kids']:
                    ret.append(''.join((tpl['keyprefix'],
                                        str(k).title(),
                                        tpl['keypostfix'],
                                        tpl['valprefix'],
                                        walk(node[k], changes['kids'][k], tpl, depth+1),
                                        tpl['valpostfix'])))
                    del changes['kids'][k]
                elif depth>0:
                    #unchanged.append(k)
                    #if type(v) in (dict, list):
                    #    v = '{unchanged}'
                    #ret.append(''.join((tpl['keyprefix'],str(k),tpl['keypostfix'],tpl['valprefix'],str(v),tpl['valpostfix'])))
                    if type(v) not in (dict, list):
                        ret.append(''.join((tpl['keyprefix'],str(k).title(),tpl['keypostfix'],tpl['valprefix'],str(v),tpl['valpostfix'])))
            #ret.append(''.join((tpl['keyprefix'],"unchanged items", tpl['keypostfix'], tpl['valprefix'], ', '.join(unchanged),tpl['valpostfix'])))
            for k, change in sorted(changes['kids'].items(), key=lambda x: str(x[0]).upper()):
                if k in node: continue
                ret.append(''.join((tpl['keyprefix'],str(k).title(),tpl['keypostfix'],tpl['valprefix'],walk({}, change, tpl, depth+1),tpl['valpostfix'])))
            ret.append(tpl['objpostfix'])
        elif isinstance(node, list):
            ret.append(tpl['objprefix'])
            #unchanged = []
            for idx, item in enumerate(node):
                if idx in changes['kids']:
                    ret.append(''.join((tpl['keyprefix'],walk(node[idx], changes['kids'][idx], tpl, depth+1),tpl['valpostfix'])))
                    #ret.append(''.join((tpl['keyprefix'],repr(idx),tpl['keypostfix'],tpl['valprefix'],walk(node[idx], changes['kids'][idx], tpl, depth+1),tpl['valpostfix'])))
                #else:
                    #unchanged.append(idx)
                    #if type(item) in (dict,list):
                    #    item = '{unchanged}'
                    #ret.append(''.join((tpl['keyprefix'],item,tpl['valpostfix'])))
                    #ret.append(''.join((tpl['keyprefix'],repr(idx),tpl['keypostfix'],tpl['valprefix'],item,tpl['valpostfix'])))
            #ret.append(''.join((tpl['keyprefix'],"unchanged list items: ", lst2ints(unchanged),tpl['valpostfix'])))
            for k, change in sorted(changes['kids'].items(), key=lambda x: str(x[0]).upper()):
                if len(node)>k: continue
                #ret.append(''.join((tpl['keyprefix'],repr(k),tpl['keypostfix'],tpl['valprefix'],walk({}, change, tpl, depth+1), tpl['valpostfix'])))
                ret.append(''.join((tpl['keyprefix'],walk({}, change, tpl, depth+1), tpl['valpostfix'])))
            ret.append(tpl['objpostfix'])
        else:
            ret.append(''.join((tpl['valprefix'],node,tpl['valpostfix'])))
    else:
        ret.append("%s%s%s%s{unchanged}%s" % (tpl['keyprefix'],str(node).title(),tpl['keypostfix'],tpl['valprefix'],tpl['valpostfix']))

    return ('\n'+tpl['indent']*(depth))+('\n'+tpl['indent']*(depth)).join(ret)

# returns a rendering of a set of `changes` for a given object with some ansi color highlighting in the terminal
def nesteddiff(obj, changes, tpl=ansi):
    ctree = paths2tree(changes)
    #from pprint import pprint
    #pprint(ctree)
    return "%s%s%s" % (tpl['header'],walk(obj, ctree, tpl),tpl['footer'])


def format_path(path):
    return '.'.join([str(y).capitalize() for y in path[:-1]])


def render_path(obj, formatted_parent, cs, ret, done, merged_changes, tpl, toplevel=True):
    parent=getitem(obj,cs[0]['path'][:-1]) if len(cs[0]['path'])>1 else None
    done.append(formatted_parent)
    isiterable = False
    for c in cs:
        if c['type']=='changed':
            node = c['data'][1]
        else:
            node = c['data']
        if isinstance(node, dict) or isinstance(node, list):
            isiterable = True
            break
    if isinstance(parent,dict) and not isiterable:
        #val = [tpl['objprefix'], tpl['keyprefix'], formatted_parent, tpl['keypostfix']]
        val = [tpl['keyheaderprefix'], formatted_parent, tpl['keyheaderpostfix']]
        for k,v in parent.items():
            rec = False
            nextparent="%s.%s" % (formatted_parent, k)
            for _k in merged_changes.keys():
                if nextparent == _k and _k not in done:
                    val, done = render_path(obj, _k, merged_changes[_k], val, done, merged_changes, tpl, False)
                    rec = True
                    #val.append(''.join((tpl['objprefix'],valx,tpl['objpostfix'])))
            if rec: continue
            if k in [c['path'][-1] for c in cs]:
                val.append(''.join((tpl['keyprefix'],k.capitalize(),tpl['keypostfix'])))
                c = [c for c in cs if k == c['path'][-1]][0]
                if (c['type']) == 'changed':
                    # TODO refactor
                    if [type(x) for x in c['data']] == [str,str]:
                        de=diff_match_patch.diff_match_patch()
                        diffs=de.diff_main(c['data'][0],c['data'][1])
                        de.diff_cleanupSemantic(diffs)
                        change_str = diff_prettyHtml(de, diffs)
                    else:
                        change_str = tpl['changed'] % (format_obj(c['data'][0], 0, tpl), format_obj(c['data'][1], 0, tpl))
                    val[-1] += "%s%s%s" % (tpl['valprefix'],change_str, tpl['valpostfix'])
                else:
                    val[-1] += "%s%s%s" % (tpl['valprefix'],tpl[c['type']] % format_obj(c['data'], 0, tpl), tpl['valpostfix'])
            else:
                val.append(''.join((tpl['keyprefix'],k.capitalize(),tpl['keypostfix'],tpl['valprefix'],str(v),tpl['valpostfix'])))
        for c in cs:
            if [c['path'][-1] for c in cs] and c['type']=='deleted':
                val.append(''.join((tpl['keyprefix'],c['path'][-1].capitalize(),tpl['keypostfix'],tpl['valprefix'],tpl[c['type']] % format_obj(c['data'], 0, tpl),tpl['valpostfix'])))
        ret.append(''.join(('\n'.join(val))))
    else:
        val = []
        for c in cs:
            if toplevel:
                formatted_path = '.'.join([y.capitalize() for y in c['path'] if isinstance(y, str)])
                if (c['type']) == 'changed':
                    if [type(x) for x in c['data']] == [str,str]:
                        de=diff_match_patch.diff_match_patch()
                        diffs=de.diff_main(c['data'][0],c['data'][1])
                        de.diff_cleanupSemantic(diffs)
                        change_str = diff_prettyHtml(de, diffs)
                    else:
                        change_str = tpl['changed'] % (format_obj(c['data'][0], 0, tpl), format_obj(c['data'][1], 0, tpl))
                    val.append(''.join((tpl['keyprefix'],tpl['keypostfix'],tpl['valprefix'],change_str,tpl['valpostfix'])))
                else:
                    val.append(''.join((tpl['keyprefix'],tpl['keypostfix'],tpl['valprefix'],tpl[c['type']] % format_obj(c['data'], 0, tpl),tpl['valpostfix'])))
            else:
                formatted_path = c['path'][-2].capitalize()
                if (c['type']) == 'changed':
                    val.append(''.join((tpl['keyprefix'],formatted_path,tpl['keypostfix'],tpl['valprefix'],tpl['changed'] % (format_obj(c['data'][0], 0, tpl), format_obj(c['data'][1], 0, tpl)),tpl['valpostfix'])))
                else:
                    val.append(''.join((tpl['keyprefix'],formatted_path,tpl['keypostfix'],tpl['valprefix'],tpl[c['type']] % format_obj(c['data'], 0, tpl),tpl['valpostfix'])))
        if toplevel:
            ret.append(''.join((tpl['keyheaderprefix'],formatted_path,tpl['keyheaderpostfix'],*val)))
        else:
            ret.append(''.join(val))
    return ret, done

from utils.objchanges import getitem
def sequentialdiff(obj, changes, tpl=ansi):
    # TODO '2019-03-18T02:35:51' is bugged, fixme
    ret = []
    #table{table-layout: fixed !important; width: 100% !important; } td{width:50%!important;   overflow-wrap: break-word; word-wrap: break-word;}

    merged_changes = {}
    for c in changes:
        parent = tuple(c['path'])
        if parent not in merged_changes: merged_changes[parent] = []
        merged_changes[parent].append(c)

    #print('-'*60)
    #print(jdump([[list(k),v] for k,v in merged_changes.items()]))
    #print('-'*60)

    done = []
    for parent,cs in sorted(merged_changes.items(),key=lambda x: x[0][0].upper()):
        formatted_parent = format_path(parent)
        if formatted_parent not in done:
            ret, done = render_path(obj, formatted_parent, cs, ret, done, merged_changes, tpl)

    return ''.join((tpl['header'],tpl['objprefix'],'\n'.join(ret),tpl['objpostfix'],tpl['footer']))

from utils.objchanges import revert
def recreate(obj, date):
    changes = obj['changes']
    del obj['changes']
    for d,c in sorted(changes.items(), key=lambda x: x[0], reverse=True)[:-1]:
        if date > d:
            break
        try:
            obj = revert(obj, c)
        except:
            print('failed to revert obj', d, c)
            break
    return obj

if __name__ == "__main__":
    from utils.log import set_level
    set_level(0)
    from db import db
    m = db.dossier('2004/2001(BUD)')
    #m = db.mep(4289)
    #m = db.mep(108570)

    date = sorted(m['changes'].keys(),reverse=True)[0]
    #print("changes from %s" % date, file=stderr)
    #date = '2019-03-18T02:35:51'
    change=m['changes'][date]
    #m = recreate(m, date)
    #del m['changes']
    #print(jdump(change))
    print(nesteddiff(m, change, mail))
    #print(sequentialdiff(m, change, ansi))
    #print(sequentialdiff(m, change, table))

    #for change in sorted(m['changes'].keys(),reverse=True):
    #    print('-------------------------------', change)
    #    print(sequentialdiff(m, m['changes'][change], ansi))
    #    input()
