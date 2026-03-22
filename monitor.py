import json
import time
import requests
import threading
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import sys
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

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

# ── Selenium 드라이버 생성 (백그라운드) ──────────────────────
def create_driver():
    opts = Options()
    opts.add_argument("--headless=new")          # 화면에 안 보이게
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--log-level=3")
    opts.add_argument("--silent")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install(), log_path=os.devnull)
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# ── bnkrmall 검색 ─────────────────────────────────────────────
TABS = [
    {"label": "일반 검색",      "search_type": "allTotal",  "tab_param": "Total"},
    {"label": "프리미엄 반다이", "search_type": "Premium",   "tab_param": "Premium"},
]

def fetch_tab(driver, keyword, search_type):
    encoded = requests.utils.quote(keyword)
    url = (f"https://m.bnkrmall.co.kr/mw/goods/search.do"
           f"?sword={encoded}&searchType={search_type}&pageNum=1")
    driver.get(url)

    # 상품 목록 로딩 대기 (최대 8초)
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.thumb-item, .no-results-wrap"))
        )
    except Exception:
        pass

    soup = BeautifulSoup(driver.page_source, "html.parser")
    products = []

    # 상품 없음 체크
    if soup.select_one(".no-results-wrap.active, .no-results-wrap"):
        return products

    items = soup.select("li.thumb-item") or soup.select("li[data-goods-no]")
    for item in items:
        goods_no = item.get("data-goods-no") or item.get("data-goodsno") or ""

        # goodsNo를 링크에서 추출
        if not goods_no:
            import re
            link = item.select_one("a[href*='goodsNo']")
            if link:
                m = re.search(r"goodsNo=(\d+)", link.get("href", ""))
                if m: goods_no = m.group(1)

        name_tag  = (item.select_one(".goods-name") or item.select_one(".prd-name")
                     or item.select_one(".item-name") or item.select_one("a"))
        price_tag = (item.select_one(".goods-price") or item.select_one(".price")
                     or item.select_one("strong"))

        name  = name_tag.get_text(strip=True)  if name_tag  else ""
        price = price_tag.get_text(strip=True) if price_tag else ""

        if name:
            products.append({
                "id":    goods_no or name,
                "name":  name,
                "price": price,
                "url":   f"https://www.bnkrmall.co.kr/goods/detail.do?goodsNo={goods_no}" if goods_no else "",
            })
    return products

def check_all(driver, keywords):
    results, errors = {}, []
    for tab in TABS:
        results[tab["label"]] = {}
        for kw in keywords:
            try:
                results[tab["label"]][kw] = fetch_tab(driver, kw, tab["tab_param"])
            except Exception as e:
                errors.append({"tab": tab["label"], "kw": kw, "msg": str(e)})
                results[tab["label"]][kw] = []
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

# ── 색상 ─────────────────────────────────────────────────────
BG      = "#04050f"
SURFACE = "#0b0d1f"
SRF2    = "#13142a"
BORDER  = "#1e2140"
ACCENT  = "#5b5eff"
ACCENT2 = "#ff5b8d"
ACCENT3 = "#00f0c0"
TEXT    = "#c8caff"
MUTED   = "#9096b8"
SUCCESS = "#4ade80"
ERROR   = "#f87171"
WARN    = "#fde68a"

TAG_COLORS = ["#a0a2ff", "#ff9bb8", "#80f8e0", "#ffd080", "#d0a0ff"]
TAG_BG     = ["#1a1060", "#3a1020", "#0a2a20", "#2a1a00", "#2a1040"]

