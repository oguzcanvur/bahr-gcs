import os
import sys
import traceback

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from gcs.main_window import MainWindow
from gcs.theme import APP_NAME, APP_ORGANIZATION, app_icon, apply_theme


def _install_exception_guard() -> None:
    """Keep a slot-level bug from taking the whole station down.

    PyQt6 escalates an unhandled Python exception raised inside a slot to
    qFatal(), which aborts the process with no traceback — a formatting edge
    case in a status timer is enough to kill the app mid-mission. Logging it
    and carrying on is far better behaviour for a ground station.
    """

    def hook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        print("Unhandled exception in Qt callback:", file=sys.stderr)
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

    sys.excepthook = hook


def _claim_windows_taskbar_identity() -> None:
    """Without an explicit AppUserModelID, Windows groups the window under the
    pythonw.exe host and shows Python's icon on the taskbar instead of ours."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_NAME.replace("-", ".")
        )
    except Exception:
        pass


def main() -> int:
    _install_exception_guard()
    _claim_windows_taskbar_identity()

    # Default GIL switch interval (5ms) lets a busy MAVLink receive thread
    # starve the GUI thread when message rates get high. Switching more
    # often gives the UI thread far more chances to run between messages.
    sys.setswitchinterval(0.001)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setWindowIcon(app_icon())
    apply_theme(app)

    window = MainWindow()
    window.resize(1680, 980)
    window.setMinimumSize(1280, 760)
    window.show()
    return app.exec()
