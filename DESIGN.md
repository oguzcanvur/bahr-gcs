# BAHR-GCS — Tasarım Sistemi

Bu belge arayüzün görsel dilini ve bileşen kurallarını tanımlar. Tek kaynak
`gcs/theme.py`; hiçbir modül kendi içinde ham renk kodu veya ölçü taşımaz.

## 1. Tasarım ilkeleri

1. **Harita birincil yüzeydir.** Kontroller haritayı çevreler, üstünü kaplamaz.
   Harita üstündeki tek katman, cam (glass) HUD panelleridir.
2. **Tek aksan rengi.** Logo camgöbeği (`#00A8F0`) yalnızca birincil eylem ve
   aktif durum için kullanılır. Aksan renginin sık kullanımı vurgu değerini
   düşürür.
3. **Renk anlam taşır.** Yeşil = normal, sarı = dikkat, kırmızı = kritik.
   Dekoratif renk kullanılmaz.
4. **Sayı ve etiket ayrımı.** Tüm sayısal telemetri monospace; tüm etiketler
   sans-serif ve küçük punto, harf aralığı açılmış büyük harf.
5. **Boşluk yapıdır.** Gruplar arasındaki 12–16 px boşluk, çizgi ve çerçeve
   kullanımının yerini alır.

## 2. Renk token'ları

Palet uygulama logosundan türetilmiştir: lacivert `#002048` (hue ≈ 213°) tüm
yüzey ve kenarlıkların rengini belirler, camgöbeği `#00A8F0` aksandır.

| Token | Değer | Kullanım |
|---|---|---|
| `bg_root` | `#050A13` | Uygulama zemini, rail |
| `bg_canvas` | `#080E1A` | Harita arkası, girdi zemini |
| `surface_1` | `#0E1826` | Panel gövdesi, üst çubuk |
| `surface_2` | `#131F30` | Kart |
| `surface_3` | `#1A2839` | Yükseltilmiş yüzey, buton |
| `border_subtle` → `border_strong` | `#1B2839` → `#38506D` | 3 kademeli ayraç |
| `text_primary` → `text_disabled` | `#EFF4FA` → `#455568` | 4 kademeli okuma hiyerarşisi |
| `accent` | `#00A8F0` | Birincil eylem, aktif durum |
| `info` / `success` / `warning` / `danger` | `#7AA2F7` / `#34D399` / `#FBBF24` / `#F87171` | Durum |

Aksan camgöbeği olduğu için `info` tonu ondan ayırt edilebilsin diye
menekşe-maviye kaydırılmıştır. Her durum renginin `_soft` varyantı rozet ve
seçili durum zeminlerinde kullanılır. Derinlik görselleştirmesi 6 kademeli ayrı
bir skala kullanır (`depth_0…depth_5`, sığdan derine); derin uç aksanla
karışmaması için mavi-menekşedir.

### 2.0 QPalette — QSS'in yetmediği yer

`apply_theme()` yalnızca stil sayfası uygulamaz, `QPalette`'i de koyu temayla
değiştirir. Bu **zorunludur**: QSS'te adı geçmeyen her widget Fusion'ın açık
varsayılan paletini korur (`Window #F0F0F0`, `Base #FFFFFF`), global `*` kuralı
ise metni beyaza boyar — sonuç beyaz üzerine beyazdır.

Bu hata projede üç kez ayrı ayrı çıktı (önce `QMessageBox`, sonra kurulum
penceresi ve parametre tablosu), çünkü her seferinde tek bir widget tipi için
düzeltilmişti. **Yeni bir üst düzey pencere veya öğe görünümü eklerken QSS
kuralı yazmak yeterli değildir; palet zaten doğru zemini verir, QSS sadece
üzerine biçim ekler.**

## 2.1 Marka

Logo iki varyantta saklanır (`gcs/assets/`):

- `logo.png` — şeffaf zeminli çıplak marka.
- `app_icon.png` — açık plaka üzerindeki marka. Logonun laciverti koyu
  yüzeylerde ~1.1:1 kontrastta kaybolduğu için **arayüzde ve pencere/görev
  çubuğu ikonunda her zaman bu varyant kullanılır** (`theme.brand_badge`,
  `theme.app_icon`).

## 3. Ölçekler

- **Spacing** — 4 px tabanlı: 2 / 4 / 8 / 12 / 16 / 24 / 32 / 48.
  Kart iç boşluğu 16, kart içi öğe aralığı 12, ilişkili öğeler arası 8.
- **Radius** — 6 (küçük) / 10 (girdi, buton) / 14 (kart) / 20 (cam panel) / pill.
- **Tipografi** — 1.25 oranlı: 26 display · 19 title · 15 heading · 13 body ·
  12 label · 11 caption · 10 micro. Mikro başlıklarda 1.2 px harf aralığı.
- **Yazı tipleri** — Arayüz: Inter → Segoe UI Variable → Segoe UI.
  Sayılar: JetBrains Mono → Cascadia Mono → Consolas.

## 4. Düzen mimarisi

```
┌──────────────────────────────────────────────────────────────┐
│ ÜST KOMUTA ÇUBUĞU  marka │ link │ pusula │ canlı metrikler │ arm │
├────┬───────────────────────────────────────────┬─────────────┤
│RAIL│              HARİTA + HUD                 │ GÖREV PANELİ│
│ 5  │  cam araç çubuğu · suni ufuk · HUD kartı  │ Plan/Mission│
│sayfa│                                          │ /Depth      │
├────┴───────────────────────────────────────────┴─────────────┤
│ DURUM ŞERİDİ  son olay · waypoint sayısı · saat  (+ konsol)  │
└──────────────────────────────────────────────────────────────┘
```

