#!/usr/bin/env python
#    This file is part of parltrack.

#    parltrack is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    parltrack is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with parltrack.  If not, see <http://www.gnu.org/licenses/>.

# (C) 2012 by Stefan Marsiske, <stefan.marsiske@gmail.com>

import os, re, sys
import Image, ImageMath
import numpy as np
from pbs import pdftotext
from parltrack.utils import fetch_raw, fetch, unws, logger, jdump, diff
from tempfile import mkstemp
from mappings import COMMITTEE_MAP
from datetime import datetime
from wand.image import Image as wimage
from cStringIO import StringIO
from bbox import find_paws, remove_overlaps, slice_to_bbox
from parltrack.db import db
from dateutil.parser import parse

def getdims(fp):
    im=wimage(file=fp)
    mask=None
    i=0
    while im.sequence:
        im.format='png'
        imfp = StringIO()
        im.save(file=imfp)
        del im.sequence.index
        imfp.seek(0)
        page=Image.open(imfp).convert("1",dither=Image.NONE)
        if not mask:
            mask=page
        imfp.close()
        mask=ImageMath.eval("a & b", a=page, b=mask)
        i+=1
    im.close()
    data = np.array(mask)
    data_slices = find_paws(255-data, smooth_radius = 5, threshold = 5)
    bboxes = remove_overlaps(slice_to_bbox(data_slices))
    m=max(bboxes,key=lambda x: (x.x2 - x.x1)*(x.y2 - x.y1))
    return (m.x1,m.y1,m.y2-m.y1,m.x2-m.x1)

def getraw(pdf):
    (fd, fname)=mkstemp()
    fd=os.fdopen(fd, 'w')
    fd.write(fetch_raw(pdf).read())
    fd.seek(0)
    x,y,h,w = getdims(fd)
    fd.close()
    logger.info("%s dims: %s %s %s %s" % (datetime.now().isoformat(), x,y,h,w))
    if w<430 or h<620:
        logger.warn("%s patching dimensions to: 89, 63, 628, 438" % datetime.now().isoformat())
        x, y, h, w = 89, 63, 628, 438
    text=pdftotext('-nopgbrk',
                   '-layout',
                   '-x', x,
                   '-y', y,
                   '-H', h,
                   '-W', w,
                   fname,
                   '-')
    os.unlink(fname)
    return text

def parse_block(block, url, reference, date, committee):
    am={u'title': unws(block[0]),
        u'src': url,
        u'reference': reference,
        u'date': date,
        u'committee': committee,
        u'authors': [],
        u'old': [],
        u'new': []}
    i=1
    am['authors'].extend(unws(block[i]).split(', '))
    while unws(block[i]).endswith(','):
        i+=1
        am['authors'].extend(unws(block[i]).split(', '))
    i+=1
    if block[i].lower().startswith('on behalf of the'): i+=1
    while not unws(block[i]): i+=1
    am[u'type']=block[i]
    i+=1
    while not unws(block[i]): i+=1
    am[u'location']=block[i]
    i+=1
    #logger.warn("%s\n%s\n%s\n\n" % (i,am,block))
    # skip over split table header
    while not unws(block[i]): i+=1
    i+=1
    while not unws(block[i]): i+=1
    #logger.info(am)
    while unws(block[i]):
        # rule out "Or. " lines.
        if 4<len(unws(block[i]))<=6 and unws(block[i]).startswith('Or.'):
            break
        if block[i].startswith('       '):
            am['new'].append(unws(block[i]))
            i+=1
            continue
        newstart = block[i].rstrip().rfind('  ')
        if newstart < 6:
            am['old'].append(unws(block[i]))
            i+=1
            continue
        if 0.1 < (len(block[i])-newstart)/float(newstart) < 1.5:
            am['old'].append(unws(block[i][:newstart]))
            am['new'].append(unws(block[i][newstart:]))
        else:
            logger.warn("%s %s" % (datetime.now().isoformat(),
                                   (len(block[i]), newstart, (len(block[i])-newstart)/float(newstart), block[i])))
        i+=1
    if am['new']==['deleted']:
        am['new']=[]
    while i<len(block) and not unws(block[i]): i+=1
    try:
        am['orig_lang']=unws(block[i])[4:]
    except:
        logger.warn(datetime.now().isoformat()+str(am)+"\n"+str(block))
        raise
    i+=1
    while i<len(block) and not unws(block[i]): i+=1
    if i<len(block) and unws(block[i])=="Justification":
        i+=1
        while i<len(block) and not unws(block[i]): i+=1
        tmp=[]
        while i<len(block) and unws(block[i]):
            tmp.append(unws(block[i]))
            i+=1
        am['justification']='\n'.join(tmp)
    return am

