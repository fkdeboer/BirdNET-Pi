import json
import logging
import subprocess

log = logging.getLogger(__name__)


def _read_from_gpspipe(timeout: float) -> tuple[float, float] | None:
    """Reads JSON sentences from gpspipe and returns (lat, lon) from the first TPV with a 2D/3D fix."""
    result = subprocess.run(
        ['gpspipe', '-w', '-n', '10'],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            sentence = json.loads(line)
        except json.JSONDecodeError:
            continue
        if sentence.get('class') != 'TPV':
            continue
        if sentence.get('mode', 0) < 2:
            continue
        lat = sentence.get('lat')
        lon = sentence.get('lon')
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    return None


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
        timeout = 3.0

    try:
        coords = _read_from_gpspipe(timeout)
    except FileNotFoundError:
        log.warning('gpspipe not installed; falling back to static coordinates')
        return static_lat, static_lon
    except subprocess.TimeoutExpired:
        log.warning('gpspipe timed out after %ss; falling back to static coordinates', timeout)
        return static_lat, static_lon
    except BaseException as e:
        log.warning('gpspipe failed (%s); falling back to static coordinates', e)
        return static_lat, static_lon

    if coords is None:
        log.warning('gpspipe returned no fix; falling back to static coordinates')
        return static_lat, static_lon

    return coords
