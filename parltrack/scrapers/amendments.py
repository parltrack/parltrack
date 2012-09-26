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
from parltrack.utils import fetch_raw, fetch, unws, logger, jdump, diff
from parltrack.views.views import getMep
from tempfile import mkstemp
from pbs import pdftotext
from mappings import COMMITTEE_MAP
from datetime import datetime
from parltrack.db import db
from dateutil.parser import parse

debug=False

def getraw(pdf):
    (fd, fname)=mkstemp()
    fd=os.fdopen(fd, 'w')
    fd.write(fetch_raw(pdf).read())
    fd.close()
    x,y,h,w = 70,63,631,473
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
          u'Radvil÷ Morkūnait÷- Mikul÷nien÷': u'Radvilė MORKŪNAITĖ-MIKULĖNIENĖ',
          u'Csaba İry': u'Csaba Őry',
          u'Enikı Gyıri': u'Enikő Győri',
          u'Mairead McGuiness': u'Mairead McGUINNESS',
          u'Alfreds Rubikson': u'Alfreds RUBIKS',
          u'Luisa Monica Macovei': u'Monica Luisa MACOVEI',
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
           }

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
    res=[y for x in res for y in mansplits.get(x,[x])]
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
       u'Proposal for a decision',
       u'Proposal for a recommendation',
       u'Proposal for a directive',
       u'Proposal for a regulation - amending act',
       u'Proposal for a regulation.',
       u'Proposal for a regulation']
