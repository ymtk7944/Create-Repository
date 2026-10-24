/**
 * 通帳・レシートの写真を読み取り、出納帳の登録候補を返す。
 *
 * 読み取りは既存の書類読み取りと同じ Vertex AI（Gemini）で行う。結果はそのまま保存せず、
 * 候補として画面に返す。職員が画面で確認・修正してから cashLedger_addBatch() で登録する。
 *
 * スクリプトプロパティ:
 *   VERTEX_PROJECT_ID  Google Cloud のプロジェクトID（既存の読み取りと同じもの）
 *   VERTEX_LOCATION    リージョン（省略時 asia-northeast1）
 *   VERTEX_MODEL       使うモデル（省略時 gemini-2.5-flash）
 *
 * 認証は ScriptApp.getOAuthToken() を使うため、appsscript.json の oauthScopes に
 * https://www.googleapis.com/auth/cloud-platform が必要。既存の読み取り処理が別の認証
 * （サービスアカウント等）を使っている場合は cashLedger_vertexToken_() をそれに合わせる。
 */

var CASH_SCAN_MAX_BYTES = 8 * 1024 * 1024;
var CASH_SCAN_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'application/pdf'];

var CASH_SCAN_PROMPTS = {
  passbook:
    'これは日本の銀行の預金通帳（または取引明細）の画像です。記帳されている取引を上から順にすべて読み取ってください。\n' +
    '- date: 取引日を西暦の YYYY-MM-DD で。和暦（R6、06 など）は西暦に直す。年が書かれていなければ前後の行から推測する\n' +
    '- description: 摘要欄の文字をそのまま（例: カード、ATM、振込 ﾄｳﾎｸﾃﾞﾝﾘﾖｸ）\n' +
    '- withdrawal: お支払金額（出金）。無ければ null\n' +
    '- deposit: お預り金額（入金）。無ければ null\n' +
    '- balance: 差引残高。無ければ null\n' +
    '- isCashWithdrawal: ATMや窓口での現金の引き出しなら true。口座振替・振込・引落など現金が手元に来ない取引は false\n' +
    '金額は数字のみ（カンマ・円記号なし）。読めない文字は推測せず、その行の confidence を low にしてください。',
  receipt:
    'これは日本のレシートまたは領収書の画像です。次の項目を読み取ってください。\n' +
    '- date: 発行日を西暦の YYYY-MM-DD で\n' +
    '- store: 店名・発行者名\n' +
    '- total: 支払合計（税込）。お預り・お釣りではなく合計金額\n' +
    '- summary: 主な購入品を短く（例: 日用品、薬、食料品）\n' +
    '- category: 次のどれか ' + JSON.stringify(['生活費', '施設費', '医療費', '公共料金', '保険・税', '手数料', '日用品', 'その他']) + '\n' +
    '金額は数字のみ。読めない部分は推測せず confidence を low にしてください。'
};

var CASH_SCAN_SCHEMAS = {
  passbook: {
    type: 'OBJECT',
    properties: {
      rows: {
        type: 'ARRAY',
        items: {
          type: 'OBJECT',
          properties: {
            date: { type: 'STRING' }, description: { type: 'STRING' },
            withdrawal: { type: 'INTEGER', nullable: true }, deposit: { type: 'INTEGER', nullable: true },
            balance: { type: 'INTEGER', nullable: true }, isCashWithdrawal: { type: 'BOOLEAN' },
            confidence: { type: 'STRING', enum: ['high', 'low'] }
          },
          required: ['date', 'description', 'isCashWithdrawal', 'confidence']
        }
      }
    },
    required: ['rows']
  },
  receipt: {
    type: 'OBJECT',
    properties: {
      date: { type: 'STRING' }, store: { type: 'STRING' }, total: { type: 'INTEGER', nullable: true },
      summary: { type: 'STRING' }, category: { type: 'STRING' },
      confidence: { type: 'STRING', enum: ['high', 'low'] }
    },
    required: ['date', 'store', 'confidence']
  }
};

/**
 * 画像を読み取り、登録候補を返す。
 * kind: 'passbook'（通帳）| 'receipt'（レシート）
 * 返り値の candidates は画面の確認表にそのまま並べる。selected は初期のチェック状態
 */
