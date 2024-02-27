#!/usr/bin/env python3
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
from utils.utils import fetch_raw, unws
from utils.log import log
from utils.mappings import COMMITTEE_MAP
from utils.process import process
from tempfile import mkstemp
from sh import pdftotext
from db import db
from dateutil.parser import parse
from config import CURRENT_TERM as TERM

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
    'table': 'ep_amendments',
    'abort_on_error': True,
}

def getraw(pdf):
    (fd, fname)=mkstemp()
    fd=os.fdopen(fd, 'wb')
    fd.write(fetch_raw(pdf, binary=True))
    fd.close()
    text=pdftotext(#'-nopgbrk',
                   '-layout',
                   #'-x', x,
                   #'-y', y,
                   #'-H', h,
                   #'-W', w,
                   fname,
                   '-')
    os.unlink(fname)
    # remove pagebreaks and footers
    return unpaginate(text,pdf)

mepmaps={ 'Elisa Ferrreira': 'Elisa Ferreira',
          'Alexander Lambsdorff': 'Alexander Graf LAMBSDORFF',
          'Miapetra Kumpula–Natri': 'Miapetra KUMPULA-NATRI',
          'Marcus Ferber': u'Markus Ferber',
          'Eleni Theocharus': 'Eleni Theocharous',
          'Laima Liucija Andrikien÷': 'Laima Liucija ANDRIKIENĖ',
          'Sarah Ludford': 'Baroness Sarah LUDFORD',
          'Călin Cătălin ChiriŃă': "Călin Cătălin CHIRIȚĂ",
          'Marinus Wiersma': 'Jan Marinus WIERSMA',
          'Elena Valenciano Martínez-Orozco': 'Elena Valenciano',
          'Graham Watson': "Sir Graham Watson",
          'Franziska Keller': "Ska Keller",
          'Monica Luisa Macovei': 'Monica Macovei',
          'Monika Flašíková Beňová': 'Monika Beňová',
          'Janusz Władysław Zemke': 'Janusz Zemke',
          'Jarosław Leszek Wałęsa': 'Jarosław Wałęsa',
          "Iliana Malinova Iotova": "Iliana Iotova",
          'Bastiaan Belder': "Bas Belder",
          'Vilija Blinkevičiūt÷': 'Vilija BLINKEVIČIŪTĖ',
          'Filiz Hakaeva Hyusmenova': 'Filiz Hyusmenova',
          u'Radvil÷ Morkūnait÷-Mikul÷nien÷': u'Radvilė MORKŪNAITĖ-MIKULĖNIENĖ',
          u'Radvil÷ Morkūnait÷- Mikul÷nien÷': u'Radvilė MORKŪNAITĖ-MIKULĖNIENĖ',
          u'Csaba İry': u'Csaba Őry',
          u'Enikı Gyıri': u'Enikő Győri',
          u'Mairead McGuiness': u'Mairead McGUINNESS',
          u'Alfreds Rubikson': u'Alfreds RUBIKS',
          u'Luisa Monica Macovei': u'Monica MACOVEI',
          u'Monica Macovei': u'Monica Luisa MACOVEI',
          u'Judith Sargebtubu': u'Judith SARGENTINI',
          u'Lena Barbara Kolarska-Bobinska': u'Lena KOLARSKA-BOBIŃSKA',
          u'Janusz Wladyslaw Zemke': u'Janusz Władysław ZEMKE',
          u'Jacek Wlosowicz': u'Jacek WŁOSOWICZ',
          u'Jaroslaw Walesa': u'Jarosław Leszek WAŁĘSA',
          u'Teresa Jimenez Becerril': u'Teresa JIMÉNEZ-BECERRIL BARRIO',
          u'Corina CreŃu': u'Corina CREŢU',
          u'Sidonia ElŜbieta': u'Sidonia Elżbieta JĘDRZEJEWSKA',
          u'ElŜbieta Katarzyna Łukacijewska': u'Elżbieta Katarzyna ŁUKACIJEWSKA',
          u'ElŜbieta Katarzyna': u'Elżbieta Katarzyna ŁUKACIJEWSKA',
          u'ElŜbieta': u'Elżbieta Katarzyna ŁUKACIJEWSKA',
          u'Silvia-Adriana łicău': u'Silvia-Adriana ŢICĂU',
          u'Silvia- Adriana łicău': u'Silvia-Adriana ŢICĂU',
          u'Silvia -Adriana łicău': u'Silvia-Adriana ŢICĂU',
          u'Adriana łicău': u'Silvia-Adriana ŢICĂU',
          u'Maria Ad Grace Carvel': u'Maria Da Graça CARVALHO',
          u'László Tıkés': u'László Tőkés',
          'Birgit Sippel on': 'Birgit Sippel',
          u'Grace O’Sullivan': "Grace O'SULLIVAN",
          u'Hans Van Baalen': u'Johannes Cornelis van BAALEN',
          u'Krišjānis KariĦš': u'Krišjānis KARIŅŠ',
          u'Arturs Krišjānis': u'Krišjānis KARIŅŠ',
          u'Arturs Krišjānis KariĦš': u'Krišjānis KARIŅŠ',
          u'KariĦš': u'Krišjānis KARIŅŠ',
          u'Corine Lepage': u'Corinne LEPAGE',
          u'Sidonia ElŜbieta Jędrzejewska': u'Sidonia Elżbieta JĘDRZEJEWSKA',
          u'RóŜa Gräfin von Thun und Hohenstein': u'Róża Gräfin von THUN UND HOHENSTEIN',
          u'Roza Thun und Hohenstein': u'Róża Gräfin von THUN UND HOHENSTEIN',
          u'RóŜa Gräfin Von Thun Und Hohenstein': u'Róża Gräfin von THUN UND HOHENSTEIN',
          u'RóŜa Thun Und Hohenstein': u'Róża Gräfin von THUN UND HOHENSTEIN',
          u'Marielle De Starnes': u'Marielle De Sarnez',
          u'Marielle De Sarnes': u'Marielle De Sarnez',
          u'Judith Merkies': u'Judith A. MERKIES',
          u'Iziaskun Bilbao Barandica': u'Izaskun BILBAO BARANDICA',
          u'José Ignacio Samaranch Sánchez-Neyra': u'José Ignacio SALAFRANCA SÁNCHEZ-NEYRA',
          u'McMillan Scott': u'Edward McMillan-Scott',
          u'Edward McMillan Scott': u'Edward McMillan-Scott',
          u'Pablo Zalba Bidegain<': u'Pablo ZALBA BIDEGAIN',
          u'Annemie Neyts--Uyttebroeck': u'Annemie Neyts-Uyttebroeck',
          u'María Paloma Muñiz De Urquiza': u'María MUÑIZ DE URQUIZA',
          u'Petru Luhan': u'Petru Constantin LUHAN',
          u'Marije Cornelissen (Greens/EFA': u'Marije Cornelissen',
          u'Marie Eleni Koppa': u'Maria Eleni Koppa',
          u'Ilda Figueiredo (GUE/NGL': u'Ilda Figueiredo',
          u'Ramon Tremors i Balcells': u'Ramon TREMOSA i BALCELLS',
          u'Sebastian Valentin 7': u'Sebastian Valentin',
          u'Bernd Langeon behalf of the S&D Group': u'Bernd Lange',
          u'Rafał Kazimierz Trzaskowski': u'Rafał TRZASKOWSKI',
          u'Artur Zasada Bogdan': u'Artur ZASADA',
          u'Anne Jensen': u'Anne E. JENSEN',
          u'Philip Juvin': u'Philippe JUVIN',
          u'Cristian Silviu Buşoim': u'Cristian Silviu BUŞOI',
          u'Kartika Liotard': u'Kartika Tamara LIOTARD',
          u'Boguslaw Sonik': u'Bogusław SONIK',
          u'Daciana Sarbu': u'Daciana Octavia SÂRBU',
          u'Ashley Foxon': u'Ashley Fox',
          u'Ramón Jáuregui Atondo (on behalf of the S&D Group)': u'Ramón Jáuregui Atondo',
          u'Íñigo Méndez de Vigo (on behalf of the EPP Group)': u'Íñigo Méndez de Vigo',
          u'Andrew Duff (on behalf of the ALDE Group)': u'Andrew Duff',
          u'Luis de Grandes PascualDraft opinion': u'Luis de Grandes Pascual',
          u'Alfreds Rubikson behalf of the GUE/NGL Group': u'Alfreds Rubiks',
          u'Philippe Lamberts in name of the Green/Efa Group': u'Philippe Lamberts',
          u'Philippe Lamberts in name of the Greens/Efa Group': u'Philippe Lamberts',
          u'Philippe Lamberts in name of Greens/Efa Group': u'Philippe Lamberts',
          u'Philippe Lamberts in name of Green/Efa Group': u'Philippe Lamberts',
          u'Philippe Lamberts in the name of the Green/Efa Group': u'Philippe Lamberts',
          u'Eider Gardiazábal Rubialon behalf of the S&D Group': u'Eider GARDIAZÁBAL RUBIAL',
          u'Minodora Cliveta': u'Minodora CLIVETI',
          u'Olle Schmidt (on behalf of ALDE)': u'Olle Schmidt',
          u'Olle Schmidt (on behalf of the ALDE)': u'Olle Schmidt',
          u'<Members>Gunnar Hökmark': u'Gunnar Hökmark',
          u'Gunnar Hökmarkon behalf of the EPP Group': u'Gunnar Hökmark',
          u'Gunnar Hökmark<AuNomDe>{EPP}': u'Gunnar Hökmark',
          u'<Members>Gunnar Hökmark</Members><AuNomDe>{EPP}on behalf of the EPPGroup</AuNomDe>': u'Gunnar Hökmark',
          u'Monika Hohlmeier</Members><AuNomDe>{EPP}on behalf of the EPP Group</AuNomDe>Motion for a resolution': u'Monika Hohlmeier',
          u'<Members>Markus Ferber</Members><AuNomDe>{EPP}on behalf of the EPP Group</AuNomDe>': u'Markus Ferber',
          u'Edite Estrelamail.com': u'Edite ESTRELA',
          u'Catherine Souille': u'SOULLIE, Catherine',
          u'Yannik Jadot': u'Yannick Jadot',
          u'Jürgen Miguel Portas': u'Miguel PORTAS',
          u'Eider Gardiazábal Rubialon': u'Eider GARDIAZÁBAL RUBIAL',
          'Liz Lynne': 'Elizabeth Lynn'}
