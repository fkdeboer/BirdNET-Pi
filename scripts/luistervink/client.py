import requests
import logging

log = logging.getLogger(__name__)


class LuistervinkClient:
    def __init__(self, conf: dict):
        self.conf = conf
        self.base_url = conf.get(
            "LUISTERVINK_SERVER_ADDRESS", "https://api.luistervink.nl"
        )
        self.params = {"token": conf.get("LUISTERVINK_DEVICE_TOKEN")}
        self.session = requests.Session()

    def get(self, endpoint: str) -> requests.Response:
        url = f"{self.base_url}/api/{endpoint}"
        return requests.get(url, params=self.params)

    def post(
        self, endpoint: str, data: dict | None = None, files: dict | None = None
    ) -> requests.Response:
        url = f"{self.base_url}/{endpoint}"
        return requests.post(url, json=data, params=self.params, files=files)

    def put(self, endpoint: str, data: dict | None = None) -> requests.Response:
        url = f"{self.base_url}/{endpoint}"
        return requests.put(url, json=data, params=self.params)
