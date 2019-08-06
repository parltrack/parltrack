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

# (C) 2019 by Stefan Marsiske, <stefan.marsiske@gmail.com>, Asciimoo

from db import db
from utils.process import process
import requests


if __name__ == "__main__":
    csv = requests.get('https://github.com/TechToThePeople/mep/raw/production/data/meps.nogender.csv').text
    genders = [l.split(',')[:2] for l in csv.split('\n')][1:-1]
    try:
        for mepid, gender in genders:
            mep = db.mep(int(mepid))
            if not mep:
                print("meeeeeheeheheh", mepid)
                continue
            mep['Gender'] = gender
            process(mep, int(mepid), db.mep, 'ep_meps', mep['Name']['full'], nopreserve=(['Addresses'], ['assistants']))
    finally:
        db.commit('ep_meps')
