import threading
from time import sleep
import pika
import secrets
import json
from logging import getLogger
from cacher import updatecache

import traceback

logger = getLogger(__name__)

class QueueManager(object):
    def __init__(self, queue, settings, **kwargs):
        logger.debug(f"Created queuemanager with {kwargs}")
        self._queue = queue
        self._settings = settings

    def getsettings(self):
        return self._settings

class Handler(object):
    def __init__(self, id, logger, exchange=None):
        self.id = id
        self.logger = logger
        self.exchange = exchange

    def handlemessage(self, ch, method, properties, body):
        self.logger.info(f"Dropping {body}")
        ch.basic_ack(delivery_tag = method.delivery_tag)

class LEDBoardHandler(Handler):
    def handlemessage(self, ch, method, properties, body):
        self.logger.info(f"LEDBoard handler received {body}")

        # LedBoard messages:
        self.logger.debug(f" [{self.id}] Parsing")
        payload = json.loads(body)
        self.logger.debug(f" [{self.id}] Parsed")

        if 'type' in payload and 'value' in payload:
            commandtype = payload['type']
            commandvalue = { 'value': payload['value'] }
            self.logger.debug(f"  [{self.id}] Command = {commandtype}. Value = {commandvalue}")

            updatecache(self.id, commandtype, commandvalue)

        self.logger.info(f" [{self.id}] Done")

    def handlepost(self, entry, value ):
        self.logger.info(f"Handling post value for {entry}: {value}")

    def setActiveState(self, active):
        self.logger.debug(f'Setting state to {active}')


class RFC8428(Handler):
    def handlemessage(self, ch, method, properties, body):
        self.logger.info(f"RFC 8428 handler received {body}")

        # RFC8428 Sensor measurement:
        self.logger.debug(f" [{self.id}] Parsing")
        senml = json.loads(body)
        self.logger.debug(f" [{self.id}] Parsed")
        self.logger.debug(f"senml = {senml}")
        ch.basic_ack(delivery_tag = method.delivery_tag)
        bn = None
        for message in senml:
            self.logger.debug(f" [{self.id}] Handling message {message}")
            if 'bn' in message:
                bn = message['bn']
                del message['bn']

            if 'n' in message:
                entryid = f"{bn}{message['n']}"
                message['bn'] = bn
                self.logger.debug(f" [{self.id}] Storing at {entryid}: {message}")
                updatecache(self.id, entryid, message)
        self.logger.info(f" [{self.id}] Done")

class RabbitListener(QueueManager):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.queues = {}

    def start(self):
        logger.debug(f"Starting threads with {self._settings}")
        for queueid in self._settings.keys():
            queuesettings = self._settings[queueid]

            logger.info(f"Starting thread for {queueid}")
            listener_thread = threading.Thread(target=self.readevents, kwargs={'settings': queuesettings, 'id':queueid})
            listener_thread.start()
            logger.info("Thread started")

    def getqueuehandler(self, queueid):
        logger.debug(f"Searching for handler for {queueid} in {self._settings}")
        if queueid in self.queues:
            logger.debug(f"Returning from cache: {self.queues[queueid]}")
            return self.queues[queueid]

        try:
            handlerclass = globals()[self._settings[queueid]['handler']]
            logger.debug(f"handlerclass = {handlerclass}")
            handler = handlerclass(queueid, logger)
            logger.debug(f"adding handler = {handler} to queue {self.queues}")
            self.queues[queueid] = handler
            logger.debug(f"returning {handler}")
            return handler
        except:
            logger.debug(f"No handler definition for {queueid}. Using self")
            self.queues[queueid] = self
            return self

    def getposthandler(self, queueid, mapping):
        logger.debug(f"Finding post handler for {queueid} and {mapping}")
        h = getattr(self.getqueuehandler(queueid), mapping['handlermethod']['name'])
        return h

    def handlemessage(self, ch, method, properties, body):
        logger.info(f"default handler received {body}")

        # RFC8428 Sensor measurement:
        logger.debug(f" [{id}] Parsing")
        senml = json.loads(body)
        logger.debug(f" [{id}] Parsed")
        logger.debug(f"senml = {senml}")
        ch.basic_ack(delivery_tag = method.delivery_tag)
        bn = None
        for message in senml:
            logger.debug(f" [{id}] Handling message {message}")
            if 'bn' in message:
                bn = message['bn']
                del message['bn']

            if 'n' in message:
                entryid = f"{bn}{message['n']}"
                message['bn'] = bn
                logger.debug(f" [{id}] Storing at {entryid}: {message}")
                updatecache(id, entryid, message)
        logger.info(f" [{id}] Done")


    def readevents(self, settings, id):
        logger = getLogger(f"rabbitlistener.{id}")

        mqrabbit_credentials = pika.PlainCredentials(settings['MQRABBIT_USER'], settings['MQRABBIT_PASSWORD'])
        mqparameters = pika.ConnectionParameters(
            host=settings['MQRABBIT_HOST'],
            virtual_host=settings['MQRABBIT_VHOST'],
            port=settings['MQRABBIT_PORT'],
            credentials=mqrabbit_credentials)
        mqconnection = pika.BlockingConnection(mqparameters)
        channel = mqconnection.channel()
        #channel.exchange_declare(exchange=settings['MQRABBIT_EXCHANGE'])

        queuename = f"rabbitlistener-{id}-{secrets.token_hex(10)}"
        result = channel.queue_declare(queue=queuename, exclusive=True, auto_delete=True )

        routing_key = settings['MQRABBIT_ROUTINGKEY'] if 'MQRABBIT_ROUTINGKEY' in settings else ""
        exchange = settings['MQRABBIT_EXCHANGE'] if 'MQRABBIT_EXCHANGE' in settings else ""

        logger.info(f"Binding queue to exchange: [{exchange}]")

        channel.queue_bind(exchange=exchange, queue=result.method.queue, routing_key=routing_key)

        if 'handler' in settings:
            handlerclass = globals()[settings['handler']]
            logger.debug(f"handlerclass = {handlerclass}")
            handler = handlerclass(id, logger)
        else:
            handler = self

        channel.basic_consume(queue=result.method.queue, on_message_callback=handler.handlemessage)
        logger.info("Waiting for messages")
        channel.start_consuming()

        while True:
            print(f"Sleeping {settings}")
            sleep(10)
