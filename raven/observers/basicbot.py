import logging
from .observer import Observer
import json
import time
import os
import math
import os, time
import sys
import traceback
import config

class BasicBot(Observer):
    def __init__(self):
        super().__init__()

        self.orders = []

        self.max_maker_volume = config.MAKER_MAX_VOLUME
        self.min_maker_volume = config.MAKER_MIN_VOLUME
        self.max_taker_volume = config.TAKER_MAX_VOLUME
        self.min_taker_volume = config.TAKER_MIN_VOLUME

        logging.info('BasicBot Setup complete')

    def process_message(self,message):
        pass

    def msg_server(self):
        import zmq
        import time
        context = zmq.Context()
        socket = context.socket(zmq.PULL)
        socket.bind("tcp://*:%s"%config.ZMQ_PORT)

        logging.info("zmq msg_server start...")
        while not self.is_terminated:
            # Wait for next request from client
            message = socket.recv()
            logging.info("new pull message: %s", message)
            self.process_message(message)

            time.sleep (1) # Do some 'work'

    def notify_obj(self, pyObj):
        import zmq
        try:
            context = zmq.Context()
            socket = context.socket(zmq.PUSH)

            socket.connect ("tcp://%s:%s" % (config.ZMQ_HOST, config.ZMQ_PORT))
            time.sleep(1)

            logging.info( "notify message %s", json.dumps(pyObj))

            socket.send_string(json.dumps(pyObj))
        except Exception as e:
            logging.warn("notify_msg Exception")
            pass

    def notify_msg(self, type, price):
        message = {'type':type, 'price':price}
        self.notify_obj(message)

    def new_order(self, kexchange, type, maker_only=True, amount=None, price=None):
        if type == 'buy' or type == 'sell':
            if not price or not amount:
                if type == 'buy':
                    price = self.get_buy_price()
                    amount = math.floor((self.cny_balance/price)*10)/10
                else:
                    price = self.get_sell_price()
                    amount = math.floor(self.btc_balance * 10) / 10
            
            if maker_only:
                amount = min(self.max_maker_volume, amount)
                if amount < self.min_maker_volume:
                    logging.warn('Maker amount is too low %s %s' % (type, amount))
                    return None
            else:
                amount = min(self.max_taker_volume, amount)
                if amount < self.min_taker_volume:
                    logging.warn('Taker amount is too low %s %s' % (type, amount))
                    return None
            
            if maker_only:                
                if type == 'buy':
                    order_id = self.clients[kexchange].buy_maker(amount, price)
                else:
                    order_id = self.clients[kexchange].sell_maker(amount, price)
            else:
                if type == 'buy':
                    order_id = self.clients[kexchange].buy_limit(amount, price)
                else:
                    order_id = self.clients[kexchange].sell_limit(amount, price)

            if not order_id:
                logging.warn("%s @%s %f/%f BTC failed, %s" % (type, kexchange, amount, price, order_id))
                return None
            
            if order_id == -1:
                logging.warn("%s @%s %f/%f BTC failed, %s" % (type, kexchange, amount, price, order_id))
                return None

            order = {
                'market': kexchange, 
                'id': order_id,
                'price': price,
                'amount': amount,
                'deal_amount':0,
                'deal_index': 0, 
                'type': type,
                'maker_only': maker_only,
                'time': time.time()
            }
            self.orders.append(order)
            logging.info("submit order %s" % (order))

            return order

        return None
        

    def cancel_order(self, kexchange, type, order_id):
        result = self.clients[kexchange].cancel_order(order_id)
        if not result:
            logging.warn("cancel %s #%s failed" % (type, order_id))
            return False
        else:
            logging.info("cancel %s #%s ok" % (type, order_id))

            return True

    def remove_order(self, order_id):
        self.orders = [x for x in self.orders if not x['id'] == order_id]

    def get_orders(self, type):
        orders_snapshot = [x for x in self.orders if x['type'] == type]
        return orders_snapshot

    def selling_len(self):
        return len(self.get_orders('sell'))

    def buying_len(self):
        return len(self.get_orders('buy'))

    def is_selling(self):
        return len(self.get_orders('sell')) > 0

    def is_buying(self):
        return len(self.get_orders('buy')) > 0

    def get_sell_price(self):
        return self.sprice

    def get_buy_price(self):
        return self.bprice

    def get_spread(self):
        return self.sprice - self.bprice
        