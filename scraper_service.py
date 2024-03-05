import asyncio
import os
import socket
import sys
import traceback

from db import Client
from utils.process import publish
from importlib.machinery import SourceFileLoader
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
            while not scraper._queue.empty():
                scraper._queue.get()
            scraper._lock.release()
            log(1, "---------------END OF EXCEPTIONS---------------")

        if job_count == 0 and scraper._queue.empty() and pool.empty():
            if 'publish' not in scraper.CONFIG or scraper.CONFIG['publish']:
                if scraper.CONFIG.get('table'):
                    publish(scraper.CONFIG['table'])
                for t in scraper.CONFIG.get('tables', []):
                    publish(t)

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
            s = SourceFileLoader(import_path, 'scrapers/' + scraper).load_module()
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


async def notify(writer, msg, **kwargs):
    log(3, "%s %s" % (msg, repr(kwargs)))
    message = {'message': msg}
    message.update(kwargs)
    writer.write(dumps(message).encode('utf-8')+b'\n')
    await writer.drain()


async def handle_client(reader, writer):
    try:
        cli_addr = reader._transport._sock.getpeername()
        log(3, 'Incoming connection from {0}:{1}'.format(*cli_addr))
        try:
            data = (await reader.read(255)).decode('utf8')
            data = loads(data)
        except:
            await notify(writer, 'Invalid json')
            writer.close()
            return

        if 'command' not in data:
            await notify(writer, 'Missing "command" attribute', type='error')
            writer.close()
            return

        if data['command'] in ['l', 'ls', 'list']:
            await notify(writer, 'scraper queue list', **get_all_jobs())

        if data['command'] in ['c', 'call']:
            if data.get('scraper') not in scrapers:
                await notify(writer, 'Missing or invalid scraper ' + data.get('scraper'))
            else:
                payload = data.get('payload', {})
                add_job(data['scraper'], payload)

        if data['command'] in ['log', 'setlog', 'setlogfile']:
            set_logfile(data.get('path'))
            log(3, 'Changing logfile to {0}'.format(data.get('path')))

        log(3, '# Command `{0}` processed'.format(data['command']))
        writer.close()
        log(3, 'Client disconnected')
    except Exception as e:
        print(f"Exception caught: {e}")
        try:
            writer.close()
        except:
            pass


async def run_server(host, port):
    server = await asyncio.start_server(handle_client, host, port)
    log(3, 'listening on {0}:{1}'.format(host, port))
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    host = 'localhost'
    port = 7676
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    asyncio.run(run_server(host, port))
