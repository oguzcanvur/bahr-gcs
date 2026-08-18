"""BAHR-GCS — design system.

Tek kaynak (single source of truth): renk token'lari, tipografi olcegi,
spacing skalasi, kose yaricaplari, global QSS ve marka kimligi burada
tanimlanir. Arayuzdeki hicbir modul kendi icinde ham renk kodu veya marka
adi metni tasimamalidir — APP_NAME ve ilgili sabitler buradan okunur.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QImage,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


# ---------------------------------------------------------------------------
# 0. Marka kimligi — tek kaynak. Yeni bir ekran/pencere marka adi gostermek
# istediginde ham metin yazmak yerine buradaki sabitleri kullanir.
# ---------------------------------------------------------------------------

APP_NAME = "BAHR-GCS"
APP_ACRONYM_EXPANSION = "Bathymetric Autonomous Hydrographic Reconnaissance"
APP_NAME_FULL = f"{APP_NAME} — {APP_ACRONYM_EXPANSION} Ground Control Station"
APP_TAGLINE_SHORT = "HYDROGRAPHIC RECONNAISSANCE"          # üst çubuk, kısa
APP_TAGLINE_EN = APP_ACRONYM_EXPANSION
APP_TAGLINE_TR = "Otonom Batimetrik Hidrografik Keşif Yer Kontrol İstasyonu"
APP_DESCRIPTION_EN = (
    "Autonomous vehicle mission planning, navigation, telemetry, mapping and "
    "hydrographic data visualization platform."
)
APP_DESCRIPTION_TR = (
    "Otonom araç görev planlama, navigasyon, telemetri, haritalama ve "
    "hidrografik veri görselleştirme yer kontrol istasyonu."
)
APP_ORGANIZATION = "BAHR-GCS"


# ---------------------------------------------------------------------------
# 1. Renk token'lari  (semantic color tokens)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Palette:
    """Operasyonel koyu tema. Kontrast oranlari WCAG AA hedefiyle secildi.

    Renkler uygulama logosundan turetilmistir: lacivert #002048 (yuzeyler ve
    kenarliklar bu hue'da, ~213°) ve camgobegi #00A8F0 (aksan).
    """

    # Yuzeyler — 5 kademeli derinlik hiyerarsisi (logo laciverti hue'sunda)
    bg_root: str = "#050A13"        # uygulama zemini
    bg_canvas: str = "#080E1A"      # harita/canvas arkasi
    surface_1: str = "#0E1826"      # panel govdesi
    surface_2: str = "#131F30"      # kart
    surface_3: str = "#1A2839"      # yukseltilmis kart / hover
    surface_glass: str = "rgba(14, 24, 38, 0.82)"

    # Kenarliklar
    border_subtle: str = "#1B2839"
    border_default: str = "#26374C"
    border_strong: str = "#38506D"

    # Metin — 4 kademeli okunabilirlik hiyerarsisi
    text_primary: str = "#EFF4FA"
    text_secondary: str = "#A4B3C6"
    text_tertiary: str = "#68798F"
    text_disabled: str = "#455568"
    text_on_accent: str = "#03182E"  # logo laciverti — aksan uzerinde okunur

    # Aksan — logo camgobegi
    accent: str = "#00A8F0"
    accent_hover: str = "#3BBDF7"
    accent_press: str = "#0086C4"
    accent_soft: str = "rgba(0, 168, 240, 0.16)"

    # Bilgi tonu aksandan ayirt edilebilir olmali; aksan camgobegi oldugu icin
    # bu ton menekse-maviye kaydirildi.
    info: str = "#7AA2F7"
    info_soft: str = "rgba(122, 162, 247, 0.16)"

    # Durum renkleri
    success: str = "#34D399"
    success_soft: str = "rgba(52, 211, 153, 0.14)"
    warning: str = "#FBBF24"
    warning_soft: str = "rgba(251, 191, 36, 0.14)"
    danger: str = "#F87171"
    danger_soft: str = "rgba(248, 113, 113, 0.14)"
    neutral_soft: str = "rgba(164, 179, 198, 0.10)"

    # Veri gorsellestirme (derinlik skalasi — sig'dan derine).
    # Derin uc, aksan camgobegiyle karismamasi icin mavi-menekseye kaydirildi.
    depth_0: str = "#F87171"
    depth_1: str = "#FB923C"
    depth_2: str = "#FBBF24"
    depth_3: str = "#34D399"
    depth_4: str = "#5B8DEF"
    depth_5: str = "#7C5CFF"


COLORS = Palette()


# ---------------------------------------------------------------------------
# 2. Spacing / radius / tipografi olcekleri
# ---------------------------------------------------------------------------

class Space:
    """4 px tabanli spacing skalasi — tum bosluklar bu adimlardan secilir."""

    xxs = 2
    xs = 4
    sm = 8
    md = 12
    lg = 16
    xl = 24
    xxl = 32
    xxxl = 48


class Radius:
    sm = 6
    md = 10
    lg = 14
    xl = 20
    pill = 999


class Type:
    """Tipografi olcegi — 1.25 orani, 4 agirlik kademesi."""

    display = 26
    title = 19
    heading = 15
    body = 13
    label = 12
    caption = 11
    micro = 10

    tracking_wide = 1.2   # px cinsinden letter-spacing (kucuk basliklar icin)


def _first_available(candidates: list[str], fallback: str) -> str:
    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            return name
    return fallback


def ui_font_family() -> str:
    return _first_available(
        ["Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Noto Sans"],
        "Sans Serif",
    )


def mono_font_family() -> str:
    """Telemetri sayilari icin tabular/monospace aile."""
    return _first_available(
        ["JetBrains Mono", "Cascadia Mono", "Consolas", "SF Mono", "DejaVu Sans Mono"],
        "Monospace",
    )


def mono_font(size: int = Type.body, weight: QFont.Weight = QFont.Weight.DemiBold) -> QFont:
    font = QFont(mono_font_family(), size)
    font.setWeight(weight)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def ui_font(size: int = Type.body, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(ui_font_family(), size)
    font.setWeight(weight)
    return font


def qcolor(token: str, alpha: int | None = None) -> QColor:
    color = QColor(token)
    if alpha is not None:
        color.setAlpha(alpha)
    return color


# ---------------------------------------------------------------------------
# 3. Marka varliklari
# ---------------------------------------------------------------------------

def brand_badge(size: int) -> QPixmap:
    """Marka + acik plaka. Logonun laciverti koyu yuzeylerde ~1.1:1 kontrastta
    kayboldugu icin arayuzde her zaman bu varyant kullanilir."""
    pixmap = QPixmap(str(ASSETS_DIR / "app_icon.png"))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def app_icon() -> QIcon:
    """Pencere/gorev cubugu ikonu — acik plaka uzerindeki marka.

    Qt tek bir buyuk kaynaktan kucultunce 16-32 px'te detay dagiliyor; her
    kademeyi ayri ayri yumusak olceklendirip QIcon'a eklemek onu onluyor.
    """
    source = QPixmap(str(ASSETS_DIR / "app_icon.png"))
    icon = QIcon()
    if source.isNull():
        return icon
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(source.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
    return icon


# ---------------------------------------------------------------------------
# 4. Ikonlar
# ---------------------------------------------------------------------------
# Qt stil sayfalari ok isaretleri icin CSS ucgen hilesini desteklemez; bu
# yuzden chevron ikonlarini calisma aninda uretip QSS'e url() ile veriyoruz.

_ICON_DIR = Path(tempfile.gettempdir()) / "bahr_gcs_icons"


def _chevron_icon(direction: str, color: str, size: int = 12, weight: float = 1.6) -> str:
    _ICON_DIR.mkdir(parents=True, exist_ok=True)
    target = _ICON_DIR / f"chevron_{direction}_{color.lstrip('#')}_{size}.png"
    if not target.exists():
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), weight)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        inset = size * 0.26
        mid = size / 2.0
        if direction == "down":
            points = [QPointF(inset, mid - inset / 1.6), QPointF(mid, mid + inset / 1.2),
                      QPointF(size - inset, mid - inset / 1.6)]
        else:
            points = [QPointF(inset, mid + inset / 1.6), QPointF(mid, mid - inset / 1.2),
                      QPointF(size - inset, mid + inset / 1.6)]
        painter.drawPolyline(points)
        painter.end()
        image.save(str(target))
    return target.as_posix()


# ---------------------------------------------------------------------------
# 5. Global QSS
# ---------------------------------------------------------------------------

def build_stylesheet() -> str:
    c = COLORS
    chevron_down = _chevron_icon("down", c.text_tertiary)
    chevron_up = _chevron_icon("up", c.text_tertiary)
    chevron_down_hi = _chevron_icon("down", c.accent)
    chevron_up_hi = _chevron_icon("up", c.accent)
    return f"""