mansplits={u'Rodi Kratsa-Tsagaropoulou Mikael Gustafsson': [u'Rodi Kratsa-Tsagaropoulou', u'Mikael Gustafsson'],
           u'Edit Bauer Lívia Járóka': [u'Edit Bauer', u'Lívia Járóka'],
           u'Eva-Britt Svensson Gesine Meissner': [u'Eva-Britt Svensson', u'Gesine Meissner'],
           u'Sven Giegold Philippe Lamberts': ['Sven Giegold', 'Philippe Lamberts'],
           u'Philippe Lamberts Bas Eickhout': ['Philippe Lamberts', 'Bas Eickhout'],
           u'Lívia Járóka Eva-Britt Svensson': [u'Lívia Járóka', u'Eva-Britt Svensson'],
           u'Enikı Gyıri Danuta Jazłowiecka': [u'Enikő Győri',u'Danuta Jazłowiecka'],
           u'Antigoni Papadopoulou Mikael Gustafsson': ['Antigoni Papadopoulou', 'Mikael Gustafsson'],
           u'Franziska Katharina Brantner Marietta Giannakou Ana Gomes': ['Franziska Katharina Brantner', 'Marietta Giannakou', 'Ana Gomes'],
           u'Sampo Terho Ana Gomes': ['Sampo Terho', 'Ana Gomes'],
           u'Jens Geier Göran Färm': [u'Jens Geier', u'Göran Färm'],
           u'Ana Gomes Marietta Giannakou Ágnes Hankiss': [u'Ana Gomes', 'Marietta Giannakou', u'Ágnes Hankiss'],
           'Ana Gomes Krzysztof Lisek Arnaud Danjean Michael Gahler': [u'Ana Gomes', 'Krzysztof Lisek', 'Arnaud Danjean', 'Michael Gahler'],
           'Franziska Katharina Brantner Ana Gomes Krzysztof Lisek Arnaud Danjean Michael Gahler': ['Franziska Katharina Brantner', 'Ana Gomes', 'Krzysztof Lisek', 'Arnaud Danjean', 'Michael Gahler'],
           u'Ioan Mircea PaşcuRoberto Gualtieri': [u'Ioan Mircea Paşcu', 'Roberto Gualtieri'],
           u'Anna Záborská (EPP Shadow)': [u'Anna Záborská'],
           u'Gesine Meissner (ALDE Shadow)': [u'Gesine Meissner'],
           u'George Sabin Cutaş Frédéric Daerden': [u'George Sabin Cutaş', u'Frédéric Daerden'],
           u'George Sabin Cutaş Ria Oomen-Ruijten': [u'George Sabin Cutaş', u'Ria Oomen-Ruijten'],
           u'Marije Cornelissen (Greens/EFA Shadow)': [u'Marije Cornelissen'],
           u'Pilar Ayuso y Esther Herranz': [u'Pilar Ayuso', u'Esther HERRANZ GARCÍA'],
           u'Cornelia Ernst (GUE/NGL Shadow)': [u'Cornelia Ernst'],
           u'Edit Bauer (EPP Shadow)': [u'Edit Bauer'],
           u'Glenis Willmott Åsa Westlund': [u'Glenis Willmott', u'Åsa Westlund'],
           u'Glenis Willmott Nessa Childers': [u'Glenis Willmott', u'Nessa Childers'],
           u'Glenis Willmott Christel Schaldemose': [u'Glenis Willmott', u'Christel Schaldemose'],
           u'Satu Hassi Åsa Westlund': [u'Satu Hassi', u'Åsa Westlund'],
           u'Kartika Tamara Liotard Bart Staes': [u'Kartika Tamara Liotard', 'Bart Staes'],
           u'Michèle Striffler Cecilia Wikström': [u'Michèle Striffler', u'Cecilia Wikström'],
           u'Raül Romeva i Rueda Mikael Gustafsson': [u'Raül Romeva i Rueda', u'Mikael Gustafsson'],
           u'Edite Estrela (S-D Shadow)': [u'Edite Estrela'],
           u'Ilda Figueiredo (GUE/NGL Shadow)': [u'Ilda Figueiredo'],
           u"Sophia in 't Veld (ALDE Shadow)": [u"Sophia in 't Veld"],
           u'Lambert van Nistelrooij Seán Kelly': [u'Lambert van Nistelrooij', u'Seán Kelly'],
           u'Cristina Gutiérrez-Cortines Rosa Estaràs Ferragut': [u'Cristina Gutiérrez-Cortines', u'Rosa Estaràs Ferragut'],
           u'Michael Theurer Yannick Jadot': [u'Michael Theurer', 'Yannick Jadot'],
           u'Michèle Rivasi Fiona Hall': [u'Michèle Rivasi', u'Fiona Hall'],
           u'Lambert van Nistelrooij Rosa Estaràs Ferragut': [u'Lambert van Nistelrooij', u'Rosa Estaràs Ferragut'],
           u'Bernd Lange Yannick Jadot': [u'Bernd Lange', 'Yannick Jadot'],
           u'Jens Rohde Philippe Lamberts': [u'Jens Rohde', u'Philippe Lamberts'],
           u'Michael Cashman Victor Boştinaru': [u'Michael Cashman', u'Victor Boştinaru'],
           u'Derek Vaughan Göran Färm': [u'Derek Vaughan', u'Göran Färm'],
           u'Peter Skinner Sergio Gaetano Cofferati': [u'Peter Skinner', u'Sergio Gaetano Cofferati'],
           u'Roberto Gualtieri Marielle De Sarnez': [u'Roberto Gualtieri', 'Marielle De Sarnez'],
           u'Constance Le Grip Lívia Járóka': [u'Constance Le Grip', u'Lívia Járóka'],
           u'Karima Delli Ernest Urtasun': ['Karima Delli', 'Ernest Urtasun'],
           }
