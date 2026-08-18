"""Seri port kesfi.

Kullaniciya "COM kaci yazayim" dedirtmemek icin: portlari acikamalariyla
listele, otopilot gibi gorunen varsa onu one al.

Windows'ta bir Pixhawk ailesi kart genellikle birden fazla COM portu acar
(orn. Cube Orange: 'Cube Orange Mavlink' ve 'Cube Orange SLCAN'). Yalnizca
MAVLink konusani secmek gerekir; SLCAN portu CAN arayuzudur ve oradan
heartbeat gelmez.
"""
from __future__ import annotations

from dataclasses import dataclass

from serial.tools import list_ports


# Pixhawk ailesi kartlarin USB satici kimlikleri.
_AUTOPILOT_VIDS = {
    0x2DAE,  # Hex / ProfiCNC — Cube serisi
    0x1209,  # generic / ArduPilot bootloader
    0x26AC,  # 3DR Pixhawk
    0x3162,  # Holybro
    0x35A7,  # ModalAI
    0x0483,  # STM32 (bircok klon kart)
}

# Ismi bunlardan birini iceren port otopilot sayilir.
_AUTOPILOT_HINTS = ("mavlink", "px4", "pixhawk", "ardupilot", "cube", "fmu", "autopilot")

# Ismi bunlari iceren port, saticisi otopilot olsa bile MAVLink konusmaz.
_NOT_MAVLINK_HINTS = ("slcan", "can", "bootloader", "dfu")


@dataclass(frozen=True)
class SerialPortInfo:
    device: str                # "COM9"
    description: str           # "Cube Orange Mavlink (COM9)"
    is_autopilot: bool
    speaks_mavlink: bool       # SLCAN/bootloader portlari icin False

    @property
    def label(self) -> str:
        """Acilir listede gorunecek metin."""
        name = self.description
        # pyserial aciklamanin sonuna portu zaten ekliyor; iki kez yazmayalim.
        suffix = f" ({self.device})"
        if name.endswith(suffix):
            name = name[: -len(suffix)]
        if not name or name == "n/a":
            return self.device
        marker = "  ●" if (self.is_autopilot and self.speaks_mavlink) else ""
        return f"{self.device} — {name}{marker}"


def _classify(port) -> SerialPortInfo:
    haystack = f"{port.description or ''} {port.product or ''} {port.manufacturer or ''}".lower()
    by_name = any(hint in haystack for hint in _AUTOPILOT_HINTS)
    by_vid = port.vid in _AUTOPILOT_VIDS if port.vid is not None else False
    blocked = any(hint in haystack for hint in _NOT_MAVLINK_HINTS)
    return SerialPortInfo(
        device=port.device,
        description=port.description or port.device,
        is_autopilot=bool(by_name or by_vid),
        speaks_mavlink=not blocked,
    )


def available_ports() -> list[SerialPortInfo]:
    """Mevcut portlar; otopilot gibi gorunenler once."""
    ports = [_classify(p) for p in list_ports.comports()]
    ports.sort(
        key=lambda p: (
            not (p.is_autopilot and p.speaks_mavlink),
            not p.is_autopilot,
            p.device,
        )
    )
    return ports


def best_guess(ports: list[SerialPortInfo] | None = None) -> SerialPortInfo | None:
    """Otomatik secilecek port — MAVLink konusan bir otopilot varsa o."""
    if ports is None:
        ports = available_ports()
    for port in ports:
        if port.is_autopilot and port.speaks_mavlink:
            return port
    return None
