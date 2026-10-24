/**
 * 現金出納帳（タブ10）サーバー側処理
 *
 * データは本体とは別のスプレッドシートに「1取引 = 1行」で保存する。
 * - 追記はロックをかけて1件ずつ行うため、同時入力でも上書きされない
 * - 残高は保存せず、表示時に日付順で計算する
 * - 更新・削除は version による楽観ロックで、他の人の変更を上書きしない
 *
 * スクリプトプロパティ:
 *   CASH_LEDGER_SPREADSHEET_ID  出納帳データ用スプレッドシートのID（cashLedger_setup() で作成）
 *   CASH_LEDGER_ALLOWED_EMAILS  利用を許可するメールアドレス（カンマ区切り）。未設定なら全員拒否
 */

var CASH_LEDGER_SHEET = '出納帳';
var CASH_LEDGER_HEADERS = [
  'id', 'userId', 'userName', 'date', 'memo', 'category',
  'income', 'expense', 'createdBy', 'createdAt', 'updatedBy', 'updatedAt',
  'deleted', 'version', 'seq'
];
var CASH_LEDGER_CATEGORIES = [
  '繰越', '通帳から', '本人から', '生活費', '施設費', '医療費', '公共料金',
  '報酬', '保険・税', '手数料', '日用品', 'その他'
];
var CASH_LEDGER_MAX_AMOUNT = 100000000;
var CASH_LEDGER_MAX_MEMO = 200;

// ---------------------------------------------------------------------------
// 画面から呼ぶ関数（google.script.run）
// ---------------------------------------------------------------------------

/** 利用者の出納帳を日付順で返す（残高つき） */
function cashLedger_list(userId) {
  cashLedger_assertAuthorized_();
  userId = cashLedger_requireId_(userId, '利用者ID');
  var rows = cashLedger_readUserRows_(userId);
  return {
    categories: CASH_LEDGER_CATEGORIES,
    entries: cashLedger_withBalance_(rows),
    summary: cashLedger_summarize_(rows)
  };
}

/** 1件追加する */
function cashLedger_add(userId, userName, entry) {
  return cashLedger_addBatch(userId, userName, [entry]);
}

/** まとめて追加する（通帳・レシートの読み取り結果の登録用）。1件でも不正なら何も保存しない */
function cashLedger_addBatch(userId, userName, entries) {
  var email = cashLedger_assertAuthorized_();
  userId = cashLedger_requireId_(userId, '利用者ID');
  if (!Array.isArray(entries) || !entries.length || entries.length > 200) {
    throw new Error('登録する内容が正しくありません');
  }
  var valid = entries.map(function (entry, i) {
    try { return cashLedger_validateEntry_(entry); }
    catch (err) { throw new Error((i + 1) + '件目：' + err.message); }
  });
  var name = cashLedger_safeText_(userName, 100);
  return cashLedger_withLock_(function () {
    var sheet = cashLedger_sheet_();
    var now = new Date(), seq = now.getTime();
    var values = valid.map(function (e) {
      var row = {
        id: Utilities.getUuid(), userId: userId, userName: name,
        date: e.date, memo: e.memo, category: e.category,
        income: e.income, expense: e.expense,
        createdBy: email, createdAt: now, updatedBy: email, updatedAt: now,
        deleted: false, version: 1, seq: seq++
      };
      return CASH_LEDGER_HEADERS.map(function (h) { return row[h]; });
    });
    sheet.getRange(sheet.getLastRow() + 1, 1, values.length, CASH_LEDGER_HEADERS.length).setValues(values);
    return cashLedger_list(userId);
  });
}

/** 1件更新する。expectedVersion が一致しないときは他の人が先に変更している */
function cashLedger_update(id, expectedVersion, entry) {
  var email = cashLedger_assertAuthorized_();
  id = cashLedger_requireId_(id, '取引ID');
  var e = cashLedger_validateEntry_(entry);
  return cashLedger_withLock_(function () {
    var found = cashLedger_findRow_(id);
    cashLedger_checkVersion_(found.row, expectedVersion);
    found.row.date = e.date;
    found.row.memo = e.memo;
    found.row.category = e.category;
    found.row.income = e.income;
    found.row.expense = e.expense;
    found.row.updatedBy = email;
    found.row.updatedAt = new Date();
    found.row.version = Number(found.row.version) + 1;
    cashLedger_writeRow_(found.index, found.row);
    return cashLedger_list(found.row.userId);
  });
}

