import json
import logging
import subprocess
import threading

log = logging.getLogger(__name__)


def _read_from_gpspipe(timeout: float) -> tuple[float, float] | None:
    """Reads streaming JSON from gpspipe, returns on first valid TPV."""
    proc = subprocess.Popen(
        ['gpspipe', '-w'],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True
    )
    result = [None]

    def read():
        for line in proc.stdout:
            try:
                sentence = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if sentence.get('class') != 'TPV':
                continue
            if sentence.get('mode', 0) < 2:
                continue
            lat = sentence.get('lat')
            lon = sentence.get('lon')
            if lat is not None and lon is not None:
                result[0] = (round(float(lat), 6), round(float(lon), 6))
                break

    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(timeout=timeout)

    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    return result[0]


def resolve_coordinates(conf) -> tuple[float, float]:
    """Returns (lat, lon) for tagging a detection.
    When USE_GPS is enabled, queries gpspipe; falls back to the static
    LATITUDE/LONGITUDE from the configuration on any error or no fix.
    """
    static_lat = conf.getfloat('LATITUDE')
    static_lon = conf.getfloat('LONGITUDE')

    if conf.get('USE_GPS', 'false').lower() != 'true':
        return static_lat, static_lon

    try:
        timeout = conf.getfloat('GPS_TIMEOUT')
    except (ValueError, TypeError):
        timeout = 5.0

    try:
        coords = _read_from_gpspipe(timeout)
    except FileNotFoundError:
        log.warning('gpspipe not installed; falling back to static coordinates')
        return static_lat, static_lon
    except Exception as e:
        log.warning('gpspipe failed (%s); falling back to static coordinates', e)
        return static_lat, static_lon

    if coords is None:
        log.warning('gpspipe returned no fix; falling back to static coordinates')
        return static_lat, static_lon

    return coords