/* ---------- Temel ---------- */
* {{
    font-family: "{ui_font_family()}";
    font-size: {Type.body}px;
    color: {c.text_primary};
}}

QWidget#appRoot, QMainWindow {{
    background: {c.bg_root};
}}

/* Dialogs are not appRoot/QMainWindow, so without this they keep the Fusion
   default light background while `*` above paints their text near-white —
   which renders confirmation prompts invisible. */
QDialog, QMessageBox {{
    background: {c.surface_1};
}}
QMessageBox QLabel {{
    color: {c.text_primary};
    font-size: {Type.body}px;
}}
QMessageBox QPushButton {{
    min-width: 78px;
}}

QToolTip {{
    background: {c.surface_3};
    color: {c.text_primary};
    border: 1px solid {c.border_default};
    border-radius: {Radius.sm}px;
    padding: {Space.xs}px {Space.sm}px;
}}

/* ---------- Ust komuta cubugu ---------- */
QWidget#topBar {{
    background: {c.surface_1};
    border-bottom: 1px solid {c.border_subtle};
}}

QLabel#brandMark {{
    font-size: {Type.title}px;
    font-weight: 700;
    letter-spacing: {Type.tracking_wide}px;
    color: {c.text_primary};
}}

QLabel#brandSub {{
    font-size: {Type.micro}px;
    font-weight: 600;
    letter-spacing: {Type.tracking_wide}px;
    color: {c.text_tertiary};
}}

