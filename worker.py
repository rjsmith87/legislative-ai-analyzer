# worker.py - Background job processor
import logging
import os
from redis import Redis
from rq import Worker, Queue, Connection

logger = logging.getLogger(__name__)

redis_url = os.environ.get('REDIS_URL')

# REMOVE decode_responses=True for RQ compatibility
redis_conn = Redis.from_url(redis_url, ssl_cert_reqs=None)  # No decode_responses!

listen = ['default']

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker(list(map(Queue, listen)))
        logger.info('Starting RQ worker, listening on: %s', listen)
        worker.work()