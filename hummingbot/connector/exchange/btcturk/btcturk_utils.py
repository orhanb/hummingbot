import os
import socket
from typing import Any, Dict

import hummingbot.connector.exchange.btcturk.btcturk_constants as CONSTANTS

from hummingbot.client.config.config_methods import using_exchange
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.core.utils.tracking_nonce import get_tracking_nonce


CENTRALIZED = True
EXAMPLE_PAIR = "BTCUSDT"
DEFAULT_FEES = [0.05, 0.09]


def get_new_client_order_id(is_buy: bool, trading_pair: str) -> str:
    """
    Creates a client order id for a new order
    :param is_buy: True if the order is a buy order, False otherwise
    :param trading_pair: the trading pair the order will be operating with
    :return: an identifier for the new order to be used in the client
    """
    side = "B" if is_buy else "S"
    symbols = trading_pair.split("-")
    base = symbols[0].upper()
    quote = symbols[1].upper()
    base_str = f"{base[0]}{base[-1]}"
    quote_str = f"{quote[0]}{quote[-1]}"
    client_instance_id = hex(abs(hash(f"{socket.gethostname()}{os.getpid()}")))[2:6]
    return f"{CONSTANTS.HBOT_ORDER_ID_PREFIX}-{side}{base_str}{quote_str}{client_instance_id}{get_tracking_nonce()}"


def is_exchange_information_valid(exchange_info: Dict[str, Any]) -> bool:
    """
    Verifies if a trading pair is enabled to operate with based on its exchange information
    :param exchange_info: the exchange information for a trading pair
    :return: True if the trading pair is enabled, False otherwise
    """
    return exchange_info.get("status", None) == "TRADING" and "SPOT" in exchange_info.get("permissions", list())


def public_rest_url(path_url: str) -> str:
    """
    Creates a full URL for provided public REST endpoint
    :param path_url: a public REST endpoint
    :param domain: the Binance domain to connect to ("com" or "us"). The default value is "com"
    :return: the full URL to the endpoint
    """
    return CONSTANTS.REST_URL + CONSTANTS.PUBLIC_API_VERSION + path_url


def private_rest_url(path_url: str) -> str:
    """
    Creates a full URL for provided private REST endpoint
    :param path_url: a private REST endpoint
    :return: the full URL to the endpoint
    """
    return CONSTANTS.REST_URL + CONSTANTS.PRIVATE_API_VERSION + path_url


KEYS = {
    "btcturk_api_key": ConfigVar(
        key="btcturk_api_key",
        prompt="Enter your Btcturk API key >>> ",
        required_if=using_exchange("btcturk"),
        is_secure=True,
        is_connect_key=True,
    ),
    "btcturk_api_secret": ConfigVar(
        key="btcturk_api_secret",
        prompt="Enter your Btcturk API secret >>> ",
        required_if=using_exchange("btcturk"),
        is_secure=True,
        is_connect_key=True,
    ),
}

"""
OTHER_DOMAINS = ["binance_us"]
OTHER_DOMAINS_PARAMETER = {"binance_us": "us"}
OTHER_DOMAINS_EXAMPLE_PAIR = {"binance_us": "BTC-USDT"}
OTHER_DOMAINS_DEFAULT_FEES = {"binance_us": [0.1, 0.1]}
OTHER_DOMAINS_KEYS = {
    "binance_us": {
        "binance_us_api_key": ConfigVar(
            key="binance_us_api_key",
            prompt="Enter your Binance US API key >>> ",
            required_if=using_exchange("binance_us"),
            is_secure=True,
            is_connect_key=True,
        ),
        "binance_us_api_secret": ConfigVar(
            key="binance_us_api_secret",
            prompt="Enter your Binance US API secret >>> ",
            required_if=using_exchange("binance_us"),
            is_secure=True,
            is_connect_key=True,
        ),
    }
}
"""
