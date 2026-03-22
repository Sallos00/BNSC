# bnkrmall Monitor

bnkrmall 신상품 실시간 감시 프로그램 (Windows EXE)

---

## 🚀 설치 순서

### 1단계 — Google Apps Script 설정
1. [Google 스프레드시트](https://sheets.google.com) 새로 만들기
2. **확장 프로그램 → Apps Script** 클릭
3. `google_apps_script.js` 내용 전체 붙여넣기 후 저장
4. **배포 → 새 배포** → 유형: 웹 앱 → 액세스: 모든 사용자 → 배포
5. 웹 앱 URL 복사

### 2단계 — GitHub에 올리기
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/유저명/bnkrmall-monitor.git
git push -u origin main
```
push 하면 GitHub Actions가 자동으로 EXE 빌드 → **Releases** 탭에서 다운로드

### 3단계 — 실행
1. `bnkrmall-monitor.exe` 다운로드 후 실행
2. 프로그램 내에서 직접 키워드, 이메일, GAS URL 입력
3. 모니터링 시작 버튼 클릭!

---

## ⚙️ 작동 방식
```
EXE 실행 (GUI)
  └─ 키워드/이메일/주기 직접 입력
  └─ bnkrmall API 주기적 체크
  └─ 신상품 발견!
       └─ GAS 웹훅으로 POST 전송
              └─ 스프레드시트에 기록
              └─ Gmail 자동 발송 ✉️
```