/** 1件削除する（行は消さず削除フラグを立てて履歴を残す） */
function cashLedger_remove(id, expectedVersion) {
  var email = cashLedger_assertAuthorized_();
  id = cashLedger_requireId_(id, '取引ID');
  return cashLedger_withLock_(function () {
    var found = cashLedger_findRow_(id);
    cashLedger_checkVersion_(found.row, expectedVersion);
    found.row.deleted = true;
    found.row.updatedBy = email;
    found.row.updatedAt = new Date();
    found.row.version = Number(found.row.version) + 1;
    cashLedger_writeRow_(found.index, found.row);
    return cashLedger_list(found.row.userId);
  });
}

/** 裁判所提出用PDFを作成し、base64で返す。from/to は 'yyyy-MM-dd'（空なら全期間） */
function cashLedger_exportPdf(userId, userName, from, to, author) {
  cashLedger_assertAuthorized_();
  userId = cashLedger_requireId_(userId, '利用者ID');
  var fromDate = from ? cashLedger_parseDate_(from) : null;
  var toDate = to ? cashLedger_parseDate_(to) : null;
  var all = cashLedger_withBalance_(cashLedger_readUserRows_(userId));

  // 期間より前の取引は「前期より繰越」1行にまとめる
  var carry = 0, entries = [];
  all.forEach(function (r) {
    if (fromDate && r.date < cashLedger_fmtDate_(fromDate)) { carry = r.balance; return; }
    if (toDate && r.date > cashLedger_fmtDate_(toDate)) return;
    entries.push(r);
  });
  if (fromDate && carry) {
    entries.unshift({ date: cashLedger_fmtDate_(fromDate), memo: '前期より繰越', category: '繰越',
                      income: null, expense: null, balance: carry });
  }

  var t = HtmlService.createTemplateFromFile('CashLedgerPrint');
  t.data = {
    userName: cashLedger_safeText_(userName, 100),
    author: cashLedger_safeText_(author, 100),
    period: (from || '') + (from || to ? ' 〜 ' : '') + (to || ''),
    entries: entries,
    totals: cashLedger_summarize_(entries.filter(function (r) { return r.category !== '繰越'; }))
  };
  var html = t.evaluate().getContent();
  var blob = Utilities.newBlob(html, 'text/html', 'ledger.html').getAs('application/pdf');
  var name = '現金出納帳_' + (userName || userId) + (from ? '_' + from : '') + (to ? '_' + to : '') + '.pdf';
  return { fileName: name, base64: Utilities.base64Encode(blob.getBytes()) };
}

// ---------------------------------------------------------------------------
// 初期設定・移行（エディタから手動で実行）
// ---------------------------------------------------------------------------

/** 出納帳データ用のスプレッドシートを作成し、IDをスクリプトプロパティに保存する */
function cashLedger_setup() {
  var props = PropertiesService.getScriptProperties();
  if (props.getProperty('CASH_LEDGER_SPREADSHEET_ID')) {
    throw new Error('すでに設定済みです: ' + props.getProperty('CASH_LEDGER_SPREADSHEET_ID'));
  }
  var ss = SpreadsheetApp.create('はくさんだい_現金出納帳データ');
  var sheet = ss.getSheets()[0].setName(CASH_LEDGER_SHEET);
  sheet.getRange(1, 1, 1, CASH_LEDGER_HEADERS.length).setValues([CASH_LEDGER_HEADERS]).setFontWeight('bold');
  sheet.setFrozenRows(1);
  // ID・日付・氏名・摘要は文字列として保存し、自動変換や数式の解釈をさせない
  sheet.getRange('A:F').setNumberFormat('@');
  props.setProperty('CASH_LEDGER_SPREADSHEET_ID', ss.getId());
  Logger.log('作成しました: ' + ss.getUrl());
}

/**
 * tools/convert_xlsx.py が出力した CSV（ドライブに置いたもの）を取り込む。
 * resolveUserId はシステムの利用者マスタから氏名→利用者IDを引く関数に差し替えること。
 */