# ── 메인 앱 ──────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("bnkrmall Monitor")
        self.geometry("500x680")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.cfg       = load_config()
        self.keywords  = list(self.cfg.get("keywords", []))
        self.emails    = list(self.cfg.get("emails", []))
        self.gas_url   = tk.StringVar(value=self.cfg.get("gas_url", ""))
        self.interval  = tk.IntVar(value=self.cfg.get("interval_seconds", 60))

        self.monitoring  = False
        self.snapshot    = None
        self.thread      = None
        self.driver      = None
        self.check_count = 0

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.monitoring = False
        if self.driver:
            try: self.driver.quit()
            except: pass
        self.destroy()

    # ── 전체 레이아웃 ─────────────────────────────────────────
    def _build(self):
        self._build_header()
        self._build_tabs()
        self._build_gas()
        self._build_bottom_bar()
        self._build_log()

    # ── 헤더 ─────────────────────────────────────────────────
    def _build_header(self):
        f = tk.Frame(self, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        f.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(f, text="🛒", bg=SURFACE, fg=TEXT, font=("", 22)).pack(pady=(10, 2))
        tk.Label(f, text="BNKRMALL MONITOR", bg=SURFACE, fg="#ffffff",
                 font=("Courier", 13, "bold")).pack()
        tk.Label(f, text="실시간 신상품 감시 시스템", bg=SURFACE, fg=TEXT,
                 font=("Courier", 8)).pack(pady=(1, 0))
        self.live_lbl = tk.Label(f, text="● STANDBY", bg=SURFACE, fg=TEXT,
                                  font=("Courier", 9, "bold"))
        self.live_lbl.pack(pady=(4, 10))

    # ── 탭 ───────────────────────────────────────────────────
    def _build_tabs(self):
        outer = tk.Frame(self, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        outer.pack(fill="x", padx=12, pady=(8, 0))

        btn_row = tk.Frame(outer, bg=SRF2)
        btn_row.pack(fill="x")
        self.tab_btns = {}
        tabs = [("keywords", "🔎 감시 키워드"), ("gmail", "📧 Gmail 알림"), ("interval", "⏱ 감시 주기")]
        for i, (tid, tlabel) in enumerate(tabs):
            btn = tk.Button(btn_row, text=tlabel, bg=SRF2, fg=MUTED,
                            font=("Courier", 8), relief="flat", cursor="hand2", bd=0,
                            activebackground=SURFACE, activeforeground=TEXT,
                            command=lambda t=tid: self._switch_tab(t))
            btn.pack(side="left", fill="x", expand=True, ipady=7)
            self.tab_btns[tid] = btn
            if i < 2:
                tk.Frame(btn_row, bg=BORDER, width=1).pack(side="left", fill="y")

        self.panel_host = tk.Frame(outer, bg=SURFACE, height=140)
        self.panel_host.pack(fill="x")
        self.panel_host.pack_propagate(False)

        self.panels = {}
        self._build_kw_panel()
        self._build_gmail_panel()
        self._build_interval_panel()
        self._switch_tab("keywords")

    def _switch_tab(self, tid):
        for k, btn in self.tab_btns.items():
            btn.configure(bg=SURFACE if k == tid else SRF2,
                          fg=TEXT    if k == tid else MUTED)
        for k, panel in self.panels.items():
            if k == tid: panel.place(x=0, y=0, relwidth=1, relheight=1)
            else:        panel.place_forget()

    # ── 키워드 패널 ──────────────────────────────────────────
    def _build_kw_panel(self):
        p = tk.Frame(self.panel_host, bg=SURFACE)
        self.panels["keywords"] = p

        self.kw_tag_frame = tk.Frame(p, bg=SURFACE, height=36)
        self.kw_tag_frame.pack(fill="x", padx=10, pady=(8, 4))
        self.kw_tag_frame.pack_propagate(False)
        self._render_kw_tags()

        row = tk.Frame(p, bg=SURFACE)
        row.pack(fill="x", padx=10, pady=(0, 8))
        self.kw_entry = tk.Entry(row, bg="#0d0d1a", fg=TEXT, insertbackground=TEXT,
                                  relief="flat", font=("", 10),
                                  highlightbackground=BORDER, highlightthickness=1)
        self.kw_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        self.kw_entry.bind("<Return>", lambda e: self._add_keyword())
        self.kw_entry.bind("<FocusIn>",  lambda e: self.kw_entry.configure(highlightbackground=ACCENT))
        self.kw_entry.bind("<FocusOut>", lambda e: self.kw_entry.configure(highlightbackground=BORDER))
        tk.Button(row, text="추가", bg=ACCENT, fg="#fff", font=("", 9, "bold"),
                  relief="flat", cursor="hand2", padx=12, pady=5,
                  command=self._add_keyword).pack(side="left")

    def _render_kw_tags(self):
        for w in self.kw_tag_frame.winfo_children(): w.destroy()
        if not self.keywords:
            tk.Label(self.kw_tag_frame, text="// 키워드를 추가해주세요",
                     bg=SURFACE, fg=MUTED, font=("Courier", 9)).pack(anchor="w", pady=6)
            return
        for i, kw in enumerate(self.keywords):
            c, b = TAG_COLORS[i % len(TAG_COLORS)], TAG_BG[i % len(TAG_BG)]
            tag = tk.Frame(self.kw_tag_frame, bg=b, padx=7, pady=2)
            tag.pack(side="left", padx=(0, 5))
            tk.Label(tag, text=kw, bg=b, fg=c, font=("Courier", 9)).pack(side="left")
            if not self.monitoring:
                tk.Button(tag, text="×", bg=b, fg=c, relief="flat", font=("", 10),
                          cursor="hand2", command=lambda k=kw: self._remove_keyword(k)).pack(side="left")

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
        p = tk.Frame(self.panel_host, bg=SURFACE)
        self.panels["gmail"] = p

        self.em_tag_frame = tk.Frame(p, bg=SURFACE, height=36)
        self.em_tag_frame.pack(fill="x", padx=10, pady=(8, 4))
        self.em_tag_frame.pack_propagate(False)
        self._render_em_tags()

        row = tk.Frame(p, bg=SURFACE)
        row.pack(fill="x", padx=10, pady=(0, 4))
        self.em_entry = tk.Entry(row, bg="#0d0d1a", fg=TEXT, insertbackground=TEXT,
                                  relief="flat", font=("", 10),
                                  highlightbackground=BORDER, highlightthickness=1)
        self.em_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        self.em_entry.bind("<Return>", lambda e: self._add_email())
        self.em_entry.bind("<FocusIn>",  lambda e: self.em_entry.configure(highlightbackground=ACCENT2))
        self.em_entry.bind("<FocusOut>", lambda e: self.em_entry.configure(highlightbackground=BORDER))
        tk.Button(row, text="추가", bg=ACCENT2, fg="#fff", font=("", 9, "bold"),
                  relief="flat", cursor="hand2", padx=12, pady=5,
                  command=self._add_email).pack(side="left")

        self.em_err = tk.Label(p, text="", bg=SURFACE, fg=ERROR, font=("Courier", 8))
        self.em_err.pack(anchor="w", padx=10)

    def _render_em_tags(self):
        for w in self.em_tag_frame.winfo_children(): w.destroy()
        if not self.emails:
            tk.Label(self.em_tag_frame, text="// 이메일을 추가해주세요",
                     bg=SURFACE, fg=MUTED, font=("Courier", 9)).pack(anchor="w", pady=6)
            return
        for i, em in enumerate(self.emails):
            c, b = TAG_COLORS[i % len(TAG_COLORS)], TAG_BG[i % len(TAG_BG)]
            tag = tk.Frame(self.em_tag_frame, bg=b, padx=7, pady=2)
            tag.pack(side="left", padx=(0, 5))
            tk.Label(tag, text=em, bg=b, fg=c, font=("Courier", 9)).pack(side="left")
            if not self.monitoring:
                tk.Button(tag, text="×", bg=b, fg=c, relief="flat", font=("", 10),
                          cursor="hand2", command=lambda e=em: self._remove_email(e)).pack(side="left")

    def _add_email(self):
        em = self.em_entry.get().strip()
        if not em: return
        if "@" not in em or "." not in em:
            self.em_err.config(text="⚠ 올바른 이메일 형식이 아니에요"); return
        if em in self.emails:
            self.em_err.config(text="⚠ 이미 추가된 이메일이에요"); return
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

    # ── 감시 주기 패널 ────────────────────────────────────────
    def _build_interval_panel(self):
        p = tk.Frame(self.panel_host, bg=SURFACE)
        self.panels["interval"] = p

        options = [(30,"30초","빠른 감시"),(60,"1분","권장"),(180,"3분","보통"),(300,"5분","느린 감시")]
        grid = tk.Frame(p, bg=SURFACE)
        grid.pack(fill="x", padx=10, pady=8)
        self.int_btns = {}

        for i, (val, lbl, desc) in enumerate(options):
            r, c = divmod(i, 2)
            active = self.interval.get() == val
            bf = tk.Frame(grid, bg=ACCENT if active else "#0d0d1a",
                          highlightbackground=ACCENT if active else BORDER, highlightthickness=1)
            bf.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
            grid.columnconfigure(c, weight=1)
            inn = tk.Frame(bf, bg=bf["bg"])
            inn.pack(expand=True, fill="both", padx=8, pady=6)
            tk.Label(inn, text=lbl, bg=inn["bg"], fg="#fff" if active else MUTED,
                     font=("Courier", 11, "bold")).pack()
            tk.Label(inn, text=desc, bg=inn["bg"], fg="#fff" if active else MUTED,
                     font=("Courier", 7)).pack()
            for w in [bf, inn] + list(inn.winfo_children()):
                w.bind("<Button-1>", lambda e, v=val: self._set_interval(v))
                w.configure(cursor="hand2")
            self.int_btns[val] = (bf, inn)

    def _set_interval(self, val):
        if self.monitoring: return
        self.interval.set(val)
        for v, (bf, inn) in self.int_btns.items():
            active = v == val
            col = ACCENT if active else "#0d0d1a"
            fg  = "#fff" if active else MUTED
            bf.configure(bg=col, highlightbackground=ACCENT if active else BORDER)
            inn.configure(bg=col)
            for w in inn.winfo_children(): w.configure(bg=col, fg=fg)
        self._save()

    # ── GAS URL ───────────────────────────────────────────────
    def _build_gas(self):
        f = tk.Frame(self, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        f.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(f, text="GOOGLE APPS SCRIPT URL", bg=SURFACE, fg=MUTED,
                 font=("Courier", 8)).pack(anchor="w", padx=10, pady=(7, 2))
        e = tk.Entry(f, textvariable=self.gas_url, bg="#0d0d1a", fg=TEXT,
                     insertbackground=TEXT, relief="flat", font=("", 10),
                     highlightbackground=BORDER, highlightthickness=1)
        e.pack(fill="x", padx=10, pady=(0, 8), ipady=5)
        e.bind("<FocusIn>",  lambda ev: e.configure(highlightbackground=ACCENT3))
        e.bind("<FocusOut>", lambda ev: (e.configure(highlightbackground=BORDER), self._save()))

    # ── 채널 배지 + 시작 버튼 ─────────────────────────────────
    def _build_bottom_bar(self):
        badge_row = tk.Frame(self, bg=BG)
        badge_row.pack(fill="x", padx=12, pady=(6, 0))
        for tab in TABS:
            tk.Label(badge_row, text=f"📡 {tab['label']}", bg="#071a10", fg="#6ee7b7",
                     font=("Courier", 8), padx=8, pady=3, relief="solid", bd=1).pack(side="left", padx=(0, 6))

        f = tk.Frame(self, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        f.pack(fill="x", padx=12, pady=(6, 0))
        self.start_btn = tk.Button(f, text="🟢 모니터링 시작", bg=ACCENT, fg="#fff",
                                    font=("", 11, "bold"), relief="flat", cursor="hand2",
                                    command=self._toggle, pady=10)
        self.start_btn.pack(fill="x", padx=10, pady=(10, 4))
        self.status_lbl = tk.Label(f, text="", bg=SURFACE, fg=ACCENT, font=("Courier", 8))
        self.status_lbl.pack(pady=(0, 8))

    # ── 로그 ─────────────────────────────────────────────────
    def _build_log(self):
        f = tk.Frame(self, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        f.pack(fill="both", expand=True, padx=12, pady=(6, 10))

        hdr = tk.Frame(f, bg=SURFACE)
        hdr.pack(fill="x", padx=10, pady=(7, 3))
        tk.Label(hdr, text="시스템 로그", bg=SURFACE, fg=MUTED, font=("Courier", 8)).pack(side="left")
        self.log_count_lbl = tk.Label(hdr, text="", bg=SURFACE, fg=ACCENT, font=("Courier", 8))
        self.log_count_lbl.pack(side="right")

        self.log_txt = tk.Text(f, bg="#04050f", fg=TEXT, font=("Courier", 9),
                                relief="flat", state="disabled", wrap="word",
                                insertbackground=TEXT)
        self.log_txt.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        for tag, color in [("s", SUCCESS),("e", ERROR),("a", ACCENT2),
                            ("i", "#93c5fd"),("g", WARN),("t", MUTED),("n", MUTED)]:
            self.log_txt.tag_configure(tag, foreground=color)

    # ── 로그 추가 ─────────────────────────────────────────────
    def _log(self, msg, tag="n"):
        def _do():
            t = datetime.now().strftime("%H:%M:%S")
            self.log_txt.configure(state="normal")
            self.log_txt.insert("end", t + "  ", "t")
            self.log_txt.insert("end", msg + "\n", tag)
            self.log_txt.configure(state="disabled")
            self.log_txt.see("end")
            lines = int(self.log_txt.index("end-1c").split(".")[0])
            self.log_count_lbl.config(text=f"▶ {lines}건")
        self.after(0, _do)

    # ── 유틸 ─────────────────────────────────────────────────
    def _save(self):
        save_config({"keywords": self.keywords, "emails": self.emails,
                     "interval_seconds": self.interval.get(), "gas_url": self.gas_url.get()})

    def _update_live(self):
        if self.monitoring:
            self.live_lbl.config(text=f"● LIVE · {self.check_count}회 완료", fg=ACCENT3)
        else:
            self.live_lbl.config(text="● STANDBY", fg=TEXT)

    # ── 시작/중지 ─────────────────────────────────────────────
    def _toggle(self):
        if self.monitoring: self._stop()
        else:               self._start()

    def _start(self):
        if not self.keywords:
            messagebox.showwarning("경고", "키워드를 먼저 추가해주세요!"); return
        self._save()
        self.monitoring  = True
        self.snapshot    = None
        self.check_count = 0
        self.start_btn.config(text="🔴 중지", bg="#b91c1c")
        self._log("🟢 모니터링 시작! (백그라운드 크롬 초기화 중...)", "s")
        if self.emails: self._log(f"📧 Gmail 알림 → {len(self.emails)}개 주소", "g")
        self._update_live()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _stop(self):
        self.monitoring = False
        if self.driver:
            try: self.driver.quit()
            except: pass
            self.driver = None
        self.start_btn.config(text="🟢 모니터링 시작", bg=ACCENT)
        self.status_lbl.config(text="")
        self._log("🔴 모니터링 중지", "n")
        self._update_live()

    def _loop(self):
        # 드라이버 초기화
        try:
            self.driver = create_driver()
            self._log("✅ 백그라운드 크롬 실행 완료 (화면에 안 보여요)", "s")
        except Exception as ex:
            self._log(f"❌ 크롬 초기화 실패: {ex}", "e")
            self.after(0, self._stop)
            return

        while self.monitoring:
            self._check()
            for i in range(self.interval.get(), 0, -1):
                if not self.monitoring: return
                self.after(0, lambda s=i: self.status_lbl.config(
                    text=f"다음 검색까지 {s // 60}:{s % 60:02d}"))
                time.sleep(1)

    def _check(self):
        self._log("🔍 bnkrmall 페이지 조회 중...", "n")
        try:
            results, errors = check_all(self.driver, self.keywords)
            for e in errors: self._log(f"⚠️ [{e['tab']}] {e['kw']}: {e['msg']}", "e")
            snap = make_snapshot(results)
            self.check_count += 1
            self.after(0, self._update_live)

            if self.snapshot is None:
                total = sum(len(l) for tab in results.values() for l in tab.values())
                self._log(f"✅ 기준 수집 완료 — 총 {total}개", "s")
                for tl, tab in results.items():
                    for kw, l in tab.items():
                        self._log(f"   📂 [{tl}] \"{kw}\" → {len(l)}개", "i")
                self.snapshot = snap
            else:
                new_items = find_new(self.snapshot, results)
                if new_items:
                    self._log(f"🚨 신상품 {len(new_items)}개 발견!", "a")
                    for p in new_items: self._log(f"   🆕 [{p['tab']}] {p['name']} {p['price']}", "a")
                    self.snapshot = snap
                    gas = self.gas_url.get().strip()
                    if gas and self.emails:
                        self._log(f"📧 Gmail 발송 중 → {len(self.emails)}개 주소", "g")
                        try:
                            ok = send_to_gas(gas, new_items, self.emails)
                            self._log("✅ Gmail 발송 완료!" if ok else "⚠️ 발송 결과 불명확", "s" if ok else "g")
                        except Exception as ex:
                            self._log(f"❌ GAS 오류: {ex}", "e")
                    elif not gas:
                        self._log("⚠️ GAS URL 미설정 — 이메일 발송 건너뜀", "g")
                else:
                    total = sum(len(l) for tab in results.values() for l in tab.values())
                    self._log(f"✅ 변동 없음 ({total}개)", "s")
        except Exception as ex:
            self._log(f"❌ 오류: {ex}", "e")

if __name__ == "__main__":
    App().mainloop()
