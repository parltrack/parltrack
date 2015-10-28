#!/usr/bin/env python
# -*- coding: utf-8 -*-

from parltrack.utils import fetch_raw, jdump, logger
from tempfile import mkstemp
from sh import pdftotext
import sys, os, re

DEBUG=False
state_map = {1: "occupation",
             2: "mandate",
             3: "activity",
             4: "membership",
             5: "occasional",
             6: "holding",
             7: "support",
             8: "other",
             9: "additional"}

iendsigs = [['Date:','Signature:'],
            [u'Fecha:', u'Firma:'],
            [u'Data:', u'Firma:'],
            [u'Päivä:', u'Allekirjoitus:'],
            [u'Päivä:', u'Allekirjoitus:'],
            [u'Kuupäev:', u'Allkiri:'],
            [u'Datums:', u'Paraksts:'],
            [u'Data', u'Parašas:'],
            [u'Data:', u'Semnătura:'],
            [u'Datum:', u'Handtekening:'],
            [u'Datum:', u'Underskrift:'],
            [u'Data:', u'Assinatura:'],
            [u'Datum:', u'Potpis:'],
            [u'Datum:', u'Podpis:'],
            [u'Dátum:', u'Podpis:'],
            [u'Data:', u'Podpis:'],
            [u'Dáta:', u'Síniú:'],
            [u'Dato:', u'Underskrift:'],
            [u'Datum:', u'Unterschrift:'],
            [u'Дата:', u'Подпис:'],
            [u'Ημερομηνία:', u'υπογραφή:'],
            [u'Ημερομηνία:', u'Υπογραφή:'],
            [u'Kelt:', u'Aláírás:']]

rownum_re = re.compile(r'^[1-9][0-9]*\. ')
def parse_table(rows, threshold=3):
    rows.append('\n') # in case last row is non-empty we need to terminate it
    ret = []
    columns = rows[0]
    column_index = {x:columns.find(str(x)) for x in range(1, 5)}
    row_texts = []

    for row in rows[1:]:
        if not row.strip():
            if row_texts:
                x_pos = max(len(l) for l in row_texts) - 1

                if x_pos > min(column_index.values()) - threshold:
                    row_text = ' '.join(x[:x_pos-1].strip() for x in row_texts)
                else:
                    row_text = ' '.join(x.strip() for x in row_texts)

                if len(row_text) > 5:
                    pos = -1
                    for i,v in column_index.items():
                        if x_pos <= v + threshold and x_pos >= v - threshold:
                            pos = i
                            break
                    ret.append((rownum_re.sub('', row_text).strip(), pos))
            row_texts = []
            continue

        row_texts.append(row)
    return ret

def parse_table_b(rows, num_of_spaces=10):
    ret = []
    row_texts = []
    row_vals = []

    for row in rows[1:]:
        if not row.strip():
            if row_texts:
                row_text = ' '.join(x.strip() for x in row_texts)

                if len(row_text) > 5:
                    ret.append((rownum_re.sub('', row_text).strip(), ' '.join(row_vals)))
            row_texts = []
            row_vals = []
            continue

        delim_pos = row.find(' '*num_of_spaces)
        if  delim_pos > -1:
            row_texts.append(row[:delim_pos+1].strip())
            row_vals.append(row[delim_pos+1:].strip())
        else:
            row_texts.append(row.strip())
    return ret