fookters=('<NuPE>PE754.361</NuPE>/',)
pere = r'(?P<PE>PE(?:TXTNRPE)? ?[0-9]{3,4}\.?[0-9]{3}(?:v[0-9]{2}(?:[-./][0-9]{1,2})?)?)'
amdoc=r'AM\\(?:[0-9]{4,7}|P\d_AMA\(20\d{2}\)\d{4}\([-0-9]*\)_?)(?:_REV)?_?(?:EN|XM|XT)?\.(?:doc|DOC|tmp|docx)'
pagere=r'(?:[0-9]{1,3})(?:\s*/\s*[0-9]{1,3})'
oddre = re.compile(r'\s*'+pere+'\s+'+pagere+r'\s+'+amdoc)
evenre = re.compile(r'\s*'+amdoc+r'\s+'+pagere+r'\s+'+pere)
p0re = re.compile(r'\s*'+amdoc+r'\s+'+pere)
ampenopage = re.compile(r'\s*'+pere+r'\s+'+amdoc)
oddnope = re.compile(r'\s*'+pagere+r'\s+'+amdoc)
evenope = re.compile(r'\s*'+amdoc+r'\s+'+pagere)
oddnoam = re.compile(r'\s*'+pagere+r'\s+'+pere)
evenoam = re.compile(r'\s*'+pere+r'\s+'+pagere)
onlypage = re.compile(r'\s*'+pagere+r"$")
pere=re.compile(r'\s*'+pere)
amdoc=re.compile(r'\s*'+amdoc)
def isfooter(line):
    for footer in fookters:
        if footer in line:
            return True
    return (oddre.match(line) or
            evenre.match(line) or
            p0re.match(line) or
            ampenopage.match(line) or
            oddnope.match(line) or
            evenope.match(line) or
            oddnoam.match(line) or
            evenoam.match(line) or
            pere.match(line) or
            onlypage.match(line) or
            amdoc.match(line))

