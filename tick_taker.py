import argparse
import pandas as pd
import numpy as np
import alpaca_trade_api as tradeapi
from collections import defaultdict

class Quote():
    """
    We use Quote objects to represent the bid/ask spread. When we encounter a
    'level change', a move of exactly 1 penny, we may attempt to make one
    trade. Whether or not the trade is successfully filled, we do not submit
    another trade until we see another level change.

    Note: Only moves of 1 penny are considered eligible because larger moves
    could potentially indicate some newsworthy event for the stock, which this
    algorithm is not tuned to trade.
    """

    def __init__(self):
        self.symbol_dict = defaultdict(dict)
        self.default_dict = {
            'prev_bid': 0,
            'prev_ask': 0,
            'prev_spread': 0,
            'bid': 0,
            'ask': 0,
            'bid_size': 0,
            'ask_size': 0,
            'spread': 0,
            'traded': True,
            'level_ct': 1,
            'time': 0
        }

    def get_symbol_dict(self, symbol):
        # Checks symbol dictionary exists. If not, starts a default one.
        if symbol in self.symbol_dict.keys():
            return_dict = self.symbol_dict[symbol]
        else:
            return_dict = self.default_dict
            self.symbol_dict[symbol] = return_dict

        return return_dict

    def update_symbol_dict(self, symbol, update_dict):
        # Updates symbol dictionary
        self.symbol_dict[symbol].update(update_dict)

    def reset_dict(self, symbol_dict):
        # Called when a level change happens
        symbol_dict['traded'] = False
        symbol_dict['level_ct'] += 1
        return symbol_dict

    def update(self, data):
        # Get the symbol and retrieve its dictionary
        symbol = str(data.symbol)
        symbol_dict = self.get_symbol_dict(symbol)

        # Update bid and ask sizes and timestamp
        symbol_dict['bid_size'] = data.bidsize
        symbol_dict['ask_size'] = data.asksize

        # Check if there has been a level change
        if (
            symbol_dict['bid'] != data.bidprice
            and symbol_dict['ask'] != data.askprice
            and round(data.askprice - data.bidprice, 2) == .01
        ):
            # Update bids and asks and time of level change
            symbol_dict['prev_bid'] = symbol_dict['bid']
            symbol_dict['prev_ask'] = symbol_dict['ask']
            symbol_dict['bid'] = data.bidprice
            symbol_dict['ask'] = data.askprice
            symbol_dict['time'] = data.timestamp
            
            # Update spreads
            symbol_dict['prev_spread'] = round(symbol_dict['prev_ask'] - symbol_dict['prev_bid'], 3)
            symbol_dict['spread'] = round(symbol_dict['ask'] - symbol_dict['bid'], 3)
            print('Symbol: {} Level change: {} {} {} {} {} {}'.format(symbol, 
                symbol_dict['prev_bid'], symbol_dict['prev_ask'], symbol_dict['prev_spread'], 
                symbol_dict['bid'], symbol_dict['ask'], symbol_dict['spread']), flush=True
            )
            # If change is from one penny spread level to a different penny
            # spread level, then initialize for new level (reset stale vars)
            if symbol_dict['prev_spread'] == 0.01:
                symbol_dict = self.reset_dict(symbol_dict)

        # Update the status of the current dict
        self.update_symbol_dict(symbol, symbol_dict)


class Position():
    """
    The position object is used to track how many shares we have. We need to
    keep track of this so our position size doesn't inflate beyond the level
    we're willing to trade with. Because orders may sometimes be partially
    filled, we need to keep track of how many shares are "pending" a buy or
    sell as well as how many have been filled into our account.
    """

    def __init__(self):
        self.orders_filled_amount = {}
        self.pending_buy_shares = 0
        self.pending_sell_shares = 0
        self.total_shares = 0

    def update_pending_buy_shares(self, quantity):
        self.pending_buy_shares += quantity

    def update_pending_sell_shares(self, quantity):
        self.pending_sell_shares += quantity

    def update_filled_amount(self, order_id, new_amount, side):
        old_amount = self.orders_filled_amount[order_id]
        if new_amount > old_amount:
            if side == 'buy':
                self.update_pending_buy_shares(old_amount - new_amount)
                self.update_total_shares(new_amount - old_amount)
            else:
                self.update_pending_sell_shares(old_amount - new_amount)
                self.update_total_shares(old_amount - new_amount)
            self.orders_filled_amount[order_id] = new_amount

    def remove_pending_order(self, order_id, side):
        old_amount = self.orders_filled_amount[order_id]
        if side == 'buy':
            self.update_pending_buy_shares(old_amount - 100)
        else:
            self.update_pending_sell_shares(old_amount - 100)
        del self.orders_filled_amount[order_id]

    def update_total_shares(self, quantity):
        self.total_shares += quantity