/* ---------- Paneller ---------- */
QWidget#sidePanel {{
    background: {c.surface_1};
    border-right: 1px solid {c.border_subtle};
}}

QWidget#sidePanelRight {{
    background: {c.surface_1};
    border-left: 1px solid {c.border_subtle};
}}

QWidget#statusStrip {{
    background: {c.surface_1};
    border-top: 1px solid {c.border_subtle};
}}

/* ---------- Kart ---------- */
QFrame#card {{
    background: {c.surface_2};
    border: 1px solid {c.border_subtle};
    border-radius: {Radius.lg}px;
}}

QFrame#cardFlat {{
    background: transparent;
    border: 1px solid {c.border_subtle};
    border-radius: {Radius.lg}px;
}}

QLabel#cardTitle {{
    font-size: {Type.caption}px;
    font-weight: 700;
    letter-spacing: {Type.tracking_wide}px;
    color: {c.text_tertiary};
}}

QLabel#cardHint {{
    font-size: {Type.caption}px;
    color: {c.text_tertiary};
}}

QLabel#sectionLabel {{
    font-size: {Type.micro}px;
    font-weight: 700;
    letter-spacing: {Type.tracking_wide}px;
    color: {c.text_tertiary};
    padding: {Space.xs}px 0px;
}}

QLabel#fieldLabel {{
    font-size: {Type.label}px;
    color: {c.text_secondary};
}}

QLabel#metricValue {{
    font-family: "{mono_font_family()}";
    font-size: {Type.heading}px;
    font-weight: 700;
    color: {c.text_primary};
}}

QLabel#metricValueLarge {{
    font-family: "{mono_font_family()}";
    font-size: {Type.display}px;
    font-weight: 700;
    color: {c.text_primary};
}}

QFrame#metricTileBare {{
    background: transparent;
    border: none;
}}

QLabel#metricCaption {{
    font-size: {Type.micro}px;
    font-weight: 600;
    letter-spacing: {Type.tracking_wide}px;
    color: {c.text_tertiary};
}}

QLabel#metricUnit {{
    font-size: {Type.caption}px;
    color: {c.text_tertiary};
}}

QFrame#divider {{
    background: {c.border_subtle};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QFrame#vDivider {{
    background: {c.border_subtle};
    max-width: 1px;
    min-width: 1px;
    border: none;
}}

/* ---------- Harita ustu cam panel ---------- */
QWidget#mapOverlayLayer {{
    background: transparent;
}}

QFrame#glassPanel {{
    background: {c.surface_glass};
    border: 1px solid rgba(56, 80, 109, 0.75);
    border-radius: {Radius.xl}px;
}}

