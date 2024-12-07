from scripts.utils.reporting import thingsboard
from unittest.mock import patch
from scripts.utils.helpers import ParseFileName, Detection
from datetime import datetime as dt


@patch("scripts.utils.reporting.requests")
@patch("scripts.utils.reporting.get_settings")
def test_thingsboard(settings_mock, requests_mock):
    settings_mock.return_value = {
        "THINGSBOARD_ADDRESS": "https://thingsboard.org",
        "THIGSBOARD_DEVICE_TOKEN": "token",
        "LATITUDE": 55.074,
        "LONGITUDE": 4.360,
        "MODEL": None,
    }
    file = ParseFileName("2024-12-07 18:34:21.file")
    detection = Detection(
        dt(2024, 12, 7, 18, 34, 21), 5, 8, "Parus major_Great tit", 0.789
    )

    thingsboard(file, [detection])

    requests_mock.post.assert_called_with(
        "https://thingsboard.org/api/v1/token/telemetry",
        json={
            "ts": 1733592866000.0,
            "values": {
                "commonName": "Great tit",
                "scientificName": "Parus major",
                "lat": 55.074,
                "lon": 4.36,
                "confidence": 0.789,
                "soundscapeId": 0,
                "soundscapeStartTime": 5.0,
                "soundscapeEndTime": 8.0,
                "algorithm": "alpha",
            },
        },
        timeout=20,
    )
