#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#    This file is part of composite data analysis tools (cdat)

#    composite data analysis tools (cdat) is free software: you can
#    redistribute it and/or modify it under the terms of the GNU
#    Affero General Public License as published by the Free Software
#    Foundation, either version 3 of the License, or (at your option)
#    any later version.

#    composite data analysis tools (cdat) is distributed in the hope
#    that it will be useful, but WITHOUT ANY WARRANTY; without even
#    the implied warranty of MERCHANTABILITY or FITNESS FOR A
#    PARTICULAR PURPOSE.  See the GNU Affero General Public License
#    for more details.

#    You should have received a copy of the GNU Affero General Public
#    License along with composite data analysis tools (cdat) If not,
#    see <http://www.gnu.org/licenses/>.

# (C) 2011, 2019 by Stefan Marsiske, <parltrack@ctrlc.hu>

import sys
from utils.utils import unws

def dump_schema(items, skip=[], title=None):
    """
    Dump schema: takes a list of data structures and computes a
    probabalistic schema out of the samples, it prints out the result
    to the output.
    @param count is optional and in case your items list is some kind of cursor that has no __len__
    @param skip is an optional list of keys to skip on the top structure
    @param title is the name for the data structure to be displayed
    """
    ax={}
    count=0
    for item in items:
        ax=scan({k:v for k,v in item.items() if k not in skip},ax)
        count+=1
    if title:
        ax['name']=title
    return(u'<div class="schema">%s</div>' % u'\n'.join(html_schema(ax,0,count)))

def scan(d, node):
    """ helper for dump_schema"""
    if not 'types' in node:
        node['types']={}
    if isinstance(d, dict):
        for k, v in d.items():
            if not 'items' in node:
                node['items']={}
            if not k in node['items']:
                node['items'][k]={'name':k}
            node['items'][k]=scan(v,node['items'][k])
    elif isinstance(d, list):
        if not 'elems' in node:
            node['elems']={}
        for v in d:
            stype=type(v)
            node['elems'][stype]=scan(v,node['elems'].get(stype,{}))
    if isinstance(d, str):
        d=unws(d) or None
    mtype=type(d)
    tmp=node['types'].get(mtype,{'count': 0, 'example': None})
    tmp['count']+=1
    if d and not tmp['example'] and not isinstance(d,dict):
        tmp['example']=d
    node['types'][mtype]=tmp
    return node

def merge_dict_lists(node):
    # ultra ugly. see test code in arch
    if ('elems' in node and
        'items' in node and
        'items' in list(node['elems'].values())[0] and
        sorted(node['items'].keys())==sorted(list(node['elems'].values())[0]['items'].keys())):

        node['types'][list]['count']+=node['types'][dict]['count']
        node['elems'][dict]['types'][dict]['count']+=node['types'][dict]['count']
        del node['types'][dict]

        for k,v in node['items'].items():
            if not k in list(node['elems'].values())[0]['items']:
                list(node['elems'].values())[0]['items'][k]=v
                continue
            for tk, tv in v['types'].items():
                if tk in list(node['elems'].values())[0]['items'][k]['types']:
                    list(node['elems'].values())[0]['items'][k]['types'][tk]['count']+=tv['count']
                else:
                    list(node['elems'].values())[0]['items'][k]['types'][tk]=tv
        del node['items']
    return node

schematpl=u"<dl><dt>{1} <span class='p'>{0}<span></dt><dd><div class='{3}'>{2}</div></dd></dl>"
def html_schema(node,indent,parent):
    """ helper for dump_schema"""
    merge_dict_lists(node)
    res=[]
    if not 'types' in node:
        print(indent)
        print(node)
        print(parent)
        sys.exit(0)
    for k,v in sorted(node['types'].items(),key=lambda x: x[1]['count'],reverse=True):
        if k==list:
            data=u"<ul>{0}</ul>".format(u''.join([u"<li>{0}</li>".format(y) for x in node['elems'].values() for y in html_schema(x,indent+1,v['count'])]))
            clss=u'contents'
        elif k==dict:
            data=u"<ul>{0}</ul>".format(u''.join([u"<li>{0}</li>".format(y) for x in node.get('items',{}).values() for y in html_schema(x,indent+1,v['count'])]))
            clss=u'contents'
        elif k==str:
            data=u"Example: {0}".format(v['example'])
            clss=u'example'
        else:
            data=u"Example: {0}".format(v['example'])
            clss= u'example'
        res.append(schematpl.format(("%02.2f%%" % (float(v['count'])/parent*100)),
                                    node.get('name','&lt;listitem&gt;'),
                                    data,
                                    clss,
                                    ))
    return res

def _html_header(table):
    """ helper for html_schema"""
    return u"""
    <link href="/static/css/schema.css" rel="stylesheet" type="text/css" />
    <div class="ui vertical segment">
      <div class="ui center aligned stackable grid container">
        <div class="row">
          <div class="left aligned column">
    <h1>Schema of the Parltrack {0} dataset</h1>
    <div class="schema-legend">Percentages show probability of this field appearing under it's parent. In case of lists, percentage also shows average length of list.</div>
    """.format(table)

def _html_footer():
    return u"""
    </div></div></div></div>
    """

def write_schema(table,DBS):
    if table in ['ep_meps', 'ep_dossiers']:
        with open("templates/schemas/%s.html" % table, "w")  as fd:
            fd.write(_html_header(table))
            fd.write(dump_schema((x for x in DBS[table].values() if x['meta'].get('updated', x['meta'].get('created')) > '2019-01-01T00:00:00'), ['changes'], title=table))
            fd.write(_html_footer())

        with open("templates/schemas/%s_v1.html" % table, "w")  as fd:
            fd.write(_html_header(table))
            fd.write(dump_schema((x for x in DBS[table].values() if x['meta'].get('updated', x['meta'].get('created')) < '2019-01-01T00:00:00'), ['changes'], title=table))
            fd.write(_html_footer())
    else:
        with open("templates/schemas/%s.html" % table, "w")  as fd:
            fd.write(_html_header(table))
            fd.write(dump_schema(DBS[table].values(), ['changes'], title=table))
            fd.write(_html_footer())

def test_dump():
    """ don't try this at home. it's an example, of how you can get a glimpse on some nosql collection"""
    from db import db, TABLES
    from utils.log import set_level

    set_level(0)
    print(_html_header())
    for table in TABLES.keys():
        #print(table, db.count(table, None), file = sys.stderr)
        vals=db.get(table, None).values()
        if len(vals) == 0: continue
        dump_schema(vals, ['changes'], title=table)
    print(_html_footer())

if __name__ == "__main__":
    test_dump()
