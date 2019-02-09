import asyncore
import os
import socket
import traceback

from json import loads, dumps
from queue import Queue
from threading import Thread


CONFIG = {
    'threads': 8,
    'timeout': 60,
    'retries': 5,
    'error_handler': None,
}


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
        print("starting {0} job".format(scraper._name))
        scraper.scrape(job)
        print("{0} job finished".format(scraper._name))


def load_scrapers():
    scrapers = {}
    for scraper in os.listdir('scrapers/'):
        if scraper.startswith('_') or not scraper.endswith('.py'):
            continue
        try:
            name = scraper[:-3]
            s = __import__('scrapers.'+scraper[:-3])
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
        print('scraper', scraper, 'added')
    return scrapers


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
            scraper = self.scrapers.get(data['scraper'])
            if not scraper:
                return
            scraper._queue.put(payload)
            print('{0} added to {1} queue'.format(payload, scraper._name))

        print('# Command `{0}` processed'.format(data['command']))

    def notify(self, msg, **kwargs):
        print(msg, repr(kwargs))
        message = {'message': msg}
        message.update(kwargs)
        self.send(dumps(message).encode('utf-8')+b'\n')

    def handle_close(self):
        self.close()
        print('Client disconnected')


class ScraperServer(asyncore.dispatcher):

    def __init__(self, host, port):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(5)
        self.scrapers = load_scrapers()

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            print('Incoming connection from {0}'.format(repr(addr)))
            handler = RequestHandler(sock, self.scrapers)


if __name__ == '__main__':
	server = ScraperServer('localhost', 7676)
	asyncore.loop()
