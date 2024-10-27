from logging import getLogger
from datetime import datetime
import valkey
import json

from abc import ABC, abstractmethod

logger = getLogger(__name__)

class Cacher(ABC):
    @abstractmethod
    def listentries(self, categoryid):
        pass

    @abstractmethod
    def listcategories():
        pass

    @abstractmethod
    def updatecache(self, categoryid, entryid, entry):
        pass

    @abstractmethod
    def getentry(categoryid, entryid):
        pass

class BaseCacher(Cacher):
    pass

class ValkeyCacher(BaseCacher):
    def __init__(self, settings, delimiter=':'):
        self.valkeyconnection = valkey.Valkey(
            host=settings['host'],
            port=settings['port'],
            db = 0,
            username=settings['user'],
            password=settings['token']
        )
        logger.info(f"Connected to valkey {settings['host']}:{settings['port']}")
        self.valkeyprefix = settings['prefix']
        self.delimiter = delimiter

    def updatecache(self, categoryid, entryid, entry):
        cachevalue = {
            'entry': entry,
            'meta': {
                'time': datetime.now().isoformat()
            }
        }
        valkeykey = f"{self.valkeyprefix}{self.delimiter}{categoryid}{self.delimiter}{entryid}"
        valkeyval = json.dumps(cachevalue)
        logger.debug(f"updating valkey {valkeykey} with {valkeyval}")
        self.valkeyconnection.set(valkeykey, valkeyval)
        logger.debug(f"updated valkey {valkeykey} with {valkeyval}")

    def getentry(self, categoryid, entryid):
        valkeykey = f"{self.valkeyprefix}{self.delimiter}{categoryid}{self.delimiter}{entryid}"
        try:
            value = json.loads(self.valkeyconnection.get(valkeykey))
            logger.debug(f"Value found: {value}")
            return value
        except:
            logger.debug("Value not found")
            return None
        
    def listcategories(self):
        try:
            categories = set()
            keys = self.valkeyconnection.keys(f"{self.valkeyprefix}{self.delimiter}*")
            for key in keys:
                key_str = key.decode('utf-8')
                logger.debug(f"Found key {key_str}")
                if self.delimiter in key_str:
                    parts = key_str.split(self.delimiter)
                    logger.debug(f"Parts: {parts}")
                    categories.add(parts[1])
            return list(categories)
        except:
            return []
        
    def listentries(self, categoryid):
        logger.debug(f"Listing entries for {categoryid}")
        try:
            entries = set()
            keys = self.valkeyconnection.keys(f"{self.valkeyprefix}{self.delimiter}{categoryid}{self.delimiter}*")
            for key in keys:
                key_str = key.decode('utf-8')
                logger.debug(f"Found key {key_str}")
                if self.delimiter in key_str:
                    parts = key_str.split(self.delimiter)
                    logger.debug(f"Parts: {parts}")
                    entries.add(parts[2])
            return list(entries)
        except:
            return []