function cashLedger_importCsv(csvFileId, dryRun) {
  var email = cashLedger_assertAuthorized_();
  var csv = Utilities.parseCsv(DriveApp.getFileById(csvFileId).getBlob().getDataAsString('UTF-8'));
  var head = csv.shift();
  var col = {};
  head.forEach(function (h, i) { col[h] = i; });
  var unknown = {}, out = [], now = new Date(), seq = now.getTime();
  csv.forEach(function (r) {
    var name = r[col.userName];
    var userId = cashLedger_resolveUserId_(name);
    if (!userId) { unknown[name] = true; return; }
    var e = cashLedger_validateEntry_({
      date: r[col.date], memo: r[col.memo], category: r[col.category],
      income: r[col.income], expense: r[col.expense]
    });
    out.push([Utilities.getUuid(), userId, name, e.date, e.memo, e.category, e.income, e.expense,
              email + '（移行）', now, email + '（移行）', now, false, 1, seq++]);
  });
  var names = Object.keys(unknown);
  if (names.length) throw new Error('利用者IDが見つからない氏名があります: ' + names.join('、'));
  if (dryRun) return out.length + ' 件を取り込めます（dryRun）';
  return cashLedger_withLock_(function () {
    var sheet = cashLedger_sheet_();
    sheet.getRange(sheet.getLastRow() + 1, 1, out.length, CASH_LEDGER_HEADERS.length).setValues(out);
    return out.length + ' 件を取り込みました';
  });
}

/** TODO: 既存システムの利用者マスタに合わせて実装する（氏名の空白ゆれを吸収して照合） */
function cashLedger_resolveUserId_(name) {
  throw new Error('cashLedger_resolveUserId_ を既存の利用者マスタに接続してください');
}

// ---------------------------------------------------------------------------
// 内部処理
// ---------------------------------------------------------------------------

/**
 * 呼び出した人が許可されているか確認する。
 * google.script.run の関数は画面を経由せず直接呼べるため、関数ごとに必ず確認する。
 * Webアプリは「アクセスしているユーザー」として実行し、組織内のみに公開する前提。
 */
function cashLedger_assertAuthorized_() {
  var email = Session.getActiveUser().getEmail();
  var allowed = (PropertiesService.getScriptProperties().getProperty('CASH_LEDGER_ALLOWED_EMAILS') || '')
    .split(',').map(function (s) { return s.trim().toLowerCase(); }).filter(String);
  if (!email || allowed.indexOf(email.toLowerCase()) === -1) {
    throw new Error('この操作を行う権限がありません');
  }
  return email;
}

function cashLedger_sheet_() {
  var id = PropertiesService.getScriptProperties().getProperty('CASH_LEDGER_SPREADSHEET_ID');
  if (!id) throw new Error('出納帳データが未設定です（cashLedger_setup を実行してください）');
  return SpreadsheetApp.openById(id).getSheetByName(CASH_LEDGER_SHEET);
}

function cashLedger_withLock_(fn) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) throw new Error('混み合っています。少し待ってからもう一度お試しください');
  try {
    var result = fn();
    SpreadsheetApp.flush();
    return result;
  } finally {
    lock.releaseLock();
  }
}

/** 該当利用者の行だけを読む（TextFinder で対象行を絞り、全件読み込みを避ける） */
function cashLedger_readUserRows_(userId) {
  var sheet = cashLedger_sheet_();
  var last = sheet.getLastRow();
  if (last < 2) return [];
  var hits = sheet.getRange(2, 2, last - 1, 1).createTextFinder(userId).matchEntireCell(true).findAll();
  if (!hits.length) return [];
  var first = hits[0].getRow(), lastHit = hits[hits.length - 1].getRow();
  var values = sheet.getRange(first, 1, lastHit - first + 1, CASH_LEDGER_HEADERS.length).getValues();
  return values.map(cashLedger_toObj_).filter(function (r) {
    return r.userId === userId && r.deleted !== true;
  });
}

function cashLedger_findRow_(id) {
  var sheet = cashLedger_sheet_();
  var last = sheet.getLastRow();
  var hit = last < 2 ? null : sheet.getRange(2, 1, last - 1, 1).createTextFinder(id).matchEntireCell(true).findNext();
  if (!hit) throw new Error('対象の記録が見つかりません');
  var index = hit.getRow();
  var row = cashLedger_toObj_(sheet.getRange(index, 1, 1, CASH_LEDGER_HEADERS.length).getValues()[0]);
  if (row.deleted === true) throw new Error('この記録はすでに削除されています');
  return { index: index, row: row };
}

function cashLedger_writeRow_(index, row) {
  cashLedger_sheet_().getRange(index, 1, 1, CASH_LEDGER_HEADERS.length)
    .setValues([CASH_LEDGER_HEADERS.map(function (h) { return row[h]; })]);
}

