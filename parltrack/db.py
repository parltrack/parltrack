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

# (C) 2012 by Stefan Marsiske, <stefan.marsiske@gmail.com>

try:
    from parltrack.environment import connect_db
    db = connect_db()
except:
    import pymongo
    db=pymongo.Connection().parltrack

def index(db):
    db.ep_comagendas.ensure_index([('epdoc', 1)])
    db.ep_comagendas.ensure_index([('meta.created', 1)])
    db.ep_comagendas.ensure_index([('meta.updated', 1)])
    db.ep_comagendas.ensure_index([('committee', 1)])
    db.ep_comagendas.ensure_index([('src', 1)])
    db.ep_comagendas.ensure_index([('date',1)])
    db.ep_comagendas.ensure_index([('end', 1)])
    db.ep_comagendas.ensure_index([('title',1)])
    db.ep_comagendas.ensure_index([('seq_no',1)])

    db.ep_meps2.ensure_index([('UserID', 1)])
    db.ep_meps2.ensure_index([('Name.full', 1)])
    db.ep_meps2.ensure_index([('Name.aliases', 1)])
    db.ep_meps2.ensure_index([('meta.url', 1)])
    db.ep_meps2.ensure_index([('meta.updated', 1)])
    db.ep_meps2.ensure_index([('meta.created', 1)])

    db.ep_votes.ensure_index([('epref', 1)])
    db.ep_votes.ensure_index([('dossierid', 1)])
    db.ep_votes.ensure_index([('ts', 1)])

    db.eurlex.ensure_index([('id.celexid', 1)])

    db.dossiers2.ensure_index([('procedure.reference', 1)])
    db.dossiers2.ensure_index([('procedure.subjects', 1)])
    db.dossiers2.ensure_index([('procedure.title', 1)])
    db.dossiers2.ensure_index([('procedure.stage_reached', 1)])
    db.dossiers2.ensure_index([('activities.actors.mepref', 1)])
    db.dossiers2.ensure_index([('activities.docs.title', 1)])
    db.dossiers2.ensure_index([('activities.committees.rapporteur.name', 1)])
    db.dossiers2.ensure_index([('activities.committees.shadows.name', 1)])
    db.dossiers2.ensure_index([('activities.committees.responsible', 1)])
    db.dossiers2.ensure_index([('activities.committees.committee', 1)])
    db.dossiers2.ensure_index([('meta.created', -1)])
    db.dossiers2.ensure_index([('meta.source', -1)])
    db.dossiers2.ensure_index([('meta.updated', -1)])
    db.dossiers2.ensure_index([('activities.docs.title', 1)])

    db.ep_ams.ensure_index([('reference', 1)])
    db.ep_ams.ensure_index([('meps', 1)])
if __name__ == "__main__":
    index(db)