def parse_table_f(rows, threshold=2):
    ret = []
    row_texts = []
    header_rows = 0
    column_index = None
    for row in rows:
        header_rows += 1
        if not row.strip():
            break
        cols = True
        for i in range(1, 5):
            if row.find(' %s' % str(i)) == -1:
                cols = False
                break
        if cols:
            column_index = {x:row.find(str(x)) for x in range(1, 5)}

    if not column_index:
        print '>>>> meeeh, missing column index'

    for row in rows[header_rows:]:
        if not row.strip():
            if row_texts:
                x_pos = max(len(l) for l in row_texts) - 1
                trows = ([], [])
                for trow in row_texts:
                    if len(trow) < column_index[1] / 2:
                        trows[0].append(trow.strip())
                    elif len(trow.lstrip()) < column_index[1] / 2:
                        trows[1].append(trow.strip())
                    else:
                        l = len(trow)/2
                        trows[0].append(trow[:l].strip())
                        if x_pos > min(column_index.values()) - threshold:
                            trows[1].append(trow[l:-1].strip())
                        else:
                            trows[1].append(trow[l:].strip())

                r1 = ' '.join(trows[0])
                r2 = ' '.join(trows[1])
                if len(r1)+len(r2) > 5:
                    pos = -1
                    for i,v in column_index.items():
                        if x_pos <= v + threshold and x_pos >= v - threshold:
                            pos = i
                            break
                    ret.append((rownum_re.sub('', r1).strip(), r2, pos))

            row_texts = []
            continue

        row_texts.append(row)
    return ret

def getraw(pdf):
    (fd, fname)=mkstemp()
    fd=os.fdopen(fd, 'w')
    fd.write(fetch_raw(pdf).read())
    fd.close()
    text=pdftotext('-nopgbrk',
                   '-layout',
                   fname,
                   '-')
    os.unlink(fname)
    return text

def issectionhead(decl, text,ptr,curstate,state, ids):
    return (curstate==state and
        (text[ptr].strip().startswith('(%s) ' % ids[0]) or
         (decl[-len('_ES.pdf'):] in ('_ES.pdf',
                                            '_SV.pdf',
                                            '_IT.pdf',
                                            '_DA.pdf') and text[ptr].strip().startswith('%s) ' % ids[0])) or
         (state==6 and decl.endswith('_MT.pdf') and text[ptr].strip().startswith(u'G)')) or
         (decl.endswith('_BG.pdf') and text[ptr].strip().startswith(u'%s.' % ids[1])) or
         (decl.endswith('_EL.pdf') and text[ptr].strip().startswith(u'(%s)' % ids[2]))))

