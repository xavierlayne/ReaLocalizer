# ReaLocalizer - BOCW Türkçe Yama & REA Yerelleştirme Stüdyosu

Call of Duty: Black Ops Cold War (T8 Engine) ve IW serisi oyunlar için
tersine mühendislik (REA) prensipleriyle geliştirilmiş profesyonel yerelleştirme ve yama motoru.

---

## 🚀 Yeni REA Özellikleri ve Arayüz Tasarımı

- **🎯 Metin & Çeviri Stüdyosu:** Akıllı arama, çift tıklamayla dize düzenleme, font uyumluluğu modları (UTF-8, Safe-ASCII, CP-1254).
- **🔬 REA Hex & Ofset Denetçisi:** Seçili dize veya başlıkların (IPAK / IWff) 16 baytlık canlı hex dökümü (`0x004A...`), ASCII/glif dökümü ve ofset haritası.
- **⚡ Canlı Bayt Bütçesi ve Taşma Koruması:** Türkçe çevirinin orijinal bayt slotuna sığıp sığmadığını canlı olarak gösteren güvenlik ölçeri (In-place buffer preservation).
- **📦 Varlık & Yedekleme Yöneticisi:** Taranan `.xpak`, `.ff` ve `.str` paketlerinin boyutları, dize sayıları ve tek tıkla orijinal `.bak` yedeğinden geri yükleme mekanizması.
- **🛡️ Ricochet & Süreç Denetçisi:** Oyunun (`BlackOpsColdWar.exe`) çalışıp çalışmadığını arka planda denetler; bellek kilitlenmesini ve dosya bütünlüğü hatalarını önler.
- **💻 Operasyonel REA Konsolu:** Renk kodlu gerçek zamanlı işlem ve ayrıştırma günlüğü.

---

## 📋 Gereksinimler

- Python 3.9 veya üzeri
- Windows 10/11
- `customtkinter>=6.0.0`
- `pillow>=10.0.0`

---

## 🛠️ Kurulum

```bash
cd bocw_tr_patch
python -m pip install -r requirements.txt
```

---

## 🖥️ Kullanım

### Grafik Arayüz (Önerilen)

```bash
python main.py
```

1. **Oyun Klasörü Seç** butonuna tıklayın ve BOCW kurulum klasörünü belirtin.
2. Otomatik tarama ile oyun paketleri listelenir ve dizeler ayıklanır.
3. Düzenleme panelinden çevirileri girin, bayt bütçesi ölçerini kontrol edin.
4. İsterseniz **Otomatik Çevir** ile DeepL/Google API üzerinden toplu çeviri yapın.
5. **Kuru Çalıştır** ile simülasyonu test edin veya **Yamayı Uygula** ile oyun dosyalarına güvenle yazdırın.

---

## 👤 Geliştirici & Katkıcı

- **Geliştirici:** [@xavierlayne](https://github.com/xavierlayne)

