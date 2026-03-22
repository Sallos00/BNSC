// Google Apps Script
// 스프레드시트 > 확장 프로그램 > Apps Script 에 붙여넣기 후 웹앱으로 배포

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const items = data.items || [];
    const emails = data.emails || [];
    const timestamp = data.timestamp || new Date().toLocaleString("ko-KR");

    logToSheet(items, timestamp);
    emails.forEach(email => sendMail(email, items, timestamp));

    return ContentService
      .createTextOutput(JSON.stringify({ success: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, error: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function logToSheet(items, timestamp) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName("감지 로그");
  if (!sheet) {
    sheet = ss.insertSheet("감지 로그");
    sheet.appendRow(["감지 시각", "탭", "상품명", "가격", "구매 링크"]);
    sheet.getRange(1,1,1,5).setFontWeight("bold").setBackground("#1e2140").setFontColor("#ffffff");
  }
  items.forEach(item => {
    sheet.appendRow([timestamp, item.tab||"", item.name||"", item.price||"", item.url||""]);
  });
}

function sendMail(toEmail, items, timestamp) {
  const subject = `🚨 [bnkrmall] 신상품 ${items.length}개 감지!`;
  const itemRows = items.map(p => `
    <tr>
      <td style="padding:12px 16px;border-bottom:1px solid #1e2140;">
        <span style="background:#1e1040;color:#a0a2ff;font-size:11px;padding:2px 8px;border-radius:4px;font-family:monospace;">${p.tab||""}</span>
        <strong style="display:block;margin-top:6px;color:#fff;font-size:14px;">${p.name||""}</strong>
        ${p.price ? `<span style="color:#a5f3fc;font-size:12px;">${p.price}</span>` : ""}
      </td>
      <td style="padding:12px 16px;border-bottom:1px solid #1e2140;text-align:right;vertical-align:middle;">
        ${p.url ? `<a href="${p.url}" style="background:#5b5eff;color:#fff;text-decoration:none;padding:8px 16px;border-radius:8px;font-size:13px;font-weight:bold;">구매하기 →</a>` : ""}
      </td>
    </tr>`).join("");

  const htmlBody = `
    <div style="background:#04050f;padding:32px;font-family:sans-serif;max-width:560px;margin:0 auto;border-radius:16px;">
      <div style="text-align:center;margin-bottom:24px;">
        <div style="font-size:36px;">🛒</div>
        <h1 style="color:#fff;font-size:20px;margin:8px 0 4px;font-family:monospace;">BNKRMALL MONITOR</h1>
        <p style="color:#4a4d6e;font-size:12px;margin:0;font-family:monospace;">신상품 감지 알림</p>
      </div>
      <div style="background:#0b0d1f;border:1px solid #1e2140;border-radius:12px;overflow:hidden;margin-bottom:20px;">
        <div style="background:linear-gradient(135deg,rgba(91,94,255,0.3),rgba(255,91,141,0.3));padding:12px 16px;">
          <span style="color:#ff9bb8;font-weight:bold;font-size:14px;">🚨 신상품 ${items.length}개가 감지되었습니다!</span>
        </div>
        <table style="width:100%;border-collapse:collapse;">${itemRows}</table>
      </div>
      <p style="color:#4a4d6e;font-size:11px;text-align:center;font-family:monospace;">bnkrmall 실시간 모니터 · ${timestamp}</p>
    </div>`;

  GmailApp.sendEmail(toEmail, subject, "", { htmlBody });
}
