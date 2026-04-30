from dataclasses import dataclass, asdict
import json
import os
import sqlite3
import logging
from datetime import datetime
import time
from luistervink.dto import Detection
from tzlocal import get_localzone

from luistervink.client import LuistervinkClient
from utils.helpers import DB_PATH, HOME_DIR

log = logging.getLogger(__name__)

MAX_DETECTIONS_UPLOAD = 100


class BaseHandler:
    type: str

    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    def __init__(self, client: LuistervinkClient, spec: dict) -> None:
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

        utc_dt = datetime.fromisoformat(self.spec["timestamp"].replace("Z", "+00:00"))
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


@dataclass
class ReloadDetectionsResult:
    uploaded: int = 0
    failed: int = 0
    skipped: int = 0
    index: int = 0
    message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class ReloadDetectionsHandler(BaseHandler):
    type: str = "reload_detections"
    spec: dict
    result: ReloadDetectionsResult
    max_index: int
    task_id: str
    max_failures: int = 5

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        try:
            self.task_id = self.spec["id"]
            previous_result = json.loads(self.spec.get("results") or "{}")
            self.result = ReloadDetectionsResult(**previous_result)
            max_uploads = int(self.spec.get("max_batch_size", MAX_DETECTIONS_UPLOAD))
            self.max_index = self.result.index + max_uploads
        except Exception as e:
            self.result = ReloadDetectionsResult(message=str(e))
            self._post_results(self.STATUS_FAILED)
            raise e

    def handle(self) -> str:
        dt = datetime.fromisoformat(self.spec["date"].replace("Z", "+00:00"))
        date = dt.strftime("%Y-%m-%d")
        log.info(f"Reloading detections for date: {date}")

        detections = self._collect_detections(date)
        log.info(f"Collected {len(detections)} detections for date: {date}")

        self._upload_detections(detections)
        log.info(
            f"Processed detections, {len(detections) - self.result.index - 1} remaining"
        )

        status = (
            self.STATUS_COMPLETED
            if (self.result.index + 1) >= len(detections)
            else self.STATUS_IN_PROGRESS
        )
        self._post_results(status)

    def _collect_detections(self, date: str) -> list[Detection]:
        # Order of fields needs to correspond with the Detection model
        sql = f"""SELECT Date as date, Time as time, Sci_Name as scientific_name,
        Com_Name as common_name, Confidence as confidence, Lat as latitude, Lon as longitude
        FROM detections WHERE Date = '{date}' AND Confidence >= Cutoff ORDER BY Time ASC"""

        with sqlite3.connect(DB_PATH) as con:
            cur = con.cursor()
            cur.execute(sql)
            detections = cur.fetchall()
        return [Detection(*detection) for detection in detections]

    def _upload_detections(self, detections: list[Detection]) -> None:
        consecutive_failures = 0

        for detection in detections[self.result.index :]:
            if self.result.index >= self.max_index:
                break
            if consecutive_failures >= self.max_failures:
                self._post_results(self.STATUS_FAILED)
                return

            local_tz = get_localzone()  # reads system timezone

            timestamp = datetime.strptime(
                f"{detection.date}T{detection.time}", "%Y-%m-%dT%H:%M:%S"
            ).replace(tzinfo=local_tz)

            data = {
                "timestamp": timestamp.isoformat(),
                "commonName": detection.common_name,
                "scientificName": detection.scientific_name,
                "lat": detection.latitude,
                "lon": detection.longitude,
                "confidence": detection.confidence,
                "soundscapeId": 0,
                "soundscapeStartTime": 0,
                "soundscapeEndTime": 0,
            }

            try:
                response = self.client.post("/api/detections/", data=data)
                log.info(f"Luistervink POST Response Status - {response.status_code}")
                if response.status_code == 201:
                    self.result.uploaded += 1
                    consecutive_failures = 0
                elif (
                    response.status_code == 409
                ):  # conflict (detection existst already)
                    self.result.skipped += 1
                    consecutive_failures = 0
                else:
                    self.result.message = f"Unexpected response: {response.text}"
                    self.result.failed += 1
                    log.warning(self.result.message)
                    consecutive_failures += 1

            except BaseException as e:
                self.result.failed += 1
                self.result.message = f"Cannot POST detection: {e}"
                log.error(self.result.message)
                consecutive_failures += 1

            self.result.index += 1
            time.sleep(0.2)  # avoid overwhelming the server

    def _post_results(self, status: str) -> None:
        url = f"/api/tasks/{self.task_id}"
        data = {"status": status, "results": self.result.to_json()}
        response = self.client.put(url, data=data)
        if response.status_code != 200:
            log.error(f"Failed to update task: {response.status_code} {response.text}")
