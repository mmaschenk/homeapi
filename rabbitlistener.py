import threading
from time import sleep
import pika
import secrets
import json
from logging import getLogger
from cacher import updatecache

logger = getLogger(__name__)

class Handler(object):
    def __init__(self, id, logger):
        self.id = id
        self.logger = logger

    def handlemessage(self, ch, method, properties, body):
        self.logger.info(f"Dropping {body}")
        ch.basic_ack(delivery_tag = method.delivery_tag)

class DropHandler(Handler):
    pass

class RFC8428(object):
    def __init__(self, id, logger):
        self.id = id
        self.logger = logger

    def handlemessage(self, ch, method, properties, body):
        self.logger.info(f"RFC 8428 handler received {body}")
        
        # RFC8428 Sensor measurement:
        self.logger.debug(f" [{id}] Parsing")
        senml = json.loads(body)
        self.logger.debug(f" [{id}] Parsed")
        self.logger.debug(f"senml = {senml}")
        ch.basic_ack(delivery_tag = method.delivery_tag)
        bn = None
        for message in senml:
            self.logger.debug(f" [{id}] Handling message {message}")
            if 'bn' in message:
                bn = message['bn']
                del message['bn']

            if 'n' in message:
                entryid = f"{bn}{message['n']}"
                message['bn'] = bn
                self.logger.debug(f" [{id}] Storing at {entryid}: {message}")
                updatecache(id, entryid, message)
        self.logger.info(f" [{id}] Done")


class RabbitListener(object):
    def __init__(self, queue, settings):
        self._queue = queue
        self._settings = settings

    def start(self):
        logger.debug(f"Starting threads with {self._settings}")
        for queueinfo in self._settings:
            queueid = list(queueinfo.keys())[0]
            queuesettings = queueinfo[queueid]
            
            logger.info(f"Starting thread for {queueinfo}")
            listener_thread = threading.Thread(target=self.readevents, kwargs={'settings': queuesettings, 'id':queueid})
            listener_thread.start()
            logger.info("Thread started")

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

        queuename = f"{id}-{secrets.token_hex(10)}"
        result = channel.queue_declare(queue=queuename, exclusive=True )

        routing_key = settings['MQRABBIT_ROUTINGKEY'] if 'MQRABBIT_ROUTINGKEY' in settings else ""
        exchange = settings['MQRABBIT_EXCHANGE'] if 'MQRABBIT_EXCHANGE' in settings else ""

        logger.info(f"Binding queue to exchange: [{exchange}]")
        channel.queue_bind(exchange=exchange, queue=result.method.queue, routing_key=routing_key)

        if 'handler' in settings:
            handlerclass = globals()[settings['handler']]
            print(f"handlerclass = {handlerclass}")
            handler = handlerclass(id, logger)
        else:
            handler = self
        
        channel.basic_consume(queue=result.method.queue, on_message_callback=handler.handlemessage)
        logger.info("Waiting for messages")
        channel.start_consuming()

        while True:
            print(f"Sleeping {settings}")
            sleep(10)
