"""Parametre sozlugu — Turkce aciklamalar, gruplar ve deger tablolari.

Kurulum ekrani iki modda calisir:

* **Gruplanmis gorunum** — burada tanimli, tekne icin anlamli parametreler,
  ne ise yaradiklarini anlatan Turkce aciklamalariyla.
* **Arama** — araçtan inen *tum* parametreler. Burada tanimi olmayan bir
  parametre de aranip degistirilebilir; sadece aciklamasi bos gorunur.

Yani bu dosya bir *beyaz liste* degil, bir *sozluk*. Eksik olmasi bir
parametreyi erisilmez yapmaz.

Deger tablolari (``choices``) ArduPilot'un resmi Rover parametre metadata'si
(https://autotest.ardupilot.org/Parameters/Rover/apm.pdef.json — Mission
Planner ve QGroundControl'un kullandigi dosya) ile birebir karsilastirilarak
dogrulanmistir. Ezberden yazilan ilk surumde yon kaynagi, sonar tipi ve EKF
failsafe gibi guvenlik acisindan kritik listelerde yanlis etiketler vardi;
yeni bir secenek eklerken ayni kaynaga bakin.

ArduPilot bazi parametreleri surumler arasinda yeniden adlandirdi (ornegin
GPS_TYPE -> GPS1_TYPE, RNGFND1_MIN_CM -> RNGFND1_MIN). Aracta hangi surumun
calistigi onceden bilinmedigi icin eski ve yeni ad birlikte tanimlidir;
kurulum ekrani tam parametre listesi indikten sonra aracta olmayan satirlari
gizler.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParamInfo:
    name: str
    label: str                      # kisa baslik
    description: str                # bilgi isaretinde gorunen Turkce anlatim
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float = 0.1
    decimals: int = 2
    # {deger: etiket} verilirse alan acilir liste olarak cizilir
    choices: dict[int, str] = field(default_factory=dict)
    # True ise degistirmek yeniden baslatma ister
    reboot_required: bool = False


def _p(name, label, description, **kwargs) -> ParamInfo:
    return ParamInfo(name=name, label=label, description=description, **kwargs)


# Birden fazla parametrenin paylastigi deger tablolari (metadata'dan dogrulandi)

_MODE_CHOICES = {0: "0 — MANUAL", 1: "1 — ACRO", 3: "3 — STEERING",
                 4: "4 — HOLD", 5: "5 — LOITER", 10: "10 — AUTO",
                 11: "11 — RTL", 15: "15 — GUIDED"}

_GPS_TYPE_CHOICES = {
    0: "0 — Yok", 1: "1 — Otomatik", 2: "2 — uBlox", 5: "5 — NMEA",
    9: "9 — DroneCAN", 10: "10 — Septentrio (SBF)", 11: "11 — Trimble (GSOF)",
    17: "17 — uBlox hareketli baz (Base)", 18: "18 — uBlox hareketli baz (Rover)",
    21: "21 — ExternalAHRS",
    22: "22 — DroneCAN hareketli baz (Base)", 23: "23 — DroneCAN hareketli baz (Rover)",
    24: "24 — Unicore NMEA", 25: "25 — Unicore çift anten (NMEA)",
    26: "26 — Septentrio çift anten (SBF)",
}

_BATT_FS_CHOICES = {0: "0 — Sadece uyar", 1: "1 — Eve dön (RTL)",
                    2: "2 — Dur (HOLD)", 3: "3 — SmartRTL",
                    4: "4 — SmartRTL veya Hold", 5: "5 — Sonlandır"}

_ROTATION_CHOICES = {0: "0 — None", 2: "2 — Yaw 90°", 4: "4 — Yaw 180°",
                     6: "6 — Yaw 270°", 8: "8 — Roll 180°"}


# --------------------------------------------------------------------------
# Gruplar. Sira, kurulum ekranindaki sira.
# --------------------------------------------------------------------------

GROUPS: list[tuple[str, str, list[ParamInfo]]] = [
    (
        "frame",
        "Gövde ve kimlik",
        [
            _p("FRAME_CLASS", "Gövde sınıfı",
               "Aracın hangi tür olduğunu söyler. Tekne projesinde bunun 2 (Boat) "
               "olması gerekir: ArduPilot o zaman tekneye özgü davranışları açar — "
               "duruş kontrolü, su üstü seyir mantığı ve fren yerine akıntıya karşı "
               "konum tutma. 1 (Rover) seçilirse araç kara aracı gibi sürülür ve "
               "durmak için frene basmaya çalışır.",
               choices={0: "0 — Tanımsız", 1: "1 — Rover (kara)", 2: "2 — Boat (tekne)"},
               reboot_required=True),
            _p("FRAME_TYPE", "Gövde tipi",
               "Motor yerleşimini tanımlar. İki motorlu bir katamaranda motorlar "
               "sağ/sol olarak ayrı sürüldüğü (skid steering) için genelde 0 kalır; "
               "asıl yerleşim SERVO çıkış fonksiyonlarıyla belirlenir.",
               choices={0: "0 — Varsayılan / skid", 1: "1 — Omni3", 2: "2 — Omni X",
                        3: "3 — Omni Plus"}),
            _p("SYSID_THISMAV", "MAVLink sistem no",
               "Aracın MAVLink ağındaki kimlik numarası. Aynı anda birden fazla araç "
               "uçuruyorsan her birine farklı bir numara verilmeli, yoksa yer "
               "istasyonu telemetrileri karıştırır. Tek araçta 1 kalır. (Eski "
               "ArduPilot sürümlerindeki adı; güncel sürümde MAV_SYSID.)",
               minimum=1, maximum=255, step=1, decimals=0, reboot_required=True),
            _p("MAV_SYSID", "MAVLink sistem no",
               "Aracın MAVLink ağındaki kimlik numarası. Aynı anda birden fazla araç "
               "uçuruyorsan her birine farklı bir numara verilmeli, yoksa yer "
               "istasyonu telemetrileri karıştırır. Tek araçta 1 kalır. (Güncel "
               "ArduPilot'taki adı; eski sürümlerde SYSID_THISMAV.)",
               minimum=1, maximum=255, step=1, decimals=0, reboot_required=True),
            _p("BRD_SAFETYENABLE", "Emniyet düğmesi",
               "Kartın üzerindeki kırmızı emniyet düğmesinin zorunlu olup olmadığı. "
               "1 iken düğmeye basılmadan motorlara sinyal gitmez — sahada güvenlik "
               "için açık bırakılması önerilir. (Eski ArduPilot sürümlerindeki "
               "ayar; güncel sürümde BRD_SAFETY_DEFLT.)",
               choices={0: "0 — Devre dışı", 1: "1 — Zorunlu"}),
            _p("BRD_SAFETY_DEFLT", "Emniyet düğmesi (açılış)",
               "Kart açıldığında emniyet düğmesinin hangi durumda başlayacağı. 1 iken "
               "güvenli (yanıp sönen) durumda başlar ve düğmeye basılana kadar motor "
               "çıkışlarına sinyal gitmez; 0 iken doğrudan güvensiz (sabit) durumda "
               "başlar. Sahada 1 bırakılması önerilir.",
               choices={0: "0 — Kapalı (güvensiz başlar)", 1: "1 — Açık (güvenli başlar)"}),
            _p("LOG_BITMASK", "Kayıt içeriği",
               "Uçuş kaydına (dataflash log) hangi veri gruplarının yazılacağını "
               "seçen bit maskesi. Varsayılan geniş değer, sonradan sorun ararken "
               "elinde veri olmasını sağlar. Kart yeriniz doluyorsa daraltılır.",
               minimum=0, step=1, decimals=0),
        ],
    ),
    (
        "outputs",
        "Motor çıkışları",
        [
            _p("SERVO1_FUNCTION", "Çıkış 1 görevi",
               "Otopilotun 1 numaralı çıkış pininden hangi sinyalin çıkacağı. "
               "İki motorlu tekne için 73 (ThrottleLeft) = sol motor. Yanlış "
               "atanırsa tekne düz gitmek yerine kendi etrafında döner.",
               choices={0: "0 — Kullanılmıyor", 26: "26 — Ground Steering",
                        70: "70 — Throttle", 73: "73 — Throttle Left",
                        74: "74 — Throttle Right"},
               reboot_required=True),
            _p("SERVO3_FUNCTION", "Çıkış 3 görevi",
               "3 numaralı çıkış pininin görevi. İki motorlu teknede 74 "
               "(ThrottleRight) = sağ motor.",
               choices={0: "0 — Kullanılmıyor", 26: "26 — Ground Steering",
                        70: "70 — Throttle", 73: "73 — Throttle Left",
                        74: "74 — Throttle Right"},
               reboot_required=True),
            _p("SERVO1_REVERSED", "Çıkış 1 ters",
               "Sol motor ters dönüyorsa (ileri komutunda geri gidiyorsa) kabloyu "
               "sökmek yerine buradan çevirin.",
               choices={0: "0 — Normal", 1: "1 — Ters"}),
            _p("SERVO3_REVERSED", "Çıkış 3 ters",
               "Sağ motor ters dönüyorsa buradan çevirin.",
               choices={0: "0 — Normal", 1: "1 — Ters"}),
            _p("MOT_PWM_TYPE", "Motor sinyal tipi",
               "ESC'ye gönderilen sinyalin biçimi. Çoğu marin ESC normal PWM "
               "kullanır (0). Yanlış seçilirse motorlar hiç dönmez veya tepki "
               "vermez.",
               choices={0: "0 — Normal PWM", 1: "1 — OneShot", 2: "2 — OneShot125",
                        3: "3 — BrushedWithRelay", 4: "4 — BrushedBipolar",
                        5: "5 — DShot150", 6: "6 — DShot300"},
               reboot_required=True),
            _p("MOT_THR_MIN", "Minimum gaz", "Motorun dönmeye başladığı en düşük gaz "
               "yüzdesi. Su içinde pervane belli bir eşiğin altında hiç itki "
               "üretmez; burayı o eşiğe ayarlamak düşük hızda tekneyi daha "
               "kontrol edilebilir yapar.", unit="%", minimum=0, maximum=20),
            _p("MOT_THR_MAX", "Maksimum gaz",
               "Otopilotun kullanmasına izin verilen en yüksek gaz yüzdesi. "
               "Motorları veya bataryayı zorlamamak için sınırlanabilir.",
               unit="%", minimum=10, maximum=100),
            _p("MOT_SLEWRATE", "Gaz değişim hızı",
               "Gazın saniyede en fazla yüzde kaç değişebileceği. Düşük değer "
               "yumuşak kalkış demektir ve dalgalı suda ani akım çekişini "
               "engeller; çok düşük olursa tekne komutlara geç tepki verir.",
               unit="%/s", minimum=0, maximum=200, step=5, decimals=0),
            _p("MOT_SAFE_DISARM", "Disarm'da sinyal kes",
               "Araç disarm iken çıkış pinlerine sinyal gitsin mi. 1 yapmak "
               "kazara motor dönmesine karşı ek güvenlik sağlar.",
               choices={0: "0 — Sinyal devam eder", 1: "1 — Sinyal kesilir"}),
        ],
    ),
    (
        "radio",
        "Kumanda (RC) girişi",
        [
            _p("RCMAP_ROLL", "Direksiyon kanalı",
               "Dümen/direksiyon komutunun hangi kumanda kanalından okunacağı. "
               "Rover/tekne yazılımında bu kanal aracın dönüşünü sürer. "
               "Varsayılan 1'dir.",
               minimum=1, maximum=16, step=1, decimals=0, reboot_required=True),
            _p("RCMAP_THROTTLE", "Gaz kanalı",
               "İleri/geri gaz komutunun okunacağı kumanda kanalı. Varsayılan 3.",
               minimum=1, maximum=16, step=1, decimals=0, reboot_required=True),
            _p("MODE_CH", "Mod anahtarı kanalı",
               "Uçuş modunu değiştiren kumanda anahtarının bağlı olduğu kanal. Bu "
               "kanalın PWM değeri 6 aralığa bölünür ve MODE1…MODE6 parametreleri "
               "hangi aralıkta hangi modun seçileceğini söyler.",
               minimum=1, maximum=16, step=1, decimals=0),
            _p("RC1_MIN", "Kanal 1 min",
               "Direksiyon çubuğu sonuna kadar itildiğinde okunan en düşük PWM "
               "değeri (mikrosaniye). Radyo kalibrasyonu bunu otomatik doldurur; "
               "elle değiştirmek genelde gerekmez.",
               unit="µs", minimum=800, maximum=2200, step=10, decimals=0),
            _p("RC1_MAX", "Kanal 1 maks",
               "Direksiyon çubuğunun diğer uçtaki PWM değeri.",
               unit="µs", minimum=800, maximum=2200, step=10, decimals=0),
            _p("RC1_TRIM", "Kanal 1 orta",
               "Çubuk serbest bırakıldığında okunan değer — aracın 'düz git' "
               "noktası. Yanlışsa tekne çubuk ortadayken bir tarafa kayar.",
               unit="µs", minimum=800, maximum=2200, step=10, decimals=0),
            _p("RC1_REVERSED", "Kanal 1 ters",
               "Direksiyon ters çalışıyorsa (sağa iterken sola dönüyorsa) çevirin.",
               choices={0: "0 — Normal", 1: "1 — Ters"}),
            _p("RC1_DZ", "Kanal 1 ölü bant",
               "Orta nokta etrafında yok sayılacak PWM aralığı. Kumandanın küçük "
               "titremelerinin tekneyi sürekli düzeltmeye zorlamasını engeller.",
               unit="µs", minimum=0, maximum=200, step=5, decimals=0),
            _p("RC3_MIN", "Kanal 3 min", "Gaz çubuğunun en alt PWM değeri.",
               unit="µs", minimum=800, maximum=2200, step=10, decimals=0),
            _p("RC3_MAX", "Kanal 3 maks", "Gaz çubuğunun en üst PWM değeri.",
               unit="µs", minimum=800, maximum=2200, step=10, decimals=0),
            _p("RC3_TRIM", "Kanal 3 orta",
               "Gaz çubuğunun nötr değeri. Teknede ileri/geri ortası budur.",
               unit="µs", minimum=800, maximum=2200, step=10, decimals=0),
            _p("RC3_DZ", "Kanal 3 ölü bant",
               "Gaz ortasındaki ölü bant. Küçük titremelerin motoru sürekli "
               "çalıştırmasını engeller.",
               unit="µs", minimum=0, maximum=200, step=5, decimals=0),
        ],
    ),
    (
        "modes",
        "Uçuş modları",
        [
            _p("MODE1", "Mod 1", "Mod anahtarının 1. konumunda seçilecek mod.",
               choices={0: "0 — MANUAL", 1: "1 — ACRO", 3: "3 — STEERING",
                        4: "4 — HOLD", 5: "5 — LOITER", 6: "6 — FOLLOW",
                        7: "7 — SIMPLE", 10: "10 — AUTO", 11: "11 — RTL",
                        12: "12 — SMART_RTL", 15: "15 — GUIDED"}),
            _p("MODE2", "Mod 2", "Mod anahtarının 2. konumundaki mod.",
               choices=dict(_MODE_CHOICES)),
            _p("MODE3", "Mod 3", "Mod anahtarının 3. konumundaki mod.",
               choices=dict(_MODE_CHOICES)),
            _p("MODE4", "Mod 4", "Mod anahtarının 4. konumundaki mod.",
               choices=dict(_MODE_CHOICES)),
            _p("MODE5", "Mod 5", "Mod anahtarının 5. konumundaki mod.",
               choices=dict(_MODE_CHOICES)),
            _p("MODE6", "Mod 6", "Mod anahtarının 6. konumundaki mod.",
               choices=dict(_MODE_CHOICES)),
            _p("INITIAL_MODE", "Açılış modu",
               "Otopilot açıldığında hangi modda başlayacağı. Güvenli olan MANUAL "
               "veya HOLD'dur; AUTO ile başlamak, açılışta görev varsa tekneyi "
               "hemen hareket ettirebilir.",
               choices={0: "0 — MANUAL", 4: "4 — HOLD", 5: "5 — LOITER",
                        10: "10 — AUTO"}),
        ],
    ),
    (
        "navigation",
        "Seyir (waypoint) ayarları",
        [
            _p("WP_RADIUS", "Varış yarıçapı",
               "Tekne bir waypoint'e bu kadar metre yaklaştığında oraya 'vardım' "
               "sayılır ve sıradakine geçer. Çok küçük olursa tekne noktayı "
               "yakalayamayıp etrafında döner; çok büyük olursa dönüşleri erken "
               "kesip tarama hatlarını bozar. Bu arayüzdeki dönüş yayı hesabı da "
               "bu değeri araçtan okuyup kullanır.",
               unit="m", minimum=0.5, maximum=20),
            _p("WP_SPEED", "Seyir hızı",
               "Otomatik görevde hedeflenen yer hızı. 0 bırakılırsa CRUISE_SPEED "
               "kullanılır.", unit="m/s", minimum=0, maximum=10),
            _p("WP_ACCEL", "İvmelenme",
               "Hız değiştirirken izin verilen en yüksek ivme. Düşük değer daha "
               "yumuşak, dalgada daha stabil bir hareket verir.",
               unit="m/s²", minimum=0, maximum=5),
            _p("WP_JERK", "Jerk (ivme değişimi)",
               "İvmenin ne kadar hızlı değişebileceği. Düşürmek dönüş girişlerini "
               "belirgin şekilde yumuşatır — dalgalı suda tekneyi sakinleştirmenin "
               "en etkili ayarlarından biridir.",
               unit="m/s³", minimum=0.1, maximum=10),
            _p("WP_OVERSHOOT", "İzin verilen sapma",
               "Teknenin hattan ne kadar sapmasına izin verildiği. Tarama işinde "
               "küçük tutmak hat düzgünlüğünü artırır ama tekneyi daha agresif "
               "düzeltmeye zorlar. (Güncel ArduPilot sürümlerinde bu parametre "
               "kaldırılmıştır; araçta yoksa bu satır gizlenir.)",
               unit="m", minimum=0, maximum=10),
            _p("WP_PIVOT_ANGLE", "Yerinde dönüş açısı",
               "Sıradaki waypoint bu açıdan daha keskinse tekne ilerlemeyi kesip "
               "yerinde döner. Tarama hatlarının ucundaki 180° dönüşler için "
               "kullanışlıdır; 0 yapmak yerinde dönüşü kapatır.",
               unit="°", minimum=0, maximum=180, step=5, decimals=0),
            _p("WP_PIVOT_RATE", "Yerinde dönüş hızı",
               "Yerinde dönerken hedeflenen dönüş hızı.",
               unit="°/s", minimum=0, maximum=180, step=5, decimals=0),
            _p("TURN_RADIUS", "Dönüş yarıçapı",
               "Teknenin fiziksel olarak dönebildiği en küçük yarıçap. Otopilot "
               "dönüşleri buna göre planlar; gerçekte olduğundan küçük girilirse "
               "tekne planlanan yayı takip edemez.",
               unit="m", minimum=0.1, maximum=20),
            _p("TURN_MAX_G", "Maksimum yanal G",
               "Dönüşte izin verilen yanal ivme. Yüksek değer daha keskin ve hızlı "
               "dönüş, ama teknede yalpalama ve alabora riski demektir. (Eski "
               "ArduPilot sürümlerindeki adı; güncel sürümde ATC_TURN_MAX_G.)",
               unit="G", minimum=0.05, maximum=2),
            _p("ATC_TURN_MAX_G", "Maksimum yanal G",
               "Dönüşte izin verilen yanal ivme. Seyir kodu yanal ivmeyi bu değerin "
               "altında tutar; yüksek değer daha keskin ve hızlı dönüş, ama teknede "
               "yalpalama ve alabora riski demektir.",
               unit="G", minimum=0.1, maximum=10),
            _p("CRUISE_SPEED", "Seyir hızı (varsayılan)",
               "Aracın normal seyir hızı. CRUISE_THROTTLE ile birlikte otopilotun "
               "gaz–hız ilişkisini öğrenmesini sağlar.",
               unit="m/s", minimum=0, maximum=10),
            _p("CRUISE_THROTTLE", "Seyir gazı",
               "CRUISE_SPEED hızına ulaşmak için gereken yaklaşık gaz yüzdesi. "
               "İkisi birlikte otopilotun ileri besleme (feed-forward) tahminini "
               "kurar; doğru girilirse hız kontrolü belirgin şekilde düzelir.",
               unit="%", minimum=0, maximum=100, step=1, decimals=0),
        ],
    ),
    (
        "tuning",
        "Direksiyon ve hız kontrolü",
        [
            _p("ATC_STR_RAT_P", "Direksiyon P",
               "Dönüş hızı hatasına anlık tepki kazancı. Yükseltmek tekneyi daha "
               "çabuk hizalar; fazlası dümenin sağa sola salınmasına yol açar.",
               minimum=0, maximum=3, step=0.01, decimals=3),
            _p("ATC_STR_RAT_I", "Direksiyon I",
               "Kalıcı hatayı toplayarak kapatır. Akıntı veya rüzgâr tekneyi sürekli "
               "bir tarafa itiyorsa bu terim onu dengeler.",
               minimum=0, maximum=3, step=0.01, decimals=3),
            _p("ATC_STR_RAT_D", "Direksiyon D",
               "Hatanın değişim hızını sönümler. Dalga kaynaklı ani sapmaları "
               "bastırmak için küçük değerlerle artırılır; fazlası gürültüyü "
               "büyütür.",
               minimum=0, maximum=1, step=0.005, decimals=3),
            _p("ATC_STR_RAT_FF", "Direksiyon ileri besleme",
               "İstenen dönüş hızını doğrudan dümene aktaran terim. Doğru "
               "ayarlanırsa P ve I'nın işi azalır ve dönüşler daha temiz olur.",
               minimum=0, maximum=3, step=0.01, decimals=3),
            _p("ATC_STR_RAT_FILT", "Direksiyon filtresi",
               "Direksiyon kontrolcüsünün giriş filtresi kesme frekansı. Düşürmek "
               "dalga gürültüsünü süzer ama tepkiyi geciktirir.",
               unit="Hz", minimum=0.5, maximum=50, step=0.5, decimals=1),
            _p("ATC_STR_RAT_MAX", "Maksimum dönüş hızı",
               "Otopilotun isteyebileceği en yüksek dönüş hızı.",
               unit="°/s", minimum=0, maximum=1000, step=10, decimals=0),
            _p("ATC_SPEED_P", "Hız P",
               "Hız hatasına anlık gaz tepkisi.",
               minimum=0, maximum=3, step=0.01, decimals=3),
            _p("ATC_SPEED_I", "Hız I",
               "Kalıcı hız hatasını kapatır — yüklü tekne veya akıntıda gereklidir.",
               minimum=0, maximum=3, step=0.01, decimals=3),
            _p("ATC_SPEED_D", "Hız D",
               "Hız değişimini sönümler. Genelde 0 bırakılır.",
               minimum=0, maximum=1, step=0.005, decimals=3),
            _p("ATC_ACCEL_MAX", "Maksimum ivme",
               "Hızlanmada izin verilen tavan. Düşük tutmak dalgada burun "
               "kalkmasını azaltır.", unit="m/s²", minimum=0, maximum=5),
            _p("ATC_DECEL_MAX", "Maksimum yavaşlama",
               "Yavaşlamada izin verilen tavan. 0 ise ATC_ACCEL_MAX kullanılır.",
               unit="m/s²", minimum=0, maximum=5),
            _p("ATC_STOP_SPEED", "Durma eşiği",
               "Bu hızın altında araç 'durdu' sayılır.",
               unit="m/s", minimum=0, maximum=2, step=0.05),
        ],
    ),
    (
        "battery",
        "Batarya",
        [
            _p("BATT_MONITOR", "Batarya izleme",
               "Batarya ölçümünün nasıl yapıldığı. 0 = ölçüm yok; 3 = sadece "
               "voltaj; 4 = voltaj ve akım (akım sensörü varsa bunu seçin). "
               "Değiştirdikten sonra otopilotu yeniden başlatmak gerekir.",
               choices={0: "0 — Yok", 3: "3 — Sadece voltaj",
                        4: "4 — Voltaj ve akım", 7: "7 — SMBus",
                        8: "8 — DroneCAN"},
               reboot_required=True),
            _p("BATT_CAPACITY", "Batarya kapasitesi",
               "Bataryanın toplam kapasitesi. Kalan yüzde hesabı buna göre yapılır; "
               "yanlış girilirse 'kalan şarj' göstergesi yanıltıcı olur.",
               unit="mAh", minimum=0, maximum=100000, step=100, decimals=0),
            _p("BATT_VOLT_MULT", "Voltaj çarpanı",
               "Sensörün ölçtüğü ham voltajı gerçek batarya voltajına çeviren "
               "katsayı. Kalibrasyonu şöyle yapılır: bataryayı multimetreyle ölç, "
               "arayüzdeki değerle karşılaştır, oranı bu sayıyla çarp.",
               minimum=0, maximum=100, step=0.01, decimals=4),
            _p("BATT_AMP_PERVLT", "Akım katsayısı",
               "Sensör çıkışındaki her volt başına kaç amper aktığı. Akım sensörünün "
               "veri sayfasında yazar.",
               unit="A/V", minimum=0, maximum=200, step=0.1, decimals=3),
            _p("BATT_LOW_VOLT", "Düşük voltaj eşiği",
               "Bu voltajın altına inince düşük batarya failsafe'i tetiklenir. "
               "LiPo için hücre başına ~3.5 V hesaplanır (4S için ~14.0 V).",
               unit="V", minimum=0, maximum=60, step=0.1),
            _p("BATT_CRT_VOLT", "Kritik voltaj eşiği",
               "Bu voltajın altında kritik failsafe devreye girer — genelde eve "
               "dönüş veya durma. Düşük eşikten daha düşük olmalı.",
               unit="V", minimum=0, maximum=60, step=0.1),
            _p("BATT_FS_LOW_ACT", "Düşük batarya davranışı",
               "Düşük voltaj eşiği aşıldığında ne yapılacağı.",
               choices=dict(_BATT_FS_CHOICES)),
            _p("BATT_FS_CRT_ACT", "Kritik batarya davranışı",
               "Kritik eşik aşıldığında ne yapılacağı.",
               choices=dict(_BATT_FS_CHOICES)),
        ],
    ),
    (
        "failsafe",
        "Failsafe (arıza güvenliği)",
        [
            _p("FS_ACTION", "Failsafe davranışı",
               "Bağlantı veya kumanda kaybında teknenin ne yapacağı. Tarama "
               "görevinde en güvenlisi genelde 2 (Hold) — tekne olduğu yerde durur "
               "ve sürüklenmesini beklersiniz. 1 (RTL) tekneyi kalkış noktasına "
               "geri getirir ama yolda engel varsa tehlikeli olabilir.",
               choices={0: "0 — Hiçbir şey", 1: "1 — Eve dön (RTL)",
                        2: "2 — Dur (HOLD)", 3: "3 — SmartRTL, olmazsa RTL",
                        4: "4 — SmartRTL veya Hold", 5: "5 — Sonlandır"}),
            _p("FS_TIMEOUT", "Failsafe gecikmesi",
               "Sinyal kaybının failsafe sayılması için kaç saniye sürmesi "
               "gerektiği. Çok kısa olursa anlık parazitler tekneyi gereksiz yere "
               "durdurur.", unit="s", minimum=1, maximum=120, step=0.5, decimals=1),
            _p("FS_THR_ENABLE", "Kumanda kaybı failsafe",
               "Kumanda sinyali kesildiğinde failsafe tetiklensin mi.",
               choices={0: "0 — Kapalı", 1: "1 — Açık"}),
            _p("FS_THR_VALUE", "Kumanda kaybı eşiği",
               "Gaz kanalı bu PWM değerinin altına düşerse sinyal kayıp sayılır. "
               "Kumandanın failsafe'te gönderdiği değerin biraz üstünde olmalı.",
               unit="µs", minimum=800, maximum=1200, step=10, decimals=0),
            _p("FS_GCS_ENABLE", "Yer istasyonu failsafe",
               "Yer istasyonuyla telemetri bağlantısı koparsa failsafe tetiklensin "
               "mi. Uzun menzilli tarama görevlerinde açmak riskli olabilir: "
               "telemetri menzilin ucunda kesilebilir ve tekne görevi bırakır.",
               choices={0: "0 — Kapalı", 1: "1 — Açık"}),
            _p("FS_CRASH_CHECK", "Çarpışma algılama",
               "Çarpışma veya sıkışma algılandığında ne yapılacağı. Açıkken tekne "
               "Hold moduna geçer; 2 seçilirse ayrıca disarm edilir.",
               choices={0: "0 — Kapalı", 1: "1 — Dur (HOLD)", 2: "2 — Dur ve disarm"}),
            _p("FS_EKF_ACTION", "Konum kaybı davranışı",
               "EKF (konum kestirimi) güvenilmez hale gelirse ne yapılacağı — yani "
               "araç kendi yerinden emin olamadığında. Tarama teknesi için 1 (Hold) "
               "önerilir; 2 seçilirse konum kaybında sadece uyarı verilir ve tekne "
               "hiçbir şey yapmadan devam eder.",
               choices={0: "0 — Kapalı", 1: "1 — Dur (HOLD)", 2: "2 — Sadece rapor et"}),
        ],
    ),
    (
        "sonar",
        "Sonar / derinlik ölçer",
        [
            _p("RNGFND1_TYPE", "Sensör tipi",
               "Derinlik ölçerin hangi protokolle bağlandığı. Bu tarama teknesinde "
               "batimetri verisi buradan gelir; 0 seçiliyken hiç veri gelmez. "
               "ArduPilot teknelerinde en yaygın echo sounder Blue Robotics "
               "Ping'dir (23); NMEA çıkışlı echo sounder'lar için 17, analog "
               "çıkışlı sensörler için 1 kullanılır.",
               choices={0: "0 — Yok", 1: "1 — Analog", 2: "2 — Maxbotix I2C",
                        7: "7 — LightWare I2C", 8: "8 — LightWare Serial",
                        10: "10 — MAVLink", 17: "17 — NMEA",
                        19: "19 — Benewake TF02", 20: "20 — Benewake TFmini (seri)",
                        23: "23 — Blue Robotics Ping", 24: "24 — DroneCAN"},
               reboot_required=True),
            _p("RNGFND1_MIN_CM", "En küçük ölçüm",
               "Sensörün güvenilir ölçebildiği en kısa mesafe. Bunun altındaki "
               "okumalar geçersiz sayılır — sığ suda derinlik verisi kaybolmasının "
               "en sık sebebi budur. (Eski ArduPilot sürümlerindeki adı, santimetre; "
               "güncel sürümde metre cinsinden RNGFND1_MIN.)",
               unit="cm", minimum=0, maximum=1000, step=5, decimals=0),
            _p("RNGFND1_MIN", "En küçük ölçüm",
               "Sensörün güvenilir ölçebildiği en kısa mesafe (metre). Bunun "
               "altındaki okumalar geçersiz sayılır — sığ suda derinlik verisi "
               "kaybolmasının en sık sebebi budur.",
               unit="m", minimum=0, maximum=50, step=0.05, decimals=2),
            _p("RNGFND1_MAX_CM", "En büyük ölçüm",
               "Sensörün ölçebildiği en uzun mesafe. Derin suda bunun üstündeki "
               "dip okunamaz; sensörün gerçek menziline göre ayarlanmalı. (Eski "
               "ArduPilot sürümlerindeki adı, santimetre; güncel sürümde metre "
               "cinsinden RNGFND1_MAX.)",
               unit="cm", minimum=0, maximum=100000, step=50, decimals=0),
            _p("RNGFND1_MAX", "En büyük ölçüm",
               "Sensörün ölçebildiği en uzun mesafe (metre). Derin suda bunun "
               "üstündeki dip okunamaz; sensörün gerçek menziline göre ayarlanmalı.",
               unit="m", minimum=0, maximum=1000, step=0.5, decimals=1),
            _p("RNGFND1_ORIENT", "Sensör yönü",
               "Sensörün baktığı yön. Derinlik ölçümü için aşağı, yani 25 "
               "(Pitch 270) olmalıdır.",
               choices={0: "0 — İleri", 25: "25 — Aşağı (Pitch 270)"}),
            _p("RNGFND1_SCALING", "Ölçek",
               "Analog sensörlerde volt başına kaç metre. Sensörün veri sayfasından "
               "alınır; yanlışsa derinlikler orantılı olarak hatalı çıkar.",
               minimum=0, maximum=100, step=0.01, decimals=3),
            _p("RNGFND1_OFFSET", "Sıfır kayması",
               "Sensörün sıfır noktası düzeltmesi. Sensör su hattının altındaysa, "
               "ölçülen derinliğe eklenecek fark buradan verilir.",
               minimum=-10, maximum=10, step=0.01, decimals=3),
            _p("RNGFND1_POS_Z", "Sensör Z konumu",
               "Sensörün ağırlık merkezine göre dikey konumu. Aşağısı pozitiftir. "
               "Doğru girilmesi derinlik verisinin tekne yalpalarken de tutarlı "
               "kalmasını sağlar.", unit="m", minimum=-5, maximum=5, step=0.01,
               decimals=3),
        ],
    ),
    (
        "gps",
        "GPS ve konum kestirimi",
        [
            _p("GPS_TYPE", "GPS tipi",
               "Birincil GPS alıcısının protokolü — eski ArduPilot sürümlerindeki "
               "adı (4.6 ve sonrası GPS1_TYPE). Çift antenli Unicore alıcılar için "
               "25, Septentrio çift anten için 26; iki ayrı u-blox alıcıyla "
               "hareketli baz kuruluyorsa birinci alıcı 17, ikinci 18.",
               choices=dict(_GPS_TYPE_CHOICES), reboot_required=True),
            _p("GPS1_TYPE", "GPS tipi",
               "Birincil GPS alıcısının protokolü. 1 (Otomatik) çoğu tek antenli "
               "alıcıyı kendi tanır. Çift antenli GNSS ile yön (heading) almak için "
               "doğru tipi seçmek gerekir: tek çipte çift antenli Unicore alıcılar "
               "(ör. UM982) için 25, Septentrio çift anten için 26; iki ayrı u-blox "
               "alıcıyla hareketli baz kuruluyorsa birinci alıcı 17, ikinci 18. "
               "Ardından Yön kaynağını (EK3_SRC1_YAW) GPS'e almayı unutmayın.",
               choices=dict(_GPS_TYPE_CHOICES), reboot_required=True),
            _p("AHRS_EKF_TYPE", "EKF sürümü",
               "Hangi konum kestirim motorunun kullanılacağı. Güncel araçlarda 3 "
               "(EKF3) kullanılır.",
               choices={2: "2 — EKF2", 3: "3 — EKF3"}, reboot_required=True),
            _p("AHRS_ORIENTATION", "Kart yönü",
               "Otopilot kartının tekne üzerindeki montaj yönü. Kart ileri bakacak "
               "şekilde düz monte edilmişse 0. Yanlışsa tekne yön duygusunu "
               "tamamen kaybeder.",
               choices=dict(_ROTATION_CHOICES)),
            _p("EK3_SRC1_YAW", "Yön kaynağı",
               "Aracın baktığı yönü (heading) neyin belirlediği. 1 = pusula. Motor "
               "ve ESC akımları pusulayı bozduğu için bu teknede çift antenli GNSS "
               "varsa 2 (GPS) veya 3 (GPS, olmazsa pusula) önerilir. 2 ve 3 yalnızca "
               "yön bilgisi veren çift antenli / hareketli baz GNSS ile çalışır — "
               "tek antenli bir GPS'le 2 seçilirse araç yön kaynağı bulamaz. "
               "8 (GSF) pusula kullanmadan hareketten yön tahmin eder.",
               choices={0: "0 — Yok", 1: "1 — Pusula", 2: "2 — GPS (çift anten)",
                        3: "3 — GPS, olmazsa pusula", 6: "6 — Harici navigasyon",
                        8: "8 — GSF (pusulasız tahmin)"}),
            _p("COMPASS_ENABLE", "Pusula kullan",
               "Pusulanın kullanılıp kullanılmayacağı. Kapatmak, güçlü manyetik "
               "girişim olan araçlarda bazen daha stabil sonuç verir ama o zaman "
               "yön için GPS'e bağımlı kalınır.",
               choices={0: "0 — Kapalı", 1: "1 — Açık"}, reboot_required=True),
            _p("COMPASS_AUTODEC", "Otomatik sapma",
               "Manyetik sapmanın (declination) konumdan otomatik hesaplanması. "
               "Açık bırakılması önerilir.",
               choices={0: "0 — Elle", 1: "1 — Otomatik"}),
            _p("COMPASS_ORIENT", "Pusula yönü",
               "Harici pusulanın montaj yönü. Yanlışsa tekne dönerken yön değeri "
               "ters veya kaymış görünür.",
               choices=dict(_ROTATION_CHOICES)),
        ],
    ),
    (
        "arming",
        "Arm koşulları",
        [
            _p("ARMING_CHECK", "Arm öncesi kontroller",
               "Arm etmeden önce hangi kontrollerin yapılacağı (bit maskesi). "
               "1 = hepsi, 0 = hiçbiri. Kapatmak sahada arm sorununu geçici çözer "
               "ama gerçek bir arızayı gizler — tez sunumunda bile açık bırakmak "
               "daha doğrudur. (Eski ArduPilot sürümlerindeki ayar; güncel sürümde "
               "mantığı ters çevrilmiş ARMING_SKIPCHK.)",
               minimum=0, step=1, decimals=0),
            _p("ARMING_SKIPCHK", "Atlanacak arm kontrolleri",
               "Arm etmeden önce hangi kontrollerin ATLANACAĞI (bit maskesi) — eski "
               "ARMING_CHECK'in tersidir. 0 = hiçbir kontrol atlanmaz (önerilen). "
               "Kontrol atlamak sahada arm sorununu geçici çözer ama gerçek bir "
               "arızayı gizler.",
               minimum=0, step=1, decimals=0),
            _p("ARMING_REQUIRE", "Arm zorunlu",
               "Motorların dönmesi için arm gerekip gerekmediği. 1 önerilir. 3 "
               "seçilirse araç, arm kontrolleri geçer geçmez kendiliğinden bir kez "
               "arm olur — teknede tehlikeli olabilir.",
               choices={0: "0 — Gerekmiyor", 1: "1 — Gerekli (disarm'da min PWM)",
                        3: "3 — Otomatik arm (kontroller geçince bir kez)"}),
            _p("ARMING_RUDDER", "Çubukla arm",
               "Kumanda çubuklarıyla arm/disarm yapılabilsin mi.",
               choices={0: "0 — Kapalı", 1: "1 — Sadece arm",
                        2: "2 — Arm ve disarm"}),
        ],
    ),
]


# --------------------------------------------------------------------------
# Aramalar icin duz sozluk
# --------------------------------------------------------------------------

BY_NAME: dict[str, ParamInfo] = {
    info.name: info for _, _, infos in GROUPS for info in infos
}

# Onek bazli genel aciklamalar — sozlukte adi gecmeyen ama ayni aileden olan
# parametreler icin (ornegin RC7_MIN) en azindan ne ise yaradigini soyler.
_PREFIX_HINTS: list[tuple[str, str]] = [
    ("SERVO", "Servo/motor çıkış ayarı. FUNCTION çıkışın görevini, MIN/MAX/TRIM "
              "sinyal aralığını, REVERSED yönünü belirler."),
    ("RC", "Kumanda kanalı ayarı. MIN/MAX/TRIM kanalın PWM aralığı, DZ ölü bant, "
           "REVERSED yön, OPTION o kanala atanmış özel işlev."),
    ("ATC_", "Duruş/hız kontrolcüsü kazancı. Aracın komutlara ne kadar sert tepki "
             "verdiğini belirler."),
    ("WP_", "Otomatik görev seyir ayarı."),
    ("BATT", "Batarya izleme ve failsafe ayarı."),
    ("FS_", "Failsafe (arıza güvenliği) ayarı."),
    ("RNGFND", "Mesafe/derinlik sensörü ayarı."),
    ("COMPASS_", "Pusula ayarı. OFS değerleri kalibrasyonun bulduğu manyetik "
                 "sapmalardır, elle değiştirilmez."),
    ("INS_", "Ataletsel sensör (ivmeölçer/jiroskop) ayarı. ACCOFFS/ACCSCAL "
             "değerleri ivmeölçer kalibrasyonunun sonucudur."),
    ("EK3_", "EKF3 konum kestirim ayarı."),
    ("GPS", "GPS alıcısı ayarı."),
    ("SERIAL", "Seri port hızı ve protokolü."),
    ("SR", "Telemetri akış hızları — hangi mesajın saniyede kaç kez gönderileceği."),
    ("MOT_", "Motor çıkış ayarı."),
    ("BRD_", "Otopilot kartı donanım ayarı."),
    ("LOG_", "Uçuş kaydı ayarı."),
    ("ARMING_", "Arm (motorları etkinleştirme) koşulları."),
    ("MODE", "Uçuş modu seçimi."),
    ("AHRS_", "Yönelim kestirimi ayarı."),
    ("NAVL1_", "L1 seyir kontrolcüsü ayarı — hatta oturma agresifliğini belirler."),
    ("MAV_", "MAVLink haberleşme ayarı."),
]


def describe(name: str) -> str:
    """Bir parametrenin Turkce aciklamasi; sozlukte yoksa aile ipucu."""
    info = BY_NAME.get(name)
    if info is not None:
        return info.description
    for prefix, hint in _PREFIX_HINTS:
        if name.startswith(prefix):
            return f"{hint}\n\n(Bu parametre için ayrıntılı açıklama tanımlı değil.)"
    return "Bu parametre için açıklama tanımlı değil."


def label_for(name: str) -> str:
    info = BY_NAME.get(name)
    return info.label if info is not None else name


def format_value(name: str, value: float) -> str:
    """Degeri, varsa secenek etiketiyle birlikte okunur hale getirir."""
    info = BY_NAME.get(name)
    if info is not None and info.choices:
        return info.choices.get(int(round(value)), f"{value:g}")
    if info is not None and info.unit:
        return f"{value:g} {info.unit}"
    return f"{value:g}"
