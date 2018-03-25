#!/usr/bin/env python3

from argparse import ArgumentParser
from json import loads
from os import walk
from os.path import realpath, dirname, join
from sys import path, stderr

PATH = dirname(realpath(__file__))
path.append(realpath(PATH))

from utils.multiplexer import Multiplexer

scraper_dir = join(PATH, 'scrapers')
path.append(realpath(scraper_dir))

scrapers = []

for _, _, files in walk(scraper_dir):
    for f in files:
        if f.startswith('.') or f.startswith('_') or not f.endswith('.py'):
            continue
        scrapers.append(f[:-3])


class Argparser(ArgumentParser):
    def error(self, message):
        stderr.write('error: %s\n' % message)
        self.print_help()
        exit(2)


def load_scraper(scraper):
    try:
        ret = __import__(scraper)
        for attr in ['run', 'save']:
            if not hasattr(ret, attr):
                print('[E] scraper {0} has no attribute {1}'.format(scraper, attr))
                return None
        return ret
    except Exception as e:
        print('[E] Failed to load scraper {0}: {1}'.format(f, e))
    return None


def run(results, scraper):
    stats = [0, 0]
    for r in results:
        scraper.save(loads(r), stats)
    print('added/updated: {0}/{1}'.format(*stats))


def debug(results, scraper):
    for r in results:
        print('got result', r)


def call(action, scraper, args, threads):
    print('{0} scraper {1} with args {2}'.format(action, scraper, args))
    res =  scraper.run(args)
    if res is None:
        return
    def yielder():
        for r in res:
            if r is None:
                continue
            if isinstance(r, tuple):
                scraper_fn, args = r
                mp = Multiplexer(scraper_fn, threads=threads)
                for r in mp.run(args):
                    yield r
            else:
                yield r

    actions[action](yielder(), scraper)


actions = {
    'run': run,
    'debug': debug,
}

if __name__ == '__main__':
    parser = Argparser()
    parser.add_argument(
        'scraper',
        help='scrapers: '+', '.join(scrapers),
        choices=scrapers,
        metavar='scraper',
    )
    parser.add_argument(
        '-t', '--threads',
        help='number of scraper threads',
        type=int,
        default=4,
    )
    parser.add_argument(
        'action',
        help='actoins: '+', '.join(actions.keys()),
        choices=actions.keys(),
        metavar='action',
    )
    parser.add_argument(
        'scraper_args',
        help='scraper specific arguments',
        nargs='*',
        metavar='scraper args',
    )
    args = parser.parse_args()
    scraper = load_scraper(args.scraper)
    if scraper is None:
        exit(1)
    call(args.action, scraper, args.scraper_args, threads=args.threads)
