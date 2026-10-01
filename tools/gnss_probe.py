"""GNSS alicisinin seri porttan gercekte ne gonderdigini olcer.

SweGeo RTD100 gibi kartlarin cikis protokolu, varsayilan baud hizi ve yon
(heading) mesaji belgelerde yazmiyor; tahmin etmek yerine cihazi dinleriz.

    python tools/gnss_probe.py                  # butun seri portlari dener
    python tools/gnss_probe.py COM7             # tek port, butun baud hizlari
    python tools/gnss_probe.py /dev/serial0     # Raspberry Pi UART'i
    python tools/gnss_probe.py COM7 --baud 115200 --send "LOG COM1 GPHDT ONTIME 1"

Her baud hizinda birkac saniye dinler; checksum'i dogru NMEA cumlelerini,
'#AD,...;...*CRC' bicimli ASCII loglari ve CRC'si dogru RTCM3 cercevelerini
sayar. En cok gecerli veri gelen hizi raporlar, ham kayitlari dosyaya yazar.
Tek bagimlilik pyserial; ayni dosya Pi uzerinde de calisir.
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import serial
from serial.tools import list_ports

# Yuksek hassasiyetli alicilarda yaygin olanlar once.
BAUDS = (115200, 460800, 921600, 230400, 38400, 9600, 57600)

# Bu kadar gecerli mesaj gelen hiz dogru kabul edilir, digerleri denenmez.
ENOUGH = 5

_NMEA = re.compile(rb"\$([A-Z0-9]{2,12}),([^$#*\r\n]*)\*([0-9A-Fa-f]{2})")
_ASCII_LOG = re.compile(rb"#([A-Z0-9_]{3,24}),([^;$#*\r\n]*);([^$#*\r\n]*)\*([0-9A-Fa-f]{8})")

# NMEA'da yon tasiyan cumle tipleri (talker'dan sonraki kisim).
_HEADING_NMEA = ("HDT", "THS", "TRA")

_GGA_QUALITY = {
    "0": "fix yok", "1": "tek nokta", "2": "DGPS/SBAS", "4": "RTK fixed",
    "5": "RTK float", "6": "tahmini (DR)",
}


def _nmea_checksum(body: bytes) -> int:
    value = 0
    for byte in body:
        value ^= byte
    return value


def _crc32_novatel(data: bytes) -> int:
    # NovAtel tarzi ASCII loglarin CRC'si: yansitilmis 0xEDB88320, baslangic 0,
    # son XOR yok (zlib.crc32'den farkli). Bynav ayni algoritmayi kullaniyor
    # olabilir; kullanmiyorsa log yine sayilir, sadece "dogrulanan" 0 kalir.
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
    return crc


def _crc24q(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xFFFFFF


@dataclass
class Capture:
    port: str
    baud: int
    seconds: float
    data: bytes
    counts: Counter = field(default_factory=Counter)
    samples: dict[str, str] = field(default_factory=dict)
    crc_ok: Counter = field(default_factory=Counter)      # ASCII loglarda dogrulanan
    last: dict[str, list[str]] = field(default_factory=dict)  # tip -> son alanlar
    covered: int = 0                                      # taninan cercevelerdeki bayt

    @property
    def valid(self) -> int:
        return sum(self.counts.values())


def _record(cap: Capture, name: str, raw: bytes, fields: list[str]) -> None:
    cap.counts[name] += 1
    cap.samples.setdefault(name, raw.decode("ascii", "replace")[:110])
    cap.last[name] = fields


def analyze(cap: Capture) -> Capture:
    data = cap.data
    spans: list[tuple[int, int]] = []
    for m in _NMEA.finditer(data):
        address, fields, checksum = m.group(1), m.group(2), m.group(3)
        if _nmea_checksum(address + b"," + fields) != int(checksum, 16):
            continue
        _record(cap, address.decode(), m.group(0), fields.decode("ascii", "replace").split(","))
        spans.append(m.span())
    for m in _ASCII_LOG.finditer(data):
        name = "#" + m.group(1).decode()
        body = data[m.start() + 1 : m.end() - 9]  # '#' ile '*' arasi
        if _crc32_novatel(body) == int(m.group(4), 16):
            cap.crc_ok[name] += 1
        _record(cap, name, m.group(0), m.group(3).decode("ascii", "replace").split(","))
        spans.append(m.span())
    index = 0
    while True:
        index = data.find(b"\xd3", index)
        if index < 0 or index + 6 > len(data):
            break
        if data[index + 1] & 0xFC == 0:
            length = ((data[index + 1] & 0x03) << 8) | data[index + 2]
            end = index + 3 + length + 3
            if (length >= 2 and end <= len(data)
                    and _crc24q(data[index:end - 3]) == int.from_bytes(data[end - 3:end], "big")):
                msg_type = (data[index + 3] << 4) | (data[index + 4] >> 4)
                cap.counts[f"RTCM3 {msg_type}"] += 1
                spans.append((index, end))
                index = end
                continue
        index += 1
    cap.covered = sum(end - start for start, end in spans)
    return cap


def capture(port: str, baud: int, seconds: float, send: str | None = None) -> Capture:
    with serial.Serial(port, baud, timeout=0.1) as link:
        link.reset_input_buffer()
        if send:
            link.write(send.encode("ascii") + b"\r\n")
        data = bytearray()
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            data += link.read(4096)
    return analyze(Capture(port, baud, seconds, bytes(data)))


def heading_names(cap: Capture) -> list[str]:
    return [
        name for name in cap.counts
        if (name.startswith("#") and "HEADING" in name)
        or (not name.startswith(("#", "RTCM")) and name[-3:] in _HEADING_NMEA)
    ]


def print_report(cap: Capture, description: str) -> None:
    print(f"\n=== {cap.port} @ {cap.baud} baud — {description}")
    print(f"    {len(cap.data)} bayt / {cap.seconds:.1f} sn "
          f"({len(cap.data) / cap.seconds:.0f} B/sn), "
          f"tanınan kısım: %{100 * cap.covered / max(len(cap.data), 1):.0f}")
    if not cap.counts:
        print("    Tanınan mesaj yok (yanlış hız ya da bilinmeyen ikili format).")
        return
    for name, count in sorted(cap.counts.items()):
        extra = f"  (CRC doğrulanan {cap.crc_ok[name]}/{count})" if name.startswith("#") else ""
        print(f"    {name:12s} {count:4d} adet  {count / cap.seconds:5.1f} Hz{extra}")
    for sample in cap.samples.values():
        print(f"      örnek: {sample}")
    gga = next((f for n, f in cap.last.items() if n.endswith("GGA") and len(f) > 6), None)
    if gga:
        print(f"    Konum çözümü: {_GGA_QUALITY.get(gga[5], gga[5] or '?')}, uydu: {gga[6] or '?'}")
    names = heading_names(cap)
    if not names:
        print("    Yön (heading) mesajı: YOK — alıcıya yön çıkışı açtırmak gerekecek.")
    for name in names:
        fields = cap.last.get(name, [])
        if name[-3:] in ("HDT", "THS") and fields:
            value = fields[0] or "boş (henüz yön çözümü yok)"
            print(f"    Yön (heading) mesajı: VAR — {name}, son değer: {value}")
        else:
            print(f"    Yön (heading) mesajı: VAR — {name} (alanlar için örneğe bak)")


def _save(cap: Capture, out_dir: Path) -> None:
    safe = cap.port.replace("/", "_").strip("_")
    (out_dir / f"{safe}_{cap.baud}.bin").write_bytes(cap.data)


def candidate_ports(requested: str | None) -> list[tuple[str, str]]:
    if requested:
        return [(requested, "elle seçildi")]
    ports = []
    for p in list_ports.comports():
        text = f"{p.description} {p.hwid}".lower()
        if "bluetooth" in text or "bthenum" in text:
            continue  # Windows'ta BT portlarini acmak saniyelerce takiliyor
        ids = f"{p.vid:04X}:{p.pid:04X}" if p.vid is not None else "USB değil"
        ports.append((p.device, f"{p.description} [{ids}]"))
    return ports


def probe_port(port: str, bauds, seconds: float, send: str | None,
               out_dir: Path) -> Capture | None:
    best: Capture | None = None
    for baud in bauds:
        try:
            cap = capture(port, baud, seconds, send)
        except (serial.SerialException, OSError) as exc:
            print(f"  {port}: açılamadı — {exc}")
            return None
        print(f"  {port} @ {baud}: {len(cap.data)} bayt, {cap.valid} geçerli mesaj")
        _save(cap, out_dir)
        if best is None or cap.valid > best.valid:
            best = cap
        if cap.valid >= ENOUGH:
            break
    return best


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="GNSS alıcısının seri porttan ne gönderdiğini ölçer.")
    parser.add_argument("port", nargs="?", help="COM7, /dev/serial0 ... (boşsa hepsi denenir)")
    parser.add_argument("--baud", type=int, help="yalnızca bu hızı dene")
    parser.add_argument("--seconds", type=float, default=2.5, help="her hızda dinleme süresi")
    parser.add_argument("--send", help="dinlemeden önce gönderilecek komut (yalnızca --baud ile)")
    parser.add_argument("--out", type=Path,
                        default=Path(tempfile.gettempdir()) / "bahr_gnss_capture",
                        help="ham kayıtların yazılacağı klasör")
    args = parser.parse_args(argv)
    if args.send and not args.baud:
        parser.error("--send yanlış hızda çöp gönderir; --baud ile birlikte kullan")

    ports = candidate_ports(args.port)
    if not ports:
        print("Hiç seri port yok. GNSS'i USB-C ile taktın mı?")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    bauds = (args.baud,) if args.baud else BAUDS
    found = False
    for port, description in ports:
        print(f"{port} — {description}")
        best = probe_port(port, bauds, args.seconds, args.send, args.out)
        if best is not None:
            print_report(best, description)
            found = found or best.valid > 0
    print(f"\nHam kayıtlar: {args.out}")
    return 0 if found else 2


if __name__ == "__main__":
    sys.exit(main())
