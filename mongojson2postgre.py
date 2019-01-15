from json import loads
from lxml import html
from os import listdir, path
from requests import get
from subprocess import call
from sys import argv
from pprint import pprint

import model
import traceback


def mep_loader(data):
    mep_id = data['UserID']
    if not model.MEP.get_by_id(mep_id):
        try:
            mep = model.MEP.insert(data)
        except Exception as e:
            print("error with MEP", mep_id)
            raise e
        model.session.add(mep)
    else:
        raise Exception('database is not empty')


def dossier_loader(data):
    pprint(data)
    raise Exception('has data')


loaders = {
    'meps': mep_loader,
    'dossiers': dossier_loader,
}

base_url = 'http://parltrack.euwiki.org/dumps/'

if __name__ == '__main__':
    if len(argv) != 3:
        print("commands: save <directory>, load <directory>")
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
            data_name = f.split('.')[0].split('_')[1]
            f =  path.join(argv[2], f)
            loader = loaders.get(data_name)
            if loader is None:
                print('cannot find loader for', data_name)
                continue
            print('loading', f)
            with open(f) as infile:
                line = infile.readline()[1:]
                i = 1
                while line:
                    if len(line.strip()) > 1:
                        data = loads(line)
                        try:
                            loader(data)
                        except Exception as e:
                            print("got exception from loader:", e)
                            traceback.print_exc()
                            break
                        i += 1
                    if i % 100:
                        model.session.commit()
                    line = infile.readline()
            model.session.commit()
