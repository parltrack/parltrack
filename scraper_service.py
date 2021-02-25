import asyncore
import os
import socket
import sys
import traceback

from db import Client
from imp import load_source
from json import loads, dumps
from queue import Queue
from threading import Thread, RLock
from datetime import datetime
from subprocess import Popen

from utils.log import log, set_logfile

CONFIG = {
    'threads': 8,
    'timeout': 60,
    'abort_on_error': False,
    'retries': 5,
    'error_handler': None,
}

scrapers = {}
db = Client()

ERROR_THRESHOLD = 10
ERROR_WINDOW = 50


def add_job(scraper_name, payload):
    scraper = scrapers.get(scraper_name)
    if not scraper:
        raise Exception("Unknown scraper")
    if scraper._queue.empty():
        scraper._lock.acquire()
        scraper._error_queue = [False for _ in range(ERROR_WINDOW)]
        scraper._lock.release()
    scraper._queue.put(payload)
    log(3, '{0} added to {1} queue'.format(payload, scraper._name))


def run_scraper(scraper):
    max_threads = scraper.CONFIG['threads']
    pool = Queue(maxsize=max_threads)
    for i in range(max_threads):
        Thread(target=consume, args=(pool, scraper), name=scraper._name + str(i)).start()

    while True:
        job = scraper._queue.get(True)
        pool.put(job, True)


def consume(pool, scraper):
    while True:
        job = pool.get(True)
        if 'onfinished' in job:
            onfinished_args = job['onfinished']
            #del(job['onfinished'])
        else:
            onfinished_args = {}
        scraper._lock.acquire()
        scraper._job_count += 1
        scraper._lock.release()
        log(3, "starting {0} job ({1})".format(scraper._name, job))
        try:
            ret = scraper.scrape(**job)
        except Exception as e:
            log(1, "failed to execute {0} job {1} ({2})".format(scraper._name, job, repr(e)))
            #traceback.print_exc(file=sys.stdout)
            log(1,''.join(traceback.format_exc()))
            sys.stdout.flush()
            if scraper.CONFIG['abort_on_error']:
                scraper._lock.acquire()
                scraper._error_queue.pop(0)
                scraper._error_queue.append(e)
                scraper._lock.release()

        else:
            if scraper.CONFIG['abort_on_error']:
                scraper._lock.acquire()
                scraper._error_queue.pop(0)
                scraper._error_queue.append(False)
                scraper._lock.release()
            log(3, "{0} job {1} finished".format(scraper._name, job))

        scraper._lock.acquire()
        scraper._job_count -= 1
        job_count = scraper._job_count
        clear_pool = False
        exceptions = []
        if scraper.CONFIG['abort_on_error']:
            exceptions = [x for x in scraper._error_queue if x is not False]
            if len(exceptions) > ERROR_THRESHOLD:
                clear_pool = True
                scraper._error_queue = [False for _ in range(ERROR_WINDOW)]
        scraper._lock.release()
        if clear_pool:
            log(1, "exception threshold exeeded for {} queue, aborting".format(scraper._name))
            log(1, "exceptions:".format(scraper._name))
            for e in exceptions:
                log(1, repr(e))
            while not pool.empty():
                pool.get()
            scraper._lock.acquire()
            while not scraper._queue.queue.empty():
                scraper._queue.queue.get()
            scraper._lock.release()
            log(1, "---------------END OF EXCEPTIONS---------------")

        if job_count == 0 and scraper._queue.empty() and pool.empty():
            if scraper.CONFIG.get('table') is not None:
                db.reindex(scraper.CONFIG['table'])
                db.commit(scraper.CONFIG['table'])
                Popen(['/bin/sh','./bin/publish-dump.sh', "%s.json" % scraper.CONFIG['table']])

            if hasattr(scraper, 'onfinished'):
                try:
                    scraper.onfinished(**onfinished_args)
                except:
                    log(1, "failed to execute {0} job's on_finished callback (params: {1})".format(scraper._name, onfinished_args))
                    traceback.print_exc(file=sys.stdout)
                    sys.stdout.flush()
                else:
                    log(3, "{0} job's on_finished callback finished (params: {1})".format(scraper._name, onfinished_args))


scrapers = {}


def get_all_jobs():
    queue_lens = {}
    job_counts = {}
    for k,v in scrapers.items():
        queue_lens[k] = v._queue.qsize()
        v._lock.acquire()
        job_counts[k] = v._job_count
        v._lock.release()
    return {'queues': queue_lens, 'job_counts': job_counts}


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
            log(1, "failed to load scraper" % scraper)
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
        s.get_all_jobs = get_all_jobs
        s._lock = RLock()
        s._job_count = 0
        if s.CONFIG['abort_on_error']:
            s._error_queue = [False for _ in range(ERROR_WINDOW)]
        Thread(target=run_scraper, args=(s,), name=s._name).start()
        log(3, 'scraper %s added' % scraper)
    return scrapers


scrapers = load_scrapers()


class RequestHandler(asyncore.dispatcher_with_send):

    def __init__(self, sock, queues):
        self.scrapers = queues
        super().__init__(sock)


    def handle_read(self):
        data = self.recv(8192)
        #print(data)
        if not data:
            return
        try:
            data = loads(data)
        except:
            self.notify('Invalid json\n')
            return
        if 'command' not in data:
            self.notify('Missing "command" attribute', type='error')
            return
        if data['command'] in ['l', 'ls', 'list']:
            self.notify('scraper queue list', **get_all_jobs())

        if data['command'] in ['c', 'call']:
            if data.get('scraper') not in self.scrapers:
                self.notify('Missing or invalid scraper ' + data.get('scraper'))
            payload = data.get('payload', {})
            add_job(data['scraper'], payload)

        if data['command'] in ['log', 'setlog', 'setlogfile']:
            set_logfile(data.get('path'))
            log(3, 'Changing logfile to {0}'.format(data.get('path')))

        log(3, '# Command `{0}` processed'.format(data['command']))

    def notify(self, msg, **kwargs):
        log(3, "%s %s" % (msg, repr(kwargs)))
        message = {'message': msg}
        message.update(kwargs)
        self.send(dumps(message).encode('utf-8')+b'\n')

    def handle_close(self):
        self.close()
        log(3, 'Client disconnected')


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
            log(3, 'Incoming connection from {0}'.format(repr(addr)))
            handler = RequestHandler(sock, self.scrapers)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        server = ScraperServer('localhost', int(sys.argv[1]), scrapers)
    else:
        server = ScraperServer('localhost', 7676, scrapers)
    asyncore.loop()
