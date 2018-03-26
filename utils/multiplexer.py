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

# (C) Stefan Marsiske <stefan.marsiske@gmail.com>

import threading

from multiprocessing import Pool, Process, JoinableQueue, log_to_stderr
from multiprocessing.sharedctypes import Value
from ctypes import c_bool
try:
    from Queue import Empty
except:
    from queue import Empty
from logging import DEBUG, WARN, INFO
import traceback
logger = log_to_stderr()
logger.setLevel(INFO)

class Multiplexer(object):
    def __init__(self, worker, threads=4):
        self.worker=worker
        self.q=JoinableQueue()
        self.done = Value(c_bool,False)
        self.consumer=Process(target=self.consume)
        self.pool = Pool(threads)

    def start(self):
        self.done.value=False
        self.consumer.start()

    def addjob(self, url, data=None):
        params=[url]
        if data: params.append(data)
        try:
           return self.pool.apply_async(self.worker,params,callback=self.q.put)
        except:
            logger.error('[!] failed to scrape '+ url)
            logger.error(traceback.format_exc())
            raise

    def finish(self):
        self.pool.close()
        logger.info('closed pool')
        self.pool.join()
        logger.info('joined pool')
        self.done.value=True
        logger.info('closed q')
        self.consumer.join()
        logger.info('joined consumer')
        #self.q.join()
        #logger.info('joined q')

    def consume(self):
        param=[0,0]
        while True:
            job=None
            try:
                job=self.q.get(True, timeout=1)
            except Empty:
                if self.done.value==True: break
            if job:
                yield job
                self.q.task_done()

        self.q.close()
        logger.info('added/updated: {0}/{1}'.format(*param))

    def run(self, params):
        def adder():
            self.start()
            for item in params:
                self.addjob(item)
            self.finish()
        threading.Thread(target=adder).start()
        return self.consume()
