import asyncio
import time
import unittest

from collections import deque
from typing import (
    Deque,
    Optional,
    Union,
)

import hummingbot.connector.exchange.btcturk.btcturk_constants as CONSTANTS
from hummingbot.connector.exchange.btcturk.btcturk_order_book import BtcturkOrderBook
from hummingbot.connector.exchange.btcturk.btcturk_order_book_tracker import BtcturkOrderBookTracker
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType


class BinanceOrderBookTrackerUnitTests(unittest.TestCase):

    trading_pair: str

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.base_asset = "BTC"
        cls.quote_asset = "TRY"
        cls.trading_pair = f"{cls.base_asset}{cls.quote_asset}"
        cls.ev_loop = asyncio.get_event_loop()

    def setUp(self) -> None:
        super().setUp()
        self.throttler = AsyncThrottler(CONSTANTS.RATE_LIMITS)
        self.tracker: BtcturkOrderBookTracker = BtcturkOrderBookTracker(trading_pairs=[self.trading_pair],
                                                                        throttler=self.throttler)
        self.tracking_task: Optional[asyncio.Task] = None

        # Simulate start()
        self.tracker._order_books[self.trading_pair] = BtcturkOrderBook()
        self.tracker._tracking_message_queues[self.trading_pair] = asyncio.Queue()
        self.tracker._past_diffs_windows[self.trading_pair] = deque()
        self.tracker._order_books_initialized.set()

    def tearDown(self) -> None:
        self.tracking_task and self.tracking_task.cancel()
        super().tearDown()

    def _simulate_message_enqueue(self, message_queue: Union[asyncio.Queue, Deque], msg: OrderBookMessage):
        if isinstance(message_queue, asyncio.Queue):
            self.ev_loop.run_until_complete(message_queue.put(msg))
        elif isinstance(message_queue, Deque):
            message_queue.append(msg)
        else:
            raise NotImplementedError

    def test_exchange_name(self):
        self.assertEqual("btcturk", self.tracker.exchange_name)

        # us_tracker = BtcturkOrderBookTracker(trading_pairs=[self.trading_pair],
        #                                      domain="us",
        #                                      throttler=self.throttler)
        #
        # self.assertEqual("binance_us", us_tracker.exchange_name)

    def test_order_book_diff_router_trading_pair_not_found_append_to_saved_message_queue(self):
        expected_msg: OrderBookMessage = OrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content={
                "update_id": 1,
                "trading_pair": self.trading_pair,
            }
        )

        self._simulate_message_enqueue(self.tracker._order_book_diff_stream, expected_msg)

        self.tracker._tracking_message_queues.clear()

        task = self.ev_loop.create_task(
            self.tracker._order_book_diff_router()
        )
        self.ev_loop.run_until_complete(asyncio.sleep(0.5))

        self.assertEqual(0, len(self.tracker._tracking_message_queues))
        self.assertEqual(1, len(self.tracker._saved_message_queues[self.trading_pair]))
        task.cancel()

    def test_order_book_diff_router_snapshot_uid_above_diff_message_update_id(self):
        expected_msg: OrderBookMessage = OrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content={
                "update_id": 1,
                "trading_pair": self.trading_pair,
            }
        )

        self._simulate_message_enqueue(self.tracker._order_book_diff_stream, expected_msg)

        task = self.ev_loop.create_task(
            self.tracker._order_book_diff_router()
        )
        self.ev_loop.run_until_complete(asyncio.sleep(0.5))

        self.assertEqual(1, self.tracker._tracking_message_queues[self.trading_pair].qsize())
        task.cancel()

    def test_order_book_diff_router_snapshot_uid_below_diff_message_update_id(self):
        # Updates the snapshot_uid
        self.tracker.order_books[self.trading_pair].apply_snapshot([], [], 2)
        expected_msg: OrderBookMessage = OrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content={
                "update_id": 1,
                "trading_pair": self.trading_pair,
            }
        )

        self._simulate_message_enqueue(self.tracker._order_book_diff_stream, expected_msg)

        task = self.ev_loop.create_task(
            self.tracker._order_book_diff_router()
        )
        self.ev_loop.run_until_complete(asyncio.sleep(0.5))

        self.assertEqual(0, self.tracker._tracking_message_queues[self.trading_pair].qsize())
        task.cancel()

    def test_track_single_book_snapshot_message_no_past_diffs(self):
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
        snapshot_msg: OrderBookMessage = BtcturkOrderBook.snapshot_message_from_exchange(
            msg=msg_431,
            timestamp=time.time()
        )
        self._simulate_message_enqueue(self.tracker._tracking_message_queues[self.trading_pair], snapshot_msg)

        self.tracking_task = self.ev_loop.create_task(
            self.tracker._track_single_book(self.trading_pair)
        )
        self.ev_loop.run_until_complete(asyncio.sleep(0.5))
        # TODO - implement restore_from_snapshot_and_diffs
        self.assertEqual(6905470, self.tracker.order_books[self.trading_pair].snapshot_uid)

    def test_track_single_book_snapshot_message_with_past_diffs(self):
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
        snapshot_msg: OrderBookMessage = BtcturkOrderBook.snapshot_message_from_exchange(
            msg=msg_431,
            timestamp=time.time()
        )
        msg_432 = [
            432,
            {
                "CS": 6905469,
                "PS": "BTCTRY",
                "AO": [
                    {"CP": 3, "P": "591468", "A": "0.01"}
                ],
                "BO": [
                    {"CP": 1, "P": "590951", "A": "0.02"}
                ],
                "channel": "obdiff",
                "event": "BTCTRY",
                "type": 432,
            },
        ]
        past_diff_msg: OrderBookMessage = BtcturkOrderBook.diff_message_from_exchange(
            msg=msg_432,
            metadata={"trading_pair": self.trading_pair}
        )

        self.tracking_task = self.ev_loop.create_task(
            self.tracker._track_single_book(self.trading_pair)
        )

        self.ev_loop.run_until_complete(asyncio.sleep(0.5))

        self._simulate_message_enqueue(self.tracker._past_diffs_windows[self.trading_pair], past_diff_msg)
        self._simulate_message_enqueue(self.tracker._tracking_message_queues[self.trading_pair], snapshot_msg)

        self.ev_loop.run_until_complete(asyncio.sleep(0.5))

        self.assertEqual(6905470, self.tracker.order_books[self.trading_pair].snapshot_uid)
        self.assertEqual(6905469, self.tracker.order_books[self.trading_pair].last_diff_uid)

    # def test_track_single_book_diff_message(self):
    #     msg_432 = [
    #         432,
    #         {
    #             "CS": 7414519,
    #             "PS": "AVAXUSDT",
    #             "AO": [
    #                 {"CP": 3, "P": "67.64", "A": "7"},
    #                 {"CP": 1, "P": "67.68", "A": "487.588"},
    #                 {"CP": 3, "P": "67.7", "A": "0.5"},
    #                 {"CP": 0, "P": "67.74", "A": "1.982"},
    #                 {"CP": 1, "P": "71.74", "A": "0.4"},
    #             ],
    #             "BO": [
    #                 {"CP": 1, "P": "67.49", "A": "4512.417"},
    #                 {"CP": 3, "P": "67.47", "A": "29.447"},
    #                 {"CP": 3, "P": "67.44", "A": "6"},
    #                 {"CP": 1, "P": "67.43", "A": "73.833"},
    #             ],
    #             "channel": "obdiff",
    #             "event": "AVAXUSDT",
    #             "type": 432,
    #         },
    #     ]
    #     diff_msg: OrderBookMessage = BtcturkOrderBook.diff_message_from_exchange(
    #         msg=msg_432,
    #         metadata={"trading_pair": self.trading_pair}
    #     )
    #
    #     self._simulate_message_enqueue(self.tracker._tracking_message_queues[self.trading_pair], diff_msg)
    #
    #     self.tracking_task = self.ev_loop.create_task(
    #         self.tracker._track_single_book(self.trading_pair)
    #     )
    #     self.ev_loop.run_until_complete(asyncio.sleep(0.5))
    #
    #     self.assertEqual(0, self.tracker.order_books[self.trading_pair].snapshot_uid)
    #     self.assertEqual(2, self.tracker.order_books[self.trading_pair].last_diff_uid)
