import asyncio
import logging
import time
import math

from decimal import Decimal
from typing import (
    Any,
    AsyncIterable,
    Dict,
    List,
    Optional,
)

from async_timeout import timeout

import hummingbot.connector.exchange.btcturk.btcturk_constants as CONSTANTS
from hummingbot.connector.client_order_tracker import ClientOrderTracker
from hummingbot.connector.exchange_base import ExchangeBase
from hummingbot.connector.exchange.btcturk import btcturk_utils
from hummingbot.connector.exchange.btcturk.btcturk_api_order_book_data_source import BtcturkAPIOrderBookDataSource
from hummingbot.connector.exchange.btcturk.btcturk_auth import BtcturkAuth
from hummingbot.connector.exchange.btcturk.btcturk_order_book_tracker import BtcturkOrderBookTracker
from hummingbot.connector.exchange.btcturk.btcturk_user_stream_tracker import BtcturkUserStreamTracker
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import TradeFillOrderDetails
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, OrderState, TradeUpdate
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.trade_fee import (
    DeductedFromReturnsTradeFee,
    TokenAmount,
    TradeFeeBase,
)
from hummingbot.core.event.events import (
    MarketEvent,
    OrderFilledEvent,
    OrderType,
    TradeType,
)
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.async_utils import (
    safe_ensure_future,
    safe_gather,
)
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest
from hummingbot.core.web_assistant.rest_assistant import RESTAssistant
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.logger import HummingbotLogger
import json

s_logger = None
s_decimal_0 = Decimal(0)
s_decimal_NaN = Decimal("nan")


