import json
import time
import requests
import threading
import tkinter as tk
from tkinter import messagebox
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
    return [{"id":    str(p.get("goodsNo") or p.get("goodsIdx") or p.get("id", "")),
             "name":  p.get("goodsNm") or p.get("goodsName") or p.get("name", ""),
             "price": f"{int(p['goodsPrice']):,}원" if p.get("goodsPrice") else "",
             "url":   f"https://www.bnkrmall.co.kr/goods/detail.do?goodsNo={p.get('goodsNo','')}"} for p in lst]

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
BG      = "#04050f"
SURFACE = "#0b0d1f"
SRF2    = "#16162a"
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

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("bnkrmall Monitor")
        self.geometry("520x740")
        self.configure(bg=BG)
        self.resizable(False, False)

        self.cfg         = load_config()
        self.keywords    = list(self.cfg.get("keywords", []))
        self.emails      = list(self.cfg.get("emails", []))
        self.gas_url_var = tk.StringVar(value=self.cfg.get("gas_url", ""))
        self.interval    = tk.IntVar(value=self.cfg.get("interval_seconds", 60))

        self.monitoring   = False
        self.snapshot     = None
        self.thread       = None
        self.check_count  = 0

        self._build_ui()

    # ── 스크롤 가능한 메인 프레임 ────────────────────────────
    def _build_ui(self):
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.sf = tk.Frame(canvas, bg=BG)
        self.sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.sf, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._header()
        self._tabs()
        self._gas_section()
        self._channel_badges()
        self._control()
        self._log_section()

    # ── 헤더 ─────────────────────────────────────────────────
    def _header(self):
        frm = self._card(pady=(16, 0))
        tk.Label(frm, text="🛒", bg=SURFACE, fg=TEXT, font=("", 26)).pack(pady=(14, 4))
        tk.Label(frm, text="BNKRMALL MONITOR", bg=SURFACE, fg="#ffffff",
                 font=("Courier", 14, "bold")).pack()
        tk.Label(frm, text="실시간 신상품 감시 시스템", bg=SURFACE, fg=TEXT,
                 font=("Courier", 9)).pack(pady=(2, 0))
        self.live_lbl = tk.Label(frm, text="● STANDBY", bg=SURFACE, fg=TEXT,
                                  font=("Courier", 10, "bold"))
        self.live_lbl.pack(pady=(8, 14))

    # ── 탭 ───────────────────────────────────────────────────
    def _tabs(self):
        outer = self._card(pady=(10, 0))
        btn_row = tk.Frame(outer, bg=SRF2)
        btn_row.pack(fill="x")

        self.tab_btns   = {}
        self.tab_panels = {}
        tabs = [("keywords", "🔎 감시 키워드"),
                ("gmail",    "📧 Gmail 알림"),
                ("interval", "⏱ 감시 주기")]

        for i, (tid, lbl) in enumerate(tabs):
            b = tk.Button(btn_row, text=lbl, bg=SRF2, fg=MUTED,
                          font=("Courier", 9), relief="flat", cursor="hand2", bd=0,
                          activebackground=SURFACE, activeforeground=TEXT,
                          command=lambda t=tid: self._switch_tab(t))
            b.pack(side="left", fill="x", expand=True, ipady=9)
            self.tab_btns[tid] = b
            if i < len(tabs) - 1:
                tk.Frame(btn_row, bg=BORDER, width=1).pack(side="left", fill="y")

        self.panel_host = tk.Frame(outer, bg=SURFACE)
        self.panel_host.pack(fill="x")

        self._kw_panel()
        self._gm_panel()
        self._iv_panel()
        self._switch_tab("keywords")

    def _switch_tab(self, tid):
        for k, b in self.tab_btns.items():
            b.configure(bg=SURFACE if k == tid else SRF2,
                        fg=TEXT    if k == tid else MUTED)
        for k, p in self.tab_panels.items():
            if k == tid: p.pack(fill="x", padx=12, pady=10)
            else:        p.pack_forget()

    # ── 키워드 패널 ──────────────────────────────────────────
    def _kw_panel(self):
        p = tk.Frame(self.panel_host, bg=SURFACE)
        self.tab_panels["keywords"] = p

        self.kw_tag_frm = tk.Frame(p, bg=SURFACE)
        self.kw_tag_frm.pack(fill="x", pady=(0, 8))
        self._render_kw_tags()

        row = tk.Frame(p, bg=SURFACE)
        row.pack(fill="x")
        self.kw_ent = self._entry(row, ACCENT)
        self.kw_ent.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.kw_ent.bind("<Return>", lambda e: self._add_kw())
        self._btn(row, "추가", ACCENT, self._add_kw).pack(side="left")

        self.kw_hint = tk.Label(p, text="", bg=SURFACE, fg=MUTED, font=("Courier", 8))
        self.kw_hint.pack(anchor="w", pady=(4, 0))

    def _render_kw_tags(self):
        for w in self.kw_tag_frm.winfo_children(): w.destroy()
        if not self.keywords:
            tk.Label(self.kw_tag_frm, text="// 키워드를 추가해주세요",
                     bg=SURFACE, fg=MUTED, font=("Courier", 9)).pack(anchor="w", pady=4)
            return
        wrap = tk.Frame(self.kw_tag_frm, bg=SURFACE)
        wrap.pack(fill="x")
        for i, kw in enumerate(self.keywords):
            c, bg = TAG_COLORS[i % len(TAG_COLORS)], TAG_BG[i % len(TAG_BG)]
            tag = tk.Frame(wrap, bg=bg, padx=8, pady=3)
            tag.pack(side="left", padx=(0, 6), pady=2)
            tk.Label(tag, text=kw, bg=bg, fg=c, font=("Courier", 10)).pack(side="left")
            if not self.monitoring:
                tk.Button(tag, text="×", bg=bg, fg=c, relief="flat", font=("", 11),
                          cursor="hand2", command=lambda k=kw: self._rm_kw(k)).pack(side="left", padx=(4, 0))

    def _add_kw(self):
        kw = self.kw_ent.get().strip()
        if not kw or kw in self.keywords: return
        self.keywords.append(kw)
        self.kw_ent.delete(0, tk.END)
        self._render_kw_tags()
        self._save()

    def _rm_kw(self, kw):
        if self.monitoring: return
        self.keywords.remove(kw)
        self._render_kw_tags()
        self._save()

    # ── Gmail 패널 ───────────────────────────────────────────
    def _gm_panel(self):
        p = tk.Frame(self.panel_host, bg=SURFACE)
        self.tab_panels["gmail"] = p

        tk.Label(p, text="신상품 감지 시 아래 이메일로 알림을 보내요.",
                 bg=SURFACE, fg=MUTED, font=("", 9), wraplength=380, justify="left").pack(anchor="w", pady=(0, 8))

        self.em_tag_frm = tk.Frame(p, bg=SURFACE)
        self.em_tag_frm.pack(fill="x", pady=(0, 8))
        self._render_em_tags()

        row = tk.Frame(p, bg=SURFACE)
        row.pack(fill="x")
        self.em_ent = self._entry(row, ACCENT2)
        self.em_ent.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.em_ent.bind("<Return>", lambda e: self._add_em())
        self._btn(row, "추가", ACCENT2, self._add_em).pack(side="left")

        self.em_err = tk.Label(p, text="", bg=SURFACE, fg=ERROR, font=("Courier", 8))
        self.em_err.pack(anchor="w", pady=(4, 0))

        self.em_status = tk.Label(p, text="— Gmail 알림 미설정", bg=SURFACE,
                                   fg=MUTED, font=("Courier", 9))
        self.em_status.pack(anchor="w", pady=(6, 0))

    def _render_em_tags(self):
        for w in self.em_tag_frm.winfo_children(): w.destroy()
        if not self.emails:
            tk.Label(self.em_tag_frm, text="// 이메일을 추가해주세요",
                     bg=SURFACE, fg=MUTED, font=("Courier", 9)).pack(anchor="w", pady=4)
            return
        wrap = tk.Frame(self.em_tag_frm, bg=SURFACE)
        wrap.pack(fill="x")
        for i, em in enumerate(self.emails):
            c, bg = TAG_COLORS[i % len(TAG_COLORS)], TAG_BG[i % len(TAG_BG)]
            tag = tk.Frame(wrap, bg=bg, padx=8, pady=3)
            tag.pack(side="left", padx=(0, 6), pady=2)
            tk.Label(tag, text=em, bg=bg, fg=c, font=("Courier", 9)).pack(side="left")
            if not self.monitoring:
                tk.Button(tag, text="×", bg=bg, fg=c, relief="flat", font=("", 11),
                          cursor="hand2", command=lambda e=em: self._rm_em(e)).pack(side="left", padx=(4, 0))
        self.em_status.config(text=f"✅ {len(self.emails)}개 주소로 알림 발송", fg=ACCENT3)

    def _add_em(self):
        em = self.em_ent.get().strip()
        if not em: return
        if "@" not in em or "." not in em:
            self.em_err.config(text="⚠ 올바른 이메일 형식이 아니에요"); return
        if em in self.emails:
            self.em_err.config(text="⚠ 이미 추가된 이메일이에요"); return
        self.emails.append(em)
        self.em_ent.delete(0, tk.END)
        self.em_err.config(text="")
        self._render_em_tags()
        self._save()

    def _rm_em(self, em):
        if self.monitoring: return
        self.emails.remove(em)
        self._render_em_tags()
        self._save()

    # ── 감시 주기 패널 ────────────────────────────────────────
    def _iv_panel(self):
        p = tk.Frame(self.panel_host, bg=SURFACE)
        self.tab_panels["interval"] = p

        options = [(30, "30초", "빠른 감시"), (60, "1분", "권장"),
                   (180, "3분", "보통"),      (300, "5분", "느린 감시")]
        grid = tk.Frame(p, bg=SURFACE)
        grid.pack(fill="x")
        self.iv_btns = {}

        for i, (val, lbl, desc) in enumerate(options):
            r, c = divmod(i, 2)
            active = self.interval.get() == val
            bf = tk.Frame(grid, bg=ACCENT if active else "#0d0d1a",
                          highlightbackground=ACCENT if active else BORDER, highlightthickness=1)
            bf.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            grid.columnconfigure(c, weight=1)
            inner = tk.Frame(bf, bg=bf["bg"])
            inner.pack(expand=True, fill="both", padx=12, pady=10)
            fg = "#fff" if active else MUTED
            tk.Label(inner, text=lbl,  bg=inner["bg"], fg=fg, font=("Courier", 13, "bold")).pack()
            tk.Label(inner, text=desc, bg=inner["bg"], fg=fg, font=("Courier", 8)).pack()
            for w in [bf, inner] + list(inner.winfo_children()):
                w.bind("<Button-1>", lambda e, v=val: self._set_iv(v))
                w.configure(cursor="hand2")
            self.iv_btns[val] = (bf, inner)

    def _set_iv(self, val):
        if self.monitoring: return
        self.interval.set(val)
        for v, (bf, inner) in self.iv_btns.items():
            active = v == val
            color  = ACCENT if active else "#0d0d1a"
            fg     = "#fff" if active else MUTED
            bf.configure(bg=color, highlightbackground=ACCENT if active else BORDER)
            inner.configure(bg=color)
            for w in inner.winfo_children(): w.configure(bg=color, fg=fg)
        self._save()

    # ── GAS URL ───────────────────────────────────────────────
    def _gas_section(self):
        frm = self._card(pady=(10, 0))
        tk.Label(frm, text="GOOGLE APPS SCRIPT URL", bg=SURFACE, fg=MUTED,
                 font=("Courier", 8)).pack(anchor="w", padx=12, pady=(10, 4))
        ent = self._entry(frm, ACCENT3, textvariable=self.gas_url_var)
        ent.pack(fill="x", padx=12, pady=(0, 10), ipady=6)
        ent.bind("<FocusOut>", lambda e: self._save())

    # ── 채널 배지 ─────────────────────────────────────────────
    def _channel_badges(self):
        frm = tk.Frame(self.sf, bg=BG)
        frm.pack(fill="x", padx=16, pady=(8, 0))
        for api in APIS:
            tk.Label(frm, text=f"📡 {api['label']}", bg="#071a10", fg="#6ee7b7",
                     font=("Courier", 9), padx=10, pady=3,
                     relief="solid", bd=1).pack(side="left", padx=(0, 6))

    # ── 시작/중지 ─────────────────────────────────────────────
    def _control(self):
        frm = self._card(pady=(10, 0))
        self.start_btn = tk.Button(frm, text="🟢 모니터링 시작", bg=ACCENT, fg="#fff",
                                    font=("", 12, "bold"), relief="flat", cursor="hand2",
                                    command=self._toggle, pady=12)
        self.start_btn.pack(fill="x", padx=12, pady=12)
        self.status_lbl = tk.Label(frm, text="", bg=SURFACE, fg=ACCENT, font=("Courier", 9))
        self.status_lbl.pack(pady=(0, 10))

    def _toggle(self):
        if self.monitoring: self._stop()
        else: self._start()

    # ── 로그 ─────────────────────────────────────────────────
    def _log_section(self):
        frm = self._card(pady=(10, 0))
        hdr = tk.Frame(frm, bg=SURFACE)
        hdr.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(hdr, text="시스템 로그", bg=SURFACE, fg=MUTED, font=("Courier", 9)).pack(side="left")
        self.log_cnt = tk.Label(hdr, text="", bg=SURFACE, fg=ACCENT, font=("Courier", 9))
        self.log_cnt.pack(side="right")

        self.log_txt = tk.Text(frm, bg="#04050f", fg=TEXT, font=("Courier", 9),
                                relief="flat", height=12, state="disabled",
                                wrap="word", insertbackground=TEXT)
        self.log_txt.pack(fill="x", padx=12, pady=(0, 10))
        for tag, fg in [("s", SUCCESS), ("e", ERROR), ("a", ACCENT2),
                        ("i", "#93c5fd"), ("g", WARN), ("t", MUTED), ("n", MUTED)]:
            self.log_txt.tag_configure(tag, foreground=fg)

        tk.Label(self.sf, text="bnkrmall Realtime Monitor", bg=BG, fg="#151728",
                 font=("Courier", 8)).pack(pady=(8, 16))

    # ── 로그 추가 ────────────────────────────────────────────
    def _log(self, msg, tag="n"):
        def _do():
            t = datetime.now().strftime("%H:%M:%S")
            self.log_txt.configure(state="normal")
            self.log_txt.insert("end", t + "  ", "t")
            self.log_txt.insert("end", msg + "\n", tag)
            self.log_txt.configure(state="disabled")
            self.log_txt.see("end")
            lines = int(self.log_txt.index("end-1c").split(".")[0])
            self.log_cnt.config(text=f"▶ {lines}건")
        self.after(0, _do)

    # ── 모니터링 ─────────────────────────────────────────────
    def _start(self):
        if not self.keywords:
            messagebox.showwarning("경고", "키워드를 먼저 추가해주세요!"); return
        self._save()
        self.monitoring  = True
        self.snapshot    = None
        self.check_count = 0
        self.start_btn.config(text="🔴 중지", bg="#b91c1c")
        self._log("🟢 모니터링 시작!", "s")
        if self.emails: self._log(f"📧 Gmail 알림 → {len(self.emails)}개 주소", "g")
        self._update_live()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _stop(self):
        self.monitoring = False
        self.start_btn.config(text="🟢 모니터링 시작", bg=ACCENT)
        self.status_lbl.config(text="")
        self._log("🔴 모니터링 중지", "n")
        self._update_live()

    def _loop(self):
        while self.monitoring:
            self._check()
            iv = self.interval.get()
            for i in range(iv, 0, -1):
                if not self.monitoring: return
                self.after(0, lambda s=i: self.status_lbl.config(
                    text=f"다음 검색까지 {s // 60}:{s % 60:02d}"))
                time.sleep(1)

    def _check(self):
        self._log("🔍 bnkrmall API 조회 중...", "n")
        try:
            results, errors = check_all(self.keywords)
            for e in errors:
                self._log(f"⚠️  [{e['tab']}] {e['kw']}: {e['msg']}", "e")
            snap = make_snapshot(results)
            self.check_count += 1
            self.after(0, self._update_live)

            if self.snapshot is None:
                total = sum(len(lst) for tab in results.values() for lst in tab.values())
                self._log(f"✅ 기준 수집 완료 — 총 {total}개 상품", "s")
                for tl, tab in results.items():
                    for kw, lst in tab.items():
                        self._log(f"   📂 [{tl}] \"{kw}\" → {len(lst)}개", "i")
                self.snapshot = snap
            else:
                new_items = find_new(self.snapshot, results)
                if new_items:
                    self._log(f"🚨 신상품 {len(new_items)}개 발견!", "a")
                    for p in new_items:
                        self._log(f"   🆕 [{p['tab']}] {p['name']} {p['price']}", "a")
                    self.snapshot = snap
                    gas = self.gas_url_var.get().strip()
                    if gas and self.emails:
                        self._log(f"📧 Gmail 발송 중 → {len(self.emails)}개 주소", "g")
                        try:
                            ok = send_to_gas(gas, new_items, self.emails)
                            self._log("✅ Gmail 발송 완료!" if ok else "⚠️  발송 결과 불명확",
                                      "s" if ok else "g")
                        except Exception as ex:
                            self._log(f"❌ GAS 오류: {ex}", "e")
                    elif not gas:
                        self._log("⚠️  GAS URL 미설정 — 이메일 발송 건너뜀", "g")
                else:
                    total = sum(len(lst) for tab in results.values() for lst in tab.values())
                    self._log(f"✅ 변동 없음 ({total}개)", "s")
        except Exception as ex:
            self._log(f"❌ 오류: {ex}", "e")

    def _update_live(self):
        if self.monitoring:
            self.live_lbl.config(text=f"● LIVE · {self.check_count}회 완료", fg=ACCENT3)
        else:
            self.live_lbl.config(text="● STANDBY", fg=TEXT)

    # ── 공통 위젯 헬퍼 ───────────────────────────────────────
    def _card(self, pady=(10, 0)):
        frm = tk.Frame(self.sf, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        frm.pack(fill="x", padx=16, pady=pady)
        return frm

    def _entry(self, parent, focus_color, textvariable=None):
        kw = {"textvariable": textvariable} if textvariable else {}
        ent = tk.Entry(parent, bg="#0d0d1a", fg=TEXT, insertbackground=TEXT,
                       relief="flat", font=("", 11),
                       highlightbackground=BORDER, highlightthickness=1, **kw)
        ent.bind("<FocusIn>",  lambda e: ent.configure(highlightbackground=focus_color))
        ent.bind("<FocusOut>", lambda e: ent.configure(highlightbackground=BORDER))
        return ent

    def _btn(self, parent, text, color, cmd):
        return tk.Button(parent, text=text, bg=color, fg="#fff",
                         font=("", 10, "bold"), relief="flat", cursor="hand2",
                         command=cmd, padx=14, pady=6)

    def _save(self):
        save_config({"keywords": self.keywords, "emails": self.emails,
                     "interval_seconds": self.interval.get(),
                     "gas_url": self.gas_url_var.get()})

if __name__ == "__main__":
    app = App()
    app.mainloop()