function cashLedger_scan(userId, kind, base64, mimeType) {
  cashLedger_assertAuthorized_();
  userId = cashLedger_requireId_(userId, '利用者ID');
  if (!CASH_SCAN_PROMPTS[kind]) throw new Error('読み取りの種類が正しくありません');
  if (CASH_SCAN_MIME_TYPES.indexOf(mimeType) === -1) throw new Error('写真（JPEG・PNG）またはPDFを選んでください');
  var bytes = Utilities.base64Decode(String(base64 || ''));
  if (!bytes.length || bytes.length > CASH_SCAN_MAX_BYTES) throw new Error('ファイルが大きすぎます（8MBまで）');

  var result = cashLedger_callGemini_(kind, base64, mimeType);
  var existing = cashLedger_readUserRows_(userId);
  var candidates = kind === 'passbook'
    ? cashLedger_passbookCandidates_(result)
    : cashLedger_receiptCandidates_(result);

  // 同じ日付・同じ金額の記録がすでにあれば二重登録の可能性として知らせる
  candidates.forEach(function (c) {
    var dup = existing.some(function (r) {
      return r.date === c.date && (r.income || null) === (c.income || null) && (r.expense || null) === (c.expense || null);
    });
    if (dup) { c.warning = '同じ日付・金額の記録がすでにあります'; c.selected = false; }
  });
  return { kind: kind, candidates: candidates };
}

function cashLedger_passbookCandidates_(result) {
  return (result.rows || []).filter(function (r) {
    return r.withdrawal > 0;  // 現金出納帳に関係するのは出金だけ（入金は口座内の動き）
  }).map(function (r) {
    return {
      date: cashLedger_normalizeScanDate_(r.date),
      memo: '通帳から' + (r.description ? '（' + String(r.description).slice(0, 40) + '）' : ''),
      category: '通帳から',
      income: r.withdrawal, expense: null,
      source: [r.description, r.balance != null ? '残高 ' + r.balance : ''].filter(String).join(' / '),
      lowConfidence: r.confidence === 'low',
      // 現金の引き出しだけ最初からチェックを入れる。振替・引落は職員が判断する
      selected: r.isCashWithdrawal === true && r.confidence !== 'low'
    };
  });
}

function cashLedger_receiptCandidates_(r) {
  var category = CASH_LEDGER_CATEGORIES.indexOf(r.category) >= 0 ? r.category : 'その他';
  return [{
    date: cashLedger_normalizeScanDate_(r.date),
    memo: ((r.store || 'レシート') + (r.summary ? '（' + r.summary + '）' : '')).slice(0, 200),
    category: category,
    income: null, expense: r.total > 0 ? r.total : null,
    source: r.store || '',
    lowConfidence: r.confidence === 'low',
    selected: r.total > 0 && r.confidence !== 'low'
  }];
}

/** 読み取った日付を YYYY-MM-DD に揃える。読めなければ空にして職員に入力してもらう */
function cashLedger_normalizeScanDate_(v) {
  try { return cashLedger_fmtDate_(cashLedger_parseDate_(v)); }
  catch (e) { return ''; }
}

function cashLedger_callGemini_(kind, base64, mimeType) {
  var props = PropertiesService.getScriptProperties();
  var project = props.getProperty('VERTEX_PROJECT_ID');
  if (!project) throw new Error('読み取り機能が未設定です（VERTEX_PROJECT_ID）');
  var location = props.getProperty('VERTEX_LOCATION') || 'asia-northeast1';
  var model = props.getProperty('VERTEX_MODEL') || 'gemini-2.5-flash';
  var url = 'https://' + location + '-aiplatform.googleapis.com/v1/projects/' + encodeURIComponent(project) +
            '/locations/' + location + '/publishers/google/models/' + encodeURIComponent(model) + ':generateContent';
  var res = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + cashLedger_vertexToken_() },
    muteHttpExceptions: true,
    payload: JSON.stringify({
      contents: [{ role: 'user', parts: [
        { inlineData: { mimeType: mimeType, data: base64 } },
        { text: CASH_SCAN_PROMPTS[kind] }
      ] }],
      generationConfig: {
        temperature: 0,
        responseMimeType: 'application/json',
        responseSchema: CASH_SCAN_SCHEMAS[kind]
      }
    })
  });
  if (res.getResponseCode() !== 200) {
    // 応答本文には入力内容が含まれることがあるため、ログには状態コードだけ残す
    console.error('Vertex AI error: ' + res.getResponseCode());
    throw new Error('読み取りに失敗しました。時間をおいてもう一度お試しください');
  }
  try {
    var body = JSON.parse(res.getContentText());
    return JSON.parse(body.candidates[0].content.parts[0].text);
  } catch (e) {
    throw new Error('読み取れませんでした。明るい場所で、全体が写るように撮り直してください');
  }
}

function cashLedger_vertexToken_() {
  return ScriptApp.getOAuthToken();
}
