"""Garmin echoMAP + SweGeo RTD100 -> BAHR-GCS MAVLink koprusu (gecici demo araci).

Pi'ye USB-seri ile bagli iki cihazi okur:
  - echoMAP: NMEA 0183, derinlik + su sicakligi + kendi (zayif) GPS'i
  - RTD100: Bynav ASCII loglari (#BESTPOSA, #HEADINGA), konum + cift anten yon
Ikisini BAHR-GCS'nin anladigi TEK bir MAVLink akisina birlestirip UDP ile
PC'ye yollar. Konum/yon icin RTD100 varsa o tercih edilir (daha dogru, cift
antenli) — yoksa echoMAP'in kendi GPS'ine duser. Gercek Pi yazilimi
(ROADMAP.md bolum 4) gelince yerini alacak; bu yuzden kucuk ve tek dosya
tutuluyor.

Kullanim (Pi uzerinde), RTD100 olmadan (sadece echoMAP):
    python tools/echomap_bridge.py /dev/ttyUSB1 10.43.0.102

RTD100 ile birlikte:
    python tools/echomap_bridge.py /dev/ttyUSB1 10.43.0.102 --rtd100-port /dev/ttyUSB0

echoMAP 38400 baud (2026-09-14), RTD100 115200 baud (2026-09-15) —
tools/gnss_probe.py ile olculdu.
"""
from __future__ import annotations

import argparse
import re
import sys
import threading
import time

import serial
from pymavlink import mavutil

_SENTENCE = re.compile(rb"\$([A-Z]{2}[A-Z]{3}),([^*\r\n]*)\*([0-9A-Fa-f]{2})")
_BYNAV_LOG = re.compile(rb"#([A-Z0-9_]{3,24}),[^;$#*\r\n]*;([^$#*\r\n]*)\*([0-9A-Fa-f]{8})")

# GGA fix kalitesi -> MAVLink GPS_FIX_TYPE. Elimizdeki cihaz hicbirini RTK
# olarak isaretlemese bile ileride RTK'li bir GNSS baglanirsa dogru essin.
_FIX_TYPE = {0: 1, 1: 3, 2: 4, 4: 6, 5: 5, 6: 2}

# Bynav/NovAtel pos_type -> MAVLink GPS_FIX_TYPE. Tam liste degil, gordugumuz/
# beklenen degerler.
_BYNAV_FIX_TYPE = {
    "NONE": 1, "INSUFFICIENT_OBS": 1,
    "SINGLE": 3, "PSRDIFF": 4, "WAAS": 4, "SBAS": 4,
    "L1_FLOAT": 5, "NARROW_FLOAT": 5, "WIDE_FLOAT": 5,
    "L1_INT": 6, "NARROW_INT": 6, "WIDE_INT": 6,
}


