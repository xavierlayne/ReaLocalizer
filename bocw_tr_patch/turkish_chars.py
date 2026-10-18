"""
turkish_chars.py — Call of Duty Türkçe Karakter Uyumluluk Modülü.

Call of Duty oyun motorlarında (IW Engine / Treyarch motorları) varsayılan İngilizce
font atlasları genellikle 128-256 glif içerir ve Türkçe karakterlerin (ş, ğ, ı vb.)
bazıları font tablolarında bulunmaz. Bu durum oyunda '?' veya boş kutucuk olarak görünür.

Bu modül üç çalışma modu sunar:
1. 'safe_ascii' (Güvenli Mod): Türkçe karakterleri font hatası vermeyecek uyumlu karakterlere dönüştürür (ş->s, ğ->g, vb.).
2. 'utf8' / 'raw' (Yerel Font Modu): Eğer oyuna Türkçe font yaması uygulanmışsa tam karakter setini korur.
3. 'cp1254' (Windows-1254 Modu): Bazı CoD motorlarının kullandığı cp1254 yerel karakter seti.
"""

from typing import Dict

TURKISH_TO_SAFE_ASCII: Dict[str, str] = {
    'ı': 'i', 'İ': 'I',
    'ş': 's', 'Ş': 'S',
    'ğ': 'g', 'Ğ': 'G',
    'ç': 'c', 'Ç': 'C',
    'ö': 'o', 'Ö': 'O',
    'ü': 'u', 'Ü': 'U',
}

def convert_turkish_characters(text: str, mode: str = "utf8") -> str:
    """Metni belirtilen karakter uyumluluk moduna göre dönüştürür."""
    if not text:
        return text
        
    if mode == "safe_ascii":
        for tr_char, safe_char in TURKISH_TO_SAFE_ASCII.items():
            text = text.replace(tr_char, safe_char)
        return text
    elif mode in ("utf8", "raw", "font_patched"):
        return text
    elif mode == "cp1254":
        try:
            encoded = text.encode('windows-1254', errors='replace')
            return encoded.decode('windows-1254')
        except Exception:
            return convert_turkish_characters(text, mode="safe_ascii")
    return text