def unpaginate(text, url):
    lines = text.split('\n')
    # find end of 1st page
    eo1p = 0
    PE = None
    while not lines[eo1p].startswith('\x0c') and eo1p<len(lines):
        eo1p+=1
    if eo1p == len(lines):
        log(1, "could not find end of 1st page in %s" % url)
        raise ValueError("eo1p not found: %s" % url)

    i = len(lines) - 1
    while i>=0:
        if not lines[i].startswith('\x0c'):
            i -= 1
            continue

        # we found a line starting with pagebreak
        lines[i]=lines[i][1:]
        i -= 1
        fstart = i

        # skip empty lines before pagebreak
        while i>=0 and unws(lines[i])=='':
            i-=1

        # we expect i>0 and lines[i] == 'EN' (or variations)
        if i<=0:
            log(1, "could not find non-empty line above pagebreak in %s" % url)
            raise ValueError("no EN marker found: %s" % url)

        tmp = unws(lines[i])
        if tmp not in ["EN", "EN EN", "EN United in diversity EN",
                       "EN Unity in diversity EN",
                       "EN Unie dans la diversité EN",
                       "EN In Vielfalt geeint EN",
                       "ENEN United in diversity EN",
                       "XM United in diversity XM",
                       "XT United in diversity EN",
                       "XM", "XM XM", "XT", "XT XT"]:
            if tmp in ["FR",'NL','HU']:
                log(2,'Document has non-english language marker: "%s" %s' % (tmp, url))
                return [], None
            if tmp=="Or. en":
                # no footer in this page
                continue
            if tmp in ['AM_Com_NonLegCompr', 'AM_Com_NonLegReport','AM_Com_NonLegOpinion']:
                # no footer on this page (and probably neither on the previous one which should be the first)
                continue
            # an exceptional document
            if (url=='http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-//EP//NONSGML+COMPARL+PE-532.324+01+DOC+PDF+V0//EN&language=EN' and
                tmp in ["Paragraph 8", "Pervenche Berès, Frédéric Daerden"]):
                continue
            if (url in  ['http://www.europarl.europa.eu/doceo/document/CJ25-AM-593898_EN.pdf',
                         'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-//EP//NONSGML+COMPARL+PE-593.898+01+DOC+PDF+V0//EN&language=EN'] and
                tmp=="(2016/2204(INI))"):
                continue
            if (url=='http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-//EP//NONSGML+COMPARL+PE-594.137+01+DOC+PDF+V0//EN&language=EN' and
                tmp=='(2016/2018(INI))'):
                continue
            if isfooter(tmp):
                if PE is None: # try to figure out PE id
                    m = pere.match(tmp)
                    if m: PE = m.group(0)
                log(3, 'no EN marker found, but footer: "%s"' % tmp)
                i+=1 # neutralize the decrement after this block
            else:
                log(1, 'could not find EN marker above pagebreak: %d %d "%s"' % (i, eo1p, tmp))
                raise ValueError('no EN marker found "%s" in %s' % (tmp,url))

        if lines[i].startswith('\x0c'): # we found a ^LEN^L
            # we found an empty page.
            while fstart > i:
                del lines[fstart]
                fstart -= 1
            lines[i]="\x0c"
            continue

        i -= 1

        # find the next non-empty line above the EN marker
        while i>0 and unws(lines[i])=='':
            i-=1
        if i<=0:
            log(1, "could not find non-empty line above EN marker: %s" % url)
            raise ValueError("no next line above EN marker found: %s" % url)

        if (not isfooter(lines[i])):
            tmp = unws(lines[i])
            if tmp=="Or. en":
                i+=1 # preserve this line - and cut of the rest
            elif tmp not in ['AM_Com_NonLegCompr', 'AM_Com_NonLegReport','AM_Com_NonLegOpinion']:
                log(1,'not a footer: "%s" line: %d in %s' % (repr(lines[i]),i,url))
                raise ValueError('not a footer: "%s" line: %d in %s' % (lines[i],i,url))
        elif PE is None: # try to figure out PE id
            m = pere.match(unws(lines[i]))
            if m: PE = m.group(0)

        if lines[i].startswith('\x0c'):
            # we found an empty page with only the footer
            lines[i]='\x0c'
            i+=1
        #else: # is a regular page
        #    i -= 1
        #    if unws(lines[i])!='':
        #        for j in range(-10,10):
        #            log(1, '"%s"' % (unws(lines[i+j])))
        #        log(1, 'line above footer is not an empty line: "%s"' % (unws(lines[i])))
        #        raise ValueError("no empty line above footer")

        # delete all lines between fstart and i
        while fstart >= i:
            del lines[fstart]
            fstart -= 1
    return lines, PE

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
    # only for devel.
    # for mep in res:
    #     if mep.startswith('on behalf of'): continue
    #     if mep.endswith('Shadow)'):
    #         logger.info('shadow: %s' % mep)
    res=[mep if not mep.endswith('Shadow)') else mep[:mep.rfind(' (')]
         for mep in res
         if not mep.startswith('on behalf of')]
    res=[unws(y) for x in res for y in mansplits.get(x,[x])]
    return [mepmaps.get(x,x) for x in res]

