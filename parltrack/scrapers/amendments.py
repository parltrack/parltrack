#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
from pbs import pdftotext, gs
from parltrack.utils import fetch_raw, fetch, unws, logger, jdump, diff
from parltrack.views.views import getMep
from tempfile import mkstemp, mkdtemp
from mappings import COMMITTEE_MAP
from datetime import datetime
from cStringIO import StringIO
from bbox import find_paws, remove_overlaps, slice_to_bbox
from parltrack.db import db
from dateutil.parser import parse
from shutil import rmtree

debug=False

def getdims(pdf):
    tmpdir=mkdtemp()
    gs('-q',
       '-dQUIET',
       '-dSAFER',
       '-dBATCH',
       '-dNOPAUSE',
       '-dNOPROMPT',
       '-sDEVICE=pngmono',
       '-r72x72',
       '-sOutputFile=%s/%%08d' % tmpdir,
       '-f%s' % pdf)
    mask=None
    i=0
    for fname in os.listdir(tmpdir):
        page=Image.open(tmpdir+'/'+fname) #.convert("1",dither=Image.NONE)
        if not mask:
            mask=page
        mask=ImageMath.eval("a & b", a=page, b=mask)
        i+=1
    rmtree(tmpdir)
    data = np.array(mask)
    data_slices = find_paws(255-data, smooth_radius = 5, threshold = 5)
    bboxes = remove_overlaps(slice_to_bbox(data_slices))
    m=max(bboxes,key=lambda x: (x.x2 - x.x1)*(x.y2 - x.y1))
    return (m.x1,m.y1,m.y2-m.y1,m.x2-m.x1)

def getraw(pdf):
    (fd, fname)=mkstemp()
    fd=os.fdopen(fd, 'w')
    fd.write(fetch_raw(pdf).read())
    fd.close()
    x,y,h,w = getdims(fname)
    logger.info("%s dimensions: %sx%s+%s+%s" % (datetime.now().isoformat(), x,y,h,w))
    if w<430 or h<620:
        logger.info("%s patching dimensions" % datetime.now().isoformat())
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

mepmaps={ 'Elisa Ferrreira': 'Elisa Ferreira',
          'Marcus Ferber': u'Markus Ferber',
          'Eleni Theocharus': 'Eleni Theocharous',
          u'Radvil÷ Morkūnait÷-Mikul÷nien÷': u'Radvilė MORKŪNAITĖ-MIKULĖNIENĖ',
          u'Csaba İry': u'Csaba Őry',
          u'Corina CreŃu': u'Corina CREŢU',
          u'Sidonia ElŜbieta': u'Sidonia Elżbieta JĘDRZEJEWSKA',
          'Birgit Sippel on': 'Birgit Sippel',
          u'Krišjānis KariĦš': u'Krišjānis KARIŅŠ',
          u'Sidonia ElŜbieta Jędrzejewska': u'Sidonia Elżbieta JĘDRZEJEWSKA',
          'Liz Lynne': 'Elizabeth Lynn'}

def splitNames(text):
    text = text.split(' on behalf ',1)[0]
    res=[]
    for delim in (', ', ' and ', ' & ', '; ', ','):
        if not res:
            res=filter(None,[item[:-1] if item[-1] in [',', "'", ';'] else item
                              for item in unws(text).split(delim)
                              if item])
            continue
        res=filter(None,[item[:-1] if item[-1] in [',', "'", ';'] else item
                         for elem in res
                         for item in elem.split(delim)
                         if item])
    return [mepmaps.get(x,x) for x in res]

types=['Motion for a resolution',
       'Draft opinion',
       'Proposal for a decision',
       'Proposal for a recommendation',
       "Parliament's Rules of Procedure",
       'Draft Agreement',
       'Draft report',
       'Draft legislative resolution',
       'Motion forf a resolution',
       'Proposal for a directive',
       'Proposal for a regulation']
locstarts=['After', 'Annex', 'Article', 'Chapter', 'Citation', 'Guideline',
           'Heading', 'Index', 'New', 'Paragraph', 'Part', 'Pecital', 'Point',
           'Proposal', 'Recital', 'Recommendation', 'Rejection', 'Rule',
           'Section', 'Subheading', 'Subtitle', 'Title', u'Considérant']

def istype(text):
    # get type
    found=False
    for t in types:
        if unws(text).startswith(t):
            found=True
            break
    return found

