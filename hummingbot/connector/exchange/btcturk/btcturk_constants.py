from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

EXCHANGE_NAME = "btcturk"

# BTCTURK NoIdea
HBOT_ORDER_ID_PREFIX = "x-XEKWYICX"

# Base URL
REST_URL = "https://api.btcturk.com/api/"
WSS_URL = "wss://ws-feed-pro.btcturk.com/"

#
PUBLIC_API_VERSION = "v2"
PRIVATE_API_VERSION = "v1"

# Public API endpoints
TICKER_PRICE_CHANGE_PATH_URL = "/ticker"
EXCHANGE_INFO_PATH_URL = "/server/exchangeInfo"
# PING_PATH_URL = "/ping"
SNAPSHOT_PATH_URL = "/orderbook"
# SERVER_TIME_PATH_URL = "/time"
PUBLIC_ORDERBOOK_PATH = "/orderbook"
PUBLIC_TRADE_PATH = "/trades"
# Private API endpoints
ACCOUNTS_PATH_URL = "/users/balances"
MY_TRADES_PATH_URL = "/users/transactions/trade"
OPEN_ORDER_PATH_URL = "/openOrders"
ALL_ORDER_PATH_URL = "/allOrders"
ORDER_PATH = "/order"
# BINANCE_USER_STREAM_PATH_URL = "/userDataStream"
WS_HEARTBEAT_TIME_INTERVAL = 30

SIDE_BUY = "buy"
SIDE_SELL = "sell"

"""TIME_IN_FORCE_GTC = "GTC"  # Good till cancelled
TIME_IN_FORCE_IOC = "IOC"  # Immediate or cancel
TIME_IN_FORCE_FOK = "FOK"  # Fill or kill
"""
# Rate Limit Type
REQUEST_WEIGHT = "REQUEST_WEIGHT"
ORDERS = "ORDERS"
ORDERS_24HR = "ORDERS_24HR"

# Rate Limit time intervals
ONE_MINUTE = 60
ONE_SECOND = 1
ONE_DAY = 86400

MAX_REQUEST = 5000

# Order States
ORDER_STATE = {
    "PENDING": OrderState.PENDING_CREATE,
    "NEW": OrderState.OPEN,
    "FILLED": OrderState.FILLED,
    "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
    "PENDING_CANCEL": OrderState.OPEN,
    "CANCELED": OrderState.CANCELLED,
    "REJECTED": OrderState.FAILED,
    "EXPIRED": OrderState.FAILED,
}

# Websocket event types
# ToDo
DIFF_EVENT_TYPE = "obdiff"
ORDERFULL_EVENT_TYPE = "order"
TRADE_EVENT_TYPE = "trade"

RATE_LIMITS = [
    # Pools
    RateLimit(limit_id=REQUEST_WEIGHT, limit=1200, time_interval=ONE_MINUTE),
    RateLimit(limit_id=ORDERS, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=ORDERS_24HR, limit=100000, time_interval=ONE_DAY),
    # Weighted Limits
    RateLimit(
        limit_id=TICKER_PRICE_CHANGE_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 40)],
    ),
    RateLimit(
        limit_id=EXCHANGE_INFO_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[(LinkedLimitWeightPair(REQUEST_WEIGHT, 10))],
    ),
    RateLimit(
        limit_id=SNAPSHOT_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 50)]),
    RateLimit(
        limit_id=ACCOUNTS_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 10)],
    ),
    RateLimit(
        limit_id=MY_TRADES_PATH_URL,
        limit=MAX_REQUEST,
        time_interval=ONE_MINUTE,
        linked_limits=[LinkedLimitWeightPair(REQUEST_WEIGHT, 10)],
    ),
]
