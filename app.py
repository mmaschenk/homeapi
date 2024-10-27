#!/usr/bin/env python

# Configure logging before importing anything!
import yaml
import logging
import logging.config

import os
from dotenv import load_dotenv
load_dotenv()
loggingconfig = os.getenv("LOGCONFIG")

print(f"Starting configuring logging using: {loggingconfig}")
with open(loggingconfig) as logyaml:
    logconfig = yaml.safe_load(logyaml)
logging.config.dictConfig(logconfig)

# Now do other stuff

from dotenv import load_dotenv

load_dotenv()

import typing as t
from apiflask import APIFlask, HTTPTokenAuth, HTTPError
from apiflask.fields import Integer, String
from apiflask.schemas import Schema
import secrets
import importlib
from collections.abc import Mapping

from apispec import BasePlugin
from rabbitlistener import RabbitListener
from queue import Queue
from cacher import ValkeyCacher

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

mastertoken = os.getenv("MASTERTOKEN")
openapi = os.getenv("OPENAPI") == "1"

mycacher = None

print(f"Openapi = {openapi}")

class QueuedAPIFlask(APIFlask):
    def run(self, host: str | None = None, port: int | None = None, debug: bool | None = None, load_dotenv: bool = True, **options) -> None:
        self.logger.debug("Running")
        self.a = "Dinges"
        return super().run(host, port, debug, load_dotenv, **options)

app = APIFlask(__name__, title="My API", version="1.0", enable_openapi=openapi)
app.secret_key = secrets.token_bytes(32)

auth = HTTPTokenAuth(scheme='bearer')

userbase = {}
rolebase = {}

@auth.verify_token
def verify_token(token):
    app.logger.debug(f"Verifying token {token} from userbase {userbase}")
    return userbase[token] if token in userbase else None
    
@auth.get_user_roles
def get_user_roles(user):
    app.logger.debug(f"Getting roles for {user} from rolebase {rolebase}")
    return rolebase[user] if user in rolebase else None
    

cache = { 'test': 'value'}

@app.get("/cache/<key>")
@app.auth_required(auth)
def readcache(key):
    return [cache[key], ]

@app.get("/raw/_listcategories")
@app.auth_required(auth)
def _listcategories():
    return mycacher.listcategories()

@app.get("/raw/_entries/<category>")
@app.auth_required(auth)
def _listentries(category):
    return mycacher.listentries(category)

@app.get("/raw/_entry/<category>/<entry>")
@app.auth_required(auth)
def _getentry(category, entry):
    value = mycacher.getentry(category, entry)
    return value

@app.post("/cache/<key>/<value>")
@app.auth_required(auth)
def writecache(key, value):
    cache[key]=value
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

                    @app.auth_required(auth)
                    @auth.login_required(role='getter')
                    def getvalue():
                        f"""
                        {map['description']}
                        """
                        app.logger.debug(f"Returning mapped entry for {q} and {e}")
                        app.logger.debug(f"User is {auth.current_user}")
                        entry = mycacher.getentry(q, e)
                        if entry:
                            return entry
                        else:
                            raise HTTPError(404, 'No value cached')
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

                        @app.post(base)
                        @app.auth_required(auth)
                        @auth.login_required(role='setter')
                        @app.input( thisschema, location='json')
                        def postvalue(json_data=None):
                            app.logger.debug(f"Posting value [{json_data}] to {q} and {e} ")
                            h(**json_data)
                            return "OK"
                        return postvalue
                    
                    schemadict = map['handlermethod']['args']
                    dict2schemadict(schemadict)

                    app.logger.debug(f"schemadict is {schemadict}")
                    postimplementation = genpostvalue(queueid, map['from'], schemadict )
                    postimplementation.__doc__ = map['description']

                    schema = Schema.from_dict( {"json_data": Integer() })

def setupusers(users):
    app.logger.info(f"Doing users: {users}")
    global userbase 
    userbase = { userinfo['token']: userinfo['id'] for userinfo in users }

    global rolebase
    rolebase = { userinfo['id']: userinfo['roles'] for userinfo in users if 'roles' in userinfo }
    app.logger.info(f"Userbase is now: {userbase}")

def preheatcache(settings):
    print(f"Settings is {settings}")
    for queuetype in settings.keys():
        print(f"queuetype: {queuetype}")
        if isinstance(settings[queuetype], Mapping):
            for queueid in settings[queuetype].keys():
                print(f"queueid: {queueid}")
                if isinstance(settings[queuetype][queueid], Mapping) and 'preheat' in settings[queuetype][queueid]:
                    preheatcollection = settings[queuetype][queueid]['preheat'].keys()
                    print(f"Doing {preheatcollection}")
                    for pentry in preheatcollection:
                        print(f"entry = {pentry}")
                        mycacher.updatecache(categoryid=queueid, entryid=pentry, entry=settings[queuetype][queueid]['preheat'][pentry])


def setup_app(app, settings):
    global mycacher
    mycacher = ValkeyCacher(settings['valkey'])
    setupusers(settings['users'])
    app.logger.info("Starting queue thread")
    queue = Queue()
    app.queue = queue
    rabbitlistener = RabbitListener(mycacher, queue=queue, settings=settings['rabbitqueues'])
    app.listeners = {'rabbitqueues': rabbitlistener }
    app.cache = rabbitlistener
    app.cache.start()
    generategettermappings(rabbitlistener)
    preheatcache(settings)
    return app

cacheconfig = os.getenv("CACHECONFIG")

with open(cacheconfig,"r") as settingsfile:
    settings = yaml.safe_load(settingsfile)
app.logger.debug(f"settings={settings}")
    
setup_app(app, settings)

def main():
    app.logger.debug("Here we go!")
    app.run(debug=True, use_reloader=False)

if __name__ == "__main__":
    main()
