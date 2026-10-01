"""NTRIP v1 istemcisi — RTK düzeltmelerini bir caster'dan çekip ham RTCM3
baytlarını sinyal olarak yayınlar.

Protokol detaylari (istek formati, ICY/HTTP 200 kontrolu, GGA periyodu)
`swegeo_gnss_app` masaustu uygulamasindaki (src/backend/ntrip-client.js)
TUSAGA-Aktif'e karsi calistigi zaten dogrulanmis mantiktan birebir alindi —
burada yeniden icat edilmedi.
"""
from __future__ import annotations

import base64
import re
import socket
import time

from PyQt6.QtCore import QThread, pyqtSignal

_GGA_INTERVAL_S = 1.0
_RECONNECT_DELAY_S = 5.0
_CONNECT_TIMEOUT_S = 10.0
_RECV_TIMEOUT_S = 1.0

_OK_RESPONSE = re.compile(rb"ICY 200 OK|HTTP/1\.\d 200", re.IGNORECASE)


class NtripClient(QThread):
    """Arka planda calisir; UI thread'ini soket G/C ile bloklamaz."""

    status_changed = pyqtSignal(dict)   # {"connected": bool, ...}
    rtcm_received = pyqtSignal(bytes)   # ham RTCM3 baytlari, parcalanmamis
    error = pyqtSignal(str)

    def __init__(self, host: str, port: int, mountpoint: str,
                 username: str, password: str, parent=None) -> None:
        super().__init__(parent)
        self.host = host
        self.port = port
        self.mountpoint = mountpoint
        self.username = username
        self.password = password
        self._running = False
        self._latest_gga: str | None = None
        self.bytes_received = 0

    def set_gga(self, sentence: str) -> None:
        """En son GGA cumlesini gunceller — VRS'nin yaklasik konumu bilmesi icin
        saniyede bir gonderilir. Ana thread'den cagrilabilir (sadece atama)."""
        self._latest_gga = sentence

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                self._connect_and_stream()
            except OSError as exc:
                self.error.emit(str(exc))
            if not self._running:
                break
            self.status_changed.emit({"connected": False, "host": self.host,
                                       "mountpoint": self.mountpoint})
            self._sleep_interruptible(_RECONNECT_DELAY_S)

    def _sleep_interruptible(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while self._running and time.monotonic() < deadline:
            time.sleep(0.1)

    def _connect_and_stream(self) -> None:
        with socket.create_connection((self.host, self.port), timeout=_CONNECT_TIMEOUT_S) as sock:
            self._handshake(sock)
            sock.settimeout(_RECV_TIMEOUT_S)
            last_gga = 0.0
            while self._running:
                now = time.monotonic()
                if self._latest_gga and now - last_gga >= _GGA_INTERVAL_S:
                    self._send_gga(sock)
                    last_gga = now
                try:
                    chunk = sock.recv(2048)
                except socket.timeout:
                    continue
                if not chunk:
                    raise OSError("Sunucu bağlantıyı kapattı")
                self._on_rtcm(chunk)

    def _handshake(self, sock: socket.socket) -> None:
        auth = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        request = (
            f"GET /{self.mountpoint} HTTP/1.0\r\n"
            f"Host: {self.host}\r\n"
            "Ntrip-Version: Ntrip/1.0\r\n"
            "User-Agent: BAHR-GCS-NTRIP/1.0\r\n"
            f"Authorization: Basic {auth}\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        sock.settimeout(_CONNECT_TIMEOUT_S)
        header_buf = b""
        while b"\r\n\r\n" not in header_buf:
            chunk = sock.recv(1024)
            if not chunk:
                raise OSError("Sunucu handshake sırasında bağlantıyı kapattı")
            header_buf += chunk
            if len(header_buf) > 8192:
                raise OSError("Sunucudan makul olmayan uzunlukta başlık geldi")
        header, _, remaining = header_buf.partition(b"\r\n\r\n")
        if not _OK_RESPONSE.search(header):
            first_line = header.split(b"\r\n", 1)[0].decode("ascii", "replace")
            raise OSError(f"NTRIP reddetti: {first_line}")
        self.status_changed.emit({"connected": True, "host": self.host,
                                   "mountpoint": self.mountpoint})
        if remaining:
            self._on_rtcm(remaining)

    def _send_gga(self, sock: socket.socket) -> None:
        gga = (self._latest_gga or "").strip()
        if not gga:
            return
        if not gga.endswith("\r\n"):
            gga += "\r\n"
        try:
            sock.sendall(gga.encode("ascii"))
        except OSError:
            pass  # bir sonraki dongude okuma zaten kopmayi yakalar

    def _on_rtcm(self, data: bytes) -> None:
        self.bytes_received += len(data)
        self.rtcm_received.emit(data)
