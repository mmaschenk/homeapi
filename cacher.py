from queue import Queue, Empty
from threading import Thread
from logging import getLogger
from datetime import datetime


logger = getLogger(__name__)
eventqueue = Queue()

cache = {}
map = {}

_worker = None



def updatecache(categoryid, entryid, entry):
    logger.debug(f"queueing {categoryid} {entryid} {entry}")
    eventqueue.put( {
        'categoryid': categoryid,
        'entryid': entryid,
        'entry': entry,
        'meta': {
            'time': datetime.now().isoformat()
        }
    })

def getentry(categoryid, entryid):
    logger.debug(f"Getting entry for {categoryid} and {entryid}")
    try:
        value =  cache[categoryid][entryid]
        logger.debug("Value found")
        return value
    except:
        logger.debug("Value not found")
        return None

def listentries(categoryid):
    try:
        return list(cache[categoryid].keys())
    except:
        return []

def listcategories():
    try:
        return list(cache.keys())
    except:
        return []


def _updatecache(entry):
    if entry['categoryid'] not in cache:
        cache[entry['categoryid']] = {}
    
    categorycache = cache[entry['categoryid']]
    categorycache[entry['entryid']] = entry['entry']
    logger.debug(f"updated cache {entry['categoryid']} {entry['entryid']}")
    if 'meta' in entry and isinstance(categorycache[entry['entryid']], dict) :
        categorycache[entry['entryid']]['_meta'] = entry['meta']
        logger.info(f"added metadata: {categorycache[entry['entryid']]}")

def mainloop():
    logger.info("Starting loop")
    while True:
        event = eventqueue.get()
        logger.debug(f"dequeued {event}")
        _updatecache(event)

def startcachehandler(settings):
    if not _worker:
        worker = Thread(target=mainloop)
        worker.start()
    logger.debug(f"Using {settings}")

