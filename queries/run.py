import argparse
from time import time
from importlib import import_module
from json import loads
from operator import itemgetter
from os import listdir
from os.path import dirname, realpath

DIR = dirname(realpath(__file__))
MODULES = [x.replace('.py', '') for x in listdir(DIR) if x.endswith('py') and x != 'run.py']


class Context():
    def __init__(self, output, json_dir):
        self.output = open(output, 'w')
        self.json_dir = json_dir

    def iterate_json(self, fname):
        with open(f'{self.json_dir}/{fname}.json', 'r') as infile:
            while line := infile.readline():
                line = line[1:-1]
                if not line:
                    continue
                obj = loads(line)
                yield obj

    def latest(self, l):
        return list(sorted(l, key=itemgetter('end')))[-1]

    def write_line(self, l):
        self.output.write(f'{l}\n')

    def close(self):
        self.output.close()


def module(mstr):
    try:
        m = import_module(f'{mstr}')
    except:
        raise ValueError(f'Module not found. Possible choices: {", ".join(MODULES)}')
    return m


def execute(args):
    print(f'Executing query "{args.query.__name__}" - writing output to "{args.output}"')
    ctx = Context(args.output, args.json_dir)
    start = time()
    args.query.run(ctx)
    print(f'Successful query execution. Runtime: {(time()-start):.2f}s')
    ctx.close()


def list_queries(args):
    print('Available queries:')
    print('\n'.join(f' - {x}' for x in MODULES))


def main():
    p = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sp = p.add_subparsers(help='sub-command help', required=True)
    r = sp.add_parser('execute', aliases=['e'], help='execute a query')
    r.set_defaults(func=execute)
    r.add_argument('query', type=module, help='query to execute')
    r.add_argument('output', help='output file name')
    r.add_argument('-j', '--json-dir', help='directory of the json data files', default='db/')
    l = sp.add_parser('list', aliases=['l'], help='list queries')
    l.set_defaults(func=list_queries)
    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