QLabel#hudCaption {{
    font-size: {Type.micro}px;
    font-weight: 700;
    letter-spacing: {Type.tracking_wide}px;
    color: {c.text_tertiary};
}}

QLabel#hudValue {{
    font-family: "{mono_font_family()}";
    font-size: {Type.title}px;
    font-weight: 700;
    color: {c.text_primary};
}}

/* ---------- Butonlar ---------- */
QPushButton {{
    background: {c.surface_3};
    color: {c.text_primary};
    border: 1px solid {c.border_default};
    border-radius: {Radius.md}px;
    padding: {Space.sm}px {Space.md}px;
    font-size: {Type.label}px;
    font-weight: 600;
    min-height: 18px;
}}
QPushButton:hover  {{ background: #21334A; border-color: {c.border_strong}; }}
QPushButton:pressed{{ background: #16222F; }}
QPushButton:disabled {{
    background: {c.surface_2};
    color: {c.text_disabled};
    border-color: {c.border_subtle};
}}
/* Aktif durum — secili ucus modu, silahlanmis harita araci. Aksan rengi
   yalnizca birincil eylem ve aktif durum icin (bkz. DESIGN.md 1.2). */
QPushButton:checked {{
    background: {c.accent_soft};
    color: {c.accent};
    border-color: {c.accent};
}}
QPushButton:checked:hover {{ background: rgba(0, 168, 240, 0.26); }}

QPushButton[variant="primary"] {{
    background: {c.accent};
    color: {c.text_on_accent};
    border: 1px solid {c.accent};
    font-weight: 700;
}}
QPushButton[variant="primary"]:hover   {{ background: {c.accent_hover}; border-color: {c.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {c.accent_press}; }}
QPushButton[variant="primary"]:disabled {{
    background: {c.surface_2}; color: {c.text_disabled}; border-color: {c.border_subtle};
}}

QPushButton[variant="danger"] {{
    background: {c.danger_soft};
    color: {c.danger};
    border: 1px solid rgba(248, 113, 113, 0.42);
}}
QPushButton[variant="danger"]:hover {{ background: rgba(248, 113, 113, 0.22); }}

QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {c.text_secondary};
}}
QPushButton[variant="ghost"]:hover {{
    background: {c.neutral_soft};
    color: {c.text_primary};
}}

QPushButton[variant="quiet"] {{
    background: transparent;
    border: 1px solid {c.border_default};
    color: {c.text_secondary};
}}
QPushButton[variant="quiet"]:hover {{ color: {c.text_primary}; border-color: {c.border_strong}; }}

QPushButton[compact="true"] {{
    padding: {Space.sm}px {Space.xs}px;
    font-size: {Type.caption}px;
}}

QPushButton:focus {{
    border: 1px solid {c.accent};
    outline: none;
}}

/* ---------- Segmented control ---------- */
QWidget#segmented {{
    background: {c.surface_1};
    border: 1px solid {c.border_subtle};
    border-radius: {Radius.md}px;
}}
QPushButton[segment="true"] {{
    background: transparent;
    border: none;
    border-radius: {Radius.sm}px;
    color: {c.text_secondary};
    padding: {Space.xs}px {Space.md}px;
    font-weight: 600;
}}
QPushButton[segment="true"]:hover  {{ color: {c.text_primary}; }}
QPushButton[segment="true"]:checked {{
    background: {c.surface_3};
    color: {c.text_primary};
    border: 1px solid {c.border_default};
}}

/* ---------- Rail (sol ikon serit) ---------- */
QWidget#navRail {{
    background: {c.bg_root};
    border-right: 1px solid {c.border_subtle};
}}
QPushButton[rail="true"] {{
    background: transparent;
    border: none;
    border-radius: {Radius.md}px;
    color: {c.text_tertiary};
    font-size: {Type.micro}px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: {Space.sm}px {Space.xs}px;
}}
QPushButton[rail="true"]:hover {{ background: {c.neutral_soft}; color: {c.text_secondary}; }}
QPushButton[rail="true"]:checked {{
    background: {c.accent_soft};
    color: {c.accent};
}}

/* ---------- Girdiler ---------- */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
    background: {c.bg_canvas};
    border: 1px solid {c.border_default};
    border-radius: {Radius.md}px;
    padding: {Space.sm}px {Space.md}px;
    color: {c.text_primary};
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
    min-height: 18px;
}}
QLineEdit:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {c.border_strong}; }}
QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {c.accent};
    background: {c.surface_1};
}}
QLineEdit:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {c.text_disabled}; }}