def _crc32_novatel(data: bytes) -> int:
    """Bynav/NovAtel ASCII loglarinin CRC'si — yansitilmis 0xEDB88320,
    baslangic 0, son XOR yok (zlib.crc32'den farkli)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
    return crc


def _checksum_ok(body: bytes, checksum: bytes) -> bool:
    value = 0
    for byte in body:
        value ^= byte
    return value == int(checksum, 16)


def _coord(raw: str, hemisphere: str, degree_width: int) -> float | None:
    """'ddmm.mmmm'/'dddmm.mmmm' + yaricure -> ondalik derece, veri yoksa None."""
    if not raw or not hemisphere:
        return None
    try:
        degrees = int(raw[:degree_width])
        minutes = float(raw[degree_width:])
    except ValueError:
        return None
    value = degrees + minutes / 60.0
    return -value if hemisphere in ("S", "W") else value


def _float(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None


class State:
    def __init__(self) -> None:
        # echoMAP'ten: derinlik, sicaklik, kendi (zayif) konumu.
        self.lat: float | None = None
        self.lon: float | None = None
        self.alt_m = 0.0
        self.fix_quality = 0
        self.satellites = 0
        self.heading_deg = 0.0
        self.depth_m: float | None = None
        self.water_temp_c: float | None = None
        self.last_gga = 0.0
        # RTD100'den: daha dogru konum + cift anten yon. Doluysa echoMAP'in
        # kendi konum/yon degerlerinin onune gecer (bkz. _combined_*).
        self.rtd100_lat: float | None = None
        self.rtd100_lon: float | None = None
        self.rtd100_pos_type = "NONE"
        self.rtd100_satellites = 0
        self.rtd100_heading_deg: float | None = None
        self._lock = threading.Lock()

    def apply(self, kind: str, fields: list[str]) -> None:
        with self._lock:
            if kind == "GPGGA" and len(fields) >= 9:
                self.lat = _coord(fields[1], fields[2], 2)
                self.lon = _coord(fields[3], fields[4], 3)
                self.fix_quality = int(fields[5]) if fields[5].isdigit() else 0
                self.satellites = int(fields[6]) if fields[6].isdigit() else 0
                self.alt_m = _float(fields[8]) or 0.0
                self.last_gga = time.monotonic()
            elif kind == "HCHDM" and fields and fields[0]:
                heading = _float(fields[0])
                if heading is not None:
                    self.heading_deg = heading
            elif kind == "SDDPT" and fields and fields[0]:
                depth = _float(fields[0])
                if depth is not None:
                    self.depth_m = depth
            elif kind == "SDDBT" and len(fields) >= 3 and fields[2]:
                depth = _float(fields[2])  # 3. alan: metre cinsinden derinlik
                if depth is not None:
                    self.depth_m = depth
            elif kind == "SDMTW" and fields and fields[0]:
                temp = _float(fields[0])
                if temp is not None:
                    self.water_temp_c = temp

    def apply_rtd100(self, kind: str, fields: list[str]) -> None:
        """Bynav ASCII log alanlari (';' sonrasi, ',' ile ayrilmis).

        #BESTPOSA: sol_status,pos_type,lat,lon,height,... (NovAtel duzeni)
        #HEADINGA: sol_status,pos_type,length,heading,pitch,...
        Tam alan listesi Bynav'in kendi belgesinde (erisilemedi, bkz.
        ardupilot-param-metadata benzeri not); bu indeksler NovAtel'in
        belgelenmis duzenine ve gnss_probe.py ile yakalanan gercek
        orneklere dayaniyor.
        """
        with self._lock:
            if kind == "BESTPOSA" and len(fields) >= 4:
                self.rtd100_pos_type = fields[1]
                lat = _float(fields[2])
                lon = _float(fields[3])
                if fields[1] not in ("NONE", "INSUFFICIENT_OBS") and lat and lon:
                    self.rtd100_lat = lat
                    self.rtd100_lon = lon
                else:
                    self.rtd100_lat = self.rtd100_lon = None
                if len(fields) >= 14:
                    try:
                        self.rtd100_satellites = int(float(fields[13]))
                    except ValueError:
                        pass
            elif kind == "HEADINGA" and len(fields) >= 4:
                if fields[1] not in ("NONE",):
                    self.rtd100_heading_deg = _float(fields[3])
                else:
                    self.rtd100_heading_deg = None

    def combined(self) -> tuple[float | None, float | None, float, int, float]:
        """(lat, lon, heading, uydu, fix_type_kaynagi_icin_kalite) — RTD100
        varsa o, yoksa echoMAP'in kendi degerleri."""
        with self._lock:
            if self.rtd100_lat is not None:
                lat, lon = self.rtd100_lat, self.rtd100_lon
                satellites = self.rtd100_satellites
                fix_type = _BYNAV_FIX_TYPE.get(self.rtd100_pos_type, 3)
            else:
                lat, lon = self.lat, self.lon
                satellites = self.satellites
                fix_type = _FIX_TYPE.get(self.fix_quality, 3 if lat is not None else 1)
            heading = (
                self.rtd100_heading_deg if self.rtd100_heading_deg is not None
                else self.heading_deg
            )
            return lat, lon, heading, satellites, fix_type


def read_sentences(port: serial.Serial):
    buf = bytearray()
    while True:
        chunk = port.read(256)
        if not chunk:
            continue  # zaman asimi, veri gelmedi - okumaya devam
        buf += chunk
        while b"\n" in buf:
            line, _, buf[:] = buf.partition(b"\n")
            m = _SENTENCE.match(line.strip())
            if m and _checksum_ok(m.group(1) + b"," + m.group(2), m.group(3)):
                yield m.group(1).decode(), m.group(2).decode().split(",")


def read_bynav_logs(port: serial.Serial):
    """RTD100'un kendi ASCII loglari (#BESTPOSA, #HEADINGA, ...) — CRC32
    dogrulanir (bkz. gnss_probe.py'deki ayni algoritma)."""
    buf = bytearray()
    while True:
        chunk = port.read(256)
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            line, _, buf[:] = buf.partition(b"\n")
            line = line.strip()
            m = _BYNAV_LOG.match(line)
            if not m:
                continue
            body = line[1:m.end(2)]  # '#' ile '*' arasi (isim+header+';'+data)
            if _crc32_novatel(body) == int(m.group(3), 16):
                yield m.group(1).decode(), m.group(2).decode().split(",")


