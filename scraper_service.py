import asyncore
import os
import socket
import sys
import traceback

from imp import load_source
from json import loads, dumps
from queue import Queue
from threading import Thread
from datetime import datetime


CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}

scrapers = {}


def add_job(scraper_name, payload):
    scraper = scrapers.get(scraper_name)
    if not scraper:
        raise Exception("Unknown scraper")
    scraper._queue.put(payload)
    print('{2} {0} added to {1} queue'.format(payload, scraper._name,datetime.isoformat(datetime.now())))


def run_scraper(scraper):
    error = None
    max_threads = scraper.CONFIG['threads']
    pool = Queue(maxsize=max_threads)
    for i in range(max_threads):
        Thread(target=consume, args=(pool, scraper), name=scraper._name + str(i)).start()

    while error is None:
        pool.put(scraper._queue.get(True), True)


def consume(pool, scraper):
    while True:
        job = pool.get(True)
        print("{2} starting {0} job ({1})".format(scraper._name, job,datetime.isoformat(datetime.now())))
        try:
            scraper.scrape(**job)
        except:
            print("{1} failed to execute {0} job".format(scraper._name,datetime.isoformat(datetime.now())))
            traceback.print_exc()
        else:
            print("{1} {0} job finished".format(scraper._name,datetime.isoformat(datetime.now())))


def load_scrapers():
    scrapers = {}
    for scraper in os.listdir('scrapers/'):
        if scraper.startswith('_') or not scraper.endswith('.py'):
            continue
        try:
            name = scraper[:-3]
            import_path = 'scrapers.'+name
            if import_path in sys.modules:
                del sys.modules[import_path]
            s = load_source(import_path, 'scrapers/' + scraper)
        except:
            print("failed to load scraper", scraper)
            traceback.print_exc()
            continue
        s._queue = Queue()
        scrapers[name] = s
        s._name = name
        if hasattr(s, 'CONFIG'):
            cfg = CONFIG.copy()
            cfg.update(s.CONFIG)
            s.CONFIG = cfg
        else:
            s.CONFIG = CONFIG.copy()
        s.add_job = add_job
        Thread(target=run_scraper, args=(s,), name=s._name).start()
        print('scraper', scraper, 'added')
    return scrapers

scrapers = load_scrapers()


class RequestHandler(asyncore.dispatcher_with_send):

    def __init__(self, sock, queues):
        self.scrapers = queues
        super().__init__(sock)


    def handle_read(self):
        data = self.recv(8192)
        if not data:
            return
        try:
            data = loads(data)
        except:
            self.send('Invalid json\n')
            return
        if 'command' not in data:
            self.notify('Missing "command" attribute', type='error')
            return
        if data['command'] in ['l', 'ls', 'list']:
            queue_lens = {}
            for k,v in self.scrapers.items():
                queue_lens[k] = v._queue.qsize()
            self.notify('scraper queue list', queues=queue_lens)

        if data['command'] in ['c', 'call']:
            if data.get('scraper') not in self.scrapers:
                self.notify('Missing or invalid scraper ' + data.get('scraper'))
            payload = data.get('payload', {})
            add_job(data['scraper'], payload)

        print('{1} # Command `{0}` processed'.format(data['command'],datetime.isoformat(datetime.now())))

    def notify(self, msg, **kwargs):
        print(msg, repr(kwargs))
        message = {'message': msg}
        message.update(kwargs)
        self.send(dumps(message).encode('utf-8')+b'\n')

    def handle_close(self):
        self.close()
        print('{0} Client disconnected'.format(datetime.isoformat(datetime.now())))


class ScraperServer(asyncore.dispatcher):

    def __init__(self, host, port, scrapers):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(5)
        self.scrapers = scrapers

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            print('{1} Incoming connection from {0}'.format(repr(addr),datetime.isoformat(datetime.now())))
            handler = RequestHandler(sock, self.scrapers)


if __name__ == '__main__':
    server = ScraperServer('localhost', 7676, scrapers)
    asyncore.loop()