QDoubleSpinBox, QSpinBox {{
    font-family: "{mono_font_family()}";
    font-weight: 600;
}}
QDoubleSpinBox::up-button, QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    background: transparent;
    border: none;
    border-left: 1px solid {c.border_subtle};
    width: 20px;
    margin: 4px 4px 0px 0px;
}}
QDoubleSpinBox::down-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    background: transparent;
    border: none;
    border-left: 1px solid {c.border_subtle};
    width: 20px;
    margin: 0px 4px 4px 0px;
}}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{
    background: {c.surface_3};
}}
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {{
    image: url({chevron_up});
    width: 12px; height: 12px;
}}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {{
    image: url({chevron_down});
    width: 12px; height: 12px;
}}
QDoubleSpinBox::up-arrow:hover, QSpinBox::up-arrow:hover {{
    image: url({chevron_up_hi});
}}
QDoubleSpinBox::down-arrow:hover, QSpinBox::down-arrow:hover {{
    image: url({chevron_down_hi});
}}

QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{
    image: url({chevron_down});
    width: 12px; height: 12px;
    margin-right: {Space.sm}px;
}}
QComboBox::down-arrow:hover {{ image: url({chevron_down_hi}); }}
QComboBox QAbstractItemView {{
    background: {c.surface_2};
    border: 1px solid {c.border_default};
    border-radius: {Radius.md}px;
    padding: {Space.xs}px;
    outline: none;
    selection-background-color: {c.accent_soft};
    selection-color: {c.text_primary};
}}

/* ---------- Checkbox / toggle ---------- */
QCheckBox {{
    spacing: {Space.sm}px;
    color: {c.text_secondary};
    font-size: {Type.label}px;
    padding: {Space.xxs}px 0px;
}}
QCheckBox:hover {{ color: {c.text_primary}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: {Radius.sm}px;
    border: 1px solid {c.border_strong};
    background: {c.bg_canvas};
}}
QCheckBox::indicator:hover {{ border-color: {c.accent}; }}
QCheckBox::indicator:checked {{
    background: {c.accent};
    border-color: {c.accent};
}}

QCheckBox[toggle="true"]::indicator {{
    width: 34px; height: 18px;
    border-radius: 9px;
    background: {c.surface_3};
    border: 1px solid {c.border_strong};
}}
QCheckBox[toggle="true"]::indicator:checked {{
    background: {c.accent};
    border-color: {c.accent};
}}

/* ---------- Slider ---------- */
QSlider::groove:horizontal {{
    height: 4px;
    background: {c.surface_3};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c.accent};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {c.text_primary};
    width: 14px; height: 14px;
    margin: -6px 0;
    border-radius: 7px;
    border: 2px solid {c.surface_1};
}}
QSlider::handle:horizontal:hover {{ background: {c.accent_hover}; }}

/* ---------- Progress ---------- */
QProgressBar {{
    background: {c.surface_3};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {c.accent};
    border-radius: 4px;
}}

/* ---------- Metin alani / log ---------- */
QTextEdit, QPlainTextEdit {{
    background: {c.bg_canvas};
    border: 1px solid {c.border_subtle};
    border-radius: {Radius.md}px;
    padding: {Space.sm}px;
    font-family: "{mono_font_family()}";
    font-size: {Type.caption}px;
    color: {c.text_secondary};
    selection-background-color: {c.accent_soft};
}}

/* ---------- Sekmeler ---------- */
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {c.text_tertiary};
    padding: {Space.sm}px {Space.md}px;
    margin-right: {Space.xs}px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: {Type.label}px;
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {c.text_secondary}; }}
QTabBar::tab:selected {{
    color: {c.text_primary};
    border-bottom: 2px solid {c.accent};
}}

