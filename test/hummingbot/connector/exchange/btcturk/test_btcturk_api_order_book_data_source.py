import asyncio
import json
import re
import unittest

from typing import (
    Any,
    Awaitable,
    Dict,
    # List,
)

# from unittest.mock import AsyncMock, patch, MagicMock

from aioresponses.core import aioresponses
from bidict import bidict
import hummingbot.connector.exchange.btcturk.btcturk_constants as CONSTANTS
import hummingbot.connector.exchange.btcturk.btcturk_utils as utils
from hummingbot.connector.exchange.btcturk.btcturk_api_order_book_data_source import BtcturkAPIOrderBookDataSource
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.order_book import OrderBook
# from hummingbot.core.data_type.order_book_message import OrderBookMessage

from test.hummingbot.connector.network_mocking_assistant import NetworkMockingAssistant


class BtcturkAPIOrderBookDataSourceUnitTests(unittest.TestCase):
    # logging.Level required to receive logs from the data source logger
    level = 0

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ev_loop = asyncio.get_event_loop()
        cls.base_asset = "BTC"
        cls.quote_asset = "USDT"
        cls.trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.ex_trading_pair = cls.base_asset + cls.quote_asset
        cls.domain = "btcturk"

    def setUp(self) -> None:
        super().setUp()
        self.log_records = []
        self.listening_task = None
        self.mocking_assistant = NetworkMockingAssistant()

        self.throttler = AsyncThrottler(rate_limits=CONSTANTS.RATE_LIMITS)
        self.data_source = BtcturkAPIOrderBookDataSource(trading_pairs=[self.trading_pair],
                                                         throttler=self.throttler,
                                                         )
        self.data_source.logger().setLevel(1)
        self.data_source.logger().addHandler(self)

        self.resume_test_event = asyncio.Event()

        BtcturkAPIOrderBookDataSource._trading_pair_symbol_map = {
            "btcturk": bidict(
                {f"{self.base_asset}{self.quote_asset}": self.trading_pair})
        }

    def tearDown(self) -> None:
        self.listening_task and self.listening_task.cancel()
        BtcturkAPIOrderBookDataSource._trading_pair_symbol_map = {}
        super().tearDown()

    def handle(self, record):
        self.log_records.append(record)

    def _is_logged(self, log_level: str, message: str) -> bool:
        return any(record.levelname == log_level and record.getMessage() == message
                   for record in self.log_records)

    def _create_exception_and_unlock_test_with_event(self, exception):
        self.resume_test_event.set()
        raise exception

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: float = 1):
        ret = self.ev_loop.run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    # def _successfully_subscribed_event(self):
    #     resp = {
    #         "result": None,
    #         "id": 1
    #     }
    #     return resp

    # def _trade_update_event(self):
    #     resp = {
    #         "e": "trade",
    #         "E": 123456789,
    #         "s": self.ex_trading_pair,
    #         "t": 12345,
    #         "p": "0.001",
    #         "q": "100",
    #         "b": 88,
    #         "a": 50,
    #         "T": 123456785,
    #         "m": True,
    #         "M": True
    #     }
    #     return resp

    # def _order_diff_event(self):
    #     resp = {
    #         "e": "depthUpdate",
    #         "E": 123456789,
    #         "s": self.ex_trading_pair,
    #         "U": 157,
    #         "u": 160,
    #         "b": [["0.0024", "10"]],
    #         "a": [["0.0026", "100"]]
    #     }
    #     return resp

    def _snapshot_response(self):
        null = ""
        true = True
        resp = {
            "data": {
                "timestamp": 1647493701782.0,
                "bids": [
                    [
                        "41177",
                        "0.03715247"
                    ],
                    [
                        "41176",
                        "0.05707413"
                    ],
                    [
                        "41173",
                        "0.05308758"
                    ]
                ],
                "asks": [
                    [
                        "41231",
                        "0.01968886"
                    ],
                    [
                        "41264",
                        "0.27050246"
                    ],
                    [
                        "41265",
                        "0.11700000"
                    ]
                ]
            },
            "success": true,
            "message": null,
            "code": 0
        }
        return resp

    @aioresponses()
    def test_get_last_trade_prices(self, mock_api):
        url = utils.public_rest_url(path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL)
        url = f"{url}?pairSymbol={self.base_asset}{self.quote_asset}"
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        null = ''
        true = True
        mock_response = {
            "data": [
                        {
                            "pair": "BTCUSDT",
                            "pairNormalized": "BTC_USDT",
                            "timestamp": 1647430954506,
                            "last": 40585,
                            "high": 41689,
                            "low": 38512,
                            "bid": 40569,
                            "ask": 40587,
                            "open": 38699,
                            "volume": 170.06575796,
                            "average": 39986,
                            "daily": 1888,
                            "dailyPercent": 4.87,
                            "denominatorSymbol": "USDT",
                            "numeratorSymbol": "BTC",
                            "order": 2000
                        }
            ],
            "success": true,
            "message": null,
            "code": 0
        }

        mock_api.get(regex_url, body=json.dumps(mock_response))

        result: Dict[str, float] = self.async_run_with_timeout(
            self.data_source.get_last_traded_prices(trading_pairs=[self.trading_pair],
                                                    throttler=self.throttler)
        )

        self.assertEqual(1, len(result))
        self.assertEqual(40585, result[self.trading_pair])

    @aioresponses()
    def test_get_all_mid_prices(self, mock_api):
        url = utils.public_rest_url(path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL)
        null = ''
        true = True
        mock_response: Dict[str, Any] = {
            "data": [
                {
                    "pair": "BTCUSDT",
                    "pairNormalized": "BTC_USDT",
                    "timestamp": 1647432522115,
                    "last": 596675.00,
                    "high": 609386.00,
                    "low": 565730.00,
                    "bid": 99.00,
                    "ask": 101.00,
                    "open": 567200.00,
                    "volume": 291.81199031,
                    "average": 586557.36,
                    "daily": 30096.00,
                    "dailyPercent": 5.20,
                    "denominatorSymbol": "TRY",
                    "numeratorSymbol": "BTC",
                    "order": 1000
                },
                {
                    "pair": "ETHBTC",
                    "pairNormalized": "ETH_BTC",
                    "timestamp": 1647432480496,
                    "last": 0.06620,
                    "high": 0.06705,
                    "low": 0.06545,
                    "bid": 0.06613,
                    "ask": 0.06647,
                    "open": 0.06560,
                    "volume": 14.99304261,
                    "average": 0.06671,
                    "daily": 0.00087,
                    "dailyPercent": 0.91,
                    "denominatorSymbol": "BTC",
                    "numeratorSymbol": "ETH",
                    "order": 3024
                },
                {
                    "pair": "ETHTRY",
                    "pairNormalized": "ETH_TRY",
                    "timestamp": 1647432520065,
                    "last": 39524.00,
                    "high": 39950.00,
                    "low": 37102.00,
                    "bid": 39523.00,
                    "ask": 39564.00,
                    "open": 37206.00,
                    "volume": 1837.35093099,
                    "average": 38774.86,
                    "daily": 2358.00,
                    "dailyPercent": 6.23,
                    "denominatorSymbol": "TRY",
                    "numeratorSymbol": "ETH",
                    "order": 1034
                },
            ],
            "success": true,
            "message": null,
            "code": 0
        }

        mock_api.get(url, body=json.dumps(mock_response))

        result: Dict[str, float] = self.async_run_with_timeout(
            self.data_source.get_all_mid_prices()
        )

        self.assertEqual(1, len(result))
        self.assertEqual(100, result[self.trading_pair])

    @aioresponses()
    def test_fetch_trading_pairs(self, mock_api):
        BtcturkAPIOrderBookDataSource._trading_pair_symbol_map = {}
        url = utils.public_rest_url(path_url=CONSTANTS.EXCHANGE_INFO_PATH_URL)
        # TODO NEED TO IMPLEMENT NULL VARIABLE
        null = ""
        mock_response: Dict[str, Any] = {
            "data": {
                "timeZone": "UTC",
                "serverTime": 1647371468056,
                "symbols": [
                    {
                        "id": 1,
                        "name": "BTCTRY",
                        "nameNormalized": "BTC_TRY",
                        "status": "TRADING",
                        "numerator": "BTC",
                        "denominator": "TRY",
                        "numeratorScale": 8,
                        "denominatorScale": 2,
                        "hasFraction": False,
                        "filters": [
                            {
                                "filterType": "PRICE_FILTER",
                                "minPrice": "0.0000000000001",
                                "maxPrice": "10000000",
                                "tickSize": "10",
                                "minExchangeValue": "99.91",
                                "minAmount": null,
                                "maxAmount": null
                            }
                        ],
                        "orderMethods": [
                            "MARKET",
                            "LIMIT",
                            "STOP_MARKET",
                            "STOP_LIMIT"
                        ],
                        "displayFormat": "#,###",
                        "commissionFromNumerator": False,
                        "order": 1000,
                        "priceRounding": False,
                        "isNew": False,
                        "marketPriceWarningThresholdPercentage": 0.2500000000000000,
                        "maximumOrderAmount": null,
                        "maximumLimitOrderPrice": 5838790.0000000000000000,
                        "minimumLimitOrderPrice": 58387.9000000000000000
                    },
                    {
                        "id": 131,
                        "name": "AAVETRY",
                        "nameNormalized": "AAVE_TRY",
                        "status": "TRADING",
                        "numerator": "AAVE",
                        "denominator": "TRY",
                        "numeratorScale": 4,
                        "denominatorScale": 2,
                        "hasFraction": True,
                        "filters": [
                            {
                                "filterType": "PRICE_FILTER",
                                "minPrice": "0.0000000000001",
                                "maxPrice": "10000000",
                                "tickSize": "0.01",
                                "minExchangeValue": "99.91",
                                "minAmount": null,
                                "maxAmount": null
                            }
                        ],
                        "orderMethods": [
                            "MARKET",
                            "LIMIT",
                            "STOP_MARKET",
                            "STOP_LIMIT"
                        ],
                        "displayFormat": "#,##0.00",
                        "commissionFromNumerator": False,
                        "order": 1002,
                        "priceRounding": False,
                        "isNew": False,
                        "marketPriceWarningThresholdPercentage": 0.2500000000000000,
                        "maximumOrderAmount": null,
                        "maximumLimitOrderPrice": 18019.8000000000000000,
                        "minimumLimitOrderPrice": 180.1980000000000000
                    }
                ],
            },
        }

        mock_api.get(url, body=json.dumps(mock_response))

        result: Dict[str] = self.async_run_with_timeout(
            self.data_source.fetch_trading_pairs()
        )

        self.assertEqual(2, len(result))
        self.assertIn("BTC-TRY", result)
        self.assertIn("AAVE-TRY", result)
        self.assertNotIn("BNB-BTC", result)

    # @aioresponses()
    # def test_fetch_trading_pairs_exception_raised(self, mock_api):
    #     BinanceAPIOrderBookDataSource._trading_pair_symbol_map = {}

    #     url = utils.public_rest_url(path_url=CONSTANTS.EXCHANGE_INFO_PATH_URL, domain=self.domain)
    #     regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

    #     mock_api.get(regex_url, exception=Exception)

    #     result: Dict[str] = self.async_run_with_timeout(
    #         self.data_source.fetch_trading_pairs()
    #     )

    #     self.assertEqual(0, len(result))

    # def test_get_throttler_instance(self):
    #     self.assertIsInstance(BinanceAPIOrderBookDataSource._get_throttler_instance(), AsyncThrottler)

    # @aioresponses()
    # def test_get_snapshot_successful(self, mock_api):
    #     url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL)
    #     regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

    #     mock_api.get(regex_url, body=json.dumps(self._snapshot_response()))

    #     result: Dict[str, Any] = self.async_run_with_timeout(
    #         self.data_source.get_snapshot(self.trading_pair)
    #     )

    #     self.assertEqual(self._snapshot_response(), result)

    # @aioresponses()
    # def test_get_snapshot_catch_exception(self, mock_api):
    #     url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL, domain=self.domain)
    #     regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

    #     mock_api.get(regex_url, status=400)
    #     with self.assertRaises(IOError):
    #         self.async_run_with_timeout(
    #             self.data_source.get_snapshot(self.trading_pair)
    #         )

    @aioresponses()
    def test_get_new_order_book(self, mock_api):
        url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        null = None
        true = True
        mock_response: Dict[str, Any] = {
            "data": {
                "timestamp": 1647501159759.0,
                "bids": [
                    [
                        "40803",
                        "0.03178618"
                    ],
                    [
                        "40796",
                        "0.00840000"
                    ],
                    [
                        "40795",
                        "0.98051231"
                    ]
                ],
                "asks": [
                    [
                        "40832",
                        "0.00962551"
                    ],
                    [
                        "40833",
                        "0.00925985"
                    ],
                    [
                        "40837",
                        "0.06084964"
                    ]
                ]
            },
            "success": true,
            "message": null,
            "code": 0
        }
        mock_api.get(regex_url, body=json.dumps(mock_response))

        result: OrderBook = self.async_run_with_timeout(
            self.data_source.get_new_order_book(self.trading_pair)
        )

        self.assertEqual(1647501159759.0, result.snapshot_uid)

    # @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    # def test_listen_for_subscriptions_subscribes_to_trades_and_order_diffs(self, ws_connect_mock):
    #     ws_connect_mock.return_value = self.mocking_assistant.create_websocket_mock()

    #     result_subscribe_trades = {
    #         "result": None,
    #         "id": 1
    #     }
    #     result_subscribe_diffs = {
    #         "result": None,
    #         "id": 2
    #     }

    #     self.mocking_assistant.add_websocket_aiohttp_message(
    #         websocket_mock=ws_connect_mock.return_value,
    #         message=json.dumps(result_subscribe_trades))
    #     self.mocking_assistant.add_websocket_aiohttp_message(
    #         websocket_mock=ws_connect_mock.return_value,
    #         message=json.dumps(result_subscribe_diffs))

    #     self.listening_task = self.ev_loop.create_task(self.data_source.listen_for_subscriptions())

    #     self.mocking_assistant.run_until_all_aiohttp_messages_delivered(ws_connect_mock.return_value)

    #     sent_subscription_messages = self.mocking_assistant.json_messages_sent_through_websocket(
    #         websocket_mock=ws_connect_mock.return_value)

    #     self.assertEqual(2, len(sent_subscription_messages))
    #     expected_trade_subscription = {
    #         "method": "SUBSCRIBE",
    #         "params": [f"{self.ex_trading_pair.lower()}@trade"],
    #         "id": 1}
    #     self.assertEqual(expected_trade_subscription, sent_subscription_messages[0])
    #     expected_diff_subscription = {
    #         "method": "SUBSCRIBE",
    #         "params": [f"{self.ex_trading_pair.lower()}@depth@100ms"],
    #         "id": 2}
    #     self.assertEqual(expected_diff_subscription, sent_subscription_messages[1])

    #     self.assertTrue(self._is_logged(
    #         "INFO",
    #         "Subscribed to public order book and trade channels..."
    #     ))

    # @patch("hummingbot.core.data_type.order_book_tracker_data_source.OrderBookTrackerDataSource._sleep")
    # @patch("aiohttp.ClientSession.ws_connect")
    # def test_listen_for_subscriptions_raises_cancel_exception(self, mock_ws, _: AsyncMock):
    #     mock_ws.side_effect = asyncio.CancelledError

    #     with self.assertRaises(asyncio.CancelledError):
    #         self.listening_task = self.ev_loop.create_task(self.data_source.listen_for_subscriptions())
    #         self.async_run_with_timeout(self.listening_task)

    # @patch("hummingbot.core.data_type.order_book_tracker_data_source.OrderBookTrackerDataSource._sleep")
    # @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    # def test_listen_for_subscriptions_logs_exception_details(self, mock_ws, sleep_mock):
    #     mock_ws.side_effect = Exception("TEST ERROR.")
    #     sleep_mock.side_effect = lambda _: self._create_exception_and_unlock_test_with_event(asyncio.CancelledError())

    #     self.listening_task = self.ev_loop.create_task(self.data_source.listen_for_subscriptions())

    #     self.async_run_with_timeout(self.resume_test_event.wait())

    #     self.assertTrue(
    #         self._is_logged(
    #             "ERROR",
    #             "Unexpected error occurred when listening to order book streams. Retrying in 5 seconds..."))

    # def test_subscribe_channels_raises_cancel_exception(self):
    #     mock_ws = MagicMock()
    #     mock_ws.send.side_effect = asyncio.CancelledError

    #     with self.assertRaises(asyncio.CancelledError):
    #         self.listening_task = self.ev_loop.create_task(self.data_source._subscribe_channels(mock_ws))
    #         self.async_run_with_timeout(self.listening_task)

    # def test_subscribe_channels_raises_exception_and_logs_error(self):
    #     mock_ws = MagicMock()
    #     mock_ws.send.side_effect = Exception("Test Error")

    #     with self.assertRaises(Exception):
    #         self.listening_task = self.ev_loop.create_task(self.data_source._subscribe_channels(mock_ws))
    #         self.async_run_with_timeout(self.listening_task)

    #     self.assertTrue(
    #         self._is_logged("ERROR", "Unexpected error occurred subscribing to order book trading and delta streams...")
    #     )

    # def test_listen_for_trades_cancelled_when_listening(self):
    #     mock_queue = MagicMock()
    #     mock_queue.get.side_effect = asyncio.CancelledError()
    #     self.data_source._message_queue[CONSTANTS.TRADE_EVENT_TYPE] = mock_queue

    #     msg_queue: asyncio.Queue = asyncio.Queue()

    #     with self.assertRaises(asyncio.CancelledError):
    #         self.listening_task = self.ev_loop.create_task(
    #             self.data_source.listen_for_trades(self.ev_loop, msg_queue)
    #         )
    #         self.async_run_with_timeout(self.listening_task)

    # def test_listen_for_trades_logs_exception(self):
    #     incomplete_resp = {
    #         "m": 1,
    #         "i": 2,
    #     }

    #     mock_queue = AsyncMock()
    #     mock_queue.get.side_effect = [incomplete_resp, asyncio.CancelledError()]
    #     self.data_source._message_queue[CONSTANTS.TRADE_EVENT_TYPE] = mock_queue

    #     msg_queue: asyncio.Queue = asyncio.Queue()

    #     self.listening_task = self.ev_loop.create_task(
    #         self.data_source.listen_for_trades(self.ev_loop, msg_queue)
    #     )

    #     try:
    #         self.async_run_with_timeout(self.listening_task)
    #     except asyncio.CancelledError:
    #         pass

    #     self.assertTrue(
    #         self._is_logged("ERROR", "Unexpected error when processing public trade updates from exchange"))

    # def test_listen_for_trades_successful(self):
    #     mock_queue = AsyncMock()
    #     mock_queue.get.side_effect = [self._trade_update_event(), asyncio.CancelledError()]
    #     self.data_source._message_queue[CONSTANTS.TRADE_EVENT_TYPE] = mock_queue

    #     msg_queue: asyncio.Queue = asyncio.Queue()

    #     try:
    #         self.listening_task = self.ev_loop.create_task(
    #             self.data_source.listen_for_trades(self.ev_loop, msg_queue)
    #         )
    #     except asyncio.CancelledError:
    #         pass

    #     msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get())

    #     self.assertTrue(12345, msg.trade_id)

    # def test_listen_for_order_book_diffs_cancelled(self):
    #     mock_queue = AsyncMock()
    #     mock_queue.get.side_effect = asyncio.CancelledError()
    #     self.data_source._message_queue[CONSTANTS.DIFF_EVENT_TYPE] = mock_queue

    #     msg_queue: asyncio.Queue = asyncio.Queue()

    #     with self.assertRaises(asyncio.CancelledError):
    #         self.listening_task = self.ev_loop.create_task(
    #             self.data_source.listen_for_order_book_diffs(self.ev_loop, msg_queue)
    #         )
    #         self.async_run_with_timeout(self.listening_task)

    # def test_listen_for_order_book_diffs_logs_exception(self):
    #     incomplete_resp = {
    #         "m": 1,
    #         "i": 2,
    #     }

    #     mock_queue = AsyncMock()
    #     mock_queue.get.side_effect = [incomplete_resp, asyncio.CancelledError()]
    #     self.data_source._message_queue[CONSTANTS.DIFF_EVENT_TYPE] = mock_queue

    #     msg_queue: asyncio.Queue = asyncio.Queue()

    #     self.listening_task = self.ev_loop.create_task(
    #         self.data_source.listen_for_order_book_diffs(self.ev_loop, msg_queue)
    #     )

    #     try:
    #         self.async_run_with_timeout(self.listening_task)
    #     except asyncio.CancelledError:
    #         pass

    #     self.assertTrue(
    #         self._is_logged("ERROR", "Unexpected error when processing public order book updates from exchange"))

    # def test_listen_for_order_book_diffs_successful(self):
    #     mock_queue = AsyncMock()
    #     mock_queue.get.side_effect = [self._order_diff_event(), asyncio.CancelledError()]
    #     self.data_source._message_queue[CONSTANTS.DIFF_EVENT_TYPE] = mock_queue

    #     msg_queue: asyncio.Queue = asyncio.Queue()

    #     try:
    #         self.listening_task = self.ev_loop.create_task(
    #             self.data_source.listen_for_order_book_diffs(self.ev_loop, msg_queue)
    #         )
    #     except asyncio.CancelledError:
    #         pass

    #     msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get())

    #     self.assertTrue(12345, msg.update_id)

    # @aioresponses()
    # def test_listen_for_order_book_snapshots_cancelled_when_fetching_snapshot(self, mock_api):
    #     url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL, domain=self.domain)
    #     regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

    #     mock_api.get(regex_url, exception=asyncio.CancelledError)

    #     with self.assertRaises(asyncio.CancelledError):
    #         self.async_run_with_timeout(
    #             self.data_source.listen_for_order_book_snapshots(self.ev_loop, asyncio.Queue())
    #         )

    # @aioresponses()
    # @patch("hummingbot.connector.exchange.binance.binance_api_order_book_data_source"
    #        ".BinanceAPIOrderBookDataSource._sleep")
    # def test_listen_for_order_book_snapshots_log_exception(self, mock_api, sleep_mock):
    #     msg_queue: asyncio.Queue = asyncio.Queue()
    #     sleep_mock.side_effect = lambda _: self._create_exception_and_unlock_test_with_event(asyncio.CancelledError())

    #     url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL, domain=self.domain)
    #     regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

    #     mock_api.get(regex_url, exception=Exception)

    #     self.listening_task = self.ev_loop.create_task(
    #         self.data_source.listen_for_order_book_snapshots(self.ev_loop, msg_queue)
    #     )
    #     self.async_run_with_timeout(self.resume_test_event.wait())

    #     self.assertTrue(
    #         self._is_logged("ERROR", f"Unexpected error fetching order book snapshot for {self.trading_pair}."))

    # @aioresponses()
    # def test_listen_for_order_book_snapshots_successful(self, mock_api, ):
    #     msg_queue: asyncio.Queue = asyncio.Queue()
    #     url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL, domain=self.domain)
    #     regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

    #     mock_api.get(regex_url, body=json.dumps(self._snapshot_response()))

    #     self.listening_task = self.ev_loop.create_task(
    #         self.data_source.listen_for_order_book_snapshots(self.ev_loop, msg_queue)
    #     )

    #     msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get())

    #     self.assertTrue(12345, msg.update_id)
