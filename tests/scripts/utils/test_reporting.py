from scripts.utils.reporting import luistervink
from unittest.mock import patch
from scripts.utils.helpers import ParseFileName, Detection
from datetime import datetime as dt


@patch("scripts.utils.reporting.requests")
@patch("scripts.utils.reporting.get_settings")
def test_luistervink(settings_mock, requests_mock):
    settings_mock.return_value = {
        "LUISTERVINK_SERVER_ADDRESS": "https://data.luistervink.nl",
        "LUISTERVINK_DEVICE_TOKEN": "token",
        "LATITUDE": 55.074,
        "LONGITUDE": 4.360,
        "MODEL": None,
    }
    file = ParseFileName("2024-12-07 18:34:21.file")
    detection = Detection(
        dt(2024, 12, 7, 18, 34, 21), 5, 8, "Parus major_Great tit", 0.789
    )

    luistervink(file, [detection])

    requests_mock.post.assert_called_with(
        "https://data.luistervink.nl/api/detections",
        json={
            "timestamp": "2024-12-07 18:34:26",
            "commonName": "Great tit",
            "scientificName": "Parus major",
            "lat": 55.074,
            "lon": 4.36,
            "confidence": 0.789,
            "soundscapeId": 0,
            "soundscapeStartTime": 5.0,
            "soundscapeEndTime": 8.0,
        },
        params={"token": "token"},
        timeout=20,
    )
