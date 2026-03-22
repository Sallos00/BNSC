import json
import time
import requests
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import sys
import os

# ── 설정 저장/로드 ────────────────────────────────────────────
def get_config_path():
    base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
    return os.path.join(base, 'config.json')

def load_config():
    path = get_config_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"keywords": [], "emails": [], "interval_seconds": 60, "gas_url": ""}

def save_config(cfg):
    with open(get_config_path(), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ── bnkrmall API ──────────────────────────────────────────────
APIS = [
    {"label": "일반 검색",      "url": "https://www.bnkrmall.co.kr/goods/search_ajax.do",   "type": "Total"},
    {"label": "프리미엄 반다이", "url": "https://www.bnkrmall.co.kr/goods/search_p_ajax.do", "type": "Premium"},
]

def fetch_products(api_url, keyword, search_type):
    params = {"sword": keyword, "swordList": keyword, "pageNum": 1,
              "searchType": search_type, "sale": "", "reserved": "",
              "soldout": "", "cate": "", "psort": ""}
    headers = {"Referer": "https://www.bnkrmall.co.kr/", "Accept": "application/json"}
    res = requests.get(api_url, params=params, headers=headers, timeout=10)
    res.raise_for_status()
    data = res.json()
    lst = data.get("goodsList") or data.get("list") or data.get("data") or data.get("items") or []
    return [{"id": str(p.get("goodsNo") or p.get("goodsIdx") or p.get("id", "")),
             "name": p.get("goodsNm") or p.get("goodsName") or p.get("name", ""),
             "price": f"{int(p['goodsPrice']):,}원" if p.get("goodsPrice") else "",
             "url": f"https://www.bnkrmall.co.kr/goods/detail.do?goodsNo={p.get('goodsNo','')}"} for p in lst]

def check_all(keywords):
    results, errors = {}, []
    for api in APIS:
        results[api["label"]] = {}
        for kw in keywords:
            try:
                results[api["label"]][kw] = fetch_products(api["url"], kw, api["type"])
            except Exception as e:
                errors.append({"tab": api["label"], "kw": kw, "msg": str(e)})
                results[api["label"]][kw] = []
    return results, errors

def make_snapshot(results):
    ids = set()
    for tab in results.values():
        for lst in tab.values():
            for p in lst: ids.add(p["id"])
    return ids

def find_new(snapshot, results):
    new_items = []
    for tab_label, tab in results.items():
        for lst in tab.values():
            for p in lst:
                if p["id"] not in snapshot:
                    new_items.append({**p, "tab": tab_label})
    return new_items

def send_to_gas(gas_url, new_items, emails):
    payload = {"items": new_items, "emails": emails,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    res = requests.post(gas_url, json=payload, timeout=15)
    return res.status_code == 200

# ── 색상 테마 ─────────────────────────────────────────────────
BG       = "#04050f"
SURFACE  = "#0b0d1f"
SURFACE2 = "#16162a"
BORDER   = "#1e2140"
ACCENT   = "#5b5eff"
ACCENT2  = "#ff5b8d"
ACCENT3  = "#00f0c0"
TEXT     = "#c8caff"
MUTED    = "#4a4d6e"
SUCCESS  = "#4ade80"
ERROR    = "#f87171"
WARN     = "#fde68a"

TAG_COLORS  = ["#a0a2ff", "#ff9bb8", "#80f8e0", "#ffd080", "#d0a0ff"]
TAG_BG      = ["#1a1060", "#3a1020", "#0a2a20", "#2a1a00", "#2a1040"]

# ── GUI 메인 ─────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("bnkrmall Monitor")
        self.geometry("520x720")
        self.minsize(480, 600)
        self.configure(bg=BG)
        self.resizable(True, True)

        self.cfg = load_config()
        self.keywords = list(self.cfg.get("keywords", []))
        self.emails   = list(self.cfg.get("emails", []))
        self.gas_url  = tk.StringVar(value=self.cfg.get("gas_url", ""))
        self.interval = tk.IntVar(value=self.cfg.get("interval_seconds", 60))

        self.monitoring = False
        self.snapshot   = None
        self.thread     = None
        self.check_count = 0

        self._build_ui()

    # ── UI 구성 ───────────────────────────────────────────────
    def _build_ui(self):
        # 스크롤 가능한 메인 캔버스
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=BG)
        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        pad = {"padx": 16, "pady": 6}
        f = self.scroll_frame

        # ── 헤더
        self._header(f)

        # ── 탭
        self._tabs(f)

        # ── GAS URL
        self._gas_section(f)

        # ── 감시 채널 표시
        self._channel_badges(f)

        # ── 시작/중지 버튼
        self._control(f)

        # ── 로그
        self._log_section(f)

    def _frame(self, parent, pady=6):
        frm = tk.Frame(parent, bg=SURFACE, bd=0, highlightbackground=BORDER,
                       highlightthickness=1, relief="flat")
        frm.pack(fill="x", padx=16, pady=(pady, 0))
        return frm

    def _label(self, parent, text, color=MUTED, size=9, bold=False):
        font = ("Courier", size, "bold" if bold else "normal")
        lbl = tk.Label(parent, text=text, bg=parent["bg"], fg=color, font=font)
        lbl.pack(anchor="w", padx=12, pady=(10, 4))
        return lbl

    # ── 헤더 ─────────────────────────────────────────────────
    def _header(self, parent):
        frm = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        frm.pack(fill="x", padx=16, pady=(16, 0))

        tk.Label(frm, text="🛒", bg=SURFACE, fg=TEXT, font=("", 28)).pack(pady=(16, 4))
        tk.Label(frm, text="BNKRMALL MONITOR", bg=SURFACE, fg="#ffffff",
                 font=("Courier", 15, "bold")).pack()
        tk.Label(frm, text="실시간 신상품 감시 시스템", bg=SURFACE, fg=MUTED,
                 font=("Courier", 9)).pack(pady=(2, 0))

        self.live_label = tk.Label(frm, text="● STANDBY", bg=SURFACE, fg=MUTED,
                                   font=("Courier", 10, "bold"))
        self.live_label.pack(pady=(8, 16))

    # ── 탭 ───────────────────────────────────────────────────
    def _tabs(self, parent):
        tab_frame = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        tab_frame.pack(fill="x", padx=16, pady=(10, 0))

        self.tab_buttons = {}
        self.tab_panels  = {}
        tabs = [("keywords", "🔎 감시 키워드"), ("gmail", "📧 Gmail 알림"), ("interval", "⏱ 감시 주기")]

        btn_row = tk.Frame(tab_frame, bg=SURFACE2)
        btn_row.pack(fill="x")

        for i, (tid, tlabel) in enumerate(tabs):
            btn = tk.Button(btn_row, text=tlabel, bg=SURFACE2, fg=MUTED,
                            font=("Courier", 9), relief="flat", cursor="hand2", bd=0,
                            activebackground=SURFACE, activeforeground=TEXT,
                            command=lambda t=tid: self._switch_tab(t))
            btn.pack(side="left", fill="x", expand=True, ipady=8)
            self.tab_buttons[tid] = btn
            if i < len(tabs) - 1:
                tk.Frame(btn_row, bg=BORDER, width=1).pack(side="left", fill="y")

        self.panel_host = tk.Frame(tab_frame, bg=SURFACE)
        self.panel_host.pack(fill="x")

        self._build_keywords_panel()
        self._build_gmail_panel()
        self._build_interval_panel()

        self._switch_tab("keywords")

    def _switch_tab(self, tab_id):
        for tid, btn in self.tab_buttons.items():
            if tid == tab_id:
                btn.configure(bg=SURFACE, fg=TEXT)
            else:
                btn.configure(bg=SURFACE2, fg=MUTED)
        for tid, panel in self.tab_panels.items():
            if tid == tab_id:
                panel.pack(fill="x", padx=12, pady=10)
            else:
                panel.pack_forget()

    # ── 키워드 패널 ──────────────────────────────────────────
    def _build_keywords_panel(self):
        panel = tk.Frame(self.panel_host, bg=SURFACE)
        self.tab_panels["keywords"] = panel

        self.kw_tags_frame = tk.Frame(panel, bg=SURFACE)
        self.kw_tags_frame.pack(fill="x", pady=(0, 8))
        self._render_kw_tags()

        row = tk.Frame(panel, bg=SURFACE)
        row.pack(fill="x")
        self.kw_entry = tk.Entry(row, bg="#0d0d1a", fg=TEXT, insertbackground=TEXT,
                                  relief="flat", font=("", 11), highlightbackground=BORDER,
                                  highlightthickness=1)
        self.kw_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.kw_entry.bind("<Return>", lambda e: self._add_keyword())
        self.kw_entry.insert(0, "")
        self.kw_entry.configure(fg=MUTED)
        self.kw_entry.bind("<FocusIn>",  lambda e: self._entry_focus(self.kw_entry, ACCENT))
        self.kw_entry.bind("<FocusOut>", lambda e: self._entry_blur(self.kw_entry))

        tk.Button(row, text="추가", bg=ACCENT, fg="#fff", font=("", 10, "bold"),
                  relief="flat", cursor="hand2", command=self._add_keyword,
                  padx=14, pady=6).pack(side="left")

        self.kw_hint = tk.Label(panel, text="", bg=SURFACE, fg=MUTED, font=("Courier", 8))
        self.kw_hint.pack(anchor="w", pady=(4, 0))

    def _render_kw_tags(self):
        for w in self.kw_tags_frame.winfo_children(): w.destroy()
        if not self.keywords:
            tk.Label(self.kw_tags_frame, text="// 키워드를 추가해주세요",
                     bg=SURFACE, fg=MUTED, font=("Courier", 9)).pack(anchor="w", pady=4)
            return
        wrap = tk.Frame(self.kw_tags_frame, bg=SURFACE)
        wrap.pack(fill="x")
        for i, kw in enumerate(self.keywords):
            color = TAG_COLORS[i % len(TAG_COLORS)]
            bg    = TAG_BG[i % len(TAG_BG)]
            tag = tk.Frame(wrap, bg=bg, padx=8, pady=3)
            tag.pack(side="left", padx=(0, 6), pady=2)
            tk.Label(tag, text=kw, bg=bg, fg=color, font=("Courier", 10)).pack(side="left")
            if not self.monitoring:
                tk.Button(tag, text="×", bg=bg, fg=color, relief="flat",
                          font=("", 11), cursor="hand2",
                          command=lambda k=kw: self._remove_keyword(k)).pack(side="left", padx=(4, 0))

    def _add_keyword(self):
        kw = self.kw_entry.get().strip()
        if not kw or kw in self.keywords: return
        self.keywords.append(kw)
        self.kw_entry.delete(0, tk.END)
        self._render_kw_tags()
        self._save()

    def _remove_keyword(self, kw):
        if self.monitoring: return
        self.keywords.remove(kw)
        self._render_kw_tags()
        self._save()

    # ── Gmail 패널 ───────────────────────────────────────────
    def _build_gmail_panel(self):
        panel = tk.Frame(self.panel_host, bg=SURFACE)
        self.tab_panels["gmail"] = panel

        tk.Label(panel, text="신상품 감지 시 아래 이메일로 알림을 보내요.", bg=SURFACE,
                 fg=MUTED, font=("", 9), wraplength=400, justify="left").pack(anchor="w", pady=(0, 8))

        self.em_tags_frame = tk.Frame(panel, bg=SURFACE)
        self.em_tags_frame.pack(fill="x", pady=(0, 8))
        self._render_em_tags()

        row = tk.Frame(panel, bg=SURFACE)
        row.pack(fill="x")
        self.em_entry = tk.Entry(row, bg="#0d0d1a", fg=TEXT, insertbackground=TEXT,
                                  relief="flat", font=("", 11), highlightbackground=BORDER,
                                  highlightthickness=1)
        self.em_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.em_entry.bind("<Return>", lambda e: self._add_email())
        self.em_entry.bind("<FocusIn>",  lambda e: self._entry_focus(self.em_entry, ACCENT2))
        self.em_entry.bind("<FocusOut>", lambda e: self._entry_blur(self.em_entry))

        tk.Button(row, text="추가", bg=ACCENT2, fg="#fff", font=("", 10, "bold"),
                  relief="flat", cursor="hand2", command=self._add_email,
                  padx=14, pady=6).pack(side="left")

        self.em_err = tk.Label(panel, text="", bg=SURFACE, fg=ERROR, font=("Courier", 8))
        self.em_err.pack(anchor="w", pady=(4, 0))

        self.em_status = tk.Label(panel, text="— Gmail 알림 미설정", bg=SURFACE,
                                   fg=MUTED, font=("Courier", 9))
        self.em_status.pack(anchor="w", pady=(6, 0))

    def _render_em_tags(self):
        for w in self.em_tags_frame.winfo_children(): w.destroy()
        if not self.emails:
            tk.Label(self.em_tags_frame, text="// 이메일을 추가해주세요",
                     bg=SURFACE, fg=MUTED, font=("Courier", 9)).pack(anchor="w", pady=4)
            return
        wrap = tk.Frame(self.em_tags_frame, bg=SURFACE)
        wrap.pack(fill="x")
        for i, em in enumerate(self.emails):
            color = TAG_COLORS[i % len(TAG_COLORS)]
            bg    = TAG_BG[i % len(TAG_BG)]
            tag = tk.Frame(wrap, bg=bg, padx=8, pady=3)
            tag.pack(side="left", padx=(0, 6), pady=2)
            tk.Label(tag, text=em, bg=bg, fg=color, font=("Courier", 9)).pack(side="left")
            if not self.monitoring:
                tk.Button(tag, text="×", bg=bg, fg=color, relief="flat",
                          font=("", 11), cursor="hand2",
                          command=lambda e=em: self._remove_email(e)).pack(side="left", padx=(4, 0))
        self._update_em_status()

    def _add_email(self):
        em = self.em_entry.get().strip()
        if not em: return
        if "@" not in em or "." not in em:
            self.em_err.config(text="⚠ 올바른 이메일 형식이 아니에요")
            return
        if em in self.emails:
            self.em_err.config(text="⚠ 이미 추가된 이메일이에요")
            return
        self.emails.append(em)
        self.em_entry.delete(0, tk.END)
        self.em_err.config(text="")
        self._render_em_tags()
        self._save()

    def _remove_email(self, em):
        if self.monitoring: return
        self.emails.remove(em)
        self._render_em_tags()
        self._save()

    def _update_em_status(self):
        if self.emails:
            self.em_status.config(text=f"✅ {len(self.emails)}개 주소로 알림 발송", fg=ACCENT3)
        else:
            self.em_status.config(text="— Gmail 알림 미설정", fg=MUTED)

    # ── 감시 주기 패널 ────────────────────────────────────────
    def _build_interval_panel(self):
        panel = tk.Frame(self.panel_host, bg=SURFACE)
        self.tab_panels["interval"] = panel

        options = [(30, "30초", "빠른 감시"), (60, "1분", "권장"),
                   (180, "3분", "보통"), (300, "5분", "느린 감시")]
        grid = tk.Frame(panel, bg=SURFACE)
        grid.pack(fill="x")

        self.int_buttons = {}
        for i, (val, label, desc) in enumerate(options):
            r, c = divmod(i, 2)
            is_active = self.interval.get() == val
            btn_frame = tk.Frame(grid, bg=ACCENT if is_active else "#0d0d1a",
                                  highlightbackground=ACCENT if is_active else BORDER,
                                  highlightthickness=1)
            btn_frame.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            grid.columnconfigure(c, weight=1)

            inner = tk.Frame(btn_frame, bg=btn_frame["bg"])
            inner.pack(expand=True, fill="both", padx=12, pady=10)
            tk.Label(inner, text=label, bg=inner["bg"], fg="#fff" if is_active else MUTED,
                     font=("Courier", 13, "bold")).pack()
            tk.Label(inner, text=desc, bg=inner["bg"], fg="#fff" if is_active else MUTED,
                     font=("Courier", 8)).pack()

            for w in [btn_frame, inner] + inner.winfo_children():
                w.bind("<Button-1>", lambda e, v=val: self._set_interval(v))
                w.configure(cursor="hand2")

            self.int_buttons[val] = (btn_frame, inner)

    def _set_interval(self, val):
        if self.monitoring: return
        self.interval.set(val)
        for v, (btn_frame, inner) in self.int_buttons.items():
            active = v == val
            color = ACCENT if active else "#0d0d1a"
            fg = "#fff" if active else MUTED
            btn_frame.configure(bg=color, highlightbackground=ACCENT if active else BORDER)
            inner.configure(bg=color)
            for w in inner.winfo_children():
                w.configure(bg=color, fg=fg)
        self._save()

    # ── GAS URL 섹션 ─────────────────────────────────────────
    def _gas_section(self, parent):
        frm = self._frame(parent, pady=10)
        self._label(frm, "GOOGLE APPS SCRIPT URL")
        self.gas_entry = tk.Entry(frm, textvariable=self.gas_url, bg="#0d0d1a", fg=TEXT,
                                   insertbackground=TEXT, relief="flat", font=("", 10),
                                   highlightbackground=BORDER, highlightthickness=1)
        self.gas_entry.pack(fill="x", padx=12, pady=(0, 10), ipady=6)
        self.gas_entry.bind("<FocusOut>", lambda e: self._save())

    # ── 채널 배지 ─────────────────────────────────────────────
    def _channel_badges(self, parent):
        frm = tk.Frame(parent, bg=BG)
        frm.pack(fill="x", padx=16, pady=(8, 0))
        for api in APIS:
            badge = tk.Label(frm, text=f"📡 {api['label']}", bg="#071a10", fg="#6ee7b7",
                             font=("Courier", 9), padx=10, pady=3,
                             relief="solid", bd=1)
            badge.pack(side="left", padx=(0, 6))

    # ── 시작/중지 버튼 ────────────────────────────────────────
    def _control(self, parent):
        frm = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        frm.pack(fill="x", padx=16, pady=(10, 0))

        self.start_btn = tk.Button(frm, text="🟢 모니터링 시작", bg=ACCENT, fg="#fff",
                                    font=("", 12, "bold"), relief="flat", cursor="hand2",
                                    command=self._toggle, pady=12)
        self.start_btn.pack(fill="x", padx=12, pady=12)

        self.status_label = tk.Label(frm, text="", bg=SURFACE, fg=ACCENT,
                                      font=("Courier", 9))
        self.status_label.pack(pady=(0, 10))

    def _toggle(self):
        if self.monitoring:
            self._stop()
        else:
            self._start()

    # ── 로그 섹션 ─────────────────────────────────────────────
    def _log_section(self, parent):
        frm = self._frame(parent, pady=10)
        header = tk.Frame(frm, bg=SURFACE)
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(header, text="시스템 로그", bg=SURFACE, fg=MUTED,
                 font=("Courier", 9)).pack(side="left")
        self.log_count_lbl = tk.Label(header, text="", bg=SURFACE, fg=ACCENT,
                                       font=("Courier", 9))
        self.log_count_lbl.pack(side="right")

        self.log_text = tk.Text(frm, bg="#04050f", fg=MUTED, font=("Courier", 9),
                                 relief="flat", height=12, state="disabled",
                                 wrap="word", insertbackground=TEXT)
        self.log_text.pack(fill="x", padx=12, pady=(0, 10))

        # 색상 태그
        self.log_text.tag_configure("success", foreground=SUCCESS)
        self.log_text.tag_configure("error",   foreground=ERROR)
        self.log_text.tag_configure("alert",   foreground=ACCENT2)
        self.log_text.tag_configure("item",    foreground="#93c5fd")
        self.log_text.tag_configure("gmail",   foreground=WARN)
        self.log_text.tag_configure("time",    foreground=MUTED)
        self.log_text.tag_configure("normal",  foreground=MUTED)

        tk.Label(parent, text="bnkrmall Realtime Monitor", bg=BG, fg="#151728",
                 font=("Courier", 8)).pack(pady=(8, 16))

    # ── 로그 추가 ────────────────────────────────────────────
    def _log(self, msg, tag="normal"):
        def _do():
            t = datetime.now().strftime("%H:%M:%S")
            self.log_text.configure(state="normal")
            self.log_text.insert("end", t + "  ", "time")
            self.log_text.insert("end", msg + "\n", tag)
            self.log_text.configure(state="disabled")
            self.log_text.see("end")
            lines = int(self.log_text.index("end-1c").split(".")[0])
            self.log_count_lbl.config(text=f"▶ {lines}건")
        self.after(0, _do)

    # ── 헬퍼 ─────────────────────────────────────────────────
    def _entry_focus(self, entry, color):
        entry.configure(highlightbackground=color, highlightcolor=color)

    def _entry_blur(self, entry):
        entry.configure(highlightbackground=BORDER)

    def _save(self):
        cfg = {"keywords": self.keywords, "emails": self.emails,
               "interval_seconds": self.interval.get(), "gas_url": self.gas_url.get()}
        save_config(cfg)

    def _update_live(self):
        if self.monitoring:
            self.live_label.config(text=f"● LIVE · {self.check_count}회 완료", fg=ACCENT3)
        else:
            self.live_label.config(text="● STANDBY", fg=MUTED)

    # ── 모니터링 시작/중지 ────────────────────────────────────
    def _start(self):
        if not self.keywords:
            messagebox.showwarning("경고", "키워드를 먼저 추가해주세요!")
            return
        self._save()
        self.monitoring  = True
        self.snapshot    = None
        self.check_count = 0
        self.start_btn.config(text="🔴 중지", bg="#b91c1c")
        self._log("🟢 모니터링 시작!", "success")
        if self.emails:
            self._log(f"📧 Gmail 알림 → {len(self.emails)}개 주소", "gmail")
        self._update_live()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _stop(self):
        self.monitoring = False
        self.start_btn.config(text="🟢 모니터링 시작", bg=ACCENT)
        self.status_label.config(text="")
        self._log("🔴 모니터링 중지", "normal")
        self._update_live()

    def _loop(self):
        while self.monitoring:
            self._check()
            interval = self.interval.get()
            for i in range(interval, 0, -1):
                if not self.monitoring: return
                self.after(0, lambda s=i: self.status_label.config(
                    text=f"다음 검색까지 {s // 60}:{s % 60:02d}"))
                time.sleep(1)

    def _check(self):
        self._log("🔍 bnkrmall API 조회 중...", "normal")
        try:
            results, errors = check_all(self.keywords)
            for e in errors:
                self._log(f"⚠️  [{e['tab']}] {e['kw']}: {e['msg']}", "error")

            snap = make_snapshot(results)
            self.check_count += 1
            self.after(0, self._update_live)

            if self.snapshot is None:
                total = sum(len(lst) for tab in results.values() for lst in tab.values())
                self._log(f"✅ 기준 수집 완료 — 총 {total}개 상품", "success")
                for tl, tab in results.items():
                    for kw, lst in tab.items():
                        self._log(f"   📂 [{tl}] \"{kw}\" → {len(lst)}개", "item")
                self.snapshot = snap
            else:
                new_items = find_new(self.snapshot, results)
                if new_items:
                    self._log(f"🚨 신상품 {len(new_items)}개 발견!", "alert")
                    for p in new_items:
                        self._log(f"   🆕 [{p['tab']}] {p['name']} {p['price']}", "alert")
                    self.snapshot = snap

                    gas = self.gas_url.get().strip()
                    if gas and self.emails:
                        self._log(f"📧 Gmail 발송 중 → {len(self.emails)}개 주소", "gmail")
                        try:
                            ok = send_to_gas(gas, new_items, self.emails)
                            self._log("✅ Gmail 발송 완료!" if ok else "⚠️  발송 결과 불명확", "success" if ok else "gmail")
                        except Exception as ex:
                            self._log(f"❌ GAS 오류: {ex}", "error")
                    elif not gas:
                        self._log("⚠️  GAS URL 미설정 — 이메일 발송 건너뜀", "gmail")
                else:
                    total = sum(len(lst) for tab in results.values() for lst in tab.values())
                    self._log(f"✅ 변동 없음 ({total}개)", "success")

        except Exception as ex:
            self._log(f"❌ 오류: {ex}", "error")

if __name__ == "__main__":
    app = App()
    app.mainloop()
