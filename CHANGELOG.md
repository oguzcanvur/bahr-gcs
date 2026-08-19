# Changelog

Bu proje [Semantic Versioning](https://semver.org/) kullanır: `MAJOR.MINOR.PATCH`.

- **PATCH** (`0.0.x`) — hata düzeltmeleri, davranış değişikliği yok
- **MINOR** (`0.x.0`) — geriye uyumlu yeni özellik
- **MAJOR** (`x.0.0`) — geriye uyumsuz değişiklik (1.0.0'a kadar bu proje için "kararlılık" anlamına gelmez, sadece kapsamlı değişiklik anlamına gelir)

Biçim [Keep a Changelog](https://keepachangelog.com/) temel alınarak tutulur.

## [Unreleased]

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

[Unreleased]: https://github.com/oguzcanvur/bahr-gcs/compare/v0.0.0...HEAD
[0.0.0]: https://github.com/oguzcanvur/bahr-gcs/releases/tag/v0.0.0