refre=re.compile(r'[0-9]{4}/[0-9]{4}\([A-Z]*\)')
amstart=re.compile(r'Amendment [0-9A-Z]+$')
def scrape(url):
    prolog=True
    res=[]
    block=None
    reference=None
    date=None
    committee=[]
    text=getraw(url).split('\n')
    for line in text:
        if prolog:
            if amstart.match(line):
                if reference==None:
                    logger.warn("[!] %s couldn't find ref, in %s" % (datetime.now().isoformat(), url))
                    return []
                if date==None or committee==[]:
                    raise ValueError
                block=[line]
                prolog=False
                continue

            line=unws(line)

            if not line: continue

            if line in COMMITTEE_MAP:
                # FIXME some pdfs are in french, so committee names also :/
                committee.append(line)
                continue

            if (committee and
                  not reference and
                  re.match(refre, line)):
                reference=line
                continue

            if (reference and
                not date):
                try:
                    date = parse(unws(line))
                except ValueError:
                    pass
            continue

        if amstart.match(line):
            # parse block
            res.append(parse_block(block, url, reference, date, committee))
            block=[line]
            continue
        block.append(line)
    if filter(None,block):
        res.append(parse_block(block, url, reference, date, committee))
    return res

#from lxml.etree import tostring
def getComAms():
    urltpl="http://www.europarl.europa.eu/committees/en/%s/documents-search.html"
    postdata="clean=false&leg=7&docType=AMCO&miType=text"
    nexttpl="http://www.europarl.europa.eu/committees/en/%s/documents-search.html?action=%s&tabActif=tabResult#sidesForm "
    for com in (k for k in COMMITTEE_MAP.keys() if len(k)==4 and k not in ['CODE', 'RETT', 'CLIM', 'TDIP']):
        url=urltpl % (com)
        i=0
        amendments=[]
        logger.info('%s crawling %s' % (datetime.now().isoformat(), com))
        root=fetch(url, params=postdata)
        prev=[]
        while True:
            logger.info("%s scraping %s" % (datetime.now().isoformat(), url))
            #logger.info(tostring(root))
            tmp=[a.get('href')
                 for a in root.xpath('//a[@title="open this PDF in a new window"]')
                 if (len(a.get('href',''))>13)]
            if not tmp or prev==tmp:
                break
            for u in tmp:
                if db.ep_ams.find_one({'src': u}): continue
                yield u
            prev=tmp
            i+=1
            url=nexttpl % (com,i)
            root=fetch(url)

def save(data, stats):
    for item in data:
        query={'location': item['location'],
               'src': item['src'],
               'date': item['date'],
               'type': item['type'],
               'title': item['title'],
               'committee': item['committee'],
               'authors': item['authors'],
               'reference': item['reference']}
        res=db.ep_ams.find_one(query) or {}
        d=diff(dict([(k,v) for k,v in res.items() if not k in ['_id', 'meta', 'changes']]),
               dict([(k,v) for k,v in item.items() if not k in ['_id', 'meta', 'changes',]]))
        if d:
            now=datetime.utcnow().replace(microsecond=0)
            if not 'meta' in item: item[u'meta']={}
            if not res:
                #logger.info((u'adding %s %s' % (item['reference'], item['title'])).encode('utf8'))
                item['meta']['created']=now
                if stats: stats[0]+=1
            else:
                logger.info((u'%s updating %s %s' % (datetime.now().isoformat(),
                                                     item['reference'],
                                                     item['title'])).encode('utf8'))
                logger.info(d)
                item['meta']['updated']=now
                if stats: stats[1]+=1
                item['_id']=res['_id']
            item['changes']=res.get('changes',{})
            item['changes'][now.isoformat()]=d
            db.ep_ams.save(item)
    if stats: return stats
    else: return data

def crawler(saver=jdump):
    stats=[0,0]
    for pdf in getComAms():
        logger.info(datetime.now().isoformat()+" scraping "+pdf)
        ctr=[0,0]
        try:
            saver(scrape(pdf), ctr)
        except:
            # ignore failed scrapes
            logger.warn("[!] %s failed to scrape: %s" % (datetime.now().isoformat(), pdf))
            #logger.warn(traceback.format_exc())
            raise
        logger.info("%s [i] added/updated: %s/%s" % (datetime.now().isoformat(), ctr[0],ctr[1]))
        stats[0]+=ctr[0]
        stats[1]+=ctr[1]
    logger.info("%s [o] total added/updated: %s/%s" % (datetime.now().isoformat(),stats[0],stats[1]))

if __name__ == "__main__":
    import pprint, sys
    if len(sys.argv)>1:
        while len(sys.argv)>1:
            pprint.pprint(scrape(sys.argv[1]))
            del sys.argv[1]
        sys.exit(0)
    crawler(saver=save)
