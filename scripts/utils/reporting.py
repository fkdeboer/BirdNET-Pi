import glob
import gzip
import json
import logging
import os
import sqlite3
import subprocess
from time import sleep

import requests

from .helpers import get_settings, ParseFileName, Detection, DB_PATH
from .notifications import sendAppriseNotifications

log = logging.getLogger(__name__)


def get_safe_title(title):
    result = subprocess.run(['iconv', '-f', 'utf8', '-t', 'ascii//TRANSLIT'],
                            check=True, input=title.encode('utf-8'), capture_output=True)
    ret = result.stdout.decode('utf-8')
    return ret


def extract(in_file, out_file, start, stop):
    result = subprocess.run(['sox', '-V1', f'{in_file}', f'{out_file}', 'trim', f'={start}', f'={stop}'],
                            check=True, capture_output=True)
    ret = result.stdout.decode('utf-8')
    err = result.stderr.decode('utf-8')
    if err:
        raise RuntimeError(f'{ret}:\n {err}')
    return ret


def extract_safe(in_file, out_file, start, stop):
    conf = get_settings()
    # This section sets the SPACER that will be used to pad the audio clip with
    # context. If EXTRACTION_LENGTH is 10, for instance, 3 seconds are removed
    # from that value and divided by 2, so that the 3 seconds of the call are
    # within 3.5 seconds of audio context before and after.
    try:
        ex_len = conf.getint('EXTRACTION_LENGTH')
    except ValueError:
        ex_len = 6
    spacer = (ex_len - 3) / 2
    safe_start = max(0, start - spacer)
    safe_stop = min(conf.getint('RECORDING_LENGTH'), stop + spacer)

    extract(in_file, out_file, safe_start, safe_stop)


def spectrogram(in_file, title, comment, raw=False):
    args = ['sox', '-V1', f'{in_file}', '-n', 'remix', '1', 'rate', '24k', 'spectrogram',
            '-t', f'{get_safe_title(title)}', '-c', f'{comment}', '-o', f'{in_file}.png']
    args += ['-r'] if raw else []
    result = subprocess.run(args, check=True, capture_output=True)
    ret = result.stdout.decode('utf-8')
    err = result.stderr.decode('utf-8')
    if err:
        raise RuntimeError(f'{ret}:\n {err}')
    return ret


def extract_detection(file: ParseFileName, detection: Detection):
    conf = get_settings()
    new_file_name = f'{detection.common_name_safe}-{detection.confidence_pct}-{detection.date}-birdnet-{detection.time}.{conf["AUDIOFMT"]}'
    new_dir = os.path.join(conf['EXTRACTED'], 'By_Date', f'{detection.date}', f'{detection.common_name_safe}')
    new_file = os.path.join(new_dir, new_file_name)
    if os.path.isfile(new_file):
        log.warning('Extraction exists. Moving on: %s', new_file)
    else:
        os.makedirs(new_dir, exist_ok=True)
        extract_safe(file.file_name, new_file, detection.start, detection.stop)
        spectrogram(new_file, detection.common_name, new_file.replace(os.path.expanduser('~/'), ''))
    return new_file


def write_to_db(file: ParseFileName, detection: Detection):
    conf = get_settings()
    # Connect to SQLite Database
    for attempt_number in range(3):
        try:
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            cur.execute("INSERT INTO detections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (detection.date, detection.time, detection.scientific_name, detection.common_name, detection.confidence,
                         conf['LATITUDE'], conf['LONGITUDE'], conf['CONFIDENCE'], str(detection.week), conf['SENSITIVITY'],
                         conf['OVERLAP'], os.path.basename(detection.file_name_extr)))
            # (Date, Time, Sci_Name, Com_Name, str(score),
            # Lat, Lon, Cutoff, Week, Sens,
            # Overlap, File_Name))

            con.commit()
            con.close()
            break
        except BaseException as e:
            log.warning("Database busy: %s", e)
            sleep(2)


def summary(file: ParseFileName, detection: Detection):
    # Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap
    # 2023-03-03;12:48:01;Phleocryptes melanops;Wren-like Rushbird;0.76950216;-1;-1;0.7;9;1.25;0.0
    conf = get_settings()
    s = (f'{detection.date};{detection.time};{detection.scientific_name};{detection.common_name};'
         f'{detection.confidence};'
         f'{conf["LATITUDE"]};{conf["LONGITUDE"]};{conf["CONFIDENCE"]};{detection.week};{conf["SENSITIVITY"]};'
         f'{conf["OVERLAP"]}')
    return s


def write_to_file(file: ParseFileName, detection: Detection):
    with open(os.path.expanduser('~/BirdNET-Pi/BirdDB.txt'), 'a') as rfile:
        rfile.write(f'{summary(file, detection)}\n')


def update_json_file(file: ParseFileName, detections: [Detection]):
    if file.RTSP_id is None:
        mask = f'{os.path.dirname(file.file_name)}/*.json'
    else:
        mask = f'{os.path.dirname(file.file_name)}/*{file.RTSP_id}*.json'
    for f in glob.glob(mask):
        log.debug(f'deleting {f}')
        os.remove(f)
    write_to_json_file(file, detections)