/* ---------- Kaydirma ---------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {c.border_default};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {c.border_strong}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{
    background: {c.border_default};
    border-radius: 5px;
    min-width: 32px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

/* ---------- Splitter ---------- */
QSplitter::handle {{ background: {c.border_subtle}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QSplitter::handle:hover {{ background: {c.accent}; }}

/* ---------- Tablo ve liste ---------- */
QTableWidget, QTableView, QListWidget, QTreeView {{
    background: {c.bg_canvas};
    alternate-background-color: {c.surface_1};
    border: 1px solid {c.border_subtle};
    border-radius: {Radius.md}px;
    gridline-color: {c.border_subtle};
    outline: none;
    selection-background-color: {c.accent_soft};
    selection-color: {c.text_primary};
}}
QTableWidget::item, QTableView::item {{
    padding: {Space.xs}px {Space.sm}px;
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {c.accent_soft};
    color: {c.text_primary};
}}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {c.surface_2};
    color: {c.text_tertiary};
    border: none;
    border-bottom: 1px solid {c.border_default};
    border-right: 1px solid {c.border_subtle};
    padding: {Space.sm}px {Space.sm}px;
    font-size: {Type.micro}px;
    font-weight: 700;
    letter-spacing: {Type.tracking_wide}px;
}}
QHeaderView::section:last {{ border-right: none; }}
QTableCornerButton::section {{
    background: {c.surface_2};
    border: none;
}}

QListWidget {{
    padding: {Space.xs}px;
}}
QListWidget::item {{
    padding: {Space.sm}px {Space.md}px;
    border-radius: {Radius.sm}px;
    color: {c.text_secondary};
}}
QListWidget::item:hover {{
    background: {c.neutral_soft};
    color: {c.text_primary};
}}
QListWidget::item:selected {{
    background: {c.accent_soft};
    color: {c.accent};
    font-weight: 600;
}}

/* Kurulum penceresinin listesi panel gibi davranir, kutu gibi degil. */
QListWidget#sidePanel {{
    background: {c.surface_1};
    border: none;
    border-right: 1px solid {c.border_subtle};
    border-radius: 0px;
}}

/* ---------- Grup kutusu (geri uyumluluk) ---------- */
QGroupBox {{
    background: {c.surface_2};
    border: 1px solid {c.border_subtle};
    border-radius: {Radius.lg}px;
    margin-top: {Space.md}px;
    padding: {Space.lg}px {Space.md}px {Space.md}px {Space.md}px;
    font-size: {Type.caption}px;
    font-weight: 700;
    color: {c.text_tertiary};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {Space.md}px;
    padding: 0px {Space.xs}px;
    letter-spacing: {Type.tracking_wide}px;
}}
"""


def dark_palette() -> QPalette:
    """Fusion'in acik varsayilan paletini koyu temayla degistirir.

    Bu olmadan, QSS'te adi gecmeyen her widget (yeni bir ust duzey pencere,
    QTableWidget'in hucre zemini, bir QMessageBox) Fusion'in acik zeminini
    korur; global `*` kurali ise metni beyaza boyar ve sonuc beyaz uzerine
    beyaz olur. Bu hata bu projede uc kez ayri ayri ortaya cikti (once
    QMessageBox, sonra kurulum penceresi ve parametre tablosu), cunku her
    seferinde tek tek widget tipi icin duzeltilmisti. Paleti duzeltmek
    sorunu sinif olarak kapatir.
    """
    palette = QPalette()
    c = COLORS

    palette.setColor(QPalette.ColorRole.Window, QColor(c.surface_1))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(c.text_primary))
    palette.setColor(QPalette.ColorRole.Base, QColor(c.bg_canvas))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c.surface_2))
    palette.setColor(QPalette.ColorRole.Text, QColor(c.text_primary))
    palette.setColor(QPalette.ColorRole.Button, QColor(c.surface_3))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(c.text_primary))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(c.danger))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(c.surface_3))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(c.text_primary))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(c.text_tertiary))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(c.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(c.text_on_accent))
    palette.setColor(QPalette.ColorRole.Link, QColor(c.accent))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(c.info))

    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c.text_disabled))

    return palette


def apply_theme(app) -> None:
    """QApplication uzerine tasarim sistemini uygular."""
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    base = ui_font(Type.body)
    app.setFont(base)
    app.setStyleSheet(build_stylesheet())


def depth_color(depth_m: float | None) -> str:
    """Derinlik degerini surekli renk skalasina esler."""
    if depth_m is None:
        return COLORS.text_tertiary
    thresholds = [
        (1.0, COLORS.depth_0),
        (3.0, COLORS.depth_1),
        (6.0, COLORS.depth_2),
        (12.0, COLORS.depth_3),
        (25.0, COLORS.depth_4),
    ]
    for limit, color in thresholds:
        if depth_m < limit:
            return color
    return COLORS.depth_5
