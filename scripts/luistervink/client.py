import requests
import logging
from typing import Optional


log = logging.getLogger(__name__)


class LuistervinkClient:
    def __init__(self, conf: dict):
        self.conf = conf
        self.base_url = conf.get(
            "LUISTERVINK_SERVER_ADDRESS", "https://api.luistervink.nl"
        )
        self.params = {"token": conf.get("LUISTERVINK_DEVICE_TOKEN")}
        self.session = requests.Session()

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url.rstrip('/')}/api/{endpoint.lstrip('/')}"

    def get(self, endpoint: str) -> requests.Response:
        return requests.get(self._url(endpoint), params=self.params)

    def post(
        self, endpoint: str, data: Optional[dict] = None, files: Optional[dict] = None
    ) -> requests.Response:
        return requests.post(
            self._url(endpoint), json=data, params=self.params, files=files, timeout=30
        )

    def put(self, endpoint: str, data: Optional[dict] = None) -> requests.Response:
        return requests.put(
            self._url(endpoint), json=data, params=self.params, timeout=30
        )