def write_to_json_file(file: ParseFileName, detections: [Detection]):
    conf = get_settings()
    json_file = f'{file.file_name}.json'
    log.debug(f'WRITING RESULTS TO {json_file}')
    dets = {'file_name': os.path.basename(json_file), 'timestamp': file.iso8601, 'delay': conf['RECORDING_LENGTH'],
            'detections': [{"start": det.start, "common_name": det.common_name, "confidence": det.confidence} for det in
                           detections]}
    with open(json_file, 'w') as rfile:
        rfile.write(json.dumps(dets))
    log.debug(f'DONE! WROTE {len(detections)} RESULTS.')


def apprise(file: ParseFileName, detections: [Detection]):
    species_apprised_this_run = []
    conf = get_settings()

    for detection in detections:
        # Apprise of detection if not already alerted this run.
        if detection.species not in species_apprised_this_run:
            try:
                sendAppriseNotifications(detection.species, str(detection.confidence), str(detection.confidence_pct),
                                         os.path.basename(detection.file_name_extr), detection.date, detection.time, str(detection.week),
                                         conf['LATITUDE'], conf['LONGITUDE'], conf['CONFIDENCE'], conf['SENSITIVITY'],
                                         conf['OVERLAP'], dict(conf), DB_PATH)
            except BaseException as e:
                log.exception('Error during Apprise:', exc_info=e)

            species_apprised_this_run.append(detection.species)


def bird_weather(file: ParseFileName, detections: [Detection]):
    conf = get_settings()
    if conf['BIRDWEATHER_ID'] == "":
        return
    if detections:
        # POST soundscape to server
        # Always skip soundscape upload
        should_skip_soundscape_upload = True
                                                                                           
        if should_skip_soundscape_upload:
            # Skip soundscape upload                                                        
            soundscape_uploaded = False
            soundscape_id = 0
        else:                                                                   
            # POST soundscape to server
            # (This code block will be skipped)
            pass
            
        for detection in detections:
            # POST detection to server
            detection_url = f'https://app.birdweather.com/api/v1/stations/{conf["BIRDWEATHER_ID"]}/detections'

            data = {'timestamp': detection.iso8601, 'lat': conf['LATITUDE'], 'lon': conf['LONGITUDE'],
                    'soundscapeId': soundscape_id,
                    'soundscapeStartTime': detection.start, 'soundscapeEndTime': detection.stop,
                    'commonName': detection.common_name, 'scientificName': detection.scientific_name,
                    'algorithm': '2p4' if conf['MODEL'] == 'BirdNET_GLOBAL_6K_V2.4_Model_FP16' else 'alpha',
                    'confidence': detection.confidence}

            log.debug(data)
            try:
                response = requests.post(detection_url, json=data, timeout=20)
                log.info("Detection POST Response Status - %d", response.status_code)
            except BaseException as e:
                log.error("Cannot POST detection: %s", e)


def thingsboard(file: ParseFileName, detections: [Detection]):
    """Posts detections to a ThingsBoard server"""
    conf = get_settings()
    if not conf["THINGSBOARD_ADDRESS"] == "":
        log.warning(
            "ThingsBoard address missing, please add THINGSBOARD_ADDRESS to the configuration"
        )
        return

    if not conf["THIGSBOARD_DEVICE_TOKEN"] == "":
        log.warning(
            "No device token configures, please add THIGSBOARD_DEVICE_TOKEN to the configuration"
        )
        return

    if detections:
        # Uploading soundscape files is not supported yet
        soundscape_id = 0

        detection_url = f"{conf['THINGSBOARD_ADDRESS']}/api/v1/{conf['THIGSBOARD_DEVICE_TOKEN']}/telemetry"

        for detection in detections:
            data = {
                "ts": detection.datetime.timestamp() * 1000,  # unix timestamp in ms
                "values": {
                    "commonName": detection.common_name,
                    "scientificName": detection.scientific_name,
                    "lat": conf["LATITUDE"],
                    "lon": conf["LONGITUDE"],
                    "confidence": detection.confidence,
                    "soundscapeId": soundscape_id,
                    "soundscapeStartTime": detection.start,
                    "soundscapeEndTime": detection.stop,
                    "algorithm": (
                        "2p4"
                        if conf["MODEL"] == "BirdNET_GLOBAL_6K_V2.4_Model_FP16"
                        else "alpha"
                    ),
                },
            }

            log.debug(data)
            try:
                response = requests.post(detection_url, json=data, timeout=20)
                log.info("Detection POST Response Status - %d", response.status_code)
            except BaseException as e:
                log.error("Cannot POST detection: %s", e)


def heartbeat():
    conf = get_settings()
    if conf['HEARTBEAT_URL']:
        try:
            result = requests.get(url=conf['HEARTBEAT_URL'], timeout=10)
            log.info('Heartbeat: %s', result.text)
        except BaseException as e:
            log.error('Error during heartbeat: %s', e)
