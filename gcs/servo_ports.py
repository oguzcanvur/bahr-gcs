"""Cikis kanali -> fiziksel port ve motor testi numarasi eslesmesi.

Mission Planner'in Motor Test / Servo Output sayfasinin gosterdigi seyin
kaynagi: SERVOn_FUNCTION parametresi hangi fiziksel pine (MAIN OUT / AUX OUT)
karsilik geliyor, ve DO_MOTOR_TEST'in "motor numarasi" o fonksiyona nasil
eslesiyor. Ikisi de tahmin degil, ArduPilot kaynagindan dogrulandi:

- SRV_Channel/SRV_Channel.h — fonksiyon numaralari (k_throttleLeft=73 vb.)
- AR_Motors/AP_MotorsUGV.cpp (motor_test_order enum, output_test_pct) —
  DO_MOTOR_TEST param1'in hangi fonksiyonu tetikledigi
- libraries/AP_HAL_ChibiOS/hwdef/CubeOrange/README.md — "ilk 8 cikis MAIN,
  kalan 6'si AUX1-AUX6" (Pixhawk/Cube ailesinin standart eslesmesi)
"""
from __future__ import annotations

FUNCTION_LABELS: dict[int, str] = {
    0: "Kullanılmıyor",
    4: "Aileron",
    19: "Elevator (yatay dümen)",
    21: "Rudder (dümen)",
    26: "Yer direksiyonu (steering)",
    33: "Motor 1 (genel)",
    34: "Motor 2 (genel)",
    35: "Motor 3 (genel)",
    36: "Motor 4 (genel)",
    70: "Gaz (tek motor)",
    73: "Sol motor gazı",
    74: "Sağ motor gazı",
    89: "Yelken (mainsail)",
    128: "Yelken kanatçığı",
    137: "Direk döndürme",
}

# fonksiyon numarasi -> DO_MOTOR_TEST param1 (AP_MotorsUGV::motor_test_order).
# AP_MotorsUGV::output_test_pct her motor_test_order icin IKI fonksiyonu
# birden kontrol eder (genel "motorN" ismi VEYA anlamli isim) — orn. order=3
# hem k_motor3(35) hem k_throttleLeft(73) atanmis kanali tetikler.
_MOTOR_TEST_ORDER: dict[int, int] = {
    33: 1, 70: 1,   # MOTOR_TEST_THROTTLE
    34: 2, 26: 2,   # MOTOR_TEST_STEERING
    35: 3, 73: 3,   # MOTOR_TEST_THROTTLE_LEFT
    36: 4, 74: 4,   # MOTOR_TEST_THROTTLE_RIGHT
    89: 5, 128: 5, 137: 5,  # MOTOR_TEST_MAINSAIL
}

MOTOR_TEST_LABELS: dict[int, str] = {
    1: "Gaz (Motor testi 1)",
    2: "Direksiyon (Motor testi 2)",
    3: "Sol motor (Motor testi 3)",
    4: "Sağ motor (Motor testi 4)",
    5: "Yelken (Motor testi 5)",
}


def function_label(function_id: int) -> str:
    return FUNCTION_LABELS.get(function_id, f"Fonksiyon {function_id}")


def motor_test_order(function_id: int) -> int | None:
    """Bu fonksiyonu test etmek icin DO_MOTOR_TEST'e verilecek param1."""
    return _MOTOR_TEST_ORDER.get(function_id)


def physical_port(servo_channel: int) -> str:
    """SERVOn -> Pixhawk/Cube ailesi fiziksel port etiketi.

    SERVO1-8 = MAIN OUT 1-8 (ayri bir IO isemcisi uzerinden), SERVO9-14 =
    AUX OUT 1-6 (ana isemciden dogrudan). Cube Orange dahil butun Pixhawk
    turevi kartlarda gecerli standart eslesme.
    """
    if 1 <= servo_channel <= 8:
        return f"MAIN OUT {servo_channel}"
    if 9 <= servo_channel <= 14:
        return f"AUX OUT {servo_channel - 8}"
    return f"SERVO{servo_channel}"