- **Sol rail (74 px):** LINK · CRAFT · POWER · PILOT · CAM + LOG.
  Dock pencereleri kaldırıldı; kullanıcı artık düzeni bozamaz.
- **Sol panel (340 px):** raile bağlı yığın (`QStackedWidget`), her sayfa kaydırılabilir.
- **Sağ panel (424 px):** Plan / Mission / Depth sekmeleri.
- **Konsol:** varsayılan gizli, LOG düğmesiyle açılan alt çekmece.

### Harita üstü katmanlar (Qt hit-test kuralı)

Harita üstündeki cam paneller iki gruba ayrılır:

| Katman | Ebeveyn | Fare |
|---|---|---|
| Suni ufuk + HUD okuma kartı | `overlay_layer` (`WA_TransparentForMouseEvents`) | Tıklama haritaya geçer |
| Araç çubuğu (katman / poligon / harita araçları) | doğrudan `MapOverlayPane` | Tam etkileşimli |

`WA_TransparentForMouseEvents` işaretli bir widget, Qt'nin `childAt()`
taramasında **tüm alt ağacıyla birlikte** atlanır. Bu yüzden tıklanabilir
hiçbir kontrol şeffaf HUD katmanının içine konulmaz; araç çubuğu pane'in
doğrudan çocuğudur, `resizeEvent` ile sağ üste konumlandırılır ve `raise_()`
ile en üstte tutulur. Harita üstüne yeni bir etkileşimli panel eklerken bu
kural izlenmelidir.

## 5. Bileşenler (`gcs/components.py`)

| Bileşen | Amaç |
|---|---|
| `Card` | Başlık + isteğe bağlı rozet + gövde içeren temel yüzey |
| `MetricTile` / `MetricGrid` | Büyük mono sayı + mikro etiket; birincil okuma birimi |
| `KeyValueRow` | Yoğun listelerde etiket/değer satırı |
| `FormRow` | Etiket üstte, girdi altta — dar panellerde hizalama sorununu çözer |
| `StatusPill` | Renk kodlu durum rozeti (6 ton) |
| `LiveDot` | Bağlantı canlılığı göstergesi |
| `SegmentedControl` | UDP/TCP/Serial, Street/Satellite gibi kompakt seçim |
| `BatteryGauge` | Kademe renkli doluluk çubuğu |
| `MissionProgressBar` | Görev ilerlemesi |
| `Sparkline` | Derinlik trend grafiği |
| `CompassStrip` | Üst çubukta kayan pusula şeridi |
| `DepthLegend` | Derinlik renk skalası lejantı |
| `AttitudeIndicator` | Yenilenmiş suni ufuk |

**Buton varyantları:** `primary` (dolu camgöbeği) · `quiet` (kenarlıklı) ·
`ghost` (şeffaf) · `danger` (kırmızı yumuşak). Ekranda aynı anda tek bir
`primary` buton bulunmalıdır.

### 5.1 Kurulum ekranı bileşenleri (`gcs/setup_widgets.py`)

| Bileşen | Amaç |
|---|---|
| `InfoDot` | Parametrenin Türkçe açıklamasını üstüne gelince gösteren `?` işareti |
| `RcChannelBar` | Canlı PWM değeri + kalibrasyonda yakalanan min/max bandı |
| `BoatPoseView` | İvmeölçer kalibrasyonunun istediği duruşu çizen şema |
| `CompassCoverageRing` | Pusula başına tarama yüzdesi halkası, sonuçta fitness |
| `MotorLayoutView` | Katamaran şeması; tıklanan motor test edilir |
| `StepStrip` | Çok adımlı bir akışta nerede olunduğunu gösteren şerit |

Bu ekranın ilkesi: bir kalibrasyon adımının **ne istediğini anlatmak yerine
göstermek**. "Aracı sol yanına yatırın" cümlesi yoruma açıktır; çizim değildir.

## 6. Harita görsel dili (`web/map.html`)

- Taban katman: CARTO **dark matter** (koyu tema ile uyumlu sokak haritası) veya
  Esri uydu. Geçiş sağ üstteki cam araç çubuğundan.
- Rota: mavi çift katman (geniş %12 opak "glow" + 2.5 px keskin çizgi).
- İz: yeşil çift katman. Waypoint: numaralı camgöbeği halka, ilk nokta dolu.
- Ev: yeşil kare rozet. Araç: camgöbeği ok + nabız halosu + yön konisi.
- Örnek noktalar mor, derinlik ısı haritası 6 kademeli skala.
- Tüm Leaflet kontrolleri cam panel diline uyarlandı; zoom ve ölçek sağ altta.
- Poligon çizimi sırasında ortada ipucu çipi belirir (çift tıklama = bitir).

## 7. Erişilebilirlik

- Gövde metni ve birincil sayılar zemine karşı ≥ 7:1, ikincil metin ≥ 4.5:1.
- Durum yalnızca renkle değil, metinle de aktarılır (`ARMED`, `LOW DEPTH`).
- Odak durumu her etkileşimli öğede aksan renkli kenarlıkla görünür.
- Minimum dokunma/tıklama hedefi 32 px.

## 8. Temayı değiştirmek

`gcs/theme.py` içindeki `Palette` sınıfındaki değerleri değiştirmek tüm
arayüzü ve harita HUD panellerini günceller. `web/map.html` başındaki CSS
değişkenleri aynı değerlerle senkron tutulmalıdır.
