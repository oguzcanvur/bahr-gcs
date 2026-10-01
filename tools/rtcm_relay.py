"""BAHR-GCS'nin RTK/NTRIP panelinden gelen duzeltmeyi (MAVLink GPS_RTCM_DATA)
alip GNSS'in seri portuna ham RTCM3 baytlari olarak yazan gecici koprubet.

echomap_bridge.py gibi gecici bir demo araci — Pi'nin asil navigasyon
yazilimi (ROADMAP.md bolum 4) gelince yerini alacak.

    python tools/rtcm_relay.py /dev/ttyUSB0 192.168.3.13

DIKKAT — su an echomap_bridge.py ile AYNI ANDA calistirmak guvenli degil:
BAHR-GCS'nin tek bagli soketi (udp:0.0.0.0:14550), MAVLink paketini en son
KIMDEN aldiysa cevabi (GPS_RTCM_DATA dahil) ona gonderir. Iki ayri Pi
sureci (bu ve echomap_bridge.py) aym porta gonderirse "en son kim
konustuysa" cevabi o alir — bu yuzden bu betik kendi heartbeat'ini duzenli
atarak "son gonderen" olmaya calisir, ama garantisi yok. Nucleo'nun gercek
Pi yazilimi gelince duzgun MAVLink bilesen adresleme (target_component)
ile cozulecek.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import serial
from pymavlink import mavutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gcs.rtcm import RtcmReassembler  # noqa: E402

_HEARTBEAT_INTERVAL_S = 1.0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serial_port", help="orn. /dev/ttyUSB0 (GNSS'in RX hattina yazilir)")
    parser.add_argument("gcs_host", help="BAHR-GCS'nin calistigi PC'nin IP'si")
    parser.add_argument("--gcs-port", type=int, default=14550)
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args(argv)

    link = mavutil.mavlink_connection(
        f"udpout:{args.gcs_host}:{args.gcs_port}",
        source_system=1, source_component=1,
    )
    m = mavutil.mavlink
    reassembler = RtcmReassembler()
    last_heartbeat = 0.0
    total_bytes = 0
    total_messages = 0

    print(f"GCS'ye gonderiliyor: udpout:{args.gcs_host}:{args.gcs_port}")
    print(f"GNSS seri portu: {args.serial_port} @ {args.baud} baud")

    while True:
        try:
            with serial.Serial(args.serial_port, args.baud, timeout=0.1) as port:
                while True:
                    now = time.monotonic()
                    if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
                        # fake_vehicle.py / echomap_bridge.py ile ayni sekil —
                        # BAHR-GCS'nin "otopilot degil" diye atlamamasi icin.
                        link.mav.heartbeat_send(
                            m.MAV_TYPE_SURFACE_BOAT, m.MAV_AUTOPILOT_ARDUPILOTMEGA,
                            m.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 0, m.MAV_STATE_ACTIVE,
                        )
                        last_heartbeat = now
                    msg = link.recv_match(type="GPS_RTCM_DATA", blocking=True, timeout=0.2)
                    if msg is None:
                        continue
                    payload = reassembler.add(msg.flags, msg.len, bytes(msg.data))
                    if payload is None:
                        continue
                    port.write(payload)
                    total_bytes += len(payload)
                    total_messages += 1
                    print(f"[{time.strftime('%H:%M:%S')}] {len(payload):3d} bayt RTCM -> GNSS "
                          f"(toplam {total_messages} mesaj, {total_bytes} bayt)", flush=True)
        except (serial.SerialException, OSError) as exc:
            print(f"Seri port hatasi: {exc} - 2 sn sonra tekrar denenecek", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
