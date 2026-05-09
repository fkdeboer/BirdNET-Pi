from dataclasses import dataclass
from typing import Any


@dataclass
class LuistervinkSettings:
    server_address: str
    device_token: str
    enable_task_processor: bool


@dataclass
class Task:
    type: str
    spec: Any


@dataclass
class Detection:
    date: str
    time: str
    scientific_name: str
    common_name: str
    confidence: float
    latitude: float
    longitude: float