types=[u'Motion for a resolution',
       u'Motion forf a resolution',
       u'Motion for a decision',
       u"Parliament's Rules of Procedure",
       u'Council position',
       u'Draft Agreement',
       u'Draft report',
       u'Draft decision',
       u'Draft regulation',
       u'Draft legislative resolution',
       u'Draft Directive – amending act',
       u'Draft opinion Amendment',
       u'Draft Interinstitutional Agreement',
       u'Draft directive',
       u'Draft opinion',
       u'Staff Regulations of Officials of the European Union',
       u'Treaty on European Union',
       u'Treaty on the Functioning of the European Union',
       u"Parliament's Rules of Procedure",
       u'Parliament’s Rules of Procedure',
       u'Proposal for a decision',
       u'Proposal for a recommendation',
       u'Proposal for a directive',
       u'Proposal for a regulation - amending act',
       u'Proposal for a regulation.',
       u'Proposal for a regulation']
locstarts=['After', 'Annex', 'Article', 'Chapter', 'Citation', 'Guideline',
           'Heading', 'Index', 'New', 'Paragraph', 'Part', 'Pecital', 'Point',
           #'Proposal', 'Recital', 'Recommendation', 'Rejection', 'Rule',
           'Recital', 'Recommendation', 'Rejection', 'Rule', 'Preamble',
           'Section', 'Subheading', 'Subtitle', 'Title', u'Considérant', 'Indent', 'indent'
           'Paragraphe', '-', u'–', 'last', 'Amendment', 'Amendments', 'Artikel', 'Annexes',
           'Column', 'Annexe', 'Sub-heading', 'ANNEX', 'Anexo', 'Articles', 'paragraph',
           'Paragraphs', 'Subh.', 'Subheading.', 'Short', 'Single', 'First', 'Articolo',
           'Suggestion', 'Allegato','Introductory', 'Explanatory', 'Statement', 'Notes',
           'Visa', 'article', 'Thematic', 'recital', 'Legislative', '.Article', 'Art.'
           'citation', 'Recitals']

def istype(text):
    # get type
    found=False
    for t in types:
        if unws(text).lower().startswith(t.lower()):
            found=True
            break
    return found

def strip(block):
    while len(block) and not unws(block[0]):
        del block[0]
    while len(block) and not unws(block[-1]):
        del block[-1]

def not_2column(line, pagewidth, margin):
    if '  ' in line.lstrip(): return False
    beginning = ((len(line)+margin) - len(line.lstrip()))
    return beginning < pagewidth // 2 < len(line) + margin

def find_sep(block, mid):
    spaces = set.intersection(*[set([i for i in range(mid+40) if i>=len(line) or line[i]==' ']) for line in block])
    if mid not in spaces:
        for e in range(8):
            if mid+e in spaces:
                mid = mid+e
                break
            if mid-e in spaces:
                mid = mid-e
                break
        if mid not in spaces:
            #log(1,f"{mid} is not in spaces: {sorted(spaces)}")
            #print("\n".join(block))
            return None

    span = [mid, mid]
    while(span[1]+1 in spaces): span[1]=span[1]+1
    while(span[0]-1 in spaces): span[0]=span[0]-1
    #print(mid, span)
    return span

