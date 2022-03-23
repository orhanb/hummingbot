from typing import (
    Dict,
    List,
    Optional,
)

from hummingbot.core.data_type.order_book_row import OrderBookRow
from hummingbot.core.data_type.order_book_message import (
    OrderBookMessage,
    OrderBookMessageType,
)
from hummingbot.connector.exchange.btcturk.btcturk_utils import convert_from_exchange_trading_pair


class BtcturkOrderBookMessage(OrderBookMessage):
    def __new__(
        cls,
        message_type: OrderBookMessageType,
        content: Dict[str, any],
        timestamp: Optional[float] = None,
        *args,
        **kwargs,
    ):
        if timestamp is None:
            if message_type is OrderBookMessageType.SNAPSHOT:
                raise ValueError("timestamp must not be None when initializing snapshot messages.")
            timestamp = float(content["CS"])
        return super(BtcturkOrderBookMessage, cls).__new__(
            cls, message_type, content, timestamp=timestamp, *args, **kwargs
        )

    @property
    def update_id(self) -> int:
        if self.type in [OrderBookMessageType.DIFF, OrderBookMessageType.SNAPSHOT]:
            change_set = self.content["CS"]
            return int(change_set)
        # Binance example is like below in TestDocument
        # elif self.type == OrderBookMessageType.TRADE:
        #     return int(self.content["D"])
        return -1

    @property
    def trade_id(self) -> int:
        if self.type is OrderBookMessageType.TRADE:
            return int(self.content["I"])
        return -1

    @property
    def trading_pair(self) -> str:
        if "PS" in self.content:
            hb_trading_pair = convert_from_exchange_trading_pair(self.content["PS"])
            return hb_trading_pair
        else:
            return -1

    @property
    def asks(self) -> List[OrderBookRow]:
        if self.type is OrderBookMessageType.SNAPSHOT:
            results = [
                OrderBookRow(float(entry["P"]), float(entry["A"]), self.update_id)
                for entry in self.content["AO"]
            ]
            sorted(results, key=lambda a: a.price)
            return results

        elif self.type is OrderBookMessageType.DIFF:
            results = [
                OrderBookRow(float(entry["P"]), float(entry["A"]) if entry["CP"] != 3 else float(0.0), self.update_id)
                for entry in self.content["AO"]
            ]
            # sorted(results, key=lambda a: a.price)
            return results
        else:
            return -1

    @property
    def bids(self) -> List[OrderBookRow]:
        if self.type is OrderBookMessageType.SNAPSHOT:
            results = [
                OrderBookRow(float(entry["P"]), float(entry["A"]), self.update_id)
                for entry in self.content["BO"]
            ]
            sorted(results, key=lambda b: b.price)
            return results

        elif self.type is OrderBookMessageType.DIFF:
            results = [
                OrderBookRow(float(entry["P"]), float(entry["A"]) if entry["CP"] != 3 else float(0.0), self.update_id)
                for entry in self.content["BO"]
            ]
            # sorted(results, key=lambda b: b.price)
            return results
        else:
            return -1

    def __eq__(self, other) -> bool:
        return self.type == other.type and self.timestamp == other.timestamp

    def __lt__(self, other) -> bool:
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        else:
            """
            If timestamp is the same, the ordering is snapshot < diff < trade
            """
            return self.type.value < other.type.value