class BtcturkExchange(ExchangeBase):
    SHORT_POLL_INTERVAL = 5.0
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0
    LONG_POLL_INTERVAL = 120.0

    MAX_ORDER_UPDATE_RETRIEVAL_RETRIES_WITH_FAILURES = 3

    def __init__(
        self,
        btcturk_api_key: str,
        btcturk_api_secret: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
    ):
        self._btcturk_time_synchronizer = TimeSynchronizer()
        super().__init__()
        self._trading_required = trading_required
        self._auth = BtcturkAuth(
            api_key=btcturk_api_key, secret_key=btcturk_api_secret, time_provider=self._btcturk_time_synchronizer
        )
        self._api_factory = WebAssistantsFactory(auth=self._auth)
        self._rest_assistant = None
        self._throttler = AsyncThrottler(CONSTANTS.RATE_LIMITS)
        self._order_book_tracker = BtcturkOrderBookTracker(
            trading_pairs=trading_pairs, api_factory=self._api_factory, throttler=self._throttler
        )
        self._user_stream_tracker = BtcturkUserStreamTracker(auth=self._auth, throttler=self._throttler)
        self._ev_loop = asyncio.get_event_loop()
        self._poll_notifier = asyncio.Event()
        self._last_timestamp = 0
        self._order_not_found_records = {}  # Dict[client_order_id:str, count:int]
        self._trading_rules = {}  # Dict[trading_pair:str, TradingRule]
        self._trade_fees = {}  # Dict[trading_pair:str, (maker_fee_percent:Decimal, taken_fee_percent:Decimal)]
        self._last_update_trade_fees_timestamp = 0
        self._status_polling_task = None
        self._user_stream_tracker_task = None
        self._user_stream_event_listener_task = None
        self._trading_rules_polling_task = None
        self._last_poll_timestamp = 0
        self._last_trades_poll_btcturk_timestamp = 0
        self._order_tracker: ClientOrderTracker = ClientOrderTracker(connector=self)

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global s_logger
        if s_logger is None:
            s_logger = logging.getLogger(__name__)
        return s_logger

    @property
    def name(self) -> str:
        return "btcturk"

    @property
    def order_books(self) -> Dict[str, OrderBook]:
        return self._order_book_tracker.order_books

    @property
    def trading_rules(self) -> Dict[str, TradingRule]:
        return self._trading_rules

    @property
    def in_flight_orders(self) -> Dict[str, InFlightOrder]:
        return self._order_tracker.active_orders

    @property
    def limit_orders(self) -> List[LimitOrder]:
        return [in_flight_order.to_limit_order() for in_flight_order in self.in_flight_orders.values()]

    @property
    def tracking_states(self) -> Dict[str, any]:
        """
        Returns a dictionary associating current active orders client id to their JSON representation
        """
        return {key: value.to_json() for key, value in self.in_flight_orders.items()}

    @property
    def order_book_tracker(self) -> BtcturkOrderBookTracker:
        return self._order_book_tracker

    @property
    def user_stream_tracker(self) -> BtcturkUserStreamTracker:
        return self._user_stream_tracker

    @property
    def status_dict(self) -> Dict[str, bool]:
        """
        Returns a dictionary with the values of all the conditions that determine if the connector is ready to operate.
        The key of each entry is the condition name, and the value is True if condition is ready, False otherwise.
        """

        return {
            "symbols_mapping_initialized": BtcturkAPIOrderBookDataSource.trading_pair_symbol_map_ready(
            ),
            "order_books_initialized": self._order_book_tracker.ready,
            "account_balance": len(self._account_balances) > 0 if self._trading_required else True,
            "trading_rule_initialized": len(self._trading_rules) > 0,
        }

    @property
    def ready(self) -> bool:
        """
        Returns True if the connector is ready to operate (all connections established with the exchange). If it is
        not ready it returns False.
        """
        return all(self.status_dict.values())

    @staticmethod
    def btcturk_order_type(order_type: OrderType) -> str:
        return order_type.name.upper()

    @staticmethod
    def to_hb_order_type(btcturk_type: str) -> OrderType:
        return OrderType[btcturk_type]

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.MARKET]

    async def start_network(self):
        """
        Start all required tasks to update the status of the connector. Those tasks include:
        - The order book tracker
        - The polling loop to update the trading rules
        - The polling loop to update order status and balance status using REST API (backup for main update process)
        - The background task to process the events received through the user stream tracker (websocket connection)
        """

        self._order_book_tracker.start()
        self._trading_rules_polling_task = safe_ensure_future(self._trading_rules_polling_loop())

        if self._trading_required:
            # TODO later status polling every 30 mins
            self._status_polling_task = safe_ensure_future(self._status_polling_loop())
            self._user_stream_tracker_task = safe_ensure_future(self._user_stream_tracker.start())
            self._user_stream_event_listener_task = safe_ensure_future(self._user_stream_event_listener())

    async def stop_network(self):
        """
        This function is executed when the connector is stopped. It perform a general cleanup and stops all background
        tasks that require the connection with the exchange to work.
        """
        # Reset timestamps and _poll_notifier for status_polling_loop
        self._last_poll_timestamp = 0
        self._last_timestamp = 0
        self._poll_notifier = asyncio.Event()

        self._order_book_tracker.stop()
        if self._status_polling_task is not None:
            self._status_polling_task.cancel()
        if self._user_stream_tracker_task is not None:
            self._user_stream_tracker_task.cancel()
        if self._user_stream_event_listener_task is not None:
            self._user_stream_event_listener_task.cancel()
        if self._trading_rules_polling_task is not None:
            self._trading_rules_polling_task.cancel()
        self._status_polling_task = self._user_stream_tracker_task = self._user_stream_event_listener_task = None

    async def check_network(self) -> NetworkStatus:
        """
        Checks connectivity with the exchange using the API
        """
        # Use exchange data instead fo PingPathUrl
        try:
            await self._api_request(
                method=RESTMethod.GET,
                path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return NetworkStatus.NOT_CONNECTED
        return NetworkStatus.CONNECTED

    def restore_tracking_states(self, saved_states: Dict[str, any]):
        """
        Restore in-flight orders from saved tracking states, this is st the connector can pick up on where it left off
        when it disconnects.
        :param saved_states: The saved tracking_states.
        """
        self._order_tracker.restore_tracking_states(tracking_states=saved_states)

    def tick(self, timestamp: float):
        """
        Includes the logic that has to be processed every time a new tick happens in the bot. Particularly it enables
        the execution of the status update polling loop using an event.
        """
        now = time.time()
        poll_interval = (
            self.SHORT_POLL_INTERVAL
            if now - self.user_stream_tracker.last_recv_time > 60.0
            else self.LONG_POLL_INTERVAL
        )
        last_tick = int(self._last_timestamp / poll_interval)
        current_tick = int(timestamp / poll_interval)

        if current_tick > last_tick:
            if not self._poll_notifier.is_set():
                self._poll_notifier.set()
        self._last_timestamp = timestamp

    def get_order_book(self, trading_pair: str) -> OrderBook:
        """
        Returns the current order book for a particular market
        :param trading_pair: the pair of tokens for which the order book should be retrieved
        """
        if trading_pair not in self._order_book_tracker.order_books:
            raise ValueError(f"No order book exists for '{trading_pair}'.")
        return self._order_book_tracker.order_books[trading_pair]

    def start_tracking_order(
        self,
        order_id: str,
        exchange_order_id: Optional[str],
        trading_pair: str,
        trade_type: TradeType,
        price: Decimal,
        amount: Decimal,
        order_type: OrderType,
    ):
        """
        Starts tracking an order by adding it to the order tracker.
        :param order_id: the order identifier
        :param exchange_order_id: the identifier for the order in the exchange
        :param trading_pair: the token pair for the operation
        :param trade_type: the type of order (buy or sell)
        :param price: the price for the order
        :param amount: the amount for the order
        :order type: type of execution for the order (MARKET, LIMIT, LIMIT_MAKER)
        """
        self._order_tracker.start_tracking_order(
            InFlightOrder(
                client_order_id=order_id,
                exchange_order_id=exchange_order_id,
                trading_pair=trading_pair,
                order_type=order_type,
                trade_type=trade_type,
                amount=amount,
                price=price,
            )
        )

    def stop_tracking_order(self, order_id: str):
        """
        Stops tracking an order
        :param order_id: The id of the order that will not be tracked any more
        """
        self._order_tracker.stop_tracking_order(client_order_id=order_id)

    def get_order_price_quantum(self, trading_pair: str, price: Decimal) -> Decimal:
        """
        Used by quantize_order_price() in _create_order()
        Returns a price step, a minimum price increment for a given trading pair.
        :param trading_pair: the trading pair to check for market conditions
        :param price: the starting point price
        """
        trading_rule = self._trading_rules[trading_pair]
        return trading_rule.min_price_increment

    def get_order_size_quantum(self, trading_pair: str, order_size: Decimal) -> Decimal:
        """
        Used by quantize_order_price() in _create_order()
        Returns an order amount step, a minimum amount increment for a given trading pair.
        :param trading_pair: the trading pair to check for market conditions
        :param order_size: the starting point order price
        """
        trading_rule = self._trading_rules[trading_pair]
        return trading_rule.min_base_amount_increment

    def quantize_order_amount(self, trading_pair: str, amount: Decimal, price: Decimal = s_decimal_0) -> Decimal:
        """
        Applies the trading rules to calculate the correct order amount for the market
        :param trading_pair: the token pair for which the order will be created
        :param amount: the intended amount for the order
        :param price: the intended price for the order
        :return: the quantized order amount after applying the trading rules
        """
        trading_rule = self._trading_rules[trading_pair]
        quantized_amount: Decimal = super().quantize_order_amount(trading_pair, amount)
        # self.logger().error(quantized_amount)
        # self.logger().error(f"trading_rule: {trading_rule}")
        # Check against min_order_size and min_notional_size. If not passing either check, return 0.
        if quantized_amount < trading_rule.min_order_size:
            return s_decimal_0

        if price == s_decimal_0:
            current_price: Decimal = self.get_price(trading_pair, False)
            notional_size = current_price * quantized_amount
        else:
            notional_size = price * quantized_amount

        # Add 1% as a safety factor in case the prices changed while making the order.
        if notional_size < trading_rule.min_notional_size * Decimal("1.01"):
            return s_decimal_0

        return quantized_amount

    def get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        amount: Decimal,
        price: Decimal = s_decimal_NaN,
        is_maker: Optional[bool] = None,
    ) -> TradeFeeBase:
        """
        Calculates the estimated fee an order would pay based on the connector configuration
        :param base_currency: the order base currency
        :param quote_currency: the order quote currency
        :param order_type: the type of order (MARKET, LIMIT, LIMIT_MAKER)
        :param order_side: if the order is for buying or selling
        :param amount: the order amount
        :param price: the order price
        :return: the estimated fee for the order
        """

        """
        To get trading fee, this function is simplified by using fee override configuration. Most parameters to this
        function are ignore except order_type. Use OrderType.LIMIT_MAKER to specify you want trading fee for
        maker order.
        """
        is_maker = order_type is OrderType.LIMIT_MAKER
        return DeductedFromReturnsTradeFee(percent=self.estimate_fee_pct(is_maker))

    def buy(
        self,
        trading_pair: str,
        amount: Decimal,
        order_type: OrderType = OrderType.LIMIT,
        price: Decimal = s_decimal_NaN,
        **kwargs,
    ) -> str:
        """
        Creates a promise to create a buy order using the parameters.
        :param trading_pair: the token pair to operate with
        :param amount: the order amount
        :param order_type: the type of order to create (MARKET, LIMIT, LIMIT_MAKER)
        :param price: the order price
        :return: the id assigned by the connector to the order (the client id)
        """
        new_order_id = btcturk_utils.get_new_client_order_id(is_buy=True, trading_pair=trading_pair)
        safe_ensure_future(self._create_order(TradeType.BUY, new_order_id, trading_pair, amount, order_type, price))
        return new_order_id

    def sell(
        self,
        trading_pair: str,
        amount: Decimal,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = s_decimal_NaN,
        **kwargs,
    ) -> str:
        """
        Creates a promise to create a sell order using the parameters.
        :param trading_pair: the token pair to operate with
        :param amount: the order amount
        :param order_type: the type of order to create (MARKET, LIMIT, LIMIT_MAKER)
        :param price: the order price
        :return: the id assigned by the connector to the order (the client id)
        """
        order_id = btcturk_utils.get_new_client_order_id(is_buy=False, trading_pair=trading_pair)
        safe_ensure_future(self._create_order(TradeType.SELL, order_id, trading_pair, amount, order_type, price))
        return order_id

    def cancel(self, trading_pair: str, order_id: str):
        """
        Creates a promise to cancel an order in the exchange
        :param trading_pair: the trading pair the order to cancel operates with
        :param order_id: the client id of the order to cancel
        :return: the client id of the order to cancel
        """
        safe_ensure_future(self._execute_cancel(trading_pair, order_id))
        return order_id

    async def cancel_all(self, timeout_seconds: float) -> List[CancellationResult]:
        """
        Cancels all currently active orders. The cancellations are performed in parallel tasks.
        :param timeout_seconds: the maximum time (in seconds) the cancel logic should run
        :return: a list of CancellationResult instances, one for each of the orders to be cancelled
        """
        incomplete_orders = [o for o in self.in_flight_orders.values() if not o.is_done]
        tasks = [self._execute_cancel(o.trading_pair, o.client_order_id) for o in incomplete_orders]
        order_id_set = set([o.client_order_id for o in incomplete_orders])
        successful_cancellations = []

        try:
            async with timeout(timeout_seconds):
                cancellation_results = await safe_gather(*tasks, return_exceptions=True)
                for cr in cancellation_results:
                    if isinstance(cr, Exception):
                        continue
                    if isinstance(cr, dict) and "cancelled_order_id" in cr:
                        client_order_id = cr.get("cancelled_order_id")
                        order_id_set.remove(client_order_id)
                        successful_cancellations.append(CancellationResult(client_order_id, True))
        except Exception:
            self.logger().network(
                "Unexpected error cancelling orders.",
                exc_info=True,
                app_warning_msg="Failed to cancel order with Btcturk. Check API key and network connection.",
            )

        failed_cancellations = [CancellationResult(oid, False) for oid in order_id_set]
        return successful_cancellations + failed_cancellations

    # TODO
    # Rest awaits the results and updates the order status to OPEN
    async def _create_order(
        self,
        trade_type: TradeType,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        order_type: OrderType,
        price: Optional[Decimal] = Decimal("NaN"),
    ):
        """
        Creates a an order in the exchange using the parameters to configure it
        :param trade_type: the side of the order (BUY of SELL)
        :param order_id: the id that should be assigned to the order (the client id)
        :param trading_pair: the token pair to operate with
        :param amount: the order amount
        :param order_type: the type of order to create (MARKET, LIMIT, LIMIT_MAKER)
        :param price: the order price
        """
        trading_rule: TradingRule = self._trading_rules[trading_pair]
        price = self.quantize_order_price(trading_pair, price)
        quantize_amount_price = Decimal("0") if price.is_nan() else price
        amount = self.quantize_order_amount(trading_pair=trading_pair, amount=amount, price=quantize_amount_price)

        self.start_tracking_order(
            order_id=order_id,
            exchange_order_id=None,
            trading_pair=trading_pair,
            trade_type=trade_type,
            price=price,
            amount=amount,
            order_type=order_type,
        )

        if amount < trading_rule.min_order_size:
            self.logger().warning(
                f"{trade_type.name.title()} order amount {amount} is lower than the minimum order"
                f" size {trading_rule.min_order_size}. The order will not be created."
            )
            order_update: OrderUpdate = OrderUpdate(
                client_order_id=order_id,
                trading_pair=trading_pair,
                update_timestamp=int(self.current_timestamp * 1e3),
                new_state=OrderState.FAILED,
            )
            self._order_tracker.process_order_update(order_update)
            return

        order_result = None
        amount_str = f"{amount:f}"
        price_str = f"{price:f}"
        type_str = BtcturkExchange.btcturk_order_type(order_type)
        side_str = CONSTANTS.SIDE_BUY if trade_type is TradeType.BUY else CONSTANTS.SIDE_SELL
        symbol = await BtcturkAPIOrderBookDataSource.exchange_symbol_associated_to_pair(
            trading_pair=trading_pair, api_factory=self._api_factory, throttler=self._throttler
        )
        api_params = {
            "pairSymbol": symbol,
            "orderType": side_str,
            "quantity": amount_str,
            "orderMethod": type_str,
            "newOrderClientId": order_id,
            "price": price_str,
        }
        # if order_type == OrderType.LIMIT:
        #     api_params["timeInForce"] = CONSTANTS.TIME_IN_FORCE_GTC

        try:
            order_result = await self._api_request(
                method=RESTMethod.POST,
                path_url=CONSTANTS.ORDER_PATH,
                data=json.dumps(api_params),
                is_auth_required=True,
                limit_path_url=CONSTANTS.ORDER_PATH
            )

            exchange_order_id = str(order_result["data"]["id"])

            order_update: OrderUpdate = OrderUpdate(
                client_order_id=order_id,
                exchange_order_id=exchange_order_id,
                trading_pair=trading_pair,
                update_timestamp=int(order_result["data"]["datetime"]),
                new_state=OrderState.OPEN,
            )
            self._order_tracker.process_order_update(order_update)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger().network(
                f"Error submitting {side_str} {type_str} order to Btcturk for " f"{amount} {trading_pair} " f"{price}.",
                exc_info=True,
                app_warning_msg=str(e),
            )
            order_update: OrderUpdate = OrderUpdate(
                client_order_id=order_id,
                trading_pair=trading_pair,
                update_timestamp=int(self.current_timestamp * 1e3),
                new_state=OrderState.FAILED,
            )
            self._order_tracker.process_order_update(order_update)

    # TODO
    # Awaits the cancel request
    async def _execute_cancel(self, trading_pair: str, order_id: str):
        """
        Requests the exchange to cancel an active order
        :param trading_pair: the trading pair the order to cancel operates with
        :param order_id: the client id of the order to cancel
        """
        tracked_order = self._order_tracker.fetch_tracked_order(order_id)
        if tracked_order is not None:
            try:
                ex_order_id = tracked_order.exchange_order_id
                cancel_result = await self._api_request(
                    method=RESTMethod.DELETE,
                    path_url=CONSTANTS.ORDER_CANCEL_PATH.format(ex_order_id),
                    is_auth_required=True,
                    limit_path_url=CONSTANTS.ORDER_CANCEL_PATH
                )

                if cancel_result.get("message") == "SUCCESS":
                    order_update: OrderUpdate = OrderUpdate(
                        client_order_id=order_id,
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=int(self.current_timestamp * 1e3),
                        new_state=OrderState.CANCELLED,
                    )
                    cancel_result["cancelled_order_id"] = order_id
                    self._order_tracker.process_order_update(order_update)
                return cancel_result

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception(f"There was a an error when requesting cancellation of order {order_id}")
                raise

    async def _status_polling_loop(self):
        """
        Performs all required operation to keep the connector updated and synchronized with the exchange.
        It contains the backup logic to update status using API requests in case the main update source (the user stream
        data source websocket) fails.
        It also updates the time synchronizer. This is necessary because Btcturk require the time of the client to be
        the same as the time in the exchange.
        Executes when the _poll_notifier event is enabled by the `tick` function.
        """
        while True:
            try:
                await self._poll_notifier.wait()
                # await self._update_time_synchronizer()
                await safe_gather(
                    self._update_balances(),
                    # self._update_order_fills_from_trades(),
                )
                await self._update_order_status()
                self._last_poll_timestamp = self.current_timestamp
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    "Unexpected error while fetching account updates.",
                    exc_info=True,
                    app_warning_msg="Could not fetch account updates from Btcturk. "
                    "Check API key and network connection.",
                )
                await asyncio.sleep(0.5)
            finally:
                self._poll_notifier = asyncio.Event()

    async def _trading_rules_polling_loop(self):
        """
        Updates the trading rules by requesting the latest definitions from the exchange.
        Executes regularly every 30 minutes
        """
        while True:
            try:
                await safe_gather(
                    self._update_trading_rules(),
                )
                await asyncio.sleep(30 * 60)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    "Unexpected error while fetching trading rules.",
                    exc_info=True,
                    app_warning_msg="Could not fetch new trading rules from Btcturk. " "Check network connection.",
                )
                await asyncio.sleep(0.5)

    async def _update_trading_rules(self):
        exchange_info = await self._api_request(method=RESTMethod.GET, path_url=CONSTANTS.EXCHANGE_INFO_PATH_URL)
        trading_rules_list = await self._format_trading_rules(exchange_info)
        self._trading_rules.clear()

        for trading_rule in trading_rules_list:
            self._trading_rules[trading_rule.trading_pair] = trading_rule

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:

        trading_pair_rules = exchange_info_dict["data"].get("symbols", [])
        retval = []
        for rule in filter(btcturk_utils.is_exchange_information_valid, trading_pair_rules):
            try:
                trading_pair = await BtcturkAPIOrderBookDataSource.trading_pair_associated_to_exchange_symbol(
                    symbol=rule.get("name"),
                    api_factory=self._api_factory,
                    throttler=self._throttler,
                )
                filters = rule.get("filters")
                numeratorScale = Decimal(str(rule.get("numeratorScale")))
                denominatorScale = Decimal(str(rule.get("denominatorScale")))
                px = Decimal(str(rule.get("minimumLimitOrderPrice"))) * 10
                min_notional = Decimal(filters[0].get("minExchangeValue"))
                min_order_size = min_notional / px
                tick_size = Decimal(10 ** (-denominatorScale)) if rule.get("hasFraction") else 1
                # tick_size = Decimal(filters[0].get("tickSize"))
                step_size_btcturk = Decimal(10 ** (-numeratorScale)) if rule.get("hasFraction") else 1

                retval.append(
                    TradingRule(
                        trading_pair,
                        min_order_size=Decimal(min_order_size),
                        min_price_increment=Decimal(tick_size),
                        min_base_amount_increment=Decimal(step_size_btcturk),
                        min_notional_size=Decimal(min_notional),
                    )
                )
                # self.logger().error(f"retval: {retval}")
            except Exception:
                self.logger().exception(f"Error parsing the trading pair rule {rule}. Skipping.")
        return retval

    async def _user_stream_event_listener(self):
        """
        This functions runs in background continuously processing the events received from the exchange by the user
        stream data source. It keeps reading events from the queue until the task is interrupted.
        The events received are balance updates, order updates and trade events.
        """
        # TODO thinking about how to get user private stream to _iter_user_event_queue()
        # Assuming btcturk_api_user_stream_data_source listen_for_user_stream automatically add
        # user related messages to user event queue
        async for event_message in self._iter_user_event_queue():
            try:
                event_type = event_message[0]

                if event_type == 201:
                    safe_ensure_future(self._update_balances())

                if event_type == 441:
                    client_order_id = event_message[1].get("clientId", None)
                    tracked_order = self._order_tracker.fetch_order(client_order_id=client_order_id)
                    if tracked_order is not None:
                        quote_ccy = btcturk_utils.convert_from_exchange_trading_pair_to_quote_ccy(tracked_order.trading_pair)
                        trade_id = btcturk_utils.get_trade_id()
                        trade_update = TradeUpdate(
                            trade_id=trade_id,
                            client_order_id=client_order_id,
                            exchange_order_id=str(event_message[1]["id"]),
                            trading_pair=tracked_order.trading_pair,
                            fee_asset=quote_ccy,
                            fee_paid=Decimal(str(event_message[1]["amount"])) * Decimal(str(event_message[1]["price"])) * Decimal(btcturk_utils.DEFAULT_FEES[0]),
                            fill_base_amount=Decimal(str(event_message[1]["amount"])),
                            fill_quote_amount=Decimal(str(event_message[1]["amount"])) * Decimal(str(event_message[1]["price"])),
                            fill_price=Decimal(str(event_message[1]["price"])),
                            fill_timestamp=int(self.current_timestamp * 1e3),
                        )
                        self._order_tracker.process_trade_update(trade_update)

                elif event_type in [451, 452, 453]:
                    client_order_id = event_message[1].get("newOrderClientId")

                else:
                    client_order_id = 0
                tracked_order = self.in_flight_orders.get(client_order_id, None)
                if tracked_order is not None:
                    old_state = tracked_order.current_state
                    new_state = old_state
                    if event_type == 451:
                        new_state = CONSTANTS.ORDER_STATE["NEW"]
                    elif event_type == 452:
                        new_state = CONSTANTS.ORDER_STATE["CANCELED"]
                    elif event_type == 441:
                        if math.isclose(tracked_order.amount, tracked_order.executed_amount_base):
                            new_state = CONSTANTS.ORDER_STATE["FILLED"]
                        else:
                            new_state = CONSTANTS.ORDER_STATE["PARTIALLY_FILLED"]
                    else:
                        new_state = old_state

                    order_update = OrderUpdate(
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=int(self.current_timestamp * 1e3),
                        new_state=new_state,
                        client_order_id=client_order_id,
                        exchange_order_id=str(event_message[1]["id"]),
                    )
                    self._order_tracker.process_order_update(order_update=order_update)

                # # event_type is channel number for btcturk
                # event_type = event_message[0]
                # # Refer to https://github.com/binance-exchange/binance-official-api-docs/blob/master/user-data-stream.md
                # # As per the order update section in Binance the ID of the order being cancelled is under the "C" key
                # # https://binance-docs.github.io/apidocs/spot/en/#listen-key-isolated-margin
                # # User related channels in ws:
                # # 201 = BalanceUpdate, 441 = Order Executed, 451 = OrderReceived
                # # 452 = OrderDelete, 453 = OrderUpdate
                # filled = False
                # if event_type in [451, 452, 453]:
                #     client_order_id = event_message[1].get("newOrderClientId", None)
                # # Partial filled order issue needs to be solved
                # elif event_type == 441:
                #     client_order_id = event_message[1].get("clientId", None)
                #     tracked_order = self._order_tracker.fetch_order(client_order_id=client_order_id)
                #     # btcturk only provides exchange order id, not trade_id
                #     if Decimal(str(event_message[1]["amount"])) > 0:
                #         filled = True
                #     if tracked_order is not None:
                #         quote_ccy = btcturk_utils.convert_from_exchange_trading_pair_to_quote_ccy(tracked_order.trading_pair)
                #         trade_id = btcturk_utils.get_trade_id()
                #         trade_update = TradeUpdate(
                #             trade_id=trade_id,
                #             client_order_id=client_order_id,
                #             exchange_order_id=str(event_message[1]["id"]),
                #             trading_pair=tracked_order.trading_pair,
                #             fee_asset=quote_ccy,
                #             fee_paid=Decimal(str(event_message[1]["amount"])) * Decimal(str(event_message[1]["price"])) * Decimal(btcturk_utils.DEFAULT_FEES[0]),
                #             fill_base_amount=Decimal(str(event_message[1]["amount"])),
                #             fill_quote_amount=Decimal(str(event_message[1]["amount"])) * Decimal(str(event_message[1]["price"])),
                #             fill_price=Decimal(str(event_message[1]["price"])),
                #             fill_timestamp=int(self.current_timestamp * 1e3),
                #         )
                #         self._order_tracker.process_trade_update(trade_update)
                # else:
                #     client_order_id = 0
                # tracked_order = self.in_flight_orders.get(client_order_id)
                # if tracked_order is not None:
                #     # TODO
                #     old_state = tracked_order.current_state
                #     new_state = old_state
                #     if filled:  # This already implies event type is 441
                #         new_state = OrderState.PARTIALLY_FILLED
                #         # TODO
                #         if math.isclose(tracked_order.amount, tracked_order.executed_amount_base):
                #             new_state = OrderState.FILLED
                #     elif event_type == 451:
                #         new_state = OrderState.OPEN
                #     elif event_type == 452:
                #         if old_state == OrderState.PENDING_CREATE:
                #             new_state = OrderState.FAILED
                #         else:
                #             new_state = OrderState.CANCELLED
                #     elif event_type == 453:
                #         new_state = old_state

                #     order_update = OrderUpdate(
                #         trading_pair=tracked_order.trading_pair,
                #         update_timestamp=int(self.current_timestamp * 1e3),
                #         new_state=new_state,
                #         client_order_id=client_order_id,
                #         exchange_order_id=str(event_message[1]["id"]),
                #     )
                #     self._order_tracker.process_order_update(order_update=order_update)
                # btcturk not providing any details about 201-BalanceUpdate message
                # elif event_type == "outboundAccountPosition":
                #     balances = event_message["B"]
                #     for balance_entry in balances:
                #         asset_name = balance_entry["a"]
                #         free_balance = Decimal(balance_entry["f"])
                #         total_balance = Decimal(balance_entry["f"]) + Decimal(balance_entry["l"])
                #         self._account_available_balances[asset_name] = free_balance
                #         self._account_balances[asset_name] = total_balance

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await asyncio.sleep(5.0)

    async def _update_order_fills_from_trades(self):
        """
        This is intended to be a backup measure to get filled events with trade ID for orders,
        in case Binance's user stream events are not working.
        NOTE: It is not required to copy this functionality in other connectors.
        This is separated from _update_order_status which only updates the order status without producing filled
        events, since Binance's get order endpoint does not return trade IDs.
        The minimum poll interval for order status is 10 seconds.
        """
        small_interval_last_tick = self._last_poll_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        small_interval_current_tick = self.current_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        long_interval_last_tick = self._last_poll_timestamp / self.LONG_POLL_INTERVAL
        long_interval_current_tick = self.current_timestamp / self.LONG_POLL_INTERVAL

        if long_interval_current_tick > long_interval_last_tick or (
            self.in_flight_orders and small_interval_current_tick > small_interval_last_tick
        ):
            query_time = int(self._last_trades_poll_btcturk_timestamp * 1e3)
            self._last_trades_poll_btcturk_timestamp = self._btcturk_time_synchronizer.time()
            order_by_exchange_id_map = {}
            for order in self._order_tracker.all_orders.values():
                order_by_exchange_id_map[order.exchange_order_id] = order
            # TODO
            tasks = []
            trading_pairs = self._order_book_tracker._trading_pairs
            for trading_pair in trading_pairs:
                symbol = await BtcturkAPIOrderBookDataSource.exchange_symbol_associated_to_pair(
                    trading_pair=trading_pair,
                    api_factory=self._api_factory,
                    throttler=self._throttler,
                )
                base_symbol = btcturk_utils.convert_from_exchange_trading_pair_to_base_quote(symbol)
                startDate = query_time

                # if self._last_poll_timestamp > 0:
                #     startDate = query_time
                tasks.append(
                    self._api_request(
                        method=RESTMethod.GET,
                        path_url=CONSTANTS.MY_TRADES_PATH_URL.format(base_symbol, startDate),
                        is_auth_required=True,
                        limit_path_url=CONSTANTS.MY_TRADES_PATH_URL
                    )
                )

            self.logger().debug(f"Polling for order fills of {len(tasks)} trading pairs.")
            results = await safe_gather(*tasks, return_exceptions=True)

            for trades, trading_pair in zip(results, trading_pairs):

                if isinstance(trades, Exception):
                    self.logger().network(
                        f"Error fetching trades update for the order {trading_pair}: {trades}.",
                        app_warning_msg=f"Failed to fetch trade update for {trading_pair}.",
                    )
                    continue
                # TODO response object quite different from binance. numeratorSymbol etc.
                for trade in trades["data"]:
                    exchange_order_id = str(trade["orderId"])
                    if exchange_order_id in order_by_exchange_id_map:
                        # This is a fill for a tracked order
                        tracked_order = order_by_exchange_id_map[exchange_order_id]
                        trade_update = TradeUpdate(
                            trade_id=tracked_order.trade_id,
                            client_order_id=tracked_order.client_order_id,
                            exchange_order_id=exchange_order_id,
                            trading_pair=trading_pair,
                            fee_asset=trade["denominatorSymbol"],
                            fee_paid=abs(Decimal(str(trade["fee"])) + Decimal(str(trade["tax"]))),
                            fill_base_amount=Decimal(abs(int(str(trade["amount"])))),
                            # fill_quote_amount=Decimal(trade["quoteQty"]),
                            fill_price=Decimal(str(trade["price"])),
                            fill_timestamp=int(trade["timestamp"]),
                        )
                        self._order_tracker.process_trade_update(trade_update)
                    elif self.is_confirmed_new_order_filled_event(tracked_order.trade_id, exchange_order_id, trading_pair):
                        # This is a fill of an order registered in the DB but not tracked any more
                        self._current_trade_fills.add(
                            TradeFillOrderDetails(
                                market=self.display_name, exchange_trade_id=tracked_order.trade_id, symbol=trading_pair
                            )
                        )
                        self.trigger_event(
                            MarketEvent.OrderFilled,
                            OrderFilledEvent(
                                timestamp=float(trade["timestamp"]) * 1e-3,
                                order_id=self._exchange_order_ids.get(str(trade["orderId"]), None),
                                trading_pair=trading_pair,
                                trade_type=TradeType.SELL if str(trade["data"]["orderType"]) == "sell" else TradeType.BUY,
                                # order_type=OrderType.LIMIT_MAKER if trade["isMaker"] else OrderType.LIMIT,
                                # price=Decimal(trade["price"]),
                                amount=Decimal(abs(int(str(trade["amount"])))),
                                trade_fee=DeductedFromReturnsTradeFee(
                                    flat_fees=[TokenAmount(fee_asset=trade["denominatorSymbol"]), abs(Decimal(str(trade["fee"])) + Decimal(str(trade["tax"])))]
                                ),
                                exchange_trade_id=tracked_order.trade_id,
                            ),
                        )
                        self.logger().info(f"Recreating missing trade in TradeFill: {trade}")

    async def _update_order_status(self):
        # This is intended to be a backup measure to close straggler orders, in case Binance's user stream events
        # are not working.
        # The minimum poll interval for order status is 10 seconds.
        last_tick = self._last_poll_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        current_tick = self.current_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL

        tracked_orders: List[InFlightOrder] = list(self.in_flight_orders.values())
        if current_tick > last_tick and len(tracked_orders) > 0:
            # Only pairSymbol needed for orders, we cant use origClientOrderId; so each result response
            # contains multiple open orders.
            tasks = [
                self._api_request(
                    method=RESTMethod.GET,
                    path_url=CONSTANTS.GET_SINGLE_ORDER_PATH.format(o.exchange_order_id),
                    limit_path_url=CONSTANTS.ORDER_PATH,
                    is_auth_required=True,
                )
                for o in tracked_orders
            ]
            self.logger().debug(f"Polling for order status updates of {len(tasks)} orders.")
            results = await safe_gather(*tasks, return_exceptions=True)
            updated_results = []
            for i in results:
                if i.get("data", None):
                    j = i.get("data")
                    updated_results.append(j)
                else:
                    continue

            for order_update, tracked_order in zip(updated_results, tracked_orders):
                client_order_id = tracked_order.client_order_id

                # If the order has already been cancelled or has failed do nothing
                if client_order_id not in self.in_flight_orders:
                    continue

                if isinstance(order_update, Exception):
                    self.logger().network(
                        f"Error fetching status update for the order {client_order_id}: {order_update}.",
                        app_warning_msg=f"Failed to fetch status update for the order {client_order_id}.",
                    )
                    self._order_not_found_records[client_order_id] = (
                        self._order_not_found_records.get(client_order_id, 0) + 1
                    )
                    if (
                        self._order_not_found_records[client_order_id]
                        >= self.MAX_ORDER_UPDATE_RETRIEVAL_RETRIES_WITH_FAILURES
                    ):
                        # Wait until the order not found error have repeated a few times before actually treating
                        # it as failed. See: https://github.com/CoinAlpha/hummingbot/issues/601

                        order_update: OrderUpdate = OrderUpdate(
                            client_order_id=client_order_id,
                            trading_pair=tracked_order.trading_pair,
                            update_timestamp=int(self.current_timestamp * 1e3),
                            new_state=OrderState.FAILED,
                        )
                        self._order_tracker.process_order_update(order_update)

                else:
                    # Update order execution status
                    # new_state = CONSTANTS.ORDER_STATE[order_update["status"]]
                    if str(order_update["status"]) == "Untouched":
                        new_state = CONSTANTS.ORDER_STATE["NEW"]
                    elif str(order_update["status"]) == "Closed":
                        new_state = CONSTANTS.ORDER_STATE["FILLED"]
                    elif order_update["status"] == "Canceled":
                        new_state = CONSTANTS.ORDER_STATE["CANCELED"]
                    update = OrderUpdate(
                        client_order_id=client_order_id,
                        exchange_order_id=str(order_update["orderClientId"]),
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=int(str(order_update["updateTime"])),
                        new_state=new_state,
                    )
                    self._order_tracker.process_order_update(update)

    async def _iter_user_event_queue(self) -> AsyncIterable[Dict[str, any]]:
        while True:
            try:
                yield await self._user_stream_tracker.user_stream.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    "Unknown error. Retrying after 1 seconds.",
                    exc_info=True,
                    app_warning_msg="Could not fetch user events from Btcturk. Check API key and network connection.",
                )
                await asyncio.sleep(1.0)

    async def _update_balances(self):
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()

        try:
            account_info = await self._api_request(
                method=RESTMethod.GET, path_url=CONSTANTS.ACCOUNTS_PATH_URL, is_auth_required=True
            )
            balances = account_info["data"]
            for balance_entry in balances:
                asset_name = balance_entry["asset"]
                free_balance = Decimal(balance_entry["free"])
                total_balance = Decimal(balance_entry["free"]) + Decimal(balance_entry["locked"])
                self._account_available_balances[asset_name] = free_balance
                self._account_balances[asset_name] = total_balance
                remote_asset_names.add(asset_name)

            asset_names_to_remove = local_asset_names.difference(remote_asset_names)
            for asset_name in asset_names_to_remove:
                del self._account_available_balances[asset_name]
                del self._account_balances[asset_name]
        except IOError:
            self.logger().exception("Error getting account balances from server")

    async def _update_time_synchronizer(self):
        try:
            await self._btcturk_time_synchronizer.update_server_time_offset_with_time_provider(
                time_provider=self._get_current_server_time()
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Error requesting time from Btcturk server")
            raise

    async def _api_request(
        self,
        method: RESTMethod,
        path_url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        is_auth_required: bool = False,
        limit_path_url: Optional[str] = None,
    ) -> Dict[str, Any]:

        client = await self._get_rest_assistant()

        if is_auth_required:
            url = btcturk_utils.private_rest_url(path_url)
            headers = self._auth.header_for_authentication()
            request = RESTRequest(
                method=method, url=url, data=data, params=params, headers=headers, is_auth_required=is_auth_required
            )
        else:
            url = btcturk_utils.public_rest_url(path_url)
            request = RESTRequest(
                method=method, url=url, data=data, params=params, is_auth_required=is_auth_required
            )
        limit_id_path = path_url if limit_path_url is None else limit_path_url
        async with self._throttler.execute_task(limit_id=limit_id_path):
            response = await client.call(request)

            if response.status != 200:
                data = await response.text()
                raise IOError(f"Error fetching data from {url}. HTTP status is {response.status} ({data}) request: {request}.")
            try:
                parsed_response = await response.json()
            except Exception:
                raise IOError(f"Error parsing data from {response}.")

            if "code" in parsed_response and "msg" in parsed_response:
                raise IOError(f"The request to Btcturk failed. Error: {parsed_response}. Request: {request}")

        return parsed_response

    async def _get_current_server_time(self):
        response = await self._api_request(
            method=RESTMethod.GET,
            path_url=CONSTANTS.EXCHANGE_INFO_PATH_URL,
        )
        return response["data"]["serverTime"]

    async def _get_rest_assistant(self) -> RESTAssistant:
        if self._rest_assistant is None:
            self._rest_assistant = await self._api_factory.get_rest_assistant()
        return self._rest_assistant