def run(args):
    symbol_list = args.symbols
    max_shares = args.quantity
    opts = {}
    if args.key_id:
        opts['key_id'] = args.key_id
    if args.secret_key:
        opts['secret_key'] = args.secret_key
    if args.base_url:
        opts['base_url'] = args.base_url
    elif 'key_id' in opts and opts['key_id'].startswith('PK'):
        opts['base_url'] = 'https://paper-api.alpaca.markets'

    # Create an API object which can be used to submit orders, etc.
    api = tradeapi.REST(**opts)


    symbol_list = [symbol.upper() for symbol in symbol_list]
    
    quote = Quote()
    
    qc_list = ['Q.%s' % symbol for symbol in symbol_list]
    tc_list = ['T.%s' % symbol for symbol in symbol_list]

    position = Position()

    # Establish streaming connection
    conn = tradeapi.StreamConn(**opts)

    # Define our message handling
    async def on_quote(conn, channel, data):

        # Quote update received
        quote.update(data)

    #@conn.on(tc_str)
    async def on_trade(conn, channel, data):
        symbol = str(data.symbol)
        symbol_dict = quote.get_symbol_dict(symbol)
        if quote.symbol_dict[symbol]['traded']:
            return
        # We've received a trade and might be ready to follow it
        if (
            data.timestamp <= (
                quote.symbol_dict[symbol]['time'] + pd.Timedelta(np.timedelta64(50, 'ms'))
            )
        ):
            # The trade came too close to the quote update
            # and may have been for the previous level
            return
        if data.size >= 100:
            # The trade was large enough to follow, so we check to see if
            # we're ready to trade. We also check to see that the
            # bid vs ask quantities (order book imbalance) indicate
            # a movement in that direction. We also want to be sure that
            # we're not buying or selling more than we should.
            if (
                data.price == quote.symbol_dict[symbol]['ask']
                and quote.symbol_dict[symbol]['bid_size'] > (quote.symbol_dict[symbol]['ask_size'] * 1.8)
                and (
                    position.total_shares + position.pending_buy_shares
                ) < max_shares - 100
            ):
                # Everything looks right, so we submit our buy at the ask
                try:
                    o = api.submit_order(
                        symbol=symbol, qty='100', side='buy',
                        type='limit', time_in_force='day',
                        limit_price=str(quote.symbol_dict[symbol]['ask'])
                    )
                    # Approximate an IOC order by immediately cancelling
                    api.cancel_order(o.id)
                    position.update_pending_buy_shares(100)
                    position.orders_filled_amount[o.id] = 0
                    print('Buy {} at {}'.format(symbol, quote.symbol_dict[symbol]['ask']), flush=True)
                    quote.symbol_dict[symbol]['traded'] = True
                except Exception as e:
                    print(e)
            elif (
                data.price == quote.symbol_dict[symbol]['bid']
                and quote.symbol_dict[symbol]['ask_size'] > (quote.symbol_dict[symbol]['bid_size'] * 1.8)
                and (
                    position.total_shares - position.pending_sell_shares
                ) >= 100
            ):
                # Everything looks right, so we submit our sell at the bid
                try:
                    o = api.submit_order(
                        symbol=symbol, qty='100', side='sell',
                        type='limit', time_in_force='day',
                        limit_price=str(quote.symbol_dict[symbol]['bid'])
                    )
                    # Approximate an IOC order by immediately cancelling
                    api.cancel_order(o.id)
                    position.update_pending_sell_shares(100)
                    position.orders_filled_amount[o.id] = 0
                    print('Sell {} at {}'.format(symbol, quote.symbol_dict[symbol]['bid']), flush=True)
                    quote.symbol_dict[symbol]['traded'] = True
                except Exception as e:
                    print(e)

    @conn.on(r'trade_updates')
    async def on_trade_updates(conn, channel, data):
        # We got an update on one of the orders we submitted. We need to
        # update our position with the new information.
        event = data.event
        if event == 'fill':
            if data.order['side'] == 'buy':
                position.update_total_shares(
                    int(data.order['filled_qty'])
                )
            else:
                position.update_total_shares(
                    -1 * int(data.order['filled_qty'])
                )
            position.remove_pending_order(
                data.order['id'], data.order['side']
            )
        elif event == 'partial_fill':
            position.update_filled_amount(
                data.order['id'], int(data.order['filled_qty']),
                data.order['side']
            )
        elif event == 'canceled' or event == 'rejected':
            position.remove_pending_order(
                data.order['id'], data.order['side']
            )

    for symbol in symbol_list:
        conn.register(r'Q\.' + symbol, on_quote)
        conn.register(r'T\.' + symbol, on_trade)

    conn.run(
        ['trade_updates'] + qc_list + tc_list
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--symbols', nargs='*', type=str, default='SNAP',
        help='Symbols you want to trade.'
    )
    parser.add_argument(
        '--quantity', type=int, default=500,
        help='Maximum number of shares to hold at once. Minimum 100.'
    )
    parser.add_argument(
        '--key-id', type=str, default=None,
        help='API key ID',
    )
    parser.add_argument(
        '--secret-key', type=str, default=None,
        help='API secret key',
    )
    parser.add_argument(
        '--base-url', type=str, default=None,
        help='set https://paper-api.alpaca.markets if paper trading',
    )
    args = parser.parse_args()
    assert args.quantity >= 100
    run(args)
