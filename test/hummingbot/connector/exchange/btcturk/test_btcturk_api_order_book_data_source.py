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

from unittest.mock import AsyncMock, patch, MagicMock
from aioresponses.core import aioresponses
from bidict import bidict
import hummingbot.connector.exchange.btcturk.btcturk_constants as CONSTANTS
import hummingbot.connector.exchange.btcturk.btcturk_utils as utils
from hummingbot.connector.exchange.btcturk.btcturk_api_order_book_data_source import BtcturkAPIOrderBookDataSource
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage

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

    def _successfully_subscribed_event(self):
        resp = [991, {'type': 991, 'current': '5.1.0', 'min': '2.3.0'}]
        return resp

    def _trade_update_event(self):
        resp = [422, {
            'D': '1647588210843',
            'I': '101963781951665674',
            'A': '0.0002456604',
            'P': '40670.0000000000',
            'PS': 'BTCUSDT',
            'S': 0,
            'channel': 'trade',
            'event': 'BTCUSDT',
            'type': 422
        }]
        return resp

    def _order_full_event(self):
        resp = [431, {'CS': 7886177, 'PS': 'BTCUSDT', 'AO': [{'A': '0.400047254781', 'P': '40678'}, {'A': '0.06028432', 'P': '40679'}, {'A': '0.06382635', 'P': '40692'}, {'A': '0.00024591', 'P': '40699'}, {'A': '0.17172015', 'P': '40717'}, {'A': '1.46109843', 'P': '40739'}, {'A': '0.01203084', 'P': '40740'}, {'A': '0.0007', 'P': '40749'}, {'A': '0.260151437602', 'P': '40750'}, {'A': '0.00476', 'P': '40786'}, {'A': '0.00026982', 'P': '40792'}, {'A': '0.0014', 'P': '40800'}, {'A': '2.65083355', 'P': '40815'}, {'A': '0.115', 'P': '40816'}, {'A': '0.00053965', 'P': '40817'}, {'A': '0.00080947', 'P': '40842'}, {'A': '0.0010793', 'P': '40867'}, {'A': '0.01233245', 'P': '40880'}, {'A': '0.00134913', 'P': '40892'}, {'A': '0.00161895', 'P': '40917'}, {'A': '0.00188878', 'P': '40942'}, {'A': '0.04258159', 'P': '40956'}, {'A': '1.153', 'P': '40958'}, {'A': '0.04903245', 'P': '40978'}, {'A': '0.00274618', 'P': '40979'}, {'A': '4.66949711', 'P': '40988'}, {'A': '0.11623257', 'P': '40996'}, {'A': '0.00117994', 'P': '40999'}, {'A': '0.04826788', 'P': '41000'}, {'A': '0.00576897', 'P': '41007'}, {'A': '0.00122733', 'P': '41029'}, {'A': '0.03459791', 'P': '41050'}, {'A': '0.0362605', 'P': '41071'}, {'A': '0.00834044', 'P': '41074'}, {'A': '0.11283354', 'P': '41100'}, {'A': '0.151330923409', 'P': '41150'}, {'A': '0.16963752', 'P': '41166'}, {'A': '0.0006', 'P': '41175'}, {'A': '0.00440745', 'P': '41183'}, {'A': '0.71537722', 'P': '41185'}, {'A': '0.005', 'P': '41189'}, {'A': '0.00369', 'P': '41198'}, {'A': '0.12378695', 'P': '41200'}, {'A': '0.003', 'P': '41201'}, {'A': '0.12722814', 'P': '41211'}, {'A': '0.55671511', 'P': '41219'}, {'A': '0.93167158', 'P': '41223'}, {'A': '0.19386844', 'P': '41230'}, {'A': '0.26128918', 'P': '41250'}, {'A': '0.02', 'P': '41255'}, {'A': '0.08916549', 'P': '41271'}, {'A': '0.00122733', 'P': '41299'}, {'A': '0.05804144', 'P': '41300'}, {'A': '0.00234963', 'P': '41310'}, {'A': '0.19084221', 'P': '41311'}, {'A': '0.0003', 'P': '41313'}, {'A': '0.00024214', 'P': '41318'}, {'A': '0.00726155', 'P': '41330'}, {'A': '0.00048412', 'P': '41332'}, {'A': '0.00364035', 'P': '41350'}, {'A': '0.00031447', 'P': '41359'}, {'A': '0.0026163', 'P': '41389'}, {'A': '0.00436968', 'P': '41390'}, {'A': '0.00145016', 'P': '41395'}, {'A': '0.02', 'P': '41397'}, {'A': '1.03682645', 'P': '41400'}, {'A': '0.00120818', 'P': '41405'}, {'A': '0.0086109', 'P': '41440'}, {'A': '0.00135176', 'P': '41441'}, {'A': '0.01115703', 'P': '41442'}, {'A': '0.00616038', 'P': '41444'}, {'A': '0.02610865', 'P': '41450'}, {'A': '0.00258268', 'P': '41455'}, {'A': '0.00639868', 'P': '41475'}, {'A': '0.40026997', 'P': '41476'}, {'A': '0.00041932', 'P': '41479'}, {'A': '0.006', 'P': '41485'}, {'A': '0.02', 'P': '41486'}, {'A': '0.0226933', 'P': '41490'}, {'A': '0.00265754', 'P': '41498'}, {'A': '0.00041017', 'P': '41499'}, {'A': '0.46352374', 'P': '41500'}, {'A': '0.02408677', 'P': '41501'}, {'A': '0.1050111', 'P': '41505'}, {'A': '0.00169026', 'P': '41532'}, {'A': '0.00595823', 'P': '41535'}, {'A': '0.01052033', 'P': '41542'}, {'A': '0.01235256', 'P': '41545'}, {'A': '0.00120397', 'P': '41550'}, {'A': '0.00073149', 'P': '41553'}, {'A': '0.00120382', 'P': '41555'}, {'A': '0.01709082', 'P': '41560'}, {'A': '0.00026998', 'P': '41571'}, {'A': '0.40026997', 'P': '41576'}, {'A': '0.02', 'P': '41581'}, {'A': '0.0007217', 'P': '41589'}, {'A': '0.07775568', 'P': '41600'}, {'A': '0.00024538', 'P': '41621'}, {'A': '0.00261238', 'P': '41636'}, {'A': '0.00120122', 'P': '41645'}], 'BO': [{'A': '0.00061549', 'P': '40674'}, {'A': '0.02807767', 'P': '40619'}, {'A': '0.29739295', 'P': '40617'}, {'A': '3.6759159', 'P': '40616'}, {'A': '0.07382518', 'P': '40600'}, {'A': '0.12287379', 'P': '40594'}, {'A': '0.00344', 'P': '40589'}, {'A': '0.115', 'P': '40561'}, {'A': '0.01232125', 'P': '40560'}, {'A': '0.00510225', 'P': '40550'}, {'A': '0.010989', 'P': '40548'}, {'A': '0.00024666', 'P': '40500'}, {'A': '0.00024686', 'P': '40471'}, {'A': '0.01323775', 'P': '40470'}, {'A': '1.40503091', 'P': '40454'}, {'A': '0.01322591', 'P': '40450'}, {'A': '1.19', 'P': '40437'}, {'A': '0.00797753', 'P': '40430'}, {'A': '0.00024735', 'P': '40408'}, {'A': '0.0588143', 'P': '40379'}, {'A': '0.00495169', 'P': '40370'}, {'A': '0.03362391', 'P': '40350'}, {'A': '0.00128833', 'P': '40326'}, {'A': '0.602', 'P': '40310'}, {'A': '0.06175571', 'P': '40300'}, {'A': '0.00230934', 'P': '40299'}, {'A': '0.00975376', 'P': '40272'}, {'A': '0.01308261', 'P': '40250'}, {'A': '0.00123018', 'P': '40224'}, {'A': '0.88500712', 'P': '40223'}, {'A': '0.1', 'P': '40201'}, {'A': '0.10091052', 'P': '40200'}, {'A': '0.00403114', 'P': '40151'}, {'A': '0.00274007', 'P': '40138'}, {'A': '0.00747', 'P': '40127'}, {'A': '0.00124619', 'P': '40102'}, {'A': '0.00089728', 'P': '40101'}, {'A': '0.01161511', 'P': '40100'}, {'A': '0.005', 'P': '40096'}, {'A': '0.00048611', 'P': '40069'}, {'A': '0.01826528', 'P': '40056'}, {'A': '0.00858943', 'P': '40050'}, {'A': '0.00024961', 'P': '40042'}, {'A': '0.01784293', 'P': '40025'}, {'A': '0.00194785', 'P': '40008'}, {'A': '0.00039961', 'P': '40003'}, {'A': '0.00042476', 'P': '40002'}, {'A': '0.01624672', 'P': '40001'}, {'A': '0.48099714', 'P': '40000'}, {'A': '0.00436', 'P': '39988'}, {'A': '0.00711453', 'P': '39972'}, {'A': '0.02488237', 'P': '39969'}, {'A': '0.01254078', 'P': '39950'}, {'A': '0.08540566', 'P': '39900'}, {'A': '0.00097749', 'P': '39862'}, {'A': '0.0149814', 'P': '39860'}, {'A': '0.0006', 'P': '39858'}, {'A': '0.01677819', 'P': '39850'}, {'A': '0.05016941', 'P': '39845'}, {'A': '0.04836598', 'P': '39801'}, {'A': '0.18515066', 'P': '39800'}, {'A': '0.00507329', 'P': '39769'}, {'A': '0.00103038', 'P': '39755'}, {'A': '0.00716433', 'P': '39750'}, {'A': '0.02228987', 'P': '39700'}, {'A': '0.241', 'P': '39687'}, {'A': '0.25', 'P': '39670'}, {'A': '0.00252074', 'P': '39659'}, {'A': '0.00403318', 'P': '39651'}, {'A': '0.01445328', 'P': '39650'}, {'A': '0.10114203', 'P': '39600'}, {'A': '0.00329376', 'P': '39566'}, {'A': '0.01263271', 'P': '39560'}, {'A': '0.00126333', 'P': '39558'}, {'A': '0.0282686', 'P': '39555'}, {'A': '0.00126519', 'P': '39550'}, {'A': '0.00252877', 'P': '39525'}, {'A': '0.00526002', 'P': '39508'}, {'A': '0.21278456', 'P': '39501'}, {'A': '0.40012826', 'P': '39500'}, {'A': '0.125', 'P': '39495'}, {'A': '0.00060744', 'P': '39490'}, {'A': '0.02780751', 'P': '39466'}, {'A': '0.00381993', 'P': '39450'}, {'A': '0.00532844', 'P': '39440'}, {'A': '0.00913296', 'P': '39400'}, {'A': '0.00329736', 'P': '39390'}, {'A': '0.00025398', 'P': '39352'}, {'A': '0.00128635', 'P': '39350'}, {'A': '0.11556046', 'P': '39345'}, {'A': '0.00254086', 'P': '39337'}, {'A': '0.00803021', 'P': '39316'}, {'A': '0.00244059', 'P': '39315'}, {'A': '0.00178023', 'P': '39301'}, {'A': '0.33690759', 'P': '39300'}, {'A': '0.5', 'P': '39256'}, {'A': '0.02546237', 'P': '39254'}, {'A': '0.2756779', 'P': '39250'}, {'A': '0.05384989', 'P': '39226'}, {'A': '0.00050965', 'P': '39223'}], 'channel': 'obdiff', 'event': 'BTCUSDT', 'type': 431}]
        return resp

    def _order_diff_event(self):
        resp = [432, {
            'CS': 7880291,
            'PS': 'BTCUSDT',
            'AO': [
                {'CP': 1, 'P': '40780', 'A': '0.0128'},
                {'CP': 3, 'P': '40782', 'A': '0.0128'},
                {'CP': 3, 'P': '40783', 'A': '0.17155853'},
                {'CP': 1, 'P': '41656', 'A': '0.3'}],
            'BO': [
                {'CP': 3, 'P': '40697', 'A': '0.0094'},
                {'CP': 1, 'P': '39152', 'A': '0.02701188'}],
            'channel': 'obdiff',
            'event': 'BTCUSDT',
            'type': 432
        }]
        return resp

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

    @aioresponses()
    def test_fetch_trading_pairs_exception_raised(self, mock_api):
        BtcturkAPIOrderBookDataSource._trading_pair_symbol_map = {}

        url = utils.public_rest_url(path_url=CONSTANTS.EXCHANGE_INFO_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        mock_api.get(regex_url, exception=Exception)

        result: Dict[str] = self.async_run_with_timeout(
            self.data_source.fetch_trading_pairs()
        )

        self.assertEqual(0, len(result))

    def test_get_throttler_instance(self):
        self.assertIsInstance(BtcturkAPIOrderBookDataSource._get_throttler_instance(), AsyncThrottler)

    @aioresponses()
    def test_get_snapshot_successful(self, mock_api):
        url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        mock_api.get(regex_url, body=json.dumps(self._snapshot_response()))

        result: Dict[str, Any] = self.async_run_with_timeout(
            self.data_source.get_snapshot(self.trading_pair)
        )

        self.assertEqual(self._snapshot_response(), result)

    @aioresponses()
    def test_get_snapshot_catch_exception(self, mock_api):
        url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        mock_api.get(regex_url, status=400)
        with self.assertRaises(IOError):
            self.async_run_with_timeout(
                self.data_source.get_snapshot(self.trading_pair)
            )

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

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    def test_listen_for_subscriptions_subscribes_to_trades_and_order_diffs(self, ws_connect_mock):
        ws_connect_mock.return_value = self.mocking_assistant.create_websocket_mock()

        result_subscribe_trades = [422, {
            'D': '1647584323581',
            'I': '110063781755411856',
            'A': '0.8414000000', 'P': '1180.4000000000',
            'PS': 'AVAXTRY', 'S': 1,
            'channel': 'trade',
            'event': 'BTCUSDT',
            'type': 422
        }]
        result_subscribe_diffs = [432, {
            'CS': 7880291,
            'PS': 'BTCUSDT',
            'AO': [
                {'CP': 1, 'P': '40780', 'A': '0.0128'},
                {'CP': 3, 'P': '40782', 'A': '0.0128'},
                {'CP': 3, 'P': '40783', 'A': '0.17155853'},
                {'CP': 1, 'P': '41656', 'A': '0.3'}],
            'BO': [{'CP': 3, 'P': '40697', 'A': '0.0094'}, {'CP': 1, 'P': '39152', 'A': '0.02701188'}], 'channel': 'obdiff', 'event': 'BTCUSDT', 'type': 432}]

        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=json.dumps(result_subscribe_trades))
        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=json.dumps(result_subscribe_diffs))

        self.listening_task = self.ev_loop.create_task(self.data_source.listen_for_subscriptions())

        self.mocking_assistant.run_until_all_aiohttp_messages_delivered(ws_connect_mock.return_value)

        sent_subscription_messages = self.mocking_assistant.json_messages_sent_through_websocket(
            websocket_mock=ws_connect_mock.return_value)

        self.assertEqual(2, len(sent_subscription_messages))

        expected_trade_subscription = [151, {
            "type": 151,
            "event": self.ex_trading_pair,
            "join": True,
            "channel": "trade"
        },
        ]
        self.assertEqual(expected_trade_subscription, sent_subscription_messages[0])
        expected_diff_subscription = [151, {
            "type": 151,
            "event": self.ex_trading_pair,
            "join": True,
            "channel": "obdiff"
        },
        ]
        self.assertEqual(expected_diff_subscription, sent_subscription_messages[1])

        self.assertTrue(self._is_logged(
            "INFO",
            "Subscribed to public order book and trade channels..."
        ))

    @patch("hummingbot.core.data_type.order_book_tracker_data_source.OrderBookTrackerDataSource._sleep")
    @patch("aiohttp.ClientSession.ws_connect")
    def test_listen_for_subscriptions_raises_cancel_exception(self, mock_ws, _: AsyncMock):
        mock_ws.side_effect = asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            self.listening_task = self.ev_loop.create_task(self.data_source.listen_for_subscriptions())
            self.async_run_with_timeout(self.listening_task)

    @patch("hummingbot.core.data_type.order_book_tracker_data_source.OrderBookTrackerDataSource._sleep")
    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    def test_listen_for_subscriptions_logs_exception_details(self, mock_ws, sleep_mock):
        mock_ws.side_effect = Exception("TEST ERROR.")
        sleep_mock.side_effect = lambda _: self._create_exception_and_unlock_test_with_event(asyncio.CancelledError())

        self.listening_task = self.ev_loop.create_task(self.data_source.listen_for_subscriptions())

        self.async_run_with_timeout(self.resume_test_event.wait())

        self.assertTrue(
            self._is_logged(
                "ERROR",
                "Unexpected error occurred when listening to order book streams. Retrying in 5 seconds..."))

    def test_subscribe_channels_raises_cancel_exception(self):
        mock_ws = MagicMock()
        mock_ws.send.side_effect = asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            self.listening_task = self.ev_loop.create_task(self.data_source._subscribe_channels(mock_ws))
            self.async_run_with_timeout(self.listening_task)

    def test_subscribe_channels_raises_exception_and_logs_error(self):
        mock_ws = MagicMock()
        mock_ws.send.side_effect = Exception("Test Error")

        with self.assertRaises(Exception):
            self.listening_task = self.ev_loop.create_task(self.data_source._subscribe_channels(mock_ws))
            self.async_run_with_timeout(self.listening_task)

        self.assertTrue(
            self._is_logged("ERROR", "Unexpected error occurred subscribing to order book trading and delta streams...")
        )

    def test_listen_for_trades_cancelled_when_listening(self):
        mock_queue = MagicMock()
        mock_queue.get.side_effect = asyncio.CancelledError()
        self.data_source._message_queue[CONSTANTS.TRADE_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        with self.assertRaises(asyncio.CancelledError):
            self.listening_task = self.ev_loop.create_task(
                self.data_source.listen_for_trades(self.ev_loop, msg_queue)
            )
            self.async_run_with_timeout(self.listening_task)

    def test_listen_for_trades_logs_exception(self):
        incomplete_resp = {
            "m": 1,
            "i": 2,
        }

        mock_queue = AsyncMock()
        mock_queue.get.side_effect = [incomplete_resp, asyncio.CancelledError()]
        self.data_source._message_queue[CONSTANTS.TRADE_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        self.listening_task = self.ev_loop.create_task(
            self.data_source.listen_for_trades(self.ev_loop, msg_queue)
        )

        try:
            self.async_run_with_timeout(self.listening_task)
        except asyncio.CancelledError:
            pass

        self.assertTrue(
            self._is_logged("ERROR", "Unexpected error when processing public trade updates from exchange"))

    def test_listen_for_trades_successful(self):
        mock_queue = AsyncMock()
        mock_queue.get.side_effect = [self._trade_update_event(), asyncio.CancelledError()]
        self.data_source._message_queue[CONSTANTS.TRADE_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        try:
            self.listening_task = self.ev_loop.create_task(
                self.data_source.listen_for_trades(self.ev_loop, msg_queue)
            )
        except asyncio.CancelledError:
            pass

        msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get())

        self.assertTrue(101963781951665674, msg.trade_id)

    def test_listen_for_order_book_diffs_cancelled(self):
        mock_queue = AsyncMock()
        mock_queue.get.side_effect = asyncio.CancelledError()
        self.data_source._message_queue[CONSTANTS.DIFF_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        with self.assertRaises(asyncio.CancelledError):
            self.listening_task = self.ev_loop.create_task(
                self.data_source.listen_for_order_book_diffs(self.ev_loop, msg_queue)
            )
            self.async_run_with_timeout(self.listening_task)

    def test_listen_for_order_book_diffs_logs_exception(self):
        incomplete_resp = {
            "m": 1,
            "i": 2,
        }

        mock_queue = AsyncMock()
        mock_queue.get.side_effect = [incomplete_resp, asyncio.CancelledError()]
        self.data_source._message_queue[CONSTANTS.DIFF_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        self.listening_task = self.ev_loop.create_task(
            self.data_source.listen_for_order_book_diffs(self.ev_loop, msg_queue)
        )

        try:
            self.async_run_with_timeout(self.listening_task)
        except asyncio.CancelledError:
            pass

        self.assertTrue(
            self._is_logged("ERROR", "Unexpected error when processing public order book updates from exchange"))

    def test_listen_for_order_book_diffs_successful(self):
        mock_queue = AsyncMock()
        mock_queue.get.side_effect = [self._order_diff_event(), asyncio.CancelledError()]
        self.data_source._message_queue[CONSTANTS.DIFF_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        try:
            self.listening_task = self.ev_loop.create_task(
                self.data_source.listen_for_order_book_diffs(self.ev_loop, msg_queue)
            )
        except asyncio.CancelledError:
            pass

        msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get())

        self.assertTrue(7880291, msg.update_id)

    # @aioresponses()
    # def test_listen_for_order_book_snapshots_cancelled_when_fetching_snapshot(self, mock_api):
    #     # url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL)
    #     # regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

    #     # mock_api.get(regex_url, exception=asyncio.CancelledError)

    #     mock_queue = AsyncMock()
    #     mock_queue.get.side_effect = [self._order_full_event(), asyncio.CancelledError()]
    #     self.data_source._message_queue[CONSTANTS.ORDERFULL_EVENT_TYPE] = mock_queue

    #     msg_queue: asyncio.Queue = asyncio.Queue()

    #     with self.assertRaises(asyncio.CancelledError):
    #         self.async_run_with_timeout(
    #             self.data_source.listen_for_order_book_snapshots(self.ev_loop, msg_queue)
    #         )

    # @aioresponses()
    # @patch("hummingbot.connector.exchange.binance.binance_api_order_book_data_source"
    #        ".BinanceAPIOrderBookDataSource._sleep")
    # def test_listen_for_order_book_snapshots_log_exception(self, mock_api, sleep_mock):
    #     msg_queue: asyncio.Queue = asyncio.Queue()
    #     sleep_mock.side_effect = lambda _: self._create_exception_and_unlock_test_with_event(asyncio.CancelledError())

    #     url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL)
    #     regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

    #     mock_api.get(regex_url, exception=Exception)

    #     self.listening_task = self.ev_loop.create_task(
    #         self.data_source.listen_for_order_book_snapshots(self.ev_loop, msg_queue)
    #     )
    #     self.async_run_with_timeout(self.resume_test_event.wait())

    #     self.assertTrue(
    #         self._is_logged("ERROR", f"Unexpected error fetching order book snapshot for {self.trading_pair}."))

    @aioresponses()
    def test_listen_for_order_book_snapshots_successful(self, mock_api, ):
        mock_queue = AsyncMock()
        mock_queue.get.side_effect = [self._order_full_event(), asyncio.CancelledError()]
        self.data_source._message_queue[CONSTANTS.ORDERFULL_EVENT_TYPE] = mock_queue

        msg_queue: asyncio.Queue = asyncio.Queue()

        try:
            self.listening_task = self.ev_loop.create_task(
                self.data_source.listen_for_order_book_snapshots(self.ev_loop, msg_queue)
            )
        except asyncio.CancelledError:
            pass

        msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get())

        self.assertTrue(7886177, msg.update_id)
    #     msg_queue: asyncio.Queue = asyncio.Queue()
    #     url = utils.public_rest_url(path_url=CONSTANTS.SNAPSHOT_PATH_URL, domain=self.domain)
    #     regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
    #     mock_api.get(regex_url, body=json.dumps(self._snapshot_response()))

    #     self.listening_task = self.ev_loop.create_task(
    #         self.data_source.listen_for_order_book_snapshots(self.ev_loop, msg_queue)
    #     )

    #     msg: OrderBookMessage = self.async_run_with_timeout(msg_queue.get())

    #     self.assertTrue(12345, msg.update_id)
