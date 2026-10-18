"""
gui.py — BOCW T8/IW Engine REA Yerelleştirme, Hex Denetçisi ve Yama Stüdyosu.

Call of Duty: Black Ops Cold War (T8 Engine) ve IW serisi oyunlar için
tersine mühendislik (REA) destekli, modern arayüzlü yerelleştirme paneli.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .xpak import LocalizeEntry, ParseResult, scan_directory
from .translator import export_for_editing, load_override_file, translate_entries
from .patch import apply_translations
from .turkish_chars import convert_turkish_characters


# ---------------------------------------------------------------------------
# REA & Tactical Palette Constants
# ---------------------------------------------------------------------------
BG_DARK          = "#0d0f14"   # Deep obsidian carbon
BG_CARD          = "#151822"   # Elevated tactical panel
BG_CARD_LIGHT    = "#1d212f"   # Input and header surface
ACCENT_AMBER     = "#f59e0b"   # Black Ops signature amber / gold
ACCENT_AMBER_HOV = "#d97706"   # Amber hover
ACCENT_CYAN      = "#06b6d4"   # REA data stream cyan
ACCENT_CYAN_HOV  = "#0891b2"   # Cyan hover
ACCENT_EMERALD   = "#10b981"   # Success / Safe green
ACCENT_ROSE      = "#ef4444"   # Warning / Overflow red
TEXT_MAIN        = "#f8fafc"   # High contrast text
TEXT_MUTED       = "#94a3b8"   # Secondary telemetry text
BORDER_COLOR     = "#262b3d"   # Crisp border accents


# ---------------------------------------------------------------------------
# Helper: Game Process & Safety Check
# ---------------------------------------------------------------------------
def check_game_process_running() -> Tuple[bool, str]:
    """Checks whether BlackOpsColdWar or related executables are running."""
    proc_names = ["BlackOpsColdWar.exe", "BlackOpsColdWar_Retail.exe", "cod.exe"]
    try:
        flags = 0x08000000  # CREATE_NO_WINDOW
        out = subprocess.check_output(
            'tasklist /NH',
            creationflags=flags,
            text=True,
            errors="ignore"
        )
        for p in proc_names:
            if p.lower() in out.lower():
                return True, p
        return False, "Oyun kapalı (Güvenli)"
    except Exception:
        return False, "Süreç taranamadı"


# ---------------------------------------------------------------------------
# Helper: REA Hex Dump Generator
# ---------------------------------------------------------------------------
def format_hex_dump(data: bytes, base_offset: int = 0, highlight_start: int = 0, highlight_len: int = 0) -> str:
    """Generates a standard REA/IDA-style 16-byte hex dump."""
    lines = []
    lines.append(f"{'OFSET (HEX)':<10}  {'00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F':<49}  {'ASCII / GLİF'}")
    lines.append("-" * 78)
    
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hex_parts = []
        for b in chunk:
            hex_parts.append(f"{b:02X}")
        
        # Split into two 8-byte blocks
        first_half = " ".join(hex_parts[:8])
        second_half = " ".join(hex_parts[8:]) if len(hex_parts) > 8 else ""
        hex_str = f"{first_half:<23}  {second_half:<23}"
        
        ascii_str = "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in chunk)
        lines.append(f"0x{base_offset + i:08X}  {hex_str:<49}  |{ascii_str:<16}|")
        
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main Application Window
# ---------------------------------------------------------------------------
class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        
        # Configure CustomTkinter Window
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        self.title("CALL OF DUTY: BLACK OPS COLD WAR // REA YERELLEŞTİRME & YAMA STÜDYOSU • by @xavierlayne")
        self.geometry("1280x840")
        self.minsize(1080, 680)
        self.configure(fg_color=BG_DARK)

        # Internal State
        self._game_dir: Optional[Path] = None
        self._results: List[ParseResult] = []
        self._all_entries: List[LocalizeEntry] = []
        self._entry_to_result: Dict[int, ParseResult] = {}
        self._translations: Dict[str, str] = {}
        self._override_path: Optional[Path] = None
        self._selected_entry: Optional[LocalizeEntry] = None

        self._build_hud_header()
        self._build_action_toolbar()
        self._build_main_workspace()
        self._build_status_footer()
        
        # Initial log
        self._log("REA Yerelleştirme Stüdyosu başlatıldı.", "SYS")
        self._log("Treyarch T8 / IW FastFile ve XPAK binary çözümleyicileri hazır.", "REA")
        self._check_process_status()

    # ------------------------------------------------------------------
    # UI Components
    # ------------------------------------------------------------------

    def _build_hud_header(self) -> None:
        """Top HUD banner with tactical badges and branding."""
        hud = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        hud.pack(fill="x", padx=14, pady=(12, 6))

        left = ctk.CTkFrame(hud, fg_color="transparent")
        left.pack(side="left", padx=16, pady=10)

        title_lbl = ctk.CTkLabel(
            left,
            text="BOCW // REA LOCALIZATION WORKSTATION  [by @xavierlayne]",
            font=ctk.CTkFont(family="Segoe UI Black", size=18, weight="bold"),
            text_color=ACCENT_AMBER
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            left,
            text="T8 IPAK / FastFile Binary In-Place Patch Engine • https://github.com/xavierlayne",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=ACCENT_CYAN
        )
        sub_lbl.pack(anchor="w")

        # Telemetry Status Badges (Right side)
        right = ctk.CTkFrame(hud, fg_color="transparent")
        right.pack(side="right", padx=16, pady=10)

        # Process Status Badge
        self._badge_proc = ctk.CTkLabel(
            right,
            text="PROSES: KONTROL EDİLİYOR",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#202636",
            text_color=ACCENT_CYAN,
            corner_radius=6,
            padx=10,
            pady=4
        )
        self._badge_proc.pack(side="left", padx=4)

        # Ricochet Safety Badge
        self._badge_ricochet = ctk.CTkLabel(
            right,
            text="RICOCHET: GÜVENLİ (IN-PLACE)",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#182c23",
            text_color=ACCENT_EMERALD,
            corner_radius=6,
            padx=10,
            pady=4
        )
        self._badge_ricochet.pack(side="left", padx=4)

        # Slot Protection Badge
        self._badge_memory = ctk.CTkLabel(
            right,
            text="BELLEK: SLOT KORUMALI",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#302315",
            text_color=ACCENT_AMBER,
            corner_radius=6,
            padx=10,
            pady=4
        )
        self._badge_memory.pack(side="left", padx=4)

    def _build_action_toolbar(self) -> None:
        """Tactical action buttons toolbar."""
        bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        bar.pack(fill="x", padx=14, pady=4)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=8, pady=8)

        # Action Buttons
        self._btn_folder = ctk.CTkButton(
            inner,
            text="📁 Oyun Klasörü Seç",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=ACCENT_AMBER,
            hover_color=ACCENT_AMBER_HOV,
            text_color="#111111",
            corner_radius=8,
            command=self._pick_folder
        )
        self._btn_folder.pack(side="left", padx=5)

        self._btn_override = ctk.CTkButton(
            inner,
            text="📥 Çeviri JSON Yükle",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#242b3d",
            hover_color="#313a52",
            text_color=TEXT_MAIN,
            corner_radius=8,
            command=self._load_override
        )
        self._btn_override.pack(side="left", padx=5)

        self._btn_export = ctk.CTkButton(
            inner,
            text="📤 JSON Dışa Aktar",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#242b3d",
            hover_color="#313a52",
            text_color=TEXT_MAIN,
            corner_radius=8,
            command=self._export_json
        )
        self._btn_export.pack(side="left", padx=5)

        self._btn_translate = ctk.CTkButton(
            inner,
            text="⚡ Otomatik Çevir (API)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_CYAN_HOV,
            text_color="#111111",
            corner_radius=8,
            command=self._auto_translate
        )
        self._btn_translate.pack(side="left", padx=5)

        self._btn_dryrun = ctk.CTkButton(
            inner,
            text="🧪 Kuru Çalıştır (Simülasyon)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#2b3145",
            hover_color="#38405a",
            text_color=TEXT_MAIN,
            corner_radius=8,
            command=self._dry_run
        )
        self._btn_dryrun.pack(side="left", padx=5)

        # Prominent Apply Button
        self._btn_apply = ctk.CTkButton(
            inner,
            text="🛡️ YAMAYI UYGULA",
            font=ctk.CTkFont(family="Segoe UI Black", size=13, weight="bold"),
            fg_color=ACCENT_EMERALD,
            hover_color="#059669",
            text_color="#0a1d13",
            corner_radius=8,
            command=self._apply
        )
        self._btn_apply.pack(side="right", padx=6)

    def _build_main_workspace(self) -> None:
        """Main workspace containing the multi-tab interface."""
        self._tabs = ctk.CTkTabview(
            self,
            fg_color=BG_CARD,
            segmented_button_fg_color="#1d2230",
            segmented_button_selected_color=ACCENT_AMBER,
            segmented_button_selected_hover_color=ACCENT_AMBER_HOV,
            segmented_button_unselected_hover_color="#2a3147",
            text_color=TEXT_MAIN,
            corner_radius=10
        )
        self._tabs.pack(fill="both", expand=True, padx=14, pady=6)

        self._tab_strings = self._tabs.add("🎯 METİN & ÇEVİRİ STÜDYOSU")
        self._tab_hex     = self._tabs.add("🔬 REA HEX & OFSET DENETÇİSİ")
        self._tab_assets  = self._tabs.add("📦 VARLIK & YEDEK YÖNETİCİSİ")
        self._tab_sec     = self._tabs.add("🛡️ GÜVENLİK & RİCOCHET")
        self._tab_log     = self._tabs.add("💻 REA KONSOLU")

        self._build_strings_tab()
        self._build_hex_tab()
        self._build_assets_tab()
        self._build_security_tab()
        self._build_log_tab()

    # ------------------------------------------------------------------
    # Tab 1: Metin & Çeviri Stüdyosu
    # ------------------------------------------------------------------

    def _build_strings_tab(self) -> None:
        parent = self._tab_strings

        # Filter and Search Bar
        fbar = ctk.CTkFrame(parent, fg_color=BG_CARD_LIGHT, corner_radius=8)
        fbar.pack(fill="x", padx=10, pady=(8, 6))

        # Search Entry
        ctk.CTkLabel(fbar, text="Arama:", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=TEXT_MAIN).pack(side="left", padx=(12, 6), pady=8)
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._refresh_table())
        self._entry_filter = ctk.CTkEntry(
            fbar,
            textvariable=self._filter_var,
            placeholder_text="Anahtar, İngilizce veya Türkçe metin ara…",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            width=320,
            fg_color="#131620",
            border_color=BORDER_COLOR
        )
        self._entry_filter.pack(side="left", padx=6, pady=8)

        # Untranslated toggle
        self._show_untranslated = tk.BooleanVar(value=False)
        self._chk_untranslated = ctk.CTkCheckBox(
            fbar,
            text="Sadece Çevrilmemiş Olanlar",
            variable=self._show_untranslated,
            command=self._refresh_table,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_MAIN,
            fg_color=ACCENT_AMBER,
            hover_color=ACCENT_AMBER_HOV
        )
        self._chk_untranslated.pack(side="left", padx=14, pady=8)

        # Font / Character Mode
        ctk.CTkLabel(fbar, text="Karakter Uyumluluğu:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_MUTED).pack(side="left", padx=(10, 4))
        self._char_mode_var = tk.StringVar(value="utf8")
        self._char_mode_combo = ctk.CTkComboBox(
            fbar,
            values=["utf8 (Tam Türkçe)", "safe_ascii (Font Hatası Önle)", "cp1254 (Windows-1254)"],
            variable=self._char_mode_var,
            command=self._on_char_mode_change,
            width=180,
            fg_color="#131620",
            border_color=BORDER_COLOR
        )
        self._char_mode_combo.pack(side="left", padx=4, pady=8)

        # Count badge
        self._label_count = ctk.CTkLabel(
            fbar,
            text="0 / 0 String Listeleniyor",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=ACCENT_AMBER
        )
        self._label_count.pack(side="right", padx=14, pady=8)

        # Modern Treeview Table Container
        table_card = ctk.CTkFrame(parent, fg_color="#12151e", corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        table_card.pack(fill="both", expand=True, padx=10, pady=4)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "REA.Treeview",
            background="#12151e",
            foreground="#e2e8f0",
            fieldbackground="#12151e",
            borderwidth=0,
            rowheight=26,
            font=("Segoe UI", 10)
        )
        style.configure(
            "REA.Treeview.Heading",
            background="#1b202e",
            foreground=ACCENT_AMBER,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 10, "bold")
        )
        style.map(
            "REA.Treeview",
            background=[("selected", "#d97706")],
            foreground=[("selected", "#090d16")]
        )

        cols = ("offset", "key", "english", "turkish", "status", "file")
        self._tree = ttk.Treeview(
            table_card,
            columns=cols,
            show="headings",
            selectmode="browse",
            style="REA.Treeview"
        )

        self._tree.heading("offset",  text="Ofset (Hex)")
        self._tree.heading("key",     text="Anahtar (Hash/Ref)")
        self._tree.heading("english", text="Orijinal İngilizce Metin")
        self._tree.heading("turkish", text="Türkçe Çeviri Karşılığı")
        self._tree.heading("status",  text="REA Durumu")
        self._tree.heading("file",    text="Kaynak Dosya")

        self._tree.column("offset",  width=110, anchor="center")
        self._tree.column("key",     width=180, anchor="w")
        self._tree.column("english", width=360, anchor="w")
        self._tree.column("turkish", width=360, anchor="w")
        self._tree.column("status",  width=110, anchor="center")
        self._tree.column("file",    width=140, anchor="w")

        vsb = ctk.CTkScrollbar(table_card, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        vsb.pack(side="right", fill="y", padx=4, pady=4)

        self._tree.bind("<<TreeviewSelect>>", self._on_row_selected)
        self._tree.bind("<Double-1>", self._on_double_click)

        # Live Edit & REA Buffer Safety Meter Card
        edit_card = ctk.CTkFrame(parent, fg_color=BG_CARD_LIGHT, corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        edit_card.pack(fill="x", padx=10, pady=(6, 8))

        # Top line: telemetry of currently selected string
        info_row = ctk.CTkFrame(edit_card, fg_color="transparent")
        info_row.pack(fill="x", padx=12, pady=(6, 2))

        self._lbl_edit_info = ctk.CTkLabel(
            info_row,
            text="Lütfen düzenlemek veya hex incelemesi yapmak için tablodan bir satır seçin.",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=TEXT_MUTED
        )
        self._lbl_edit_info.pack(side="left")

        # REA Safety Badge on edit row
        self._lbl_safety_meter = ctk.CTkLabel(
            info_row,
            text="SLOT DURUMU: —",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            fg_color="#182333",
            text_color=ACCENT_CYAN,
            corner_radius=6,
            padx=8,
            pady=2
        )
        self._lbl_safety_meter.pack(side="right")

        # Edit Inputs Row
        inp_row = ctk.CTkFrame(edit_card, fg_color="transparent")
        inp_row.pack(fill="x", padx=12, pady=(2, 8))

        ctk.CTkLabel(inp_row, text="Türkçe Metin:", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=TEXT_MAIN).pack(side="left", padx=(0, 6))

        self._edit_var = tk.StringVar()
        self._edit_var.trace_add("write", lambda *_: self._update_buffer_safety_meter())
        self._edit_entry = ctk.CTkEntry(
            inp_row,
            textvariable=self._edit_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#11131a",
            border_color=BORDER_COLOR
        )
        self._edit_entry.pack(side="left", fill="x", expand=True, padx=6)
        self._edit_entry.bind("<Return>", lambda _: self._save_edit())

        self._btn_save_edit = ctk.CTkButton(
            inp_row,
            text="💾 Kaydet",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=ACCENT_AMBER,
            hover_color=ACCENT_AMBER_HOV,
            text_color="#111111",
            width=90,
            command=self._save_edit
        )
        self._btn_save_edit.pack(side="left", padx=4)

        self._btn_translate_single = ctk.CTkButton(
            inp_row,
            text="🤖 Çevir",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_CYAN_HOV,
            text_color="#111111",
            width=80,
            command=self._translate_single_entry
        )
        self._btn_translate_single.pack(side="left", padx=4)

        self._btn_font_safe = ctk.CTkButton(
            inp_row,
            text="🔤 Glif Uyumla",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#272e42",
            hover_color="#363f59",
            text_color=TEXT_MAIN,
            width=95,
            command=self._convert_current_to_safe_font
        )
        self._btn_font_safe.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Tab 2: REA Hex & Ofset Denetçisi
    # ------------------------------------------------------------------

    def _build_hex_tab(self) -> None:
        parent = self._tab_hex

        # Split: Header telemetry card
        top_card = ctk.CTkFrame(parent, fg_color=BG_CARD_LIGHT, corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        top_card.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(
            top_card,
            text="T8 / IW FASTFILE VE XPAK İKİLİ (BINARY) DENETÇİSİ",
            font=ctk.CTkFont(family="Segoe UI Black", size=14, weight="bold"),
            text_color=ACCENT_CYAN
        ).pack(anchor="w", padx=12, pady=(8, 2))

        self._hex_meta_lbl = ctk.CTkLabel(
            top_card,
            text="Bir satır seçildiğinde hedef dosyadaki gerçek baytlar ve ofset haritası burada canlı çözümlenir.",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=TEXT_MUTED
        )
        self._hex_meta_lbl.pack(anchor="w", padx=12, pady=(2, 8))

        # Hex viewer card
        hex_card = ctk.CTkFrame(parent, fg_color="#0e1017", corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        hex_card.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self._hex_text = ctk.CTkTextbox(
            hex_card,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0e1017",
            text_color="#38bdf8",
            corner_radius=8
        )
        self._hex_text.pack(fill="both", expand=True, padx=8, pady=8)
        self._hex_text.insert("1.0", "Hex dökümü görüntülemek için 'Metin & Çeviri Stüdyosu' sekmesinden bir dizeye tıklayın veya çift tıklayın.\n")
        self._hex_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Tab 3: Varlık & Paket Ağacı
    # ------------------------------------------------------------------

    def _build_assets_tab(self) -> None:
        parent = self._tab_assets

        top_info = ctk.CTkFrame(parent, fg_color=BG_CARD_LIGHT, corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        top_info.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(
            top_info,
            text="TESPİT EDİLEN PAKETLER (.xpak, .ff, .str) VE YEDEK (.bak) YÖNETİMİ",
            font=ctk.CTkFont(family="Segoe UI Black", size=14, weight="bold"),
            text_color=ACCENT_AMBER
        ).pack(anchor="w", padx=12, pady=(8, 2))

        ctk.CTkLabel(
            top_info,
            text="Yama işlemi uygulanmadan önce tüm orijinal dosyalar otomatik olarak '.bak' uzantısıyla korunur. İstediğiniz zaman orijinal haline geri dönebilirsiniz.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED
        ).pack(anchor="w", padx=12, pady=(2, 8))

        # Asset Table
        ast_card = ctk.CTkFrame(parent, fg_color="#12151e", corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        ast_card.pack(fill="both", expand=True, padx=10, pady=4)

        cols = ("filename", "format", "strings", "size", "backup", "fullpath")
        self._tree_assets = ttk.Treeview(
            ast_card,
            columns=cols,
            show="headings",
            selectmode="browse",
            style="REA.Treeview"
        )
        self._tree_assets.heading("filename", text="Dosya Adı")
        self._tree_assets.heading("format",   text="Format")
        self._tree_assets.heading("strings",  text="Dize Sayısı")
        self._tree_assets.heading("size",     text="Boyut (MB)")
        self._tree_assets.heading("backup",   text="Yedek (.bak) Durumu")
        self._tree_assets.heading("fullpath", text="Tam Yol")

        self._tree_assets.column("filename", width=180, anchor="w")
        self._tree_assets.column("format",   width=110, anchor="center")
        self._tree_assets.column("strings",  width=100, anchor="center")
        self._tree_assets.column("size",     width=90,  anchor="center")
        self._tree_assets.column("backup",   width=150, anchor="center")
        self._tree_assets.column("fullpath", width=340, anchor="w")

        asb = ctk.CTkScrollbar(ast_card, command=self._tree_assets.yview)
        self._tree_assets.configure(yscrollcommand=asb.set)
        self._tree_assets.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        asb.pack(side="right", fill="y", padx=4, pady=4)

        # Asset Actions
        act_card = ctk.CTkFrame(parent, fg_color=BG_CARD_LIGHT, corner_radius=8)
        act_card.pack(fill="x", padx=10, pady=(6, 8))

        ctk.CTkButton(
            act_card,
            text="⏪ Seçili Dosyayı Orijinal Yedekten Geri Yükle",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=ACCENT_AMBER,
            hover_color=ACCENT_AMBER_HOV,
            text_color="#111111",
            command=self._restore_selected_backup
        ).pack(side="left", padx=10, pady=8)

        ctk.CTkButton(
            act_card,
            text="🔄 Tüm Dosyaları Orijinale Çevir",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#2b3145",
            hover_color="#38405a",
            text_color=TEXT_MAIN,
            command=self._restore_all_backups
        ).pack(side="left", padx=6, pady=8)

        ctk.CTkButton(
            act_card,
            text="📂 Dosya Klasörünü Aç",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#242b3d",
            hover_color="#313a52",
            text_color=TEXT_MAIN,
            command=self._open_selected_file_folder
        ).pack(side="right", padx=10, pady=8)

    # ------------------------------------------------------------------
    # Tab 4: REA Güvenlik & Ricochet Denetçisi
    # ------------------------------------------------------------------

    def _build_security_tab(self) -> None:
        parent = self._tab_sec

        card = ctk.CTkFrame(parent, fg_color=BG_CARD_LIGHT, corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="both", expand=True, padx=10, pady=8)

        ctk.CTkLabel(
            card,
            text="RICOCHET ANTI-CHEAT VE TERSİNE MÜHENDİSLİK GÜVENLİK PROTOKOLÜ",
            font=ctk.CTkFont(family="Segoe UI Black", size=15, weight="bold"),
            text_color=ACCENT_EMERALD
        ).pack(anchor="w", padx=16, pady=(14, 6))

        # Live Process Check Card
        proc_box = ctk.CTkFrame(card, fg_color="#12151e", corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        proc_box.pack(fill="x", padx=16, pady=8)

        self._lbl_proc_detail = ctk.CTkLabel(
            proc_box,
            text="Süreç Durumu: Denetleniyor...",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color=ACCENT_CYAN
        )
        self._lbl_proc_detail.pack(side="left", padx=14, pady=12)

        ctk.CTkButton(
            proc_box,
            text="🔄 Yeniden Tara",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=ACCENT_CYAN,
            hover_color=ACCENT_CYAN_HOV,
            text_color="#111111",
            width=110,
            command=self._check_process_status
        ).pack(side="right", padx=12, pady=10)

        # Security Principles Checklist
        principles = [
            ("✅ In-Place Bayt Değişimi", "Bellek adreslerini, ofset tablolarını veya PE başlıklarını bozmaz. Yalnızca metin verisini aynı bayt yuvasına yazar."),
            ("✅ Buffer Overflow / Taşma Koruması", "Türkçe metin orijinalinden uzunsa otomatik olarak kırpılır; yanındaki fonksiyon işaretçilerine (pointers) taşma engellenir."),
            ("✅ Çift Yönlü Güvenli Yedekleme", "Orijinal oyun dosyaları her zaman '.bak' uzantısıyla korunur; tek tıkla %100 orijinal haline döner."),
            ("⚠️ Çevrimiçi Mod (Multiplayer / Warzone) Uyarısı", "Yama Senaryo (Campaign) ve Zombiler modu için optimize edilmiştir. Rekabetçi çevrimiçi modlarda dosya bütünlüğü kontrolü riski olabilir."),
            ("✅ DLL Injection ve Memory Hooking Yoktur", "Oyun çalışırken belleğe müdahale edilmez. Ricochet Kernel sürücüsü yalnızca dosya statik olarak yamalanıp oyun kapalıyken tetiklenmez.")
        ]

        for title, desc in principles:
            p_card = ctk.CTkFrame(card, fg_color="#161924", corner_radius=6)
            p_card.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(p_card, text=title, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=ACCENT_AMBER).pack(anchor="w", padx=10, pady=(6, 1))
            ctk.CTkLabel(p_card, text=desc, font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_MUTED, justify="left").pack(anchor="w", padx=10, pady=(0, 6))

    # ------------------------------------------------------------------
    # Tab 5: REA Konsolu
    # ------------------------------------------------------------------

    def _build_log_tab(self) -> None:
        parent = self._tab_log

        bar = ctk.CTkFrame(parent, fg_color=BG_CARD_LIGHT, corner_radius=8)
        bar.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(bar, text="CANLI TERSİNE MÜHENDİSLİK VE OPERASYON GÜNLÜĞÜ", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=ACCENT_CYAN).pack(side="left", padx=12, pady=6)

        ctk.CTkButton(
            bar,
            text="🧹 Günlüğü Temizle",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#242b3d",
            hover_color="#313a52",
            text_color=TEXT_MAIN,
            width=120,
            command=self._clear_log
        ).pack(side="right", padx=10, pady=6)

        log_card = ctk.CTkFrame(parent, fg_color="#0b0d12", corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        log_card.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self._log_text = ctk.CTkTextbox(
            log_card,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0b0d12",
            text_color="#a5f3fc",
            corner_radius=8
        )
        self._log_text.pack(fill="both", expand=True, padx=8, pady=8)
        self._log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Status Footer
    # ------------------------------------------------------------------

    def _build_status_footer(self) -> None:
        """Footer status bar with progress telemetry."""
        footer = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        footer.pack(fill="x", side="bottom", padx=14, pady=(2, 10))

        # Status text
        self._status_var = tk.StringVar(value="Hazır — Başlamak için oyun klasörünü seçin.")
        self._lbl_status = ctk.CTkLabel(
            footer,
            textvariable=self._status_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MAIN
        )
        self._lbl_status.pack(side="left", padx=14, pady=6)

        # Progress bar
        self._progress = ctk.CTkProgressBar(footer, width=220, fg_color="#1f2433", progress_color=ACCENT_AMBER)
        self._progress.pack(side="right", padx=14, pady=6)
        self._progress.set(0)

        # Game Dir Display
        self._lbl_dir_status = ctk.CTkLabel(
            footer,
            text="Dizin: Seçilmedi",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=TEXT_MUTED
        )
        self._lbl_dir_status.pack(side="right", padx=14)

    # ------------------------------------------------------------------
    # Logging & Telemetry
    # ------------------------------------------------------------------

    def _log(self, msg: str, tag: str = "INFO") -> None:
        time_str = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{time_str}] [{tag:<4}] {msg}\n"
        self._log_text.configure(state="normal")
        self._log_text.insert("end", formatted)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def _status(self, msg: str, color: str = TEXT_MAIN) -> None:
        self._status_var.set(msg)
        self._lbl_status.configure(text_color=color)

    def _check_process_status(self) -> None:
        running, p_name = check_game_process_running()
        if running:
            self._badge_proc.configure(
                text=f"PROSES: {p_name.upper()} ÇALIŞIYOR!",
                fg_color="#3b1717",
                text_color=ACCENT_ROSE
            )
            self._lbl_proc_detail.configure(
                text=f"⚠️ UYARI: {p_name} arka planda çalışıyor! Yama yapmadan önce oyunu kapatın.",
                text_color=ACCENT_ROSE
            )
            self._log(f"Oyun süreci tespit edildi: {p_name}. Yama öncesi kapatılmalıdır.", "WARN")
        else:
            self._badge_proc.configure(
                text="PROSES: OYUN KAPALI (GÜVENLİ)",
                fg_color="#182c23",
                text_color=ACCENT_EMERALD
            )
            self._lbl_proc_detail.configure(
                text="✅ GÜVENLİ: Oyun süreci kapalı. Dosyalar kilitlenmeden doğrudan yamalanabilir.",
                text_color=ACCENT_EMERALD
            )

    # ------------------------------------------------------------------
    # Actions: Folder Scanning
    # ------------------------------------------------------------------

    def _pick_folder(self) -> None:
        d = filedialog.askdirectory(title="BOCW Oyun Klasörünü Seçin")
        if not d:
            return
        self._game_dir = Path(d)
        self._lbl_dir_status.configure(text=f"Dizin: {self._game_dir.name}")
        self._status("Oyun klasörü taranıyor…", ACCENT_AMBER)
        self._progress.set(0.2)
        self._log(f"Klasör taraması başlatıldı: {self._game_dir}", "SCAN")
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self) -> None:
        try:
            self._results = scan_directory(self._game_dir)
            self._all_entries = []
            self._entry_to_result = {}
            for r in self._results:
                for e in r.entries:
                    self._all_entries.append(e)
                    self._entry_to_result[id(e)] = r
            self.after(0, self._on_scan_done)
        except Exception as exc:
            self.after(0, lambda: self._on_scan_error(str(exc)))

    def _on_scan_done(self) -> None:
        n = len(self._all_entries)
        files_count = len(self._results)
        self._progress.set(1.0)
        self._status(f"{n} metin bulundu — {files_count} paket başarıyla incelendi.", ACCENT_EMERALD)
        self._log(f"Tarama tamamlandı: {files_count} dosyada {n} yerelleştirilmiş metin tespit edildi.", "DONE")
        self._refresh_table()
        self._refresh_assets_table()
        self._check_process_status()

    def _on_scan_error(self, err_msg: str) -> None:
        self._progress.set(0)
        self._status(f"Hata: {err_msg}", ACCENT_ROSE)
        self._log(f"Tarama hatası: {err_msg}", "ERR")
        messagebox.showerror("Tarama Hatası", err_msg)

    # ------------------------------------------------------------------
    # Actions: Table Refresh & Filtering
    # ------------------------------------------------------------------

    def _refresh_table(self) -> None:
        ftext = self._filter_var.get().lower().strip()
        only_untr = self._show_untranslated.get()

        for row in self._tree.get_children():
            self._tree.delete(row)

        shown = 0
        char_mode = self._char_mode_var.get().split()[0]

        for entry in self._all_entries:
            tr = self._translations.get(entry.value, "")
            if only_untr and tr:
                continue

            # Filtering
            matches_filter = (
                not ftext
                or ftext in entry.value.lower()
                or ftext in tr.lower()
                or ftext in entry.key.lower()
            )
            if not matches_filter:
                continue

            r = self._entry_to_result.get(id(entry))
            fname = r.source_path.name if r else "—"
            off_str = f"0x{entry.offset:08X}" if entry.offset else "Brute-force"

            # Status determination
            if not tr:
                status_str = "Bekliyor"
                tag = "untranslated"
            else:
                orig_bytes_len = len(entry.value.encode("utf-8"))
                tr_bytes_len = len(tr.encode("utf-8"))
                if tr_bytes_len > orig_bytes_len:
                    status_str = f"Kırpılacak (+{tr_bytes_len - orig_bytes_len}b)"
                    tag = "overflow"
                else:
                    status_str = "Çevrildi (Güvenli)"
                    tag = "translated"

            iid = self._tree.insert(
                "", "end",
                values=(off_str, entry.key[:30], entry.value[:60], tr[:60], status_str, fname)
            )
            self._tree.item(iid, tags=(tag,))
            shown += 1

        self._tree.tag_configure("translated",   background="#13231a", foreground="#4ade80")
        self._tree.tag_configure("untranslated", background="#241517", foreground="#f87171")
        self._tree.tag_configure("overflow",     background="#2a2012", foreground="#fbbf24")

        total = len(self._all_entries)
        self._label_count.configure(text=f"{shown} / {total} Metin")

    def _refresh_assets_table(self) -> None:
        for row in self._tree_assets.get_children():
            self._tree_assets.delete(row)

        for r in self._results:
            p = r.source_path
            size_mb = f"{p.stat().st_size / (1024 * 1024):.2f}" if p.exists() else "—"
            bak = p.with_suffix(p.suffix + ".bak")
            bak_status = "✅ Yedek Var (.bak)" if bak.exists() else "—"
            fmt = r.format_detected.upper()

            self._tree_assets.insert(
                "", "end",
                values=(p.name, fmt, len(r.entries), size_mb, bak_status, str(p))
            )

    # ------------------------------------------------------------------
    # Actions: Row Selection & REA Hex Inspector
    # ------------------------------------------------------------------

    def _on_row_selected(self, event: tk.Event) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        item = self._tree.item(sel[0])
        vals = item["values"]
        if not vals:
            return

        off_str, key_str, eng_val, tr_val, _, fname = vals

        # Find matching entry
        matched_entry = None
        for e in self._all_entries:
            if e.key.startswith(key_str) and e.value.startswith(eng_val[:30]):
                matched_entry = e
                break

        if not matched_entry:
            return

        self._selected_entry = matched_entry
        curr_tr = self._translations.get(matched_entry.value, "")
        self._edit_var.set(curr_tr)

        # Update edit row info
        r = self._entry_to_result.get(id(matched_entry))
        f_display = r.source_path.name if r else fname
        self._lbl_edit_info.configure(
            text=f"Seçili: [Ofset: {off_str}] | [Paket: {f_display}] | [Anahtar: {matched_entry.key[:45]}]",
            text_color=ACCENT_AMBER
        )

        self._update_buffer_safety_meter()
        self._load_hex_view_for_entry(matched_entry, r)

    def _on_double_click(self, event: tk.Event) -> None:
        self._on_row_selected(event)
        self._edit_entry.focus_set()
        self._edit_entry.selection_range(0, "end")

    def _update_buffer_safety_meter(self) -> None:
        if not self._selected_entry:
            self._lbl_safety_meter.configure(text="SLOT DURUMU: —", text_color=TEXT_MUTED)
            return

        orig_len = len(self._selected_entry.value.encode("utf-8"))
        new_text = self._edit_var.get()
        new_len = len(new_text.encode("utf-8"))

        if not new_text:
            self._lbl_safety_meter.configure(
                text=f"SLOT BÜTÇESİ: {orig_len} bayt (Henüz çevrilmedi)",
                text_color=TEXT_MUTED,
                fg_color="#1d2230"
            )
        elif new_len <= orig_len:
            padding = orig_len - new_len
            self._lbl_safety_meter.configure(
                text=f"✅ GÜVENLİ: {new_len}/{orig_len} bayt (+{padding} bayt null dolgu)",
                text_color=ACCENT_EMERALD,
                fg_color="#14261d"
            )
        else:
            overflow = new_len - orig_len
            self._lbl_safety_meter.configure(
                text=f"⚠️ TAŞMA: {new_len}/{orig_len} bayt! ({overflow} bayt otomatik kırpılacak)",
                text_color=ACCENT_ROSE,
                fg_color="#331719"
            )

    def _load_hex_view_for_entry(self, entry: LocalizeEntry, result: Optional[ParseResult]) -> None:
        if not result or not result.source_path.exists():
            return

        p = result.source_path
        offset = entry.offset

        try:
            with open(p, "rb") as f:
                if offset > 0:
                    read_start = max(0, offset - 32)
                    f.seek(read_start)
                    data = f.read(128)
                    base_off = read_start
                else:
                    f.seek(0)
                    data = f.read(128)
                    base_off = 0

            hex_dump = format_hex_dump(data, base_offset=base_off)
            
            # Format header telemetry
            magic = data[:4]
            magic_hex = " ".join(f"{b:02X}" for b in magic)
            magic_str = "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in magic)
            
            meta_text = (
                f"Dosya: {p.name} | Boyut: {p.stat().st_size:,} bayt | Magic: [{magic_hex}] '{magic_str}'\n"
                f"Hedef Dize Ofseti: 0x{offset:08X} | Orijinal Dize Uzunluğu: {len(entry.value)} karakter ({len(entry.value.encode('utf-8'))} bayt UTF-8)"
            )
            self._hex_meta_lbl.configure(text=meta_text, text_color=ACCENT_CYAN)

            self._hex_text.configure(state="normal")
            self._hex_text.delete("1.0", "end")
            self._hex_text.insert("1.0", hex_dump)
            self._hex_text.configure(state="disabled")

        except Exception as exc:
            self._log(f"Hex dökümü okunurken hata: {exc}", "ERR")

    # ------------------------------------------------------------------
    # Actions: Edit Saving & Translation
    # ------------------------------------------------------------------

    def _save_edit(self) -> None:
        if not self._selected_entry:
            return
        new_val = self._edit_var.get()
        self._translations[self._selected_entry.value] = new_val
        self._log(f"Çeviri güncellendi: [{self._selected_entry.key[:25]}] -> '{new_val[:30]}'", "EDIT")
        self._refresh_table()
        self._status(f"Kaydedildi: {self._selected_entry.key[:30]}…", ACCENT_EMERALD)

    def _translate_single_entry(self) -> None:
        if not self._selected_entry:
            return
        val = self._selected_entry.value
        self._status("Tekil dize çevriliyor…", ACCENT_CYAN)
        threading.Thread(target=self._translate_single_thread, args=(val,), daemon=True).start()

    def _translate_single_thread(self, text: str) -> None:
        try:
            res = translate_entries([text], verbose=False)
            tr = res.get(text, text)
            self._translations[text] = tr
            self.after(0, lambda: self._edit_var.set(tr))
            self.after(0, self._save_edit)
            self.after(0, lambda: self._status("Çeviri tamamlandı.", ACCENT_EMERALD))
        except Exception as exc:
            self.after(0, lambda: self._status(f"Çeviri hatası: {exc}", ACCENT_ROSE))

    def _convert_current_to_safe_font(self) -> None:
        curr = self._edit_var.get()
        if not curr:
            return
        safe_text = convert_turkish_characters(curr, mode="safe_ascii")
        self._edit_var.set(safe_text)
        self._save_edit()
        self._log(f"Glif uyumluluğu uygulandı: '{curr}' -> '{safe_text}'", "GLYPH")

    def _on_char_mode_change(self, choice: str) -> None:
        mode = choice.split()[0]
        self._log(f"Karakter modu değiştirildi: {mode}", "SYS")
        self._refresh_table()

    # ------------------------------------------------------------------
    # Actions: Auto Translation (Batch)
    # ------------------------------------------------------------------

    def _auto_translate(self) -> None:
        untranslated = [e.value for e in self._all_entries if e.value not in self._translations]
        if not untranslated:
            messagebox.showinfo("Bilgi", "Tüm metinler zaten çevrilmiş!")
            return

        ans = messagebox.askyesno(
            "Otomatik Çeviri",
            f"{len(untranslated)} adet çevrilmemiş metin tespit edildi.\n"
            f"API (DeepL / Google / Önbellek) kullanılarak çevrilsin mi?"
        )
        if not ans:
            return

        self._status(f"{len(untranslated)} metin otomatik çevriliyor…", ACCENT_AMBER)
        self._progress.set(0.3)
        self._log(f"Toplu çeviri başlatıldı: {len(untranslated)} metin", "TR")
        threading.Thread(target=self._translate_batch_thread, args=(untranslated,), daemon=True).start()

    def _translate_batch_thread(self, strings: List[str]) -> None:
        try:
            result = translate_entries(strings, verbose=True)
            self._translations.update(result)
            self.after(0, self._refresh_table)
            self.after(0, lambda: self._on_batch_translate_done(len(result)))
        except Exception as exc:
            self.after(0, lambda: self._status(f"Çeviri hatası: {exc}", ACCENT_ROSE))
            self.after(0, lambda: self._log(f"Çeviri hatası: {exc}", "ERR"))

    def _on_batch_translate_done(self, count: int) -> None:
        self._progress.set(1.0)
        self._status(f"{count} metin başarıyla çevrildi.", ACCENT_EMERALD)
        self._log(f"Toplu çeviri tamamlandı: {count} metin havuza eklendi.", "DONE")
        messagebox.showinfo("Başarılı", f"{count} metin başarıyla çevrildi.")

    # ------------------------------------------------------------------
    # Actions: JSON Import / Export
    # ------------------------------------------------------------------

    def _load_override(self) -> None:
        p = filedialog.askopenfilename(
            title="Çeviri JSON Dosyası Seç",
            filetypes=[("JSON Dosyaları", "*.json"), ("Tüm Dosyalar", "*.*")]
        )
        if not p:
            return
        self._override_path = Path(p)
        try:
            overrides = load_override_file(self._override_path)
            for en, tr in overrides.items():
                self._translations[en] = tr
            self._status(f"{len(overrides)} çeviri JSON dosyasından yüklendi.", ACCENT_EMERALD)
            self._log(f"Çeviri JSON yüklendi: {len(overrides)} kayıt ({p})", "JSON")
            self._refresh_table()
        except Exception as exc:
            self._status(f"JSON yükleme hatası: {exc}", ACCENT_ROSE)
            messagebox.showerror("Hata", f"JSON yüklenemedi: {exc}")

    def _export_json(self) -> None:
        p = filedialog.asksaveasfilename(
            title="Çevirileri JSON Olarak Dışa Aktar",
            defaultextension=".json",
            filetypes=[("JSON Dosyaları", "*.json")]
        )
        if not p:
            return
        strings = [e.value for e in self._all_entries]
        try:
            export_for_editing(strings, Path(p), self._translations)
            self._status(f"JSON dışa aktarıldı: {Path(p).name}", ACCENT_EMERALD)
            self._log(f"Çeviriler JSON olarak kaydedildi: {p}", "EXPORT")
            messagebox.showinfo("Başarılı", f"Dosya kaydedildi:\n{p}")
        except Exception as exc:
            self._status(f"Dışa aktarma hatası: {exc}", ACCENT_ROSE)

    # ------------------------------------------------------------------
    # Actions: Dry-Run & Patching
    # ------------------------------------------------------------------

    def _dry_run(self) -> None:
        self._run_patch(dry_run=True)

    def _apply(self) -> None:
        # Check if game is running before applying
        running, p_name = check_game_process_running()
        if running:
            ans = messagebox.askyesno(
                "Süreç Uyarısı",
                f"{p_name} oyunu şu anda açık görünüyor!\n"
                f"Oyun açıkken dosyaları yamalamak dosya kilitlenme hatalarına veya Ricochet bütünlük uyarılarına sebep olabilir.\n\n"
                f"Yine de devam etmek istiyor musunuz?"
            )
            if not ans:
                return

        if not messagebox.askyesno(
            "Yama Onayı",
            "BOCW oyun dosyaları in-place bayt yamasıyla değiştirilecektir.\n"
            "Orijinal dosyalar otomatik olarak '.bak' olarak yedeklenecektir.\n\n"
            "Devam etmek istiyor musunuz?"
        ):
            return

        self._run_patch(dry_run=False)

    def _run_patch(self, dry_run: bool) -> None:
        if not self._results:
            self._status("Önce bir oyun klasörü seçin.", ACCENT_AMBER)
            messagebox.showwarning("Uyarı", "Lütfen önce oyun klasörünü seçip tarayın.")
            return

        all_msgs: List[str] = []
        mode = "KURU ÇALIŞMA (SİMÜLASYON)" if dry_run else "GERÇEK YAMA"
        self._log(f"Yama operasyonu başlatıldı: {mode}", "PATCH")

        char_mode = self._char_mode_var.get().split()[0]

        for r in self._results:
            tr_map = {}
            for e in r.entries:
                if e.value in self._translations:
                    raw_tr = self._translations[e.value]
                    tr_map[e.key] = convert_turkish_characters(raw_tr, mode=char_mode)
                else:
                    tr_map[e.key] = e.value

            msgs = apply_translations(r, tr_map, dry_run=dry_run)
            all_msgs.extend(msgs)
            for m in msgs:
                self._log(f"[{r.source_path.name}] {m}", "WARN")

        tag_color = ACCENT_AMBER if all_msgs else ACCENT_EMERALD
        lbl = "Kuru Çalıştırma" if dry_run else "Yama"
        self._status(f"{lbl} tamamlandı! {len(all_msgs)} uyarı kaydedildi.", tag_color)
        self._log(f"{lbl} operasyonu bitti. {len(all_msgs)} adet bayt kırpma / ofset uyarısı.", "DONE")
        self._refresh_assets_table()

        if dry_run:
            messagebox.showinfo("Kuru Çalıştırma Tamamlandı", f"Simülasyon tamamlandı. {len(all_msgs)} dize orijinal bayt sınırına göre ayarlandı.")
        else:
            messagebox.showinfo("Yama Başarılı", f"Türkçe yama oyun dosyalarına yazıldı!\nOrijinal dosyalar '.bak' olarak güvenle yedeklendi.")

    # ------------------------------------------------------------------
    # Actions: Backup & Restore
    # ------------------------------------------------------------------

    def _restore_selected_backup(self) -> None:
        sel = self._tree_assets.selection()
        if not sel:
            messagebox.showwarning("Seçim Yok", "Lütfen tablodan geri yüklenecek bir dosya seçin.")
            return

        item = self._tree_assets.item(sel[0])
        fullpath = item["values"][5]
        target_file = Path(fullpath)
        bak_file = target_file.with_suffix(target_file.suffix + ".bak")

        if not bak_file.exists():
            messagebox.showinfo("Yedek Yok", f"{target_file.name} için bir .bak yedek dosyası bulunamadı.")
            return

        if messagebox.askyesno("Geri Yükle", f"{target_file.name} orijinal yedeğinden geri yüklensin mi?"):
            try:
                shutil.copy2(bak_file, target_file)
                self._log(f"Orijinal yedek geri yüklendi: {target_file.name}", "RESTORE")
                self._status(f"{target_file.name} orijinal haline döndürüldü.", ACCENT_EMERALD)
                self._refresh_assets_table()
                messagebox.showinfo("Başarılı", f"{target_file.name} başarıyla orijinal haline geri döndürüldü.")
            except Exception as exc:
                self._log(f"Geri yükleme hatası: {exc}", "ERR")
                messagebox.showerror("Hata", f"Geri yüklenemedi: {exc}")

    def _restore_all_backups(self) -> None:
        if not self._results:
            return
        if not messagebox.askyesno("Tümünü Geri Yükle", "Taranan tüm paketler orijinal .bak yedeklerinden geri yüklensin mi?"):
            return

        restored = 0
        for r in self._results:
            p = r.source_path
            bak = p.with_suffix(p.suffix + ".bak")
            if bak.exists():
                try:
                    shutil.copy2(bak, p)
                    restored += 1
                except Exception as exc:
                    self._log(f"Hata [{p.name}]: {exc}", "ERR")

        self._log(f"{restored} adet dosya orijinal yedeğine döndürüldü.", "RESTORE")
        self._status(f"{restored} dosya başarıyla orijinal yedeğine döndürüldü.", ACCENT_EMERALD)
        self._refresh_assets_table()
        messagebox.showinfo("Tamamlandı", f"{restored} adet dosya orijinal haline getirildi.")

    def _open_selected_file_folder(self) -> None:
        sel = self._tree_assets.selection()
        if not sel:
            return
        fullpath = self._tree_assets.item(sel[0])["values"][5]
        folder = str(Path(fullpath).parent)
        try:
            os.startfile(folder)
        except Exception as exc:
            self._log(f"Klasör açılamadı: {exc}", "ERR")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run() -> None:
    app = App()
    app.mainloop()
