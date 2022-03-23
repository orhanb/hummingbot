from typing import Dict, Optional, List
from hummingbot.core.event.events import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import (
    OrderBookMessage,
    OrderBookMessageType
)
from hummingbot.connector.exchange.btcturk.btcturk_orderbook_message import BtcturkOrderBookMessage
# from hummingbot.hummingbot.core.data_type.order_book_message import OrderBookMessage
# from hummingbot.connector.exchange.btcturk.btcturk_constants import EXCHANGE_NAME


class BtcturkOrderBook(OrderBook):

    @classmethod
    def snapshot_message_from_exchange(cls,
                                       msg: List[any],
                                       timestamp: float,
                                       metadata: Optional[Dict] = None) -> BtcturkOrderBookMessage:
        """
        Creates a snapshot message with the order book snapshot message
        :param msg: the response from the exchange when requesting the order book snapshot
        :param timestamp: the snapshot timestamp
        :param metadata: a dictionary with extra information to add to the snapshot data
        :return: a snapshot message with the snapshot information received from the exchange
        """
        if metadata:
            msg[1].update(metadata)
        return BtcturkOrderBookMessage(
            message_type=OrderBookMessageType.SNAPSHOT,
            content=msg[1],
            timestamp=timestamp
        )

    @classmethod
    def restfull_snapshot_message_from_exchange(cls,
                                                msg: Dict[str, any],
                                                timestamp: float,
                                                metadata: Optional[Dict] = None) -> OrderBookMessage:
        if metadata:
            msg.update(metadata)
        # raise Exception(msg)
        return OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
            "trading_pair": msg["trading_pair"],
            "update_id": msg["data"]["timestamp"],
            "bids": msg["data"]["bids"],
            "asks": msg["data"]["asks"]
        }, timestamp=timestamp)

    @classmethod
    def diff_message_from_exchange(cls,
                                   msg: List[any],
                                   timestamp: Optional[float] = None,
                                   metadata: Optional[Dict] = None) -> BtcturkOrderBookMessage:
        """
        Creates a diff message with the changes in the order book received from the exchange
        :param msg: the changes in the order book
        :param timestamp: the timestamp of the difference
        :param metadata: a dictionary with extra information to add to the difference data
        :return: a diff message with the changes in the order book notified by the exchange
        """
        if metadata:
            msg[1].update(metadata)
        return BtcturkOrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content=msg[1],
            timestamp=timestamp
        )

    @classmethod
    def trade_message_from_exchange(cls,
                                    msg: List[any],
                                    metadata: Optional[Dict] = None) -> BtcturkOrderBookMessage:
        """
        Creates a trade message with the information from the trade event sent by the exchange
        :param msg: the trade event details sent by the exchange
        :param metadata: a dictionary with extra information to add to trade message
        :return: a trade message with the details of the trade as provided by the exchange
        """
        if metadata:
            msg[1].update(metadata)
        msg[1].update({
            "price": msg[1].get("P"),
            "amount": msg[1].get("A"),
            "trade_type": float(TradeType.SELL.value) if msg[1]["S"] == 0 else float(TradeType.BUY.value)
        })
        timestamp = float(msg[1]["D"]) * (1e-3)
        return BtcturkOrderBookMessage(
            message_type=OrderBookMessageType.TRADE,
            content=msg[1],
            timestamp=timestamp
        )

    # @classmethod
    # def from_snapshot(cls, snapshot: OrderBookMessage):
    #     raise NotImplementedError(EXCHANGE_NAME + " order book needs to retain individual order data.")
    #
    # @classmethod
    # def restore_from_snapshot_and_diffs(self, snapshot: OrderBookMessage, diffs: List[OrderBookMessage]):
    #     raise NotImplementedError(EXCHANGE_NAME + " order book needs to retain individual order data.")