def scrape(decl):
    mep_id = decl.split('/')[-1].split('_')[0]
    data = {'mep_id': mep_id, 'url': unicode(decl), 'date': ''}
    logger.info("findecl scraping %s" % mep_id)

    text=getraw(decl).split('\n')
    state=0
    ptr=0
    while ptr<len(text):
        # bg: "А Б В Г Д Е  Ж З И"
        # el: "A B Γ Δ E ΣΤ Ζ H Θ"
        if (issectionhead(decl, text,ptr,state,0,('A',u'А','A')) or
            issectionhead(decl, text,ptr,state,2,('C',u'В',u'Γ')) or
            issectionhead(decl, text,ptr,state,3,('D',u'Г',u'Δ')) or
            issectionhead(decl, text,ptr,state,4,('E',u'Д',u'E')) or
            issectionhead(decl, text,ptr,state,5,('F',u'Е',u'ΣΤ'))):
            # skip to table
            while (text[ptr].split()[-4:]!=['1','2','3','4']):
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] %s table not found' % state)
                    raise IndexError
            start=ptr
            # skip empty lines
            while not text[ptr].split():
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] %s fail skip empty lines' % state)
                    raise IndexError
            while True:
                if ptr>len(text):
                    logger.error('[meh] fail past end of block %s' % state)
                    raise IndexError
                if (text[ptr].strip()=='' and
                    (text[ptr+1] in ['1',''] or
                    text[ptr+1].strip()[:3] == '1/6')):
                    break
                if text[ptr].startswith(' ' * 20) and (text[ptr].strip()[1]=='/' and
                                                       text[ptr].strip()[0] in ['2','3','4']):
                    break
                ptr+=1
            end=ptr
            state+=1
            #print >> sys.stderr, text[start:end]
            if state == 6:
                t = parse_table_f(text[start:end])
            else:
                t = parse_table(text[start:end])
            data[state_map[state]] = t
            if DEBUG:
                print "\t%s" % ('\n\t'.join((repr(x) for x in t)) or "none"), state
        elif issectionhead(decl, text,ptr,state,1,('B',u'Б', u'B')):
            while len([x for x in text[ptr].split(' ' * 10) if x]) != 2:
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] table B not found')
                    raise IndexError
            start=ptr
            # skip empty lines
            while ptr<len(text) and not text[ptr].split():
                ptr+=1
            while True:
                if ptr>len(text):
                    logger.error('[meh] fail skip empty lines in B')
                    raise IndexError
                if [text[ptr].strip(), text[ptr+1]] in (['','1'], ['','']):
                    break
                if text[ptr].startswith(' ' * 20) and (text[ptr].strip()[1]=='/' and
                                                       text[ptr].strip()[0] in ['2','3','4']):
                    break
                ptr+=1
            end=ptr
            state+=1
            t = parse_table_b(text[start:end])
            if DEBUG:
                print "\t%s" % ('\n\t'.join((repr(x) for x in t)) or "none"), state
            data[state_map[state]] = t
        elif state==6:
            while not issectionhead(decl, text,ptr,state,6,('G',u'Ж',u'Ζ')):
                ptr+=1
            # skip continuation lines
            while text[ptr].split():
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] continuation in G fail')
                    raise IndexError
            # skip empty lines
            while not text[ptr].split():
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] fail skip empty lines in G')
                    raise IndexError
            gstart=ptr
            state+=1
            while not issectionhead(decl, text,ptr,state,7,('H',u'З',u'H')):
                ptr+=1
            gend=ptr-1
            if DEBUG:
                print "\t", text[gstart:gend], state
            data[state_map[state]] = '\n'.join(x for x in map(unicode.strip, text[gstart:gend]) if x)
            # skip continuation lines
            while text[ptr].split():
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] continuation in H fail')
                    raise IndexError
            # skip empty lines
            while not text[ptr].split():
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] fail skip empty lines in H')
                    raise IndexError
            hstart=ptr
            state+=1
            while not issectionhead(decl, text,ptr,state,8,('I',u'И',u'Θ')):
                ptr+=1
            hend=ptr-1
            if DEBUG:
                print "\t", text[hstart:hend], state
            data[state_map[state]] = '\n'.join(x for x in map(unicode.strip, text[hstart:hend]) if x)
            # skip continuation lines
            while text[ptr].split():
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] continuation in I fail')
                    raise IndexError
            # skip empty lines
            while not text[ptr].split():
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] fail skip empty lines in I')
                    raise IndexError
            istart=ptr
            while True:
                tmp = text[ptr].split()
                if len(tmp)==3:
                    data['date']=tmp[1]
                    del tmp[1]
                    if tmp in iendsigs:
                        break
                elif len(tmp)==5:
                    # date=tmp[2] could be preserved in data
                    del tmp[2]
                    if tmp in [['Date', ':','Signature', ':']]:
                        break
                ptr+=1
                if ptr>=len(text):
                    logger.error('[meh] fail find end in I')
                    if DEBUG:
                        print 'meh\n>>>%s' % '\n>>>'.join(text[istart:istart+14]).encode('utf8')
                    raise IndexError
            state+=1
            if DEBUG:
                print >> sys.stderr, state
                #print >> sys.stderr, "\t", text[istart:ptr], state
            data[state_map[state]] = '\n'.join(x for x in map(unicode.strip, text[istart:ptr]) if x)
        #else:
            #print >> sys.stderr, '>>>>>>>>', line.encode('utf8')
        ptr+=1
    if state!=9:
        print >> sys.stderr, '>>>>>>>>', "wtfwtf", state
        logger.error('[wtf] did not reach final state %s' % state)
        return {}
    else:
        return data

if __name__ == "__main__":
    DEBUG=True
    print jdump(scrape(sys.argv[1]))
