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

# (C) 2015 by Stefan Marsiske, <stefan.marsiske@gmail.com>, Asciimoo

import rdflib, csv, sys, json
from rdflib.namespace import RDF

class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return unicode(obj.isoformat())
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))

def jdump(d):
    # simple json dumper default for saver
    return json.dumps(d, default=dateJSONhandler, ensure_ascii=False)

cols = ['id', 'date', 'act', 'type', 'action', 'procedure', 'rule',
        'status', 'session', 'council_doc', 'ep_doc', 'area',
        'config']

def out(g, format='json'):
    votes = {}
    countries = []
    for (a,b,c) in g.triples((None, rdflib.term.URIRef(u'http://data.consilium.europa.eu/data/public_voting/qb/dimensionproperty/act'), None)):
        res={}
        for x in g.triples((a, None, None)):
            val = g.preferredLabel(x[2])
            val = val[0][1].toPython() if val else x[2].toPython()
            k = x[1].toPython().split('/')[-1]
            res[k]=val
        if res['id'] not in votes:
            votes[res['id']]={
                'id': res['id'],
                'date': res['actdate'],
                'act': res['act'],
                'type': res['acttype'],
                'action': res['actionbycouncil'],
                'procedure': res['votingprocedure'],
                'rule': res['votingrule'],
                'status': res['publicationstatus'],
                'session': res['sessionnrnumber'],
                'council_doc': res['docnrcouncil'],
                'ep_doc': res.get('docnrinterinst'),
                'area': res['policyarea'],
                'config': res['configuration'],
            }
        votes[res['id']][res['country']] = res['vote']
        if res['country'] not in countries: countries.append(res['country'])

    if format=='json':
        print '['
        for vote in sorted(votes.values()):
            print jdump(vote),','
        print ']'

    elif format=='csv':
        writer = csv.writer(sys.stdout)
        cols.extend(sorted(countries))
        writer.writerow(cols)

        for vote in sorted(votes.values()):
            writer.writerow([vote.get(k) for k in cols])

if __name__ == "__main__":
    format='json'
    if 'json' in sys.argv:
        del sys.argv[sys.argv.index('json')]
    if 'csv' in sys.argv:
        format='csv'
        del sys.argv[sys.argv.index('csv')]
    if len(sys.argv)<=1:
        dump='turtle-dump.ttl'
    else:
        dump=sys.argv[1]
    g = rdflib.Graph()
    g.parse(dump, format='n3')
    out(g, format)