function cashLedger_checkVersion_(row, expectedVersion) {
  if (Number(row.version) !== Number(expectedVersion)) {
    throw new Error('ほかの人がこの記録を変更しました。画面を更新してからもう一度お試しください');
  }
}

function cashLedger_toObj_(values) {
  var o = {};
  CASH_LEDGER_HEADERS.forEach(function (h, i) { o[h] = values[i]; });
  o.date = o.date instanceof Date ? cashLedger_fmtDate_(o.date) : String(o.date);
  o.income = o.income === '' ? null : Number(o.income);
  o.expense = o.expense === '' ? null : Number(o.expense);
  return o;
}

/** 日付→入力順に並べて残高を計算する。画面に返す項目だけに絞る */
function cashLedger_withBalance_(rows) {
  var sorted = rows.slice().sort(function (a, b) {
    return a.date < b.date ? -1 : a.date > b.date ? 1 : Number(a.seq) - Number(b.seq);
  });
  var bal = 0;
  return sorted.map(function (r) {
    bal += (r.income || 0) - (r.expense || 0);
    return {
      id: r.id, version: r.version, date: r.date, memo: r.memo, category: r.category,
      income: r.income, expense: r.expense, balance: bal,
      updatedBy: r.updatedBy, updatedAt: r.updatedAt instanceof Date ? r.updatedAt.toISOString() : String(r.updatedAt || '')
    };
  });
}

function cashLedger_summarize_(rows) {
  var byCat = {}, income = 0, expense = 0;
  rows.forEach(function (r) {
    income += r.income || 0;
    expense += r.expense || 0;
    var c = r.category || 'その他';
    byCat[c] = byCat[c] || { income: 0, expense: 0 };
    byCat[c].income += r.income || 0;
    byCat[c].expense += r.expense || 0;
  });
  return { income: income, expense: expense, byCategory: byCat };
}

function cashLedger_validateEntry_(entry) {
  if (!entry || typeof entry !== 'object') throw new Error('入力内容がありません');
  var date = cashLedger_parseDate_(entry.date);
  var income = cashLedger_parseAmount_(entry.income, '収入');
  var expense = cashLedger_parseAmount_(entry.expense, '支出');
  if (income === null && expense === null) throw new Error('収入か支出のどちらかを入力してください');
  if (income !== null && expense !== null) throw new Error('収入と支出は別々の行で入力してください');
  var category = String(entry.category || 'その他');
  if (CASH_LEDGER_CATEGORIES.indexOf(category) === -1) throw new Error('区分が正しくありません');
  var memo = cashLedger_safeText_(entry.memo, CASH_LEDGER_MAX_MEMO);
  if (!memo) throw new Error('摘要を入力してください');
  return { date: cashLedger_fmtDate_(date), memo: memo, category: category, income: income, expense: expense };
}

function cashLedger_parseDate_(v) {
  var m = /^(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})$/.exec(String(v || '').trim());
  if (!m) throw new Error('日付は 2026-10-22 の形式で入力してください');
  var d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (d.getMonth() !== Number(m[2]) - 1 || d.getFullYear() < 2000 || d.getFullYear() > 2100) {
    throw new Error('日付が正しくありません');
  }
  return d;
}

function cashLedger_parseAmount_(v, label) {
  if (v === null || v === undefined || String(v).trim() === '') return null;
  var n = Number(String(v).replace(/[,¥円\s]/g, ''));
  if (!isFinite(n) || n < 0 || n > CASH_LEDGER_MAX_AMOUNT || Math.floor(n) !== n) {
    throw new Error(label + 'は0以上の整数（円）で入力してください');
  }
  return n;
}

/** 文字列を整え、先頭の = + - @ をエスケープしてシートで数式として動かないようにする */
function cashLedger_safeText_(v, max) {
  var s = String(v === null || v === undefined ? '' : v).replace(/[\r\n\t]+/g, ' ').trim().slice(0, max);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

function cashLedger_requireId_(v, label) {
  var s = String(v || '').trim();
  if (!/^[A-Za-z0-9_\-]{1,64}$/.test(s)) throw new Error(label + 'が正しくありません');
  return s;
}

function cashLedger_fmtDate_(d) {
  return Utilities.formatDate(d, 'Asia/Tokyo', 'yyyy-MM-dd');
}
