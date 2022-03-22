import asyncio
import logging
import hashlib
import hmac
import base64

from hummingbot.connector.time_synchronizer import TimeSynchronizer

from typing import (
    Optional
)

import hummingbot.connector.exchange.btcturk.btcturk_constants as CONSTANTS
from hummingbot.connector.exchange.btcturk.btcturk_auth import BtcturkAuth
from hummingbot.connector.utils import build_api_factory
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.web_assistant.rest_assistant import RESTAssistant
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger


class BtcturkAPIUserStreamDataSource(UserStreamTrackerDataSource):

    LISTEN_KEY_KEEP_ALIVE_INTERVAL = 1800  # Recommended to Ping/Update listen key to keep connection alive
    HEARTBEAT_TIME_INTERVAL = 30.0

    _bausds_logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 auth: BtcturkAuth,
                 api_factory: Optional[WebAssistantsFactory] = None,
                 throttler: Optional[AsyncThrottler] = None):
        super().__init__()
        self._auth: BtcturkAuth = auth
        self._current_listen_key = None
        self._last_recv_time: float = 0
        self._throttler = throttler or self._get_throttler_instance()
        self._api_factory = api_factory or build_api_factory()
        self._rest_assistant: Optional[RESTAssistant] = None
        self._ws_assistant: Optional[WSAssistant] = None

        self._ws_auth_event: asyncio.Event = asyncio.Event()
        # self._last_listen_key_ping_ts = 0

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._bausds_logger is None:
            cls._bausds_logger = logging.getLogger(__name__)
        return cls._bausds_logger

    @property
    def last_recv_time(self) -> float:
        """
        Returns the time of the last received message
        :return: the timestamp of the last received message in seconds
        """
        if self._ws_assistant:
            return self._ws_assistant.last_recv_time
        return -1

    async def listen_for_user_stream(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Connects to the user private channel in the exchange using a websocket connection. With the established
        connection listens to all balance events and order updates provided by the exchange, and stores them in the
        output queue
        """
        ws = None
        while True:
            try:

                ws: WSAssistant = await self._get_ws_assistant()
                url = f"{CONSTANTS.WSS_URL}"
                await ws.connect(ws_url=url, ping_timeout=CONSTANTS.WS_HEARTBEAT_TIME_INTERVAL)
                safe_ensure_future(self._send_authentication_request(ws))

                async for ws_response in ws.iter_messages():
                    data = ws_response.data

                    if len(data) > 0:
                        if data[0] == 114:
                            login_result = data[1]["ok"]
                            if not login_result:
                                self.logger().error("Login failed", data)
                                break
                            else:
                                self._ws_auth_event.set()

                        if (data[0] == 201) or (data[0] == 441) or (data[0] == 451) or (data[0] == 452) or (data[0] == 453):
                            # User related channels in ws: 201 = BalanceUpdate, 441 = Order Executed, 451 = OrderReceived
                            # 452 = OrderDelete, 453 = OrderUpdate
                            # if data[0] == 441:
                            output.put_nowait(data)

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception("Unexpected error while listening to user stream. Retrying after 5 seconds...")
            finally:
                # Make sure no background task is leaked.
                ws and await ws.disconnect()
                await self._sleep(5)

    @classmethod
    def _get_throttler_instance(cls) -> AsyncThrottler:
        return AsyncThrottler(CONSTANTS.RATE_LIMITS)

    async def _send_authentication_request(self, ws: WSAssistant):
        public_key = self._auth.api_key
        private_key = self._auth.secret_key
        nonce = 3000
        base_string = "{}{}".format(public_key, nonce).encode("utf-8")
        signature = hmac.new(
            base64.b64decode(private_key), base_string, hashlib.sha256
        ).digest()
        signature = base64.b64encode(signature)
        ts = TimeSynchronizer()
        timestamp = round(ts.time() * 1000)
        hmac_message_object = [
            114,
            {
                "nonce": nonce,
                "publicKey": public_key,
                "signature": signature.decode("utf-8"),
                "timestamp": timestamp,
                "type": 114,
            },
        ]
        # request = WSRequest(payload=hmac_message_object)
        await ws._connection._connection.send_json(hmac_message_object)

    async def _get_rest_assistant(self) -> RESTAssistant:
        if self._rest_assistant is None:
            self._rest_assistant = await self._api_factory.get_rest_assistant()
        return self._rest_assistant

    async def _get_ws_assistant(self) -> WSAssistant:
        if self._ws_assistant is None:
            self._ws_assistant = await self._api_factory.get_ws_assistant()
        return self._ws_assistant
