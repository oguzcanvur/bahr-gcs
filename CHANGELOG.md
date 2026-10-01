# Changelog

Bu proje [Semantic Versioning](https://semver.org/) kullanır: `MAJOR.MINOR.PATCH`.

- **PATCH** (`0.0.x`) — hata düzeltmeleri, davranış değişikliği yok
- **MINOR** (`0.x.0`) — geriye uyumlu yeni özellik
- **MAJOR** (`x.0.0`) — geriye uyumsuz değişiklik (1.0.0'a kadar bu proje için "kararlılık" anlamına gelmez, sadece kapsamlı değişiklik anlamına gelir)

Biçim [Keep a Changelog](https://keepachangelog.com/) temel alınarak tutulur.

## [Unreleased]

## [0.1.0] — 2026-10-01

### Eklenen
- **RTK/NTRIP istemcisi doğrudan BAHR-GCS içinde** (Ayarlar sekmesinde
  kapanabilir "RTK / NTRIP" kartı): herhangi bir NTRIP sunucusuna
  (TUSAGA-Aktif dahil) bağlanma, GGA konum cümlesi gönderme, gelen RTCM3
  düzeltmelerini MAVLink `GPS_RTCM_DATA` olarak araca iletme
  (`gcs/ntrip_client.py`, `gcs/rtcm.py`). Önceki ayrı `tools/rtcm_relay.py`
  betiğinin yerini alıyor — artık GCS'nin kendisinden, ayrı bir süreç
  başlatmaya gerek kalmadan.
- Kapanabilir kart bileşeni (`gcs/components.py`'nin `Card`'ına
  `collapsible`/`start_collapsed`) — "RTK / NTRIP" ve "Local demo" blokları
  artık varsayılan kapalı, ekranı gereksiz kaplamıyor.
- "TUNING" ve "SETUP" artık Plan sekmesinden sol bara taşındı, ayrı
  pencere olarak açılıyor ve bağlantı yokken de açılabiliyor (önceden
  Plan'ı meşgul ediyordu ve bağlantı istiyordu).
- Özel otopilot (bahr_pilot) için yeni parametreler: `RCMAP_ARM`,
  `RCMAP_OVERRIDE` (kumandada arm/elle-devralma anahtarı kanalları),
  `BATT_FS_ENABLE` (düşük batarya motorları durdursun mu).
- GPS uydu sayısı ve su sıcaklığı artık telemetri panelinde gösteriliyor.
- `docs/architecture-diagram.html` — sistem mimarisi ve bağlantı portları
  diyagramı. `tools/gnss_probe.py` — RTD100 GNSS seri port tanılama aracı.

### Düzeltilen
- GPS uydu sayısı, MAVLink'in "bilinmiyor" değeri olan 255'i gerçek bir
  sayıymış gibi gösteriyordu; artık `None` olarak ele alınıyor.
- Kurulum penceresindeki parametre açılır listeleri ArduPilot'un resmi
  parametre metadata'sıyla (`apm.pdef.json`) karşılaştırıldı; güvenlik
  açısından kritik yanlış etiketler düzeltildi — yön kaynağı
  (`EK3_SRC1_YAW`), sonar tipi (`RNGFND1_TYPE`), konum kaybı failsafe'i
  (`FS_EKF_ACTION`), çarpışma algılama (`FS_CRASH_CHECK`), arm zorunluluğu
  (`ARMING_REQUIRE`) ve GPS tipi. Çift antenli GNSS ve Blue Robotics Ping
  seçenekleri eklendi.
- Cevap alınamayan parametre indirmesi "0 parametre, tamamlandı" olarak
  görünüyordu; artık istek 4 kez tekrar gönderiliyor ve sonuç alınamazsa
  başarısız olarak raporlanıyor.
- Otopilotun heartbeat'i ilk geldiğinde komutlar bileşen 0'a (yayın)
  gönderiliyordu; artık her durumda otopilotun kendi bileşenine gidiyor.
- Simülatör, bağlantıdan hemen sonra gelen istekleri ~1 sn geç
  cevaplıyordu (Windows'ta biriken "port ulaşılamaz" hataları); artık aynı
  döngüde boşaltılıyor.

### Değişen
- Yeni ArduPilot sürümlerinde adı değişen parametreler (`GPS_TYPE` →
  `GPS1_TYPE`, `SYSID_THISMAV` → `MAV_SYSID`, `RNGFND1_MIN_CM` →
  `RNGFND1_MIN` vb.) iki adla da tanımlı; araçta olmayan ad, tam parametre
  listesi indikten sonra kurulum ekranında gizleniyor.

## [0.0.0] — 2026-08-18

Genesis etiketi — versiyonlama başlamadan önce projede birikmiş olan her şeyin
anlık görüntüsü. Buradan sonraki her değişiklik bu dosyaya, `[Unreleased]`
altına eklenip bir sürüm etiketlendiğinde kendi başlığına taşınır.

### Eklenen
- MAVLink bağlantısı (`UDP`/`TCP`/`Serial`), canlı telemetri paneli
- Harita tabanlı görev planlama: poligon çizimi, boustrophedon tarama rotası,
  araç `WP_RADIUS`'una göre boyutlanan dönüş yayları
- Görev yükleme + otomatik doğrulama (aynı görev geri okunup karşılaştırılır)
- **Go to point** — QGroundControl/Mission Planner mantığıyla `DO_REPOSITION`
  + `SET_POSITION_TARGET_GLOBAL_INT` yedeği
- Uyarlanabilir tarama hızı (dönüşlerde yavaşlama, düzlerde hızlanma)
- `RC_CHANNELS_OVERRIDE` üzerinden sanal joystick ile manuel sürüş
- Araç parametre okuma/yazma (Vehicle tuning paneli)
- **Tam kurulum ve kalibrasyon penceresi** — kumanda/ivmeölçer/pusula
  kalibrasyonu, motor testi (gerçek port haritasıyla), Türkçe parametre
  sözlüğü, `.param` içe/dışa aktarma — Mission Planner'a ihtiyaç bırakmadan
- Derinlik ısı haritası ve 2D batimetri görünümü (coğrafi/kartezyen)
- Waypoint koordinat listesi, USB kamera paneli, suni ufuk
- Gazebo/SITL olmadan test için Python araç simülatörü (`sim/fake_vehicle.py`)
- `run.bat` / `setup.bat` ile tek tıkla kurulum ve çalıştırma

### Marka
- Proje adı **BAHR-GCS** (Bathymetric Autonomous Hydrographic Reconnaissance
  Ground Control Station) olarak belirlendi; marka kimliği `gcs/theme.py`
  içinde tek kaynaktan yönetiliyor

[Unreleased]: https://github.com/oguzcanvur/bahr-gcs/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/oguzcanvur/bahr-gcs/compare/v0.0.0...v0.1.0
[0.0.0]: https://github.com/oguzcanvur/bahr-gcs/releases/tag/v0.0.0