def extract_cmt(block, pagewidth, margin):
    # todo if handle also sequential diffs with comments, page 3 has a test case:
    # https://www.europarl.europa.eu/doceo/document/A-9-2023-0048-AM-157-158_EN.pdf
    #print('\n'.join(block))
    #print('asdf')
    i = len(block)-1
    orig_lang = None
    c_start = None
    c_end = None
    diff_end = len(block)-1
    comment = None
    span = None

    while (i>0
           and not unws(block[i]) in {'Text proposed by the Commission Amendment',
                                      'Present text Amendment',
                                      'Draft legislative resolution Amendment'}
           and not " "*(len(block[i])//5)+"Amendment" in block[i]):

        tmp = block[i].lstrip()
        if tmp.startswith('Or.') and len(tmp)<=6 and len(block[i])>(pagewidth - pagewidth//4):
            log(4, f"found original language: {tmp[3:].strip()}")
            orig_lang=tmp[3:].strip()
            del block[i]
            if c_end is not None: c_end-=1
            if c_start is not None: c_start-=1
            diff_end = i-1
            i-=1
            continue

        if tmp.endswith(')') and not_2column(block[i], pagewidth, margin):
           if c_end is None:
              log(4,f"found end of comment block")
              c_end = i
           else:
              log(2, f"found another comment end: {repr(block[i])}")
        if (c_end is not None
            and tmp.startswith('(')
            and not_2column(block[i], pagewidth, margin)):
            #and (unws(block[i-1])==''
            #     or (block[i-1].lstrip().startswith('Or.')
            #         and len(block[i-1].lstrip())<=6
            #         and len(block[i-1])>(pagewidth - pagewidth//4)))):
           log(4,f"found start of comment block")
           c_start = i
        i-=1

    if i<0:
        return orig_lang, comment, span
    log(4, f"found top of 2 column amendment")

    if (c_end is not None
        and c_start is not None):

        # check if diff block is really 2 column
        span = find_sep(block[i:c_start], (pagewidth) // 2 - margin)
        if not span or span[1]-span[0] < 10:
            log(2, f"find_sep failed: {span}")
            return orig_lang, comment, span

        comment = [unws(l) for l in block[c_start:c_end+1]]
        log(4, f"found comment block")
        del block[c_start:c_end+1]

    return orig_lang, comment, span

def parse_block(block, url, reference, date, rapporteur, PE, committee=None, pagewidth=None, parse_dossier=None, top_of_diff=2, margin=None):
    am={u'src': url,
        u'peid': PE,
        u'reference': reference,
        u'date': date}
    if committee is not None:
        am['committee']=committee
    strip(block)

    # get title
    try:
        am[u'seq']=int(unws(block[0]).split()[1])
    except ValueError:
        am[u'seq']=unws(block[0]).split()[1]
    except IndexError:
        log(2,"wrong seq %s" % (block[0]))
        am[u'seq']=unws(block[0])
    del block[0]

    pefix = PE.split('v')[0] # we strip of the v0[0-9]-[0-9]{1,2} part of the PEID
    am['id']="%s-%s" % (pefix,am['seq'])

    strip(block)

    # find and strip justification
    i=len(block)-1
    while i>top_of_diff and not (unws(block[i])=="Justification" and block[i].startswith(' ' * 6)):
        i-=1
    if i>top_of_diff:
        if i<len(block)-1:
            tmp = block[i+1:]
            strip(tmp)
            if len(tmp)>0:
                am['justification']='\n'.join(tmp)
            else:
                log(2,f"empty justification in am:", am['seq'], url, repr('\n'.join(block[i:])))
        del block[i:]
        strip(block)

    sep = None
    # https://www.europarl.europa.eu/doceo/document/A-9-2023-0238-AM-001-156_EN.pdf
    # has landscape tables cropped by portrait page, but not cropped by pdf to text conversion
    # https://www.europarl.europa.eu/doceo/document/A-9-2023-0048-AM-001-151_EN.pdf
    # page 66 fucks pagewidth up.
    # https://www.europarl.europa.eu/doceo/document/A-9-2023-0298-AM-001-165_EN.pdf
    # has a weird table that needs a different y_density, but that fucks up other parts of the page...
    if pagewidth is not None and pagewidth in {248, 245, 374}:
        margin = 24
        pagewidth = 171

    # https://www.europarl.europa.eu/doceo/document/A-9-2023-0033-AM-002-005_EN.pdf
    if pagewidth is not None and margin is not None:
        orig_lang, comment, span =extract_cmt(block, pagewidth, margin)
        if orig_lang is not None:
            am['orig_lang']=orig_lang
        if span is not None:
            sep = span[0]
        if comment is not None:
            am['comment']=comment
            strip(block)

    # get original language
    if ('orig_lang' not in am # we can skip this is extract_cmt already took care of it
        and 4<len(unws(block[-1]))<=6
        and unws(block[-1]).startswith('Or.')):

        am['orig_lang']=unws(block[-1])[4:]
        del block[-1]
        strip(block)

    # find split column new/old heading
    i=len(block)-1
    while (i>top_of_diff and
           not ((block[i].endswith("     Amendment") or
                 block[i].endswith("     PARTICULARS") or
                 block[i].endswith("     Remedy") or
                 block[i].endswith("     Amended text") or
                 block[i].endswith("     Amendement") or
                 block[i].endswith("           Amendments by Parliament") or
                 block[i].endswith("           Proposal for rejection") or
                 block[i].endswith("           Proposal for a rejection") or
                 block[i].endswith("           Does not affect English version") or
                 block[i].endswith("           (Does not affect English version)") or
                 block[i].endswith("      Amendment by Parliament")) and
                len(block[i])>33) and
           not (unws(block[i])=='Text proposed by the Commission' or
                unws(block[i]) in types)):
        i-=1
    if i>top_of_diff:
        #if block[i].endswith("               Proposal for rejection"):
        #    pass # location will be possibly '-'
        seq=False
        if unws(block[i]) in ["Amendment", "Amendment by Parliament"]:
            # sequential format, search for preceeding original text
            j=i
            while (j>top_of_diff and not (unws(block[j]) in types or unws(block[j])=='Text proposed by the Commission')):
                j-=1
            if j>top_of_diff: i=j
            seq=True; key='old'
        elif unws(block[i])=='Text proposed by the Commission' or block[i].strip() in types:
            seq=True; key='old'
        # throw headers
        del block[i]
        while i<len(block) and not unws(block[i]): del block[i]        # skip blank lines
        if pagewidth is not None and margin is not None:
            mid = pagewidth // 2 - margin
        else:
            mid=max([len(x) for x in block])//2
        if sep is None:
            sep = find_sep(block[i:], mid)
            if sep is not None:
                sep = sep[0]
        while i<len(block):
            if seq:
                if unws(block[i]) in ["Amendment", "Amendment by Parliament", "Text Amended"]:
                    key='new'
                    del block[i]
                    continue
                try: am[key].append(block[i])
                except KeyError: am[key]=[block[i]]
                del block[i]
                continue
            # only new, old is empty
            if not sep and block[i].startswith('         '):
                try: am['new'].append(unws(block[i]))
                except KeyError: am['new']=[unws(block[i])]
                del block[i]
                continue
            newstart = block[i].rstrip().rfind('  ')
            # only old, new is empty
            if not sep and newstart < 6:
                try: am['old'].append(unws(block[i]))
                except KeyError: am['old']=[unws(block[i])]
                del block[i]
                continue
            #mid=len(block[i])/2
            #mid=40
            if not sep:
                lsep=block[i].rfind('  ', 0, mid)
                rsep=block[i].find('  ', mid)
                sep=None
                if abs(lsep-mid)<abs(rsep-mid):
                    if abs(lsep-mid)<15:
                        sep=lsep
                else:
                    if abs(rsep-mid)<15:
                        sep=rsep
            if sep:
                try: am['old'].append(unws(block[i][:sep]))
                except KeyError: am['old']=[unws(block[i][:sep])]
                try: am['new'].append(unws(block[i][sep:]))
                except KeyError: am['new']=[unws(block[i][sep:])]
            else:
                # no sane split found
                #logger.warn("no split: %s %s\n%s" % (datetime.now().isoformat(),
                #                                     (sep, mid, len(block[i]), newstart, block[i]),
                #                                     block[i][mid-1:mid+2]))
                # fallback to naive splitting
                try: am['old'].append(unws(block[i][:newstart]))
                except KeyError: am['old']=[unws(block[i][:newstart])]
                try: am['new'].append(unws(block[i][newstart:]))
                except KeyError: am['new']=[unws(block[i][newstart:])]
            del block[i]
        strip(block)
    else:
        if not 'Does not affect English version.' in block[i:]:
            log(2, "no table\n%s" % ('\n'.join(block[i:])))
            return None
            #am['content']=block[i:]
            #return am

    i=0
    # find end of authors
    while (i<len(block) and
           unws(block[i]) and
           not unws(block[i]).lower().startswith('compromise') and
           not istype(block[i]) and
           not unws(block[i]).split()[0] in locstarts): i+=1
    if i<len(block):
        if i>0:
            names=' '.join(block[:i])
            am['authors']=unws(names)
            #logger.info("names \n%s" % names)

            # convert to pt mep _ids
            for text in filter(None,splitNames(names)):
                mepid=db.getMep(text,date)
                if mepid:
                    try: am['meps'].append(mepid)
                    except KeyError: am['meps']=[mepid]
                else:
                    log(3, "fix %s" % text)
            del block[:i]
            strip(block)
        elif rapporteur:
            am['authors']=rapporteur
            if isinstance(rapporteur,list):
                for text in rapporteur:
                    mepid=db.getMep(text,date)
                    if mepid:
                        try: am['meps'].append(mepid)
                        except KeyError: am['meps']=[mepid]
                    else:
                        log(3, "fix %s" % text)
            else:
                for text in filter(None,splitNames(rapporteur)):
                    mepid=db.getMep(text,date)
                    if mepid:
                        try: am['meps'].append(mepid)
                        except KeyError: am['meps']=[mepid]
                    else:
                        log(3, "fix %s" % text)
        else:
            log(4, "no authors in Amendment %s %s" % (am['seq'], url))
    else:
        log(2, "no boundaries in Amendment %s %s\n%s" % (am['seq'], url,
                                                      '\n'.join(block)))
        am['rest']=block
        return am

    # handle compromise info
    i=0
    while (i<len(block) and
           unws(block[i]) and
           not istype(block[i]) and
           not unws(block[i]).split()[0] in locstarts): i+=1
    if i<len(block) and i>0:
        if [unws(x) for x in block[:i]]!=["Draft proposal for a recommendation"]:
           if parse_dossier is not None:
              am['dossier'] = parse_dossier(block[:i], date)
           else:
              am['compromise']=block[:i]
        del block[:i]
        strip(block)

    i=0
    while (i<len(block) and unws(block[i])):
        if unws(block[i]).split()[0] in locstarts:
            try: am['location'].append((unws(' '.join(block[:i])),unws(block[i])))
            except KeyError: am['location']=[(unws(' '.join(block[:i])),unws(block[i]))]
            del block[:i+1]
            i=0
        else:
            i+=1
    if len(block)>0 and ((len(block)==1 or
                          not unws(block[1])) and
                         unws(block[0])!='1' and
                         'location' in am):
        am['location'][-1]=(am['location'][-1][0],"%s %s" % (am['location'][-1][1],block[0]))
        del block[0]
        strip(block)

    if block:
        if not ((len(block)==3 and
                unws(block[0])=='1' and
                not unws(block[1]) and
                block[2].startswith("  ")) or
                (len(block)==2 and
                unws(block[0])=='1' and
                block[1].startswith("  "))):
            # ignore obvious footnotes
            log(3, "rest in Amendment %s\n%s" % (am['seq'],'\n'.join(block)))
    # strip trailing empty lines from old/new
    while len(am.get('old',[])) and not unws(am['old'][-1]):
        del am['old'][-1]
    if am.get('old')==[]: del am['old']
    while len(am.get('new',[])) and not unws(am['new'][-1]):
        del am['new'][-1]
    if am.get('new')==[]: del am['new']
    return am

refre=re.compile(r'([0-9]{4}/[0-9]{4}[A-Z]?\((?:ACI|APP|AVC|BUD|CNS|COD|COS|DCE|DEA|DEC|IMM|INI|INL|INS|NLE|REG|RPS|RSO|RSP|SYN)\))')
amstart=re.compile(r' *(Emendamenti|Amende?ment)\s*[0-9A-Z]+( a|/PP)?$')
def scrape(url, meps=None, **kwargs):
    prolog=True
    res=[]
    block=None
    reference=None
    date=None
    committee=[]
    #text, PE=getraw(url)
    import pamendment
    text, PE, date, _, margin = pamendment.getraw(url)
    pagewidth = max(len(line) for line in text)
    #log(3,f"page width is {pagewidth}")
    motion = False
    for line in text:
        #log(4,'line is: "%s"' % line)
        if prolog:
            line=unws(line)
            if not line: continue

            if amstart.match(line):
                if PE is None:
                    log(1, "document has no PE id: %s" % url)
                if reference==None:
                    log(1,"[!] couldn't find ref: %s" % (unws([x for x in text[:20] if unws(x)][2])))
                    # marking as scraped though
                    if not motion:
                        log(1, "couldn't find dossier reference in source pdf: %s" % url)
                        #raise ValueError("No dossier reference in amendment: %s" % url)
                        return
                    log(3, "couldn't find dossier reference in source pdf, but was marked as motion: %s" % url)
                    return
                if date==None or committee==[]:
                    log(1,"[!] couldn't find date or committee: %s" % url)
                    raise ValueError("No date or committee in amendment")
                block=[line]
                prolog=False
                continue

            if line == 'Draft motion for a resolution': 
                log(4,"document is a draft motion for resolution")
                motion = True

            m = re.search(pere, line)
            if m:
                if PE is None: PE = m.group(0)
                log(4,"found PE reference: %s" % PE)
                line = unws(line.replace(PE,''))
                log(4,'updated line is: "%s"' % line)

            if line in COMMITTEE_MAP:
                log(4,'found committee: "%s"' % line)
                committee.append(COMMITTEE_MAP[line])
                continue

            m = re.search(refre, line)
            if (committee and not reference and m):
                reference=m.group(1)
                log(4,'found reference: "%s"' % reference)
                if url == 'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-506.166%2b03%2bDOC%2bPDF%2bV0%2f%2fEN':
                    log(3, "adjusting reference to eudatap")
                    reference="2012/0011(COD)"
                continue

            if (not date):
                try:
                    date = parse(unws(line), dayfirst=True)
                    log(4,'found date: "%s"' % line)
                except ValueError:
                    pass
                except TypeError:
                    pass
            continue

        if amstart.match(line):
            # parse block
            am=parse_block(block, url, reference, date, meps, PE, committee=committee, pagewidth=pagewidth, margin=margin)
            #am=parse_block(block, url, reference, date, meps, PE, committee)
            if am is not None:
                process(am, am['id'], db.amendment, 'ep_amendments', am['reference']+' '+am['id'], nodiff=True, **kwargs)
                res.append(am)
            block=[line]
            continue
        block.append(line)
    if block and filter(None,block):
        #am = parse_block(block, url, reference, date, meps, PE, pagewidth, committee)
        #am = parse_block(block, url, reference, date, meps, PE, committee)
        am=parse_block(block, url, reference, date, meps, PE, committee=committee, pagewidth=pagewidth, margin=margin)
        if am is not None:
            process(am, am['id'], db.amendment, 'ep_amendments', am['reference']+' '+am['id'], nodiff=True, **kwargs)
            res.append(am)
    log(3,"total amendments %d in %s" % (len(res),url))
    return res

from utils.process import publish_logs
def onfinished(daisy=True):
    publish_logs(get_all_jobs)

if __name__ == "__main__":
    from utils.utils import jdump
    #print(jdump(scrape('https://www.europarl.europa.eu/doceo/document/INTA-AM-658734_EN.pdf', ['Enikő GYŐRI'])))
    #print(jdump(scrape("http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-//EP//NONSGML+COMPARL+PE-609.623+01+DOC+PDF+V0//EN&language=EN", "Krišjānis Kariņš")))
    #print(jdump(scrape(sys.argv[1],"ANDERSSON Max")))
    print(jdump(scrape(sys.argv[1],sys.argv[2])))
