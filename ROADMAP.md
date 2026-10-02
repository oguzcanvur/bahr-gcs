# Yol Haritası

Kendi otopilotumuza geçiş için yapılacaklar. Biten madde `[x]` ile işaretlenir.
Son güncelleme: 2026-09-14.

```
BAHR-GCS (PC) ──Ethernet──► SXT SA5 ac  ┄┄5 GHz┄┄►  Metal 52 ac ──Ethernet──► Raspberry Pi 4 ──USB──► NUCLEO-G431RB ──PWM──► Sol / Sağ ESC
                            (karada,                (teknede)     │  (beyin)              │  (refleks)
                             yönlü anten)                  SweGeo RTD100 GNSS          BNO086, RC alıcı (AT9S Pro + R9DS), batarya
                                                            Derinlik sensörü (Garmin echoMAP 42cv)
```

Cube Orange artık kullanılmıyor. BAHR-GCS, ArduPilot/SITL ile uyumlu kalmaya
devam ediyor.

## 0. Önce netleşmesi gerekenler

- [ ] ESC modeli: 3.3 V sinyali kabul ediyor mu, çift yönlü mü, BEC var mı
- [x] Kumanda: RadioLink **AT9S Pro** (verici) + **R9DS** (alıcı, 9-10 kanal)
      zaten kullanıcıda var (2026-09-14). R9DS tek kablodan **SBUS**
      çıkışı veriyor (mavi işaretli CH9 pini) — tek tek PWM kablosu çekmek
      yerine bunu Nucleo'nun UART'ına bağlayacağız. SBUS ters logikli
      (inverted) 100000 baud 8E2; STM32G431'in bunu donanımsal
      ters çevirebilip çeviremediğini (RXINV) Nucleo'ya geçince
      datasheet'ten doğrulamak lazım — doğrulanmadan devre kurulmayacak.
- [x] Derinlik sensörü: **Garmin echoMAP 42cv kullanılacak**, ayrı sensöre
      gerek yok. Kurulum kılavuzuna bakıp "derinlik vermiyor" sonucuna
      vardım ama yanlıştı — kılavuzdaki tablo varsayılan liste, cihazın
      kendi ayarında "Sounder" NMEA çıkışı açılınca derinlik de geliyor.
      2026-09-14: kullanıcı FTDI USB-seri adaptörle Pi'ye bağladı,
      `tools/gnss_probe.py` ile `/dev/ttyUSB0`'dan gerçek veri okundu:
      **38400 baud** (NMEA standardı 4800 değil), 1 Hz — GPGGA, GPRMC,
      GPGLL, GPRMB, GPVTG, GPBWC, GPBOD, GPAPB, HCHDM (pusula yönü),
      PGRME/PGRMM/PGRMZ, **SDDBT, SDDPT (derinlik)**, **SDMTW (su sıcaklığı,
      test anında 23.85°C)**, SDVHW, WIMWV (rüzgar). Test anında GPS'in
      gökyüzü görmediği ve transducer'ın suda olmadığı için konum/derinlik
      alanları boştu, cümlelerin kendisi düzgün geliyordu.