locstarts=['After', 'Annex', 'Article', 'Chapter', 'Citation', 'Guideline',
           'Heading', 'Index', 'New', 'Paragraph', 'Part', 'Pecital', 'Point',
           #'Proposal', 'Recital', 'Recommendation', 'Rejection', 'Rule',
           'Recital', 'Recommendation', 'Rejection', 'Rule',
           'Section', 'Subheading', 'Subtitle', 'Title', u'Considérant', 'Indent',
           'Paragraphe', '-', u'–', 'last', 'Amendment', 'Artikel', 'Annexes',
           'Column', 'Annexe', 'Sub-heading', 'ANNEX', 'Anexo', 'Articles', 'paragraph',
           'Paragraphs', 'Subh.', 'Subheading.', 'Short', 'Single', 'First', 'Articolo',
           'Suggestion', 'Allegato','Introductory', 'Explanatory', 'Statement', 'Notes',
           'Visa', 'article', 'Thematic', 'recital', 'Legislative', '.Article',
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

def parse_block(block, url, reference, date, committee):
    am={u'src': url,
        u'reference': reference,
        u'date': date,
        u'committee': committee}

    #logger.info(block)
    # get title
    try:
        am[u'seq']=int(unws(block[0]).split()[1])
    except ValueError:
        am[u'seq']=unws(block[0]).split()[1]
    except IndexError:
        logger.warn("%s wrong seq" % (datetime.now().isoformat()), block[0])
        am[u'seq']=unws(block[0])
    del block[0]

    strip(block)

    # find and strip justification
    i=len(block)-1
    while i>2 and not (unws(block[i])=="Justification" and block[i].startswith(' ' * 6)):
        i-=1
    if i>2:
        if i<len(block)-1 and (not unws(block[i+1]) or not block[i+1].startswith(' ') ):
            am['justification']='\n'.join(block[i+2:])
            del block[i:]
            strip(block)
        else:
            logger.warn("%s wrong justification\n%s" % (datetime.now().isoformat(), '\n'.join(block[i:])))

    # get original language
    if 4<len(unws(block[-1]))<=6 and unws(block[-1]).startswith('Or.'):
        am['orig_lang']=unws(block[-1])[4:]
        del block[-1]
        strip(block)

    # find split column new/old heading
    i=len(block)-1
    while (i>2 and
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
    if i>2:
        #if block[i].endswith("               Proposal for rejection"):
        #    pass # location will be possibly '-'
        seq=False
        if unws(block[i]) in ["Amendment", "Amendment by Parliament"]:
            # sequential format, search for preceeding original text
            j=i
            while (j>2 and not (unws(block[j]) in types or unws(block[j])=='Text proposed by the Commission')):
                j-=1
            if j>2: i=j
            seq=True; key='old'
        elif unws(block[i])=='Text proposed by the Commission' or unws(block[i]) in types:
            seq=True; key='old'
        # throw headers
        del block[i]
        while i<len(block) and not unws(block[i]): del block[i]        # skip blank lines
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
            if block[i].startswith('         '):
                try: am['new'].append(unws(block[i]))
                except KeyError: am['new']=[unws(block[i])]
                del block[i]
                continue
            newstart = block[i].rstrip().rfind('  ')
            # only old, new is empty
            if newstart < 6:
                try: am['old'].append(unws(block[i]))
                except KeyError: am['old']=[unws(block[i])]
                del block[i]
                continue
            #mid=len(block[i])/2
            mid=40
            lsep=block[i].rfind('  ', 0, mid)
            # todo calculate both, and use the one closer to the center
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
        logger.warn("%s no table\n%s" % (datetime.now().isoformat(), '\n'.join(block[i:])))
        am['content']=block[i:]
        return am

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
            am['authors']=names
            #logger.info("names \n%s" % names)

            # convert to pt mep _ids
            for text in filter(None,splitNames(names)):
                mep=getMep(text,None,True)
                if mep:
                    try: am['meps'].append(mep)
                    except KeyError: am['meps']=[mep]
                else:
                    logger.info("fix %s" % text)
            del block[:i]
            strip(block)
        else:
            logger.info("%s no authors in Amendment %s" % (datetime.now().isoformat(), am['seq']))
    else:
        logger.warn("%s no boundaries in Amendment %s\n%s" % (datetime.now().isoformat(),
                                                              am['seq'],
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
        am['compromise']=block[:i]
        del block[:i]
        strip(block)

    i=0
    while (i<len(block) and unws(block[i])):
        if unws(block[i]).split()[0] in locstarts:
            try: am['location'].append((' '.join(block[:i]),unws(block[i])))
            except KeyError: am['location']=[(' '.join(block[:i]),unws(block[i]))]
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
            logger.info("rest in Amendment %s\n%s" % (am['seq'],'\n'.join(block)))
    return am

refre=re.compile(r'[0-9]{4}/[0-9]{4}\([A-Z]*\)')
amstart=re.compile(r' *(Emendamenti|Amende?ment)\s*[0-9A-Z]+( a|/PP)?$')
def scrape(url):
    if (url in ['http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-483.680%2b02%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-454.387%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-456.679%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-494.504%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.705%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.767%2b02%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-454.385%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-465.012%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.724%2b01%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.721%2b02%2bDOC%2bPDF%2bV0%2f%2fEN',
                'http://www.europarl.europa.eu/sides/getDoc.do?pubRef=-%2f%2fEP%2f%2fNONSGML%2bCOMPARL%2bPE-469.723%2b03%2bDOC%2bPDF%2bV0%2f%2fEN']
        or not url.endswith('EN')):
        logger.info("skipping unparsable url")
        return []
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
                    logger.warn("%s [!] couldn't find ref: %s" %
                                (datetime.now().isoformat(),
                                 unws([x for x in text[:20] if unws(x)][2])))
                    # marking as scraped though
                    db.ep_ams.save({'src': url})
                    return []
                if date==None or committee==[]:
                    raise ValueError
                block=[line]
                prolog=False
                continue

            line=unws(line)

            if not line: continue

            if line in COMMITTEE_MAP:
                committee.append(COMMITTEE_MAP[line])
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
def getComAms(leg=7, update=False):
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
            if update: break
            i+=1
            url=nexttpl % (com,i)
            root=fetch(url)

def save(data, stats):
    for item in data:
        query={'src': item['src'],
               'date': item['date'],
               'seq': item['seq'],
               'committee': item['committee'],
               'reference': item['reference']}
        if 'location' in item:
            query['location']=item['location']
        else:
            query['location']={ '$exists': False }
        # todo uncomment and remove next line after - devel only
        #res=db.ep_ams.find_one(query) or {}
        res={}
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
                logger.info((u'%s updating %s Amendment %s' % (datetime.now().isoformat(),
                                                               item['reference'],
                                                               item['seq'])).encode('utf8'))
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
        if sys.argv[1]=='update':
            crawler(saver=save)
            sys.exit(0)
        debug=True
        while len(sys.argv)>1:
            logger.info(sys.argv[1])
            pprint.pprint(scrape(sys.argv[1]))
            del sys.argv[1]
        sys.exit(0)
    crawler(saver=save)
