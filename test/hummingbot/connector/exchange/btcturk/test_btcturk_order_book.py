from unittest import TestCase

from hummingbot.connector.exchange.btcturk.btcturk_order_book import BtcturkOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessageType


class BtcturkOrderBookTests(TestCase):

    def test_snapshot_message_from_exchange(self):
        msg_431 = [431,
                   {'AO': [
                       {'A': '0.01394686', 'P': '591468'},
                       {'A': '0.54552192', 'P': '591469'},
                       {'A': '0.01182674', 'P': '592000'},
                       {'A': '0.17179163', 'P': '592005'},
                       {'A': '0.00845273', 'P': '592116'}],
                       'BO': [
                           {'A': '0.00289257', 'P': '590951'},
                           {'A': '0.2', 'P': '590948'},
                           {'A': '0.02674451', 'P': '590694'},
                           {'A': '0.02', 'P': '590569'},
                           {'A': '0.28886161', 'P': '590154'}],
                       'CS': 6905470,
                       'PS': 'BTCTRY',
                       'channel': 'orderbook',
                       'event': 'BTCTRY',
                       'type': 431}]
        snapshot_message = BtcturkOrderBook.snapshot_message_from_exchange(
            msg=msg_431,
            timestamp=1640000000.0,
            metadata={"trading_pair": "BTC-TRY"}
        )

        self.assertEqual("BTC-TRY", snapshot_message.trading_pair)
        self.assertEqual(OrderBookMessageType.SNAPSHOT, snapshot_message.type)
        self.assertEqual(1640000000.0, snapshot_message.timestamp)
        self.assertEqual(6905470, snapshot_message.update_id)
        self.assertEqual(-1, snapshot_message.trade_id)
        self.assertEqual(5, len(snapshot_message.bids))
        self.assertEqual(590951, snapshot_message.bids[0].price)
        self.assertEqual(0.00289257, snapshot_message.bids[0].amount)
        self.assertEqual(6905470, snapshot_message.bids[0].update_id)
        self.assertEqual(5, len(snapshot_message.asks))
        self.assertEqual(591468, snapshot_message.asks[0].price)
        self.assertEqual(0.01394686, snapshot_message.asks[0].amount)
        self.assertEqual(6905470, snapshot_message.asks[0].update_id)

    def test_diff_message_from_exchange(self):
        msg_432 = [
            432,
            {
                "CS": 7414519,
                "PS": "AVAXUSDT",
                "AO": [
                    {"CP": 3, "P": "67.64", "A": "7"},
                    {"CP": 1, "P": "67.68", "A": "487.588"},
                    {"CP": 3, "P": "67.7", "A": "0.5"},
                    {"CP": 0, "P": "67.74", "A": "1.982"},
                    {"CP": 1, "P": "71.74", "A": "0.4"},
                ],
                "BO": [
                    {"CP": 1, "P": "67.49", "A": "4512.417"},
                    {"CP": 3, "P": "67.47", "A": "29.447"},
                    {"CP": 3, "P": "67.44", "A": "6"},
                    {"CP": 1, "P": "67.43", "A": "73.833"},
                ],
                "channel": "obdiff",
                "event": "AVAXUSDT",
                "type": 432,
            },
        ]

        diff_msg = BtcturkOrderBook.diff_message_from_exchange(
            msg=msg_432,
            timestamp=1640000000.0,
            metadata={"trading_pair": "AVAX-USDT"}
        )

        self.assertEqual("AVAX-USDT", diff_msg.trading_pair)
        self.assertEqual(OrderBookMessageType.DIFF, diff_msg.type)
        self.assertEqual(1640000000.0, diff_msg.timestamp)
        self.assertEqual(7414519, diff_msg.update_id)
        # self.assertEqual(1, diff_msg.first_update_id)
        self.assertEqual(-1, diff_msg.trade_id)
        self.assertEqual(4, len(diff_msg.bids))
        self.assertEqual(67.49, diff_msg.bids[0].price)
        self.assertEqual(4512.417, diff_msg.bids[0].amount)
        self.assertEqual(7414519, diff_msg.bids[0].update_id)
        self.assertEqual(5, len(diff_msg.asks))
        self.assertEqual(67.64, diff_msg.asks[0].price)
        self.assertEqual(7.0, diff_msg.asks[0].amount)
        self.assertEqual(7414519, diff_msg.asks[0].update_id)

    def test_trade_message_from_exchange(self):
        # 421 for recent trades
        # 422 for trades. API keeps sending 421, send 422 in case of trade
        msg_422 = [
            422,
            {
                "D": "1647357507716",
                "I": "110063781755340883",
                "A": "0.0000503001",
                "P": "1011.3000000000",
                "PS": "AVAXTRY",
                "S": 1,
                "channel": "trade",
                "event": "AVAXTRY",
                "type": 422,
            },
        ]

        trade_message = BtcturkOrderBook.trade_message_from_exchange(
            msg=msg_422,
            metadata={"trading_pair": "AVAX-TRY"}
        )

        self.assertEqual("AVAX-TRY", trade_message.trading_pair)
        self.assertEqual(OrderBookMessageType.TRADE, trade_message.type)
        self.assertEqual(1647357507.716, trade_message.timestamp)
        self.assertEqual(-1, trade_message.update_id)
        self.assertEqual(110063781755340883, trade_message.trade_id)