def parse_block(block, url, reference, date, committee):
    am={u'title': unws(block[0]),
        u'src': url,
        u'reference': reference,
        u'date': date,
        u'committee': committee,
        u'type': [],
        u'authors': [],
        u'meps': [],
        u'old': [],
        u'new': []}
    i=1
    while not unws(block[i]): i+=1 # skip blanks

    # parse authors
    while unws(block[i]):
        # skip leading "on behalf..."
        while block[i].lower().startswith('on behalf ') or block[i].lower().startswith('behalf of '):
            am['authors'].append(block[i])
            i+=1
        if block[i].lower().startswith('compromise amendment replacing amendment'):
            while unws(block[i]):
                try:
                    am['compromising'].append(block[i])
                except:
                    am['compromising']=[block[i]]
                i+=1
                if unws(block[i-1])[-1]!=',': break
            break
        while not unws(block[i]): i+=1        # skip blank lines
        if istype(block[i]) or unws(block[i]).split()[0] in locstarts:
            break
        # get authors
        authors=filter(None,splitNames(block[i]))
        #logger.info("asdf"+str(authors))
        if len(authors)==0: break
        # check authors in ep_meps
        tmp=filter(None,
                   [getMep(author,None)['_id']
                    for author in authors
                    if unws(author)])
        if not tmp and am['authors']: break
        am['authors'].extend(authors)
        am['meps'].extend(tmp)
        i+=1
    if len(am['meps'])<1:
        #logger.warn("%s [!] no meps found in %s\n\n%s" %
        logger.warn("%s [!] no meps found in %s" %
                    (datetime.now().isoformat(),
                     am['title'],
                     #'\n'.join(block)))
                    ))

    while not unws(block[i]): i+=1        # skip blank lines
    while block[i].lower().startswith('on behalf ') or block[i].lower().startswith('behalf of '):
        am['authors'].append(block[i])
        i+=1
    while not unws(block[i]): i+=1        # skip blank lines

    if not unws(block[i]).split()[0] in locstarts:
        if not istype(block[i]):
            logger.warn("%s [!] unknown type %s" %
                        (datetime.now().isoformat(),
                         unws(block[i])))
        am[u'type'].append(block[i])
        i+=1
        # possible continuation lines
        while unws(block[i+1]) and unws(block[i]).split()[0] not in locstarts:
            am[u'type'].append(block[i])
            i+=1

    while not unws(block[i]): i+=1        # skip blank lines

    # get location
    if not unws(block[i]).split()[0] in locstarts:
        logger.warn("%s [!] unknown type %s" % (datetime.now().isoformat(),unws(block[i])))
    am[u'location']=block[i]
    i+=1
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
        if block[i][len(block[i])/2]==' ' and (
            block[i][(len(block[i])/2)+1]==' ' or
            block[i][(len(block[i])/2)-1]==' '):
            am['old'].append(unws(block[i][:len(block[i])/2]))
            am['new'].append(unws(block[i][len(block[i])/2:]))
        else:
            am['old'].append(unws(block[i][:newstart]))
            am['new'].append(unws(block[i][newstart:]))
            if 0.1 <= (len(block[i])-newstart)/float(newstart) >= 1.5:
                logger.warn("%s %s" % (datetime.now().isoformat(),
                                       (len(block[i]), newstart, (len(block[i])-newstart)/float(newstart), block[i])))
        i+=1
    if am['new']==['deleted']:
        am['new']=[]
    while i<len(block) and not unws(block[i]): i+=1
    try:
        am['orig_lang']=unws(block[i])[4:]
    except:
        # workaround: am44 has no language:
        if (url=='http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-441.284%2b01%2bDOC%2bPDF%2bV0%2f%2fEN' and
            am['title']=="Amendment 44"):
            am['orig_lang']="en"
        else:
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
    # get mep refs in db
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
                    logger.warn("%s [!] couldn't find ref" % (datetime.now().isoformat()))
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
    if block and filter(None,block):
        res.append(parse_block(block, url, reference, date, committee))
    return res

#from lxml.etree import tostring
def getComAms(leg=7):
    urltpl="http://www.europarl.europa.eu/committees/en/%s/documents-search.html"
    postdata="clean=false&leg=%s&docType=AMCO&miType=text" % leg
    nexttpl="http://www.europarl.europa.eu/committees/en/%s/documents-search.html?action=%s&tabActif=tabResult#sidesForm "
    for com in (k for k in COMMITTEE_MAP.keys()
                if len(k)==4 and k not in ['CODE', 'RETT', 'CLIM', 'TDIP']):
        url=urltpl % (com)
        i=0
        amendments=[]
        logger.info('%s crawling %s' % (datetime.now().isoformat(), com))
        root=fetch(url, params=postdata)
        prev=[]
        while True:
            logger.info("%s %s" % (datetime.now().isoformat(), url))
            #logger.info(tostring(root))
            tmp=[a.get('href')
                 for a in root.xpath('//a[@title="open this PDF in a new window"]')
                 if (len(a.get('href',''))>13)]
            if not tmp or prev==tmp:
                break
            prev=tmp
            for u in tmp:
                if db.ep_ams.find_one({'src': u}): continue
                yield u
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
        logger.info(datetime.now().isoformat()+" "+pdf)
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
        #if sys.argv[1]=='meps':
        #    addmeprefs()
        #    sys.exit(0)
        debug=True
        while len(sys.argv)>1:
            pprint.pprint(scrape(sys.argv[1]))
            del sys.argv[1]
        sys.exit(0)
    crawler(saver=save)