def _run_rtd100_reader(serial_port: str, baud: int, state: State) -> None:
    """Ayri thread'de calisir — echoMAP okuma dongusunu bloklamaz."""
    while True:
        try:
            with serial.Serial(serial_port, baud, timeout=0.2) as port:
                for kind, fields in read_bynav_logs(port):
                    state.apply_rtd100(kind, fields)
        except (serial.SerialException, OSError) as exc:
            print(f"RTD100 seri port hatasi: {exc} - 2 sn sonra tekrar denenecek", flush=True)
            time.sleep(2)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serial_port", help="orn. /dev/ttyUSB0")
    parser.add_argument("gcs_host", help="BAHR-GCS'nin calistigi PC'nin IP'si")
    parser.add_argument("--gcs-port", type=int, default=14550)
    parser.add_argument("--baud", type=int, default=38400)
    parser.add_argument("--rtd100-port", help="orn. /dev/ttyUSB0 — verilirse RTD100 de okunur")
    parser.add_argument("--rtd100-baud", type=int, default=115200)
    args = parser.parse_args(argv)

    link = mavutil.mavlink_connection(
        f"udpout:{args.gcs_host}:{args.gcs_port}",
        source_system=1, source_component=1,
    )
    m = mavutil.mavlink
    state = State()
    start = time.monotonic()
    last_send = 0.0

    print(f"Dinleniyor (echoMAP): {args.serial_port} @ {args.baud} baud")
    if args.rtd100_port:
        print(f"Dinleniyor (RTD100): {args.rtd100_port} @ {args.rtd100_baud} baud")
        threading.Thread(
            target=_run_rtd100_reader,
            args=(args.rtd100_port, args.rtd100_baud, state),
            daemon=True,
        ).start()
    print(f"Gonderiliyor: udpout:{args.gcs_host}:{args.gcs_port}")

    while True:
        try:
            with serial.Serial(args.serial_port, args.baud, timeout=0.2) as port:
                for kind, fields in read_sentences(port):
                    state.apply(kind, fields)
                    now = time.monotonic()
                    if now - last_send < 0.9:
                        continue
                    last_send = now
                    now_ms = int((now - start) * 1000)
                    src_lat, src_lon, heading, satellites, fix_type = state.combined()
                    have_fix = src_lat is not None and src_lon is not None
                    lat = int((src_lat or 0.0) * 1e7)
                    lon = int((src_lon or 0.0) * 1e7)

                    link.mav.heartbeat_send(
                        m.MAV_TYPE_SURFACE_BOAT, m.MAV_AUTOPILOT_ARDUPILOTMEGA,
                        m.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 0, m.MAV_STATE_ACTIVE,
                    )
                    link.mav.global_position_int_send(
                        now_ms, lat, lon, int(state.alt_m * 1000), 0,
                        0, 0, 0, int(heading * 100),
                    )
                    link.mav.gps_raw_int_send(
                        now_ms * 1000, fix_type, lat, lon,
                        int(state.alt_m * 1000), 65535, 65535, 65535,
                        int(heading * 100), satellites,
                    )
                    if state.depth_m is not None:
                        link.mav.distance_sensor_send(
                            now_ms, 20, 5000, int(state.depth_m * 100),
                            m.MAV_DISTANCE_SENSOR_ULTRASOUND, 1,
                            m.MAV_SENSOR_ROTATION_PITCH_270, 0,
                        )
                    if state.water_temp_c is not None:
                        link.mav.named_value_float_send(
                            now_ms, b"water_temp", state.water_temp_c,
                        )
                    depth_text = f"{state.depth_m:.2f} m" if state.depth_m is not None else "yok"
                    temp_text = f"{state.water_temp_c:.2f} C" if state.water_temp_c is not None else "yok"
                    fix_text = "VAR" if have_fix else "yok"
                    src_text = "RTD100" if state.rtd100_lat is not None else "echoMAP"
                    print(f"[{time.strftime('%H:%M:%S')}] fix={fix_text} ({src_text}) "
                          f"uydu={satellites} yon={heading:.0f} pos_type={state.rtd100_pos_type} "
                          f"derinlik={depth_text} sicaklik={temp_text}", flush=True)
        except (serial.SerialException, OSError) as exc:
            print(f"Seri port hatasi: {exc} - 2 sn sonra tekrar denenecek", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