- [x] RTK düzeltmesinin kaynağı: **TUSAGA-Aktif** (VRS, mount point
      `VRSRTCM31`) — kullanıcının zaten `swegeo_gnss_app` masaüstü
      uygulamasında kayıtlı bir hesabı var (2026-09-15'te keşfedildi).
      Düzeltme olmadan konum hatası ~1.5 m (datasheet). Çift anten yönü
      düzeltme olmadan da çalışır.
- [ ] GNSS antenlerinin teknedeki yeri ve aralarındaki mesafe
- [ ] Teknede Pi 4 için 5 V / 3 A besleme

## 1. Temin edilecekler

- [ ] Raspberry Pi 4 + microSD kart + teknede 5 V regülatör
- [ ] NUCLEO-G431RB
- [ ] BNO086
- [ ] Batarya voltajı ölçümü için gerilim bölücü (ya da güç modülü)
- [ ] Multimetre (RTD100'ün UART pinlerini doğrulamak için)
- [ ] Gerekirse harici Wi-Fi anteni / erişim noktası (menzil ölçüldükten sonra)

## 2. GNSS — SweGeo RTD100

- [x] Datasheet incelendi: 3.3 V besleme ve UART, 10 Hz, pinler
      1 3.3V · 2 GND · 3 TXD · 4 RXD · 5 PPS · 6 MODE
- [x] Okuma aracı yazıldı: `tools/gnss_probe.py` (sahte verilerle 16/16 test)
- [x] USB-C ile Pi'ye takıldı (2026-09-15), `gnss_probe.py` ile ölçüldü:
      **115200 baud**. Hem standart NMEA (`GPGGA`, `GPGSA`, `GPGSV`, 1 Hz)
      hem cihazın kendi Bynav ASCII formatı (`#BESTPOSA` 5 Hz,
      `#HEADINGA` 1 Hz, ikisi de CRC doğrulanmış) geliyor.
- [x] Yön mesajı zaten açık geliyor (`GPTRA` + `#HEADINGA`) — açtırmaya
      gerek yokmuş, madde kapandı
- [x] **RTD100 artık BAHR-GCS arayüzüne canlı bağlı (2026-09-16).**
      `tools/echomap_bridge.py` genişletildi — artık hem echoMAP'i hem
      RTD100'ü aynı anda okuyup TEK bir MAVLink akışında birleştiriyor.
      Konum/yön için RTD100 varsa o kullanılıyor (echoMAP'in kendi zayıf
      GPS'inin önüne geçiyor). Gerçek donanımla doğrulandı: **32 uydu,
      153° yön (çift antenden), pos_type=SINGLE → GPS 3D FIX** olarak
      arayüzde doğru göründü. `#BESTPOSA`/`#HEADINGA` (Bynav ASCII,
      CRC32 doğrulanmış) parse ediliyor; alan indeksleri NovAtel'in
      belgelenmiş BESTPOS/HEADING düzenine dayanıyor (Bynav'ın kendi
      belgesine hâlâ erişilemiyor) — sonuç gerçek veriyle tutarlı çıktı.
- [ ] Açık alanda yön doğruluğunu ölç (şu an kapalı mekanda — RTK için
      zaten açık alan gerekiyor, aynı testte birlikte yapılabilir)
- [ ] Hangi konnektörün UART olduğunu ve 3.3 V pinini multimetreyle doğrula
- [ ] `tools/gnss_probe.py`'yi GitHub'a gönder
- [ ] **Port çakışması notu (2026-09-15):** RTD100 (CH340 çipi) ve Echomap'in
      FTDI adaptörü ikisi de `/dev/ttyUSB0` olarak görünebiliyor —
      hangisi önce takılıysa o ismi alıyor. `bahr-echomap-bridge.service`
      açılışta otomatik `/dev/ttyUSB0`'ı kilitleyip GNSS'in test edilmesini
      engelledi, elle durduruldu. Kalıcı çözüm: Pi'nin gerçek yazılımı
      (bölüm 4) cihazları `/dev/serial/by-id/` altındaki sabit isimlerle
      seçmeli, ikisi de aynı anda takılıyken bile karışmasın.

## 3. Raspberry Pi 4 kurulumu

- [x] Bu PC'de SSH anahtarı oluştur (`C:\Users\VUR\.ssh\id_ed25519`, 2026-09-14)
- [x] Raspberry Pi Imager: Raspberry Pi OS (other) → Raspberry Pi OS Lite
      (64-bit) (Debian Trixie); hostname `bahr-pi`, kullanıcı `bahr`, Wi-Fi ve
      SSH (açık anahtarla) ayarları — 2026-09-14
- [x] İlk SSH bağlantısı çalışıyor (`ssh bahr-pi`, PC'deki `~/.ssh/config`
      içinde takma ad). Pi 4B Rev 1.5, 4 GB RAM, Python 3.13.5, IP
      192.168.3.14 (o an)
- [x] Pi'de sudo şifresiz açıldı (kullanıcı `/etc/sudoers.d/010-bahr-nopasswd`
      ekledi, 2026-09-14) — sistemi buradan yönetebiliyorum
- [x] Sistem güncellemesi (apt update/upgrade, yeniden başlatma gerekmedi)
- [x] Python ortamı: `~/bahr-gcs/.venv` içinde pymavlink + pyserial kurulu
- [x] Yazılım gönderme düzeni: `~/bahr-gcs` GitHub'dan `git clone` edildi;
      güncellemek için `git pull --ff-only`. `ROADMAP.md` ve
      `tools/gnss_probe.py` henüz GitHub'a gönderilmediği için Pi'nin
      kopyasında yok — pushlanınca `git pull` ile gelecek
- [x] Açılışta otomatik başlayan servis (systemd) — 2026-09-14, şu an sadece
      `echomap_bridge.py` için (`bahr-echomap-bridge.service`,
      `/etc/systemd/system/`, `enabled` + `Restart=always`). Gerçek reboot
      testiyle doğrulandı: Pi yeniden başladıktan 8 sn sonra servis kendi
      kendine ayağa kalktı, elle dokunulmadı.
- [x] **Sahada Pi'nin kendi Wi-Fi ağı — kuruldu (2026-09-15).**
      NetworkManager profili `bahr-field-ap`, SSID **BAHR-Tekne**, şifre
      `bahrgcs2026`, Pi'nin adresi `10.42.0.1` (paylaşımlı/NAT modu).
      Varsayılan kapalı (`autoconnect no`), ev ağını etkilemiyor.
      - Açmak: `sudo nmcli connection up bahr-field-ap`
      - Ev ağına dönmek: `sudo nmcli connection up netplan-wlan0-Beha`
      - Bu PC'de SSH kısayolu eklendi: `ssh bahr-pi-saha` (10.42.0.1) —
        sahadayken `bahr-bahr_pilot.local` yerine bunu kullan
      - **Henüz uçtan uca test edilmedi** — laptop "BAHR-Tekne"ye
        bağlanıp SSH ve BAHR-GCS'nin gerçekten çalıştığı doğrulanmadı
      - MikroTik köprüsü (bölüm 3b) kurulunca daha uzun menzil için o
        kullanılacak; bu, ondan önce de sahada çalışmayı sağlayan
        bağımsız bir yedek/birincil çözüm
      - Kullanıcı bu çözümü tercih etmedi, yerine kablolu bağlantıyı
        seçti (aşağıya bak) — bu profil dursun, ama birincil plan değil
- [x] **Kablolu doğrudan bağlantı — tercih edilen çözüm (2026-09-15),
      SSH tarafı test edildi ve çalışıyor.** NetworkManager profili
      `bahr-field-eth` (eth0), paylaşımlı/NAT modu, Pi'nin adresi
      `10.43.0.1`. Wi-Fi'ye hiç dokunmuyor — Pi'nin kablosuz bağlantısı ve
      laptop'un Wi-Fi'si (telefon hotspot'una bağlanabilir) bozulmadan
      çalışır. USB tethering gerekmiyor, Wi-Fi AP çözümünden daha basit.
      - **Artık tamamen otomatik (2026-09-15 düzeltildi):** ilk kurulumda
        kablo çıkarılıp takılınca Pi varsayılan DHCP-istemci profiline
        dönüyordu, elle `nmcli connection up` gerektiriyordu — sahada
        Wi-Fi olmayınca bu düzeltilemezdi (tavuk-yumurta sorunu). Şimdi
        `bahr-field-eth` otomatik bağlanan ve öncelikli (`autoconnect
        yes`, öncelik 10 > varsayılan profilin 0'ı) — **kabloyu takmak
        yeterli, hiçbir komut gerekmiyor.** Gerçek indirip-kaldırma
        testiyle doğrulandı.
      - Bu PC'de SSH kısayolu: `ssh bahr-pi-kablo` (10.43.0.1) — **canlı
        test edildi, çalışıyor**
      - Laptop'un kablo üzerindeki IP'si (DHCP ile): `10.43.0.102`
      - [x] **Telemetri de kabloya taşındı ve doğrulandı (2026-09-15).**
        `echomap_bridge` servisinin hedefi `10.43.0.102`'ye güncellendi.
        Gerçek veriyle test edildi: `HEARTBEAT`, `GLOBAL_POSITION_INT`,
        `GPS_RAW_INT`, su sıcaklığı (24.97°C) — hepsi kablo üzerinden
        geldi. Wi-Fi ile artık bir ilgisi yok, tamamen kablo üzerinden
        çalışıyor. (Not: laptop'un IP'si `10.43.0.102` değişebilir —
        ağa her yeniden bağlanışta DHCP kirası değişirse bu adresin
        güncellenmesi gerekebilir.)
- [ ] Wi-Fi menzilini sahada ölç (hem bu AP modunda hem MikroTik'te)

## 3b. Kara-tekne telsiz köprüsü (MikroTik)

Kullanıcıda hazır, ikisi de RouterOS çalıştırıyor. Amaç: PC ile Pi'yi sanki
uzun bir Ethernet kablosuyla bağlıymış gibi aynı ağa koymak (köprü/bridge
modu) — mevcut MAVLink/UDP kodu hiç değişmeden çalışsın.

- [x] Cihazlar ve yerleşim belirlendi (2026-09-14):
      - **SXT SA5 ac** (RBSXTG-5HPacD-SA) — **karada**. Yönlü sektör anten,
        13-16 dBi, 90° açı, sadece 5 GHz, 1300 mW'a kadar çıkabiliyor
        (gereğinden fazla güç kullanılmayacak, BTK dış mekan sınırlarına
        dikkat). Rolü: AP (erişim noktası), suyun olduğu yöne sabit bakacak.
      - **Metal 52 ac** (RBMetalG-52SHPacn) — **teknede**. Yönsüz anten
        (6 dBi 2.4 GHz / 8 dBi 5 GHz) — tekne hangi yöne dönerse dönsün
        karayı görmeye devam eder. Rolü: istasyon (client), 5 GHz'de
        SXT'ye bağlanacak.
- [ ] Karadaki SXT'yi PoE adaptörüyle bu PC'ye bağla, ağda görünür hale
      getir (kullanıcı fiziksel olarak yapacak; "bağladım" dedikten sonra
      buradan SSH/RouterOS CLI ile devam edilecek)
- [ ] SXT'yi AP-bridge, Metal 52'yi station-bridge moduna al; ikisini de
      Ethernet portlarıyla bridge'e bağla (L2 şeffaf köprü)
- [ ] 5 GHz kanal seç, SSID/parola belirle, TX gücünü menzile göre
      (maksimuma değil) ayarla
- [ ] Teknedeki Metal 52'yi Pi'ye Ethernet ile bağla, karadaki SXT'yi
      bu PC'ye Ethernet ile bağla
- [ ] Uçtan uca test: PC'den Pi'ye ping, sonra `echomap_bridge.py`'nin
      MikroTik hattı üzerinden BAHR-GCS'ye ulaştığını doğrula
- [ ] Sahada gerçek menzili ölç (SXT'nin baktığı yönde, gölette/nehirde)
- [ ] **EMI notu (2026-09-14):** SXT SA5 ac 1300 mW'a kadar çıkabiliyor —
      RTD100'ün GNSS anteni yakınına konursa alıcı ön-ucunu doyurup
      (desensitizasyon) fix kalitesini bozabilir. Metal 52'nin anteni ile GNSS
      antenleri arasında mümkün olduğunca fiziksel mesafe (en az 50 cm-1 m,
      tekne boyu izin verdiğince), mümkünse aralarına gövde girecek şekilde
      montaj. Doğrulama: Metal 52 açık/kapalıyken `GPGGA`'daki uydu sayısı
      ve HDOP karşılaştırılır.

## 4. Pi yazılımı (teknenin beyni)

- [x] **İskelet yazıldı ve bu PC'de MAVLink uyumluluğu doğrulandı
      (2026-10-01).** `bahr_pilot/` paketi: `vehicle.py` (ana süreç, komut/mod/arm/
      görev işleme, telemetri), `state.py` (paylaşılan araç durumu),
      `sensors.py` (RTD100+echoMAP okuyucuları, `tools/echomap_bridge.py`'den
      birebir taşındı — regex/CRC/alan indeksleri aynı, donanımda
      doğrulanmış mantık), `nucleo_link.py` (Pi→Nucleo paket protokolünün
      Python tarafı, `bahr_pilot/firmware/reflex/Core/Src/pi_link.c` ile eşleşiyor),
      `rtcm_forward.py` (`tools/rtcm_relay.py`'nin yerini alıyor,
      `gcs.rtcm.RtcmReassembler`'ı kullanıyor), `navigation.py` (waypoint
      takibi → motor komutu, `sim/fake_vehicle.py`'nin geometri
      formülleriyle aynı).
      > `python -m bahr_pilot.vehicle --gcs-host <pc_ip> [--nucleo-port ...]
      > [--gnss-port ...] [--echomap-port ...]`
      > **Gerçekten test edildi** (donanım yokken, bu PC'de): sahte bir GCS
      > dinleyicisiyle uçtan uca — HEARTBEAT/GLOBAL_POSITION_INT/GPS_RAW_INT/
      > VFR_HUD/ATTITUDE/SYS_STATUS/MISSION_CURRENT/NAV_CONTROLLER_OUTPUT/
      > RC_CHANNELS hepsi doğru biçimde geldi; `DO_SET_MODE` kabul edildi;
      > GPS fix'i yokken `ARM_DISARM` doğru şekilde reddedildi; 2 parçalı
      > görev yükleme protokolü (`MISSION_COUNT`→`MISSION_REQUEST_INT`×2→
      > `MISSION_ACK`) uçtan uca çalıştı. Bu süreçte gerçek bir hata
      > yakalandı ve düzeltildi: `sys_status_send`'e `voltage_battery` için
      > -1 (unsigned alan, taşma hatası verdi) yerine 65535 (bilinmiyor)
      > verilmesi gerekiyordu.
      > **Henüz test edilmeyen/eksik kısımlar:** gerçek RTD100/echoMAP/
      > Nucleo/BNO086/batarya donanımıyla uçtan uca (Pi'ye hiç deploy
      > edilmedi); `pi_link` artık çift yönlü ve roll/pitch + batarya
      > voltajı taşıyor (2026-10-01, aşağıdaki not), ama bunların ikisi de
      > donanımda doğrulanmadı — batarya gerilim bölücü oranı yer tutucu,
      > BNO086 sürücüsü hiç gerçek sensöre karşı çalışmadı; navigasyonun
      > dönüş kazancı/motor yön işareti gerçek teknede doğrulanmadı.
      >
      > **İkinci doğrulama turu (2026-10-01):** tüm repo (`gcs/`, `sim/`,
      > `tools/`, `bahr_pilot/`, `web/`) sözdizimi+import kontrolünden geçti, hata
      > yok. Gerçek BAHR-GCS uygulaması açılıp `bahr_pilot.vehicle`'a canlı
      > bağlanarak test edildi (sahte dinleyici değil) — 9 telemetri
      > mesajı doğru hızda (5 Hz) geldi, GPS'siz arm reddi hem GCS hem
      > sunucu logunda doğrulandı, `DO_SET_MODE` GCS'nin PILOT panelinden
      > tıklanarak canlı test edildi (MANUAL→GUIDED anında yansıdı).
      >
      > **MANUAL modda GPS fix şartı kaldırıldı (kullanıcı isteği,
      > 2026-10-01):** MANUAL navigasyon kullanmadığı için GPS'siz arm
      > edilebiliyor artık; AUTO/GUIDED/RTL/LOITER hâlâ GPS fix istiyor.
      > Not: kumandanın kendi "elle devralma" switch'i (`failsafe.c`,
      > `SBUS_CH_OVERRIDE_SWITCH`) zaten Pi/GPS'ten tamamen bağımsız
      > çalışıyordu — bu değişiklik sadece GCS üzerinden MANUAL arm etme
      > yolunu açıyor.
      >
      > **Klasör yeniden düzenlendi: `pi/` → `bahr_pilot/` (kullanıcı isteği,
      > 2026-10-01).** Otopilotun iki yarısı (Python/Pi tarafı + STM32
      > firmware) artık tek bir `bahr_pilot/` klasörü altında: Python paketi
      > doğrudan `bahr_pilot/` (önceden `pi/`), Nucleo firmware'i de onun
      > içinde `bahr_pilot/firmware/reflex/` (önceden repo kökünde ayrı bir
      > `firmware/` klasörüydü) — `gcs/`/`sim/`/`tools/`/`web/`'den ayrı,
      > kendi başına duran tek bir birim. Tüm `pi.*` import'ları
      > `bahr_pilot.*`'ya çevrildi, çalıştırma komutu artık
      > `python -m bahr_pilot.vehicle`. Firmware tarafında sadece
      > `Debug/makefile`'da mutlak yol (linker script) vardı, o düzeltildi
      > — `.cproject`/`.project`/`.ioc` zaten göreli yol kullanıyordu.
      > Her ikisi de yeni konumdan tekrar derlenip/import edilip doğrulandı
      > (firmware 0 hata, Python importları ve uçtan uca MAVLink testi
      > temiz). **Not:** STM32CubeIDE'nin workspace'i (`.metadata`, eski
      > `firmware/` klasöründeydi) projenin eski konumuna kayıtlıydı — proje
      > taşındığı için silindi; IDE'yi tekrar açarsan projeyi
      > `bahr_pilot/firmware/reflex`'ten yeniden import etmen gerekebilir
      > (File > Import > Existing Projects). Komut satırından derleme
      > (`make`, bu oturumda zaten asıl kullanılan yöntem) buna bağlı değil.
- [x] BAHR-GCS'nin beklediği MAVLink mesajları — yukarıdaki iskelette.
- [x] Heartbeat'teki otopilot tipi ve mod numaraları — `bahr_pilot/modes.py`,
      `fake_vehicle.py` ile birebir aynı değerler.
- [x] GNSS sürücüsü — `bahr_pilot/sensors.py` (yukarıda).
- [x] Nucleo sürücüsü (Python tarafı) — `bahr_pilot/nucleo_link.py`, artık çift
      yönlü (motor komutu + RC haritası ayarı gönderiyor, telemetri
      okuyor — bkz. bölüm 5'teki `pi_link` notu). `bahr_pilot/vehicle.py`,
      BAHR-GCS'nin `RCMAP_ROLL/RCMAP_THROTTLE/RCMAP_ARM/RCMAP_OVERRIDE` ve
      `RC1..8_MIN/MAX/TRIM/REVERSED` parametrelerini (ve RadioPage'in
      `MAV_CMD_PREFLIGHT_CALIBRATION` akışını) gerçekten işliyor ve her
      değişiklikte Nucleo'ya aktarıyor. `RCMAP_ARM`/`RCMAP_OVERRIDE`
      ArduPilot'ta olmayan, bu araç için `gcs/param_meta.py`'ye eklenen 2
      yeni parametre — ikisi de var olan parametre sayfasında aynı
      desenle (RCMAP_ROLL/THROTTLE gibi) görünüyor, yeni bir GCS ekranı
      gerekmedi. Loopback seri port ile byte seviyesinde doğrulandı,
      gerçek donanımda henüz değil.
- [x] BNO086'dan roll/pitch — `bahr_pilot/firmware/reflex/Core/Src/imu.c`
      (SHTP/I2C, Game Rotation Vector raporu, 2026-10-01, kart yokken
      yazıldı) artık roll/pitch üretiyor ve `pi_link`'in telemetri
      çerçevesiyle Pi'ye ulaşıyor; `ATTITUDE` mesajında gerçek değerler.
      Donanımda hiç test edilmedi, montaj yönüne göre eksen/işaret
      doğrulanmadı.
- [ ] Yön birleştirme: GNSS yönü (10 Hz) + BNO086 dönüş hızı — bu, yukarıdaki
      roll/pitch'ten AYRI bir madde: yaw'ı GNSS+gyro ile yumuşatan bir
      complementary filter. Henüz yapılmadı, yaw hâlâ sadece GNSS'ten
      (tasarım gereği — bkz. imu.c, pusula füzyonu yok).
- [x] Navigasyon: waypoint takibi, yön ve hız kontrolü, dönüşlerde
      yavaşlama — `bahr_pilot/navigation.py`, gerçek teknede doğrulanmadı.
- [x] Modlar: MANUAL, HOLD, AUTO, GUIDED (go-to), RTL — uygulandı ve
      MISSION_START/DO_REPOSITION/NAV_RETURN_TO_LAUNCH üzerinden test edildi.
- [x] Failsafe (Pi tarafı): GCS bağlantısı koparsa (`FS_GCS_ENABLE` +
      `FS_TIMEOUT`, varsayılan açık / 3 sn — 2026-10-02'ye kadar adı
      `GCS_FS_TIMEOUT_S`'ti) motorlar nötre düşüyor. Düşük batarya
      failsafe'i `BATT_LOW_VOLT`/`BATT_FS_ENABLE` ile var (varsayılan kapalı).

> **2026-10-02 — Mimari inceleme (Faz 0):** otopilotun hedef mimariye
> (STM32/FreeRTOS + ROS 2) göre boşluk analizi, BAHR-GCS uyumluluk matrisi,
> bulunup düzeltilen hatalar ve karar listesi artık bahr-pilot reposunda:
> `docs/ARCHITECTURE_REVIEW.md` ve `docs/BAHR_GCS_ARCHITECTURE.md`. Bu
> bölümdeki yollar repo ayrılmadan önceki düzene göre; Python paketi artık
> bahr-pilot reposunun içinde `bahr_pilot/` alt klasöründe ve **repo
> kökünden** çalıştırılıyor (`python -m bahr_pilot.vehicle`).
- [x] Derinlik: `DISTANCE_SENSOR` + `NAMED_VALUE_FLOAT` (`water_temp`) —
      `bahr_pilot/sensors.py` + `bahr_pilot/vehicle.py` zaten gönderiyor.
- [x] Ham veri kaydı: GNSS + derinlik + IMU + batarya, zaman damgalı
      (`bahr_pilot/datalog.py`, NDJSON, `--log-dir` ile açılır,
      2026-10-01). Birim testli (`bahr_pilot/tests/test_datalog.py`),
      gerçek bir seyirde hiç kullanılmadı.
- [x] **Pi tarafı da tamamlandı (2026-09-15): `tools/rtcm_relay.py`.**
      GPS_RTCM_DATA'yı alıp parçaları birleştirip RTD100'ün seri portuna ham
      bayt olarak yazıyor. Gerçek donanımda uçtan uca doğrulandı: bu PC'den
      sahte bir MAVLink "GCS" ile 78 baytlık test verisi gönderildi, Pi'deki
      betik heartbeat attı, veriyi aldı, birleştirdi ve gerçek
      `/dev/ttyUSB0`'a (RTD100) hatasız yazdı — log: "78 bayt RTCM -> GNSS".
      Kalıcı servis yapılmadı (bkz. not).
      > Not: bu betik ile `bahr-echomap-bridge.service` **aynı anda
      > çalıştırılmamalı** — ikisi de aynı porta (14550) konuştuğu için
      > BAHR-GCS'nin cevabı "en son kim konuştuysa" ona gider, hangisinin
      > kazanacağı garantisiz. Düzgün çözüm (MAVLink component adresleme)
      > Nucleo'nun gerçek Pi yazılımıyla (bölüm 4) gelecek.
      >
      > **Test ederken bulunan gerçek bir hata:** `gcs/rtcm.py`'deki
      > parçalama mantığı, veri tam olarak 180 baytın katıysa (180, 360,
      > 720…) ve 4'ten az parçayla bitiyorsa son parçayı sessizce
      > kaybediyordu — düzeltildi (boş bir sonlandırıcı parça ekleniyor),
      > 300 rastgele sınır-durumu testiyle doğrulandı.

## 5. STM (Nucleo) yazılımı (refleks)

- [x] **Geliştirme ortamı + LED yakma (2026-09-22, donanımda doğrulandı).**
      STM32CubeIDE 1.19.0 (`C:\ST\STM32CubeIDE_1.19.0`), proje
      `bahr_pilot/firmware/reflex/` altında — `bahr_pilot/` repo köküyle aynı
      seviyede `gcs/`/`sim/`/`tools/` gibi (2026-10-01'de `pi/`'den
      yeniden adlandırıldı ve firmware kendi altına taşındı, bkz. bölüm
      4'teki not), Nucleo firmware'i de onun içinde `firmware/reflex/`
      olarak duruyor. Board: NUCLEO-G431RB. ST-LINK'in sürükle-bırak
      programlama özelliğiyle (`.elf`'ten `arm-none-eabi-objcopy` ile `.bin`
      üretip `D:\` (NOD_G431RB) sürücüsüne kopyalayarak) flaşlandı — gerçek
      kartta yeşil LED (LD1) yanıp sönmesi kullanıcı tarafından doğrulandı.
      > Pin haritası (`.ioc`'den doğrulandı, LED/buton ile çakışma yok):
      > LD1 (yeşil LED) = **PA5**, USER BUTTON = **PC13** (board varsayılanı)
      > ADC1_IN1 (batarya voltajı) = **PA0**
      > TIM2_CH1 (motor 1 PWM) = **PA15**, TIM2_CH2 (motor 2 PWM) = **PA1**
      > I2C1_SDA/SCL (BNO086) = **PB7 / PB8**
      > USART1_TX/RX (RC alıcı SBUS, sadece RX kullanılacak) = **PC4 / PC5**
      > USART3_TX/RX (Raspberry Pi bağlantısı) = **PB10 / PB11**
      > ST-LINK VCP = LPUART1 üzerinden PA2/PA3 (USART2 değil — Nucleo-G431RB'nin
      > kendine özgü BSP tercihi)
      > Bu pin adları Nucleo'nun ST Morpho konektöründe (CN7/CN10) doğrudan
      > serigrafiyle yazılı, Arduino D-numarasına çevirmeye gerek yok.
      > Komut satırından derleme de kuruldu (`make` + CubeIDE'nin gömülü
      > `arm-none-eabi-gcc`'si, PATH'e eklenerek) — artık IDE GUI'sini açmadan
      > derlenip doğrulanabiliyor.
- [x] **ESC'lere PWM; açılışta "dur" sinyali (2026-10-01, kart yokken yazıldı — henüz donanımda test edilmedi).**
      `Core/Src/esc.c`+`.h`: TIM2 50 Hz'e ayarlandı (Prescaler=169,
      Period=19999 → 1 µs çözünürlük), `ESC_SetPulse()` 1000-2000 µs'e
      clamp'liyor, `ESC_Init()` açılışta hemen nötr (1500 µs) komutluyor.
      Failsafe (aşağıya bakın) her durumda açılışta/komut gelmeden önce
      motorları nötrde tutuyor.
- [x] **BNO086 okuma (I2C, pusulasız mod) — yazıldı 2026-10-01, kart yokken,
      hiç donanımda test edilmedi.** `Core/Src/imu.c`+`.h`: SHTP/SH-2
      protokolü, "Game Rotation Vector" raporu (0x08, pusulasız — pusula
      füzyonu yok, bu projede yaw her zaman GNSS'ten). Protokol sabitleri
      (kanal numaraları, rapor ID'leri, Set Feature çerçeve biçimi, Q14
      ölçek) hafızadan değil, bilinen çalışan açık kaynak bir sürücüden
      (sparkfun/SparkFun_BNO080_Arduino_Library) doğrudan okunarak alındı.
      I2C adresi (0x4B) ve eksen/işaret kuralı donanımda doğrulanmadı —
      bazı kartlar 0x4A kullanabilir, montaj yönüne göre roll/pitch işareti
      ters çıkabilir.
- [x] **Pi ile sağlama kodlu paket haberleşmesi — artık çift yönlü
      (2026-10-01, kart yokken yazıldı, bir loopback seri portla byte
      seviyesinde doğrulandı — gerçek donanımda henüz test edilmedi).**
      `Core/Src/pi_link.c`+`.h`, USART3 üzerinde üç çerçeve tipi:
      1) Pi→Nucleo motor komutu (7 bayt, değişmedi),
      2) **Pi→Nucleo RC haritası ayarı (20 bayt, yeni)** — throttle/steering/
      arm/override kanal indeksleri + min/max/trim/reversed, BAHR-GCS'nin
      `RCMAP_*`/`RCn_MIN/MAX/TRIM/REVERSED` parametrelerini (ve RadioPage
      kalibrasyon ekranını) gerçekten Nucleo'ya ulaştırıyor,
      3) **Nucleo→Pi telemetri (36 bayt, yeni)** — 16 ham SBUS kanalı +
      armed/rc_link_up/override/pi_fresh/battery_valid/imu_valid durum
      bitleri, 100 ms'de bir gönderiliyor; `bahr_pilot/vehicle.py`'nin
      `RC_CHANNELS`/`SYS_STATUS`/`ATTITUDE` mesajları artık bunu taşıyor
      (önceden hep sıfır/bilinmiyordu). Çerçeve 2026-10-01'de 36'dan
      42 bayta büyüdü (batarya voltajı + roll/pitch eklendi).
      RC haritası artık flash'a kalıcı yazılıyor (`settings.c`,
      2026-10-01) — güç kesilince kaybolmuyor, bozuk/boş flash'ta
      derlenmiş varsayılanlara döner.
- [x] **Failsafe: öncelik tablosuna göre, artık donanımsal arm switch +
      yapılandırılabilir throttle/steering mix ile birlikte (2026-10-01,
      kart yokken yazıldı — henüz donanımda test edilmedi).**
      `Core/Src/failsafe.c`+`.h`, tablonun 0-4. maddelerini uyguluyor.
      **0. madde (2026-10-01):** kumandada ayrı bir fiziksel arm switch
      (`RCMAP_ARM`, varsayılan CH6) — kapalıyken motorlar donanım
      seviyesinde durur, Pi/GCS'in kendi "armed" durumundan tamamen
      bağımsız; ikisi birbirinden habersiz, pervane dönmesi için ikisi de
      "evet" demeli. **Elle devralma artık "ileri/geri/sağ/sol" tek
      stickle çalışıyor (kullanıcı isteği):** önceden CH1→motor1/CH2→motor2
      ham geçişti, şimdi `pi_link`'ten gelen `RcMapConfig` ile throttle+
      steering normalize edilip (`RCn_MIN/MAX/TRIM/REVERSED`) karıştırılıyor
      (motor1=throttle-steering, motor2=throttle+steering). Varsayılanlar
      ArduPilot Rover'ın kendi kuralıyla aynı: `RCMAP_THROTTLE`=CH3,
      `RCMAP_ROLL`=CH1, `RCMAP_OVERRIDE`=CH5. Kanal atamaları ve
      kalibrasyon artık BAHR-GCS'nin **var olan** parametre sayfası +
      RadioPage ekranından ayarlanıyor — yeni bir GCS ekranı yazmaya gerek
      kalmadı. Diğer maddeler değişmedi: RC sinyali yoksa dur, RC var ama
      Pi 500 ms'den uzun süredir sessizse dur, açılışta varsayılan dur.
      **5. madde (kendi firmware'i takılırsa donanım watchdog) artık var
      (2026-10-01)** — `Core/Src/wdg.c`, IWDG'yi HAL sürücüsü yerine
      doğrudan register erişimiyle sürüyor (CubeMX hiç etkinleştirmediği
      için HAL_IWDG kaynak dosyası projede yoktu; IWDG zaten 4 registerlık
      basit bir çevrebirim olduğu için buna gerek kalmadı). LSI saatiyle
      ~500 ms zaman aşımı, `main.c`'nin ana döngüsünde her turda
      besleniyor. Donanımda hiç test edilmedi (gerçek bir kilitlenme
      senaryosu tetiklenmedi).
- [x] **Kumandayla elle devralma — `failsafe.c` içinde RC override olarak
      uygulandı**, kanal ataması artık sabit `#define` değil (2026-10-01'de
      `RcMapConfig`'e taşındı, bkz. yukarıdaki pi_link/failsafe notları) —
      `RCMAP_ARM`=CH6, `RCMAP_OVERRIDE`=CH5, `RCMAP_THROTTLE`=CH3,
      `RCMAP_ROLL`=CH1 **varsayılan** değerler, BAHR-GCS'nin parametre
      sayfasından değiştirilebilir. Hâlâ gerçek AT9S Pro kanal ayarlarıyla
      karşılaştırılıp doğrulanmadı. Kumandada bu kanallara karşılık gelen
      switch'leri atamak kullanıcının kendi transmitter menüsünden yapması
      gereken bir adım.

> **Önemli not (2026-10-01, güncellendi):** Bu oturumda kart yanında
> olmadığı için ESC/SBUS/pi_link/failsafe/battery/imu/settings/wdg
> modüllerinin HİÇBİRİ gerçek donanımda, gerçek bir RC alıcısıyla,
> gerçek bir BNO086/batarya ile ya da gerçek bir Pi paketiyle test
> edilmedi — sadece derleniyor (0 hata/uyarı, `make` ile tam temiz
> yeniden derleme dahil). SBUS çerçeve çözme algoritması, pulse-genişlik
> hesaplamaları ve BNO086'nın SHTP protokol sabitleri mantık olarak
> doğru kurgulandı (ikincisi bilinen çalışan bir açık kaynak sürücüden
> doğrudan alındı) ama doğrulama donanım geldiğinde yapılmalı. Ayrıca `.ioc` üzerinden CubeMX'in
> komut satırı (`java -jar STM32CubeMX.jar -q script`) ile kod üretimi
> denendi — çalıştı ama `ProjectManager.TargetToolchain`'i yan etki olarak
> EWARM'a çevirdi ve istenmeyen IAR proje dosyaları (`.ewp`/`.ewd`/`.eww`)
> üretti; bunlar temizlendi ve toolchain STM32CubeIDE'ye geri düzeltildi.
> Ayrıca USART1'in WordLength/Parity/StopBits için `.ioc`'e doğru anahtarlar
> (ve `IPParameters` listesine eklendiler) yazıldığı halde üretilen `main.c`'ye
> yansımadı (sadece BaudRate ve RxPinLevelInvert gerçekten işe yaradı) — sebebi
> belirsiz. Bu üçü `main.c`'de elle düzeltildi; bir sonraki tam kod üretiminde
> (CubeIDE GUI'den ya da tekrar headless'tan) bu üç satırın main.c'den
> silinip silinmediği kontrol edilmeli.

### Failsafe öncelik tablosu (2026-09-14)

Nucleo yalnızca üç şeyi bilir: RC sinyali var mı, Pi'den taze komut geliyor
mu, kendi firmware'i takılı mı. GPS/Wi-Fi kaybı Nucleo'nun değil, Pi'nin
sorunu (bkz. bölüm 4'teki not) — Nucleo GPS'in var olduğunu bile bilmez.

En yüksek öncelikten en düşüğe (üsttekiler alttakileri ezer):

| # | Durum | Nucleo tepkisi |
|---|---|---|
| 1 | Kumandada (RC) elle devralma anahtarı açık | RC ne diyorsa o — Pi'den gelen her komut yok sayılır |
| 2 | RC sinyali tamamen kesildi (R9DS failsafe bayrağı) | Motorları durdur, ne moddaysan ol |
| 3 | RC var, elle devralma kapalı, Pi ~0.5 sn sessiz kaldı | Motorları durdur (station-keeping/HOLD yok — kapsam dışı, en güvenlisi dur) |
| 4 | Açılış anı / henüz hiç komut gelmedi | Disarm, motorlara "dur" sinyali |
| 5 | Kendi firmware'i takıldı | Donanım bekçi sayacı (watchdog) kartı resetler, açılış disarm'a döner |

RC her zaman en yüksek öncelikte, çünkü ağdan tamamen bağımsız tek kanal bu.

**Pi'nin kendi sorumluluğu (bölüm 4'e not):** GPS kaybı ya da GCS/Wi-Fi
kaybı olduğunda ne yapılacağına Pi'nin navigasyon yazılımı karar verir —
varsayılan: waypoint'e gitmeyi durdur, Nucleo'ya "dur" komutu gönder. Görevi
otomatik sürdürme (GCS geri gelene kadar beklemeden devam etme) bilinçli bir
karar olarak ileride ayrıca değerlendirilebilir, varsayılan güvenli tarafta.
- [x] **Batarya voltajı (ADC) — yazıldı 2026-10-01, kart yokken.**
      `Core/Src/battery.c`: ADC1_IN1/PA0'dan tek seferlik dönüşüm +
      üstel hareketli ortalama filtresi, `pi_link` telemetrisiyle Pi'ye
      ulaşıyor, `SYS_STATUS.voltage_battery`'de gerçek değer olarak
      görünüyor. **Gerilim bölücü oranı (11:1) ölçülmedi, yer tutucu** —
      gerçek direnç değerleri multimetreyle doğrulanmadan bu sayıya
      güvenilmemeli. Pi tarafında `BATT_LOW_VOLT`/`BATT_FS_ENABLE`
      parametreleriyle düşük voltaj failsafe'i de eklendi, varsayılan
      kapalı (aynı kalibrasyon sebebiyle).
- [x] **Pi üzerinden uzaktan güncelleme — şablon yazıldı 2026-10-01,
      gerçek Pi'de hiç denenmedi.** `bahr_pilot/deploy/bahr-pilot.service`
      (systemd birimi) + `deploy/update.sh` (`git pull` + venv güncelle +
      servisi yeniden başlat). `--*-port` yolları ve `--gcs-host` şablonda
      yer tutucu, gerçek Pi'ye kurulurken doldurulmalı.
- [x] **Donanımdan bağımsız mantığın (paket, parametre, RTCM) PC'de
      testleri — `bahr_pilot/tests/` (pytest, 2026-10-01), 20 test.**
      Gerçek `NucleoLink` sınıfını `pyserial` loopback port üzerinden
      (motor/config/genişletilmiş-42-bayt-telemetri çerçeveleri dahil),
      gerçek `RtcmFragmenter`/`RtcmReassembler`'ı rastgele/sınır-durum
      round-trip testleriyle, gerçek `Vehicle` sınıfını parametre/arm
      komut işleme testleriyle kapsıyor. **Kapsam dışı: `failsafe.c`'nin
      kendi C durum makinesi** — bu Python testleri Nucleo firmware'ini
      değil, Pi tarafındaki Python mantığını ve wire-protokolü kapsıyor.

## 6. BAHR-GCS uyarlamaları

- [ ] Kurulum penceresi ArduPilot'a özel. Kendi otopilotumuz için sade bir
      parametre sayfası: ESC PWM aralıkları, failsafe süreleri, kontrol
      kazançları, anten ofseti
- [x] Motor testi: `bahr_pilot/vehicle.py` artık `MAV_CMD_DO_MOTOR_TEST`'i
      destekliyor (2026-10-01, bölüm 4'teki not) — mevcut ekran GCS tarafında
      değişiklik gerekmeden çalışmalı, gerçek donanımla doğrulanmadı.
- [ ] Küçük: araç ayarları listesindeki `WP_OVERSHOOT` yeni ArduPilot'ta yok
- [x] **"Vehicle tuning" / "Vehicle setup & calibration" Plan sekmesinden
      sol rayına taşındı (2026-10-01, kullanıcı isteği).** İkisi de zaten
      kendi ayrı penceresini açıyordu (`VehicleTuningDialog` QDialog,
      `SetupWindow` ayrı QWidget) — sadece tetikleyici düğmeler
      `_build_plan_page()`'den `_build_nav_rail()`'e taşındı, LOG
      düğmesiyle aynı desende (rail_group'un dışında, "link" durumuna göre
      gri/aktif). Yeni pencere mantığı yazılmadı, `_show_tuning`/
      `_show_setup` değişmedi. `main_window.py`, canlı GCS'de görsel olarak
      doğrulandı: TUNING/SETUP sol rayda görünüyor, Plan sekmesi artık bu
      ikisini içermiyor, bağlantı yokken doğru şekilde pasif.
- [x] **RTK / NTRIP paneli (2026-09-15)** — "Connection" kartının hemen
      altında yeni bir kart. TUSAGA-Aktif'e (ya da başka bir NTRIP
      caster'a) bağlanır, RTCM3'ü alır, `GPS_RTCM_DATA` olarak (180 baytlık
      parçalara bölerek, MAVLink'in 4-parça sıralama şemasıyla) bağlı araca
      gönderir. Protokol detayları (istek biçimi, GGA periyodu)
      `swegeo_gnss_app`'ten alındı, yeniden icat edilmedi.
      - Yeni dosyalar: `gcs/rtcm.py` (parçalama, saf mantık, 34/34 test),
        `gcs/ntrip_client.py` (QThread tabanlı istemci, gerçek soket
        sunucusuna karşı 10/10 test — handshake, kimlik doğrulama, RTCM
        akışı, GGA gönderimi, ret/bağlantı hatası senaryoları)
      - `gcs/mavlink_worker.py` / `gcs/mavlink_service.py`'ye `send_rtcm`
        eklendi
      - Ayarlar `QSettings` ile kalıcı (host/port/mount/kullanıcı/şifre/
        yaklaşık konum) — kullanıcı arayüzden bir kez girip unutur
      - Gerçek uygulamada ekran görüntüsüyle doğrulandı, kartın tamamı
        doğru render oluyor
      - **Eksik:** bu sadece döngünün GCS/kara tarafı. Düzeltme MAVLink
        üzerinden araca gidiyor ama Pi tarafında bunu alıp GNSS'e yazacak
        bir şey henüz yok (bkz. bölüm 4)

## 7. Entegrasyon ve testler

Her testte ölçüm kaydı tutulacak; bunlar rapora girer.

- [ ] Tezgâh testi (pervanesiz): GCS → Wi-Fi → Pi → USB → Nucleo → ESC
- [ ] Failsafe ölçümleri: Pi'nin fişini çek, Wi-Fi'yi kes, kumandayla devral.
      Motorlar kaç ms'de duruyor?
- [ ] Sakin suda: elle sürüş, HOLD, go-to
- [ ] Yön ve waypoint kontrolünün ayarı
- [ ] Tam tarama görevi: rota + derinlik kaydı + ısı haritası
- [ ] Wi-Fi menzil ölçümü

## 8. Belgeler ve sürüm

- [ ] README'ye yeni mimari (Pi + STM) bölümü
- [ ] Kendi otopilotla ilk çalışan sürümde versiyonu artırmak (istendiğinde)
