import hashlib
import hmac
from collections import OrderedDict
from typing import Any, Dict
from urllib.parse import urlencode

from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, RESTMethod, WSRequest
from hummingbot.connector.time_synchronizer import TimeSynchronizer
import base64
import json


class BtcturkAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str, time_provider: TimeSynchronizer):
        self.api_key = api_key
        self.secret_key = secret_key
        self.time_provider = time_provider

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions. It also adds
        the required parameter in the request header.
        :param request: the request to be configured for authenticated interaction
        """
        if request.method == RESTMethod.POST:
            # request.params = self.add_auth_to_params(params=request.params)
            # params = {}
            # params.update()
            # request.
            request.params = json.dumps(request.params)

        elif request.method == RESTMethod.GET:
            headers = {}
            headers.update(self.header_for_authentication())
            request.headers = headers

        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        This method is intended to configure a websocket request to be authenticated. Binance does not use this
        functionality
        """
        return request  # pass-through

    def add_params_to_json(self, params: Dict[str, Any]):
        # timestamp = int(self.time_provider.time() * 1e3)

        request_params = OrderedDict(params or {})
        # request_params["timestamp"] = timestamp

        # signature = self._generate_signature(params=request_params)
        # request_params["signature"] = signature

        return request_params

    def header_for_authentication(self) -> Dict[str, str]:
        apiKey = self.api_key
        apiSecret = self.secret_key
        apiSecret = base64.b64decode(apiSecret)
        stamp = str(int(self.time_provider.time() * 1e3))
        data = "{}{}".format(apiKey, stamp).encode("utf-8")
        signature = hmac.new(apiSecret, data, hashlib.sha256).digest()
        signature = base64.b64encode(signature)
        signature = signature.decode("utf-8")
        return {
            "X-PCK": apiKey,
            "X-Stamp": stamp,
            "X-Signature": signature,
            "Content-Type": "application/json",
        }

    def _generate_signature(self, params: Dict[str, Any]) -> str:

        encoded_params_str = urlencode(params)
        digest = hmac.new(self.secret_key.encode("utf8"), encoded_params_str.encode("utf8"), hashlib.sha256).hexdigest()
        return digest
