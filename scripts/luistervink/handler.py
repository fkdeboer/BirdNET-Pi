import os
import sqlite3
import logging
from datetime import datetime, timezone
from tzlocal import get_localzone

from luistervink.client import LuistervinkClient
from utils.helpers import DB_PATH, HOME_DIR

log = logging.getLogger(__name__)


class BaseHandler:
    type: str

    def __init__(self, client: LuistervinkClient, spec: dict | str) -> None:
        self.client = client
        self.spec = spec

    def handle(self) -> str:
        """Handle the task and return a result."""
        raise NotImplementedError("Subclasses should implement this method.")


class DetectionSoundHandler(BaseHandler):
    type: str = "sound_request"
    spec: dict

    def handle(self) -> str:
        filepath = self._find_detection_filename()
        if filepath is None:
            log.warning("No detection found for the given spec.")
            return self._handle_no_sound("Detection not found")

        if not os.path.exists(filepath):
            log.error(f"Detection file does not exist: {filepath}")
            return self._handle_no_sound("Sound file not available")

        log.info(f"Found detection file: {filepath}")
        return self._handle_sound(filepath)

    def _find_detection_filename(self) -> str | None:
        """Find a detection in the database based on the spec."""
        scientific_name = self.spec.get("scientific_name")
        confidence = self.spec.get("confidence")

        utc_dt = datetime.strptime(
            self.spec["timestamp"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        local_tz = utc_dt.astimezone(get_localzone())

        date = local_tz.strftime("%Y-%m-%d")
        time = local_tz.strftime("%H:%M:%S")

        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()

        sql = f"""SELECT Date, Com_Name, File_Name FROM detections
            WHERE Date = DATE('{date}')
            AND Time = TIME('{time}')
            AND Sci_Name = '{scientific_name}'
            AND Confidence >= {confidence}"""
        cur.execute(sql)
        detections = cur.fetchall()

        if len(detections) == 1:
            return self._construct_file_path(detections[0])
        return None

    def _handle_no_sound(self, status: str) -> None:
        """Handle cases where no detection sound is found."""
        url = f"/api/detections/{self.spec['id']}"
        response = self.client.put(url, data={"sound_reference": status})
        if response.status_code != 200:
            log.error(
                f"Failed to update detection: {response.status_code} {response.text}"
            )

    def _handle_sound(self, filepath: str) -> str:
        """Handle the case where a sound file is found."""
        with open(filepath, "rb") as f:
            files = {"sound": (os.path.basename(filepath), f, "audio/mpeg")}
            url = f"/api/detections/{self.spec['id']}/sound/"
            response = self.client.post(url, files=files)

        if response.status_code != 201:
            log.error(
                f"Failed to upload sound file: {response.status_code} {response.text}"
            )

    @staticmethod
    def _construct_file_path(detection: tuple[str]) -> str:
        """Construct the file path for the detection file."""
        date, com_name, file_name = detection
        com_name = com_name.replace(" ", "_").replace("'", "")
        return f"{HOME_DIR}/BirdSongs/Extracted/By_Date/{date}/{com_name}/{file_name}"
