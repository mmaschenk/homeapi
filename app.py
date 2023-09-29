#!/usr/bin/env python

# Configure logging before importing anything!
import yaml
import logging
import logging.config

with open("logging.yaml") as logyaml:
    logconfig = yaml.safe_load(logyaml)
logging.config.dictConfig(logconfig)

# Now do other stuff

import typing as t
from apiflask import APIFlask
from apiflask.fields import Integer, String
import secrets
import os
import importlib

from apispec import BasePlugin
from rabbitlistener import RabbitListener
from queue import Queue
from cacher import startcachehandler, getentry, listcategories, listentries

# logger = logging.getLogger("mymain")
# logger.debug("Mymain module debug")
# logger.info("Mymain module info")
# logger.warning("Mymain module warn")
# logger.error("Mymain module error")

# logger = logging.getLogger("notmymain")
# logger.debug("Notmymain module debug")
# logger.info("Notmymain module info")
# logger.warning("Notmymain module warn")
# logger.error("Notmymain module error")

#import sys
#sys.exit()


class QueuedAPIFlask(APIFlask):
    def run(self, host: str | None = None, port: int | None = None, debug: bool | None = None, load_dotenv: bool = True, **options) -> None:
        self.logger.debug("Running")
        self.a = "Dinges"
        return super().run(host, port, debug, load_dotenv, **options)

#app = QueuedAPIFlask(__name__)
app = APIFlask(__name__)
app.secret_key = secrets.token_bytes(32)

cache = { 'test': 'value'}

@app.route("/")
def hello_world():
    """
    This gives you the classical hello world thingy
    """
    print("Actie", app.queue)
    return "<p>Hello world</p>"

@app.route("/temperature/<sensor>")
def gettemperature(sensor):
    return f'Temperature for {sensor}'

@app.get("/cache/<key>")
def readcache(key):
    return [cache[key], ]

@app.get("/raw/_listcategories")
def _listcategories():
    return listcategories()

@app.get("/raw/_entries/<category>")
def _listentries(category):
    return listentries(category)

@app.get("/raw/_entry/<category>/<entry>")
def _getentry(category, entry):
    value = getentry(category, entry)
    return value


@app.post("/cache/<key>/<value>")
def writecache(key, value):
    cache[key]=value
    return "OK"

@app.post("/ledboard/")
@app.input( {"status": Integer()}, location='json')
def ledboard(json_data):
    """
    Sets the state of the LED-board
    """
    return "OK"

fieldmodule = importlib.import_module('apiflask.fields')

def dict2schemadict(map):
    for key in map.keys():
        app.logger.debug(f"Setting field type to {map[key]}")        
        class_ = getattr(fieldmodule, map[key])
        instance = class_()
        map[key] = instance

def generategettermappings(queuemanager):
    queuecollection = queuemanager.getsettings()
    app.logger.info(f"Found queues {queuecollection}")

    for queueid in queuecollection.keys():
        queuesettings = queuecollection[queueid]
        
        app.logger.info(f"Registering mappings for {queueid} -> {queuesettings}")

        mappings = queuesettings['mapping'] if 'mapping' in queuesettings else {}

        if 'map' in mappings:
            for map in mappings['map']:
                app.logger.debug(f"mapping: {map}")
                base = f"{mappings['base']}/{map['to']}"
                app.logger.debug(f"Mapping from {base} using description {map['description']}")

                def gengetvalue(queueid, entry):
                    q = queueid
                    e = entry
                    def getvalue():
                        f"""
                        {map['description']}
                        """
                        app.logger.debug(f"Returning mapped entry for {q} and {e}")
                        return getentry(q, e)
                    return getvalue
                
                implementation = gengetvalue(queueid, map['from'])
                implementation.__doc__ = map['description']
                app.add_url_rule( base, map['description'], implementation )
                

                if 'post' in map and map['post']:
                    
                    app.logger.debug(f"map is {map}")
                    handlefunction = queuemanager.getposthandler(queueid, map)
                    app.logger.debug(f"Retrieved handlerfunction {handlefunction} that should be {queuemanager.getposthandler(queueid, map)}")

                    def genpostvalue(queueid, entry, thisschema):
                        q = queueid
                        e = entry
                        h = handlefunction

                        #@app.post("/ledboardtest/")
                        @app.post(base)
                        @app.input( thisschema, location='json')
                        def postvalue(json_data=None):
                            app.logger.debug(f"Posting value [{json_data}] to {q} and {e} ")

                            h(**json_data)

                            return "OK"
                        return postvalue
                    
                    schemadict = map['handlermethod']['args']
                    dict2schemadict(schemadict)

                    app.logger.debug(f"schemadict is {schemadict}")
                    
                    #postimplementation = genpostvalue(queueid, map['from'], { 'aa': Integer(), 'bb': String()})
                    postimplementation = genpostvalue(queueid, map['from'], schemadict )
                    postimplementation.__doc__ = map['description']

                    from apiflask.schemas import Schema
                    from apiflask.scaffold import _annotate

                    schema = Schema.from_dict( {"json_data": Integer() })

                    #app.add_url_rule( base, f"Posting at {map['description']}", postimplementation, methods=['POST'] )
                    #_annotate(postimplementation, body=schema, body_example=None, body_examples=None)

def setup_app(app, settings):
    app.logger.info("Starting thread")
    queue = Queue()
    app.queue = queue
    rabbitlistener = RabbitListener(queue=queue, settings=settings['rabbitqueues'])
    app.listeners = {'rabbitqueues': rabbitlistener }
    app.cache = rabbitlistener
    app.cache.start()
    generategettermappings(rabbitlistener)
    startcachehandler(settings)
    return app

with open('cacher.yaml',"r") as settingsfile:
    settings = yaml.safe_load(settingsfile)
app.logger.debug(f"settings={settings}")
    
setup_app(app, settings)

def main():
    app.logger.debug("Here we go!")
    app.run(debug=True, use_reloader=False)

if __name__ == "__main__":
    main()
