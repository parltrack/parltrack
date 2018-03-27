from json import loads
from lxml import html
from os import listdir, path
from requests import get
from subprocess import call
from sys import argv

import model

base_url = 'http://parltrack.euwiki.org/dumps/'

if __name__ == '__main__':
    if len(argv) != 3:
        print("possible commands: save <directory>, load <directory>")
        exit(1)
    if argv[1] == 'save':
        dom = html.fromstring(get(base_url).text)
        for link in dom.xpath('//a/@href'):
            if not link.endswith('json.xz'):
                continue
            filepath = path.join(argv[2], link)
            print('downloading', link, 'to', filepath)
            with open(filepath, 'wb') as outfile:
                outfile.write(get(base_url + link).content)
            call(["unxz", filepath])
            print(link, 'downladed and extracted')
        exit(0)
    if argv[1] == 'load':
        for f in listdir(argv[2]):
            if not f.startswith('ep_'):
                continue
            f =  path.join(argv[2], f)
            tablename = f.split('.')[0].split('_')[1]
            print(tablename)
            if tablename.endswith('s'):
                tablename = tablename[:-1]
            m = None
            for a in dir(model):
                a = getattr(model, a)
                if not hasattr(a, '__tablename__'):
                    continue
                if a.__tablename__ == tablename:
                    m = a
                    break
            if m is None:
                continue
            if model.session.query(m).count():
                print(tablename, "is not empty, skipping")
                continue
            print('loading', f)
            with open(f) as infile:
                line = infile.readline()[1:]
                i = 1
                while line:
                    if len(line.strip()) > 1:
                        data = loads(line)
                        if hasattr(m, 'load'):
                            m.load(data)
                        else:
                            model.session.add(m(data=data))
                        if i % 1000 == 0:
                            try:
                                model.session.commit()
                            except Exception as e:
                                print('error occured:', e)
                                model.session.rollback()
                                break
                            print(i, 'done..')
                        i += 1
                    line = infile.readline()
                try:
                    model.session.commit()
                except:
                    model.session.rollback()
                    continue
        exit(0)
