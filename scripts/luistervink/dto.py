from dataclasses import dataclass
from typing import Any


@dataclass
class Task:
    type: str
    spec: Any
