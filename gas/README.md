# 現金出納帳（タブ10）モジュール

はくさんだい後見事務所 管理システム（GAS）に追加する現金出納帳機能です。
既存システムのコードに依存しない部分をまとめています。

| ファイル | 内容 |
|---|---|
| `CashLedger.gs` | サーバー側処理（一覧・追加・修正・削除・PDF出力・初期設定・CSV取り込み） |
| `CashLedgerScan.gs` | 通帳・レシートの写真を Vertex AI で読み取り、登録候補を返す |
| `CashLedgerTab.html` | タブ10の画面部品（通帳・レシート読み込みの確認画面を含む） |
| `CashLedgerPrint.html` | 裁判所提出用PDFの様式 |
| `../tools/convert_xlsx.py` | ■現金出納.xlsx → 取り込み用CSV と照合レポート |

## 仕組み

- 出納帳のデータは本体とは別のスプレッドシートに「1取引 = 1行」で保存します。
- 追加はスクリプトロックをかけて1件ずつ追記するので、同時に入力しても上書きされません。
- 修正・削除は version を照合し、他の人が先に変更していたらエラーにします（上書きしない）。
- 削除は行を消さずに削除フラグを立てます。入力者・更新者・日時が残ります。
- 残高は保存せず、表示のたびに「日付 → 入力順」で計算します。
- タブ10を開いたときだけ、その利用者の行を読み込みます。
- 通帳・レシートの読み取り結果は自動では保存しません。確認画面で職員がチェック・修正してから登録します。
  - 通帳：出金の行だけを候補にし、ATM・窓口での現金引き出しに最初からチェックを入れます（振替・引落は外す）。
    登録すると「通帳から」の収入になります。
  - レシート：日付・店名・合計・区分の候補を出し、支出として登録します。
  - 同じ日付・同じ金額の記録がすでにあれば警告を出し、チェックを外します。
  - 写真は送信前に長辺2000pxへ縮めます。

## 既存システムへの組み込み手順

1. `CashLedger.gs`・`CashLedgerScan.gs`・`CashLedgerTab.html`・`CashLedgerPrint.html` の4つをGASプロジェクトに追加する。
2. エディタで `cashLedger_setup()` を1回実行する（データ用スプレッドシートが作られる）。
3. スクリプトプロパティ `CASH_LEDGER_ALLOWED_EMAILS` に、使う職員のメールアドレスをカンマ区切りで入れる。
4. 利用者詳細画面にタブ「10 現金出納帳」を追加し、`CashLedgerTab` を差し込む。
   タブを開いたときに `CashLedgerTab.open(利用者ID, 氏名, 作成者氏名)` を呼ぶ。
5. 読み取り用に、既存の書類読み取りと同じ Vertex AI の設定をスクリプトプロパティに入れる。
   `VERTEX_PROJECT_ID`（必須）、`VERTEX_LOCATION`（省略時 asia-northeast1）、`VERTEX_MODEL`（省略時 gemini-2.5-flash）。
   `appsscript.json` の oauthScopes に `https://www.googleapis.com/auth/cloud-platform` を入れる。
   既存の読み取りがサービスアカウント等で認証している場合は `cashLedger_vertexToken_()` をそれに合わせる。
6. `cashLedger_resolveUserId_()` を既存の利用者マスタ（氏名 → 利用者ID）に接続する。
7. 既存システムの認証の仕組みがあれば、`cashLedger_assertAuthorized_()` をそれに合わせる。

## データ移行

過去の記録は Excel で保管し、システムでは開始日から新しく始めます。各利用者の最終残高を開始日の
「前期より繰越」1行として登録します（残高が Excel と合わない利用者は出力せず、要確認に出します）。

```
python3 tools/convert_xlsx.py ■現金出納.xlsx migration_out/ --opening 2026-11-01
```

`--opening` を付けなければ全件を移行します。

1. `migration_out/report.md` で「要確認」と自動補正の内容を確認し、必要なら Excel を直して再実行する。
2. `migration_out/import.csv` をドライブに置き、`cashLedger_importCsv(ファイルID, true)` で事前チェックする。
3. 問題なければ `cashLedger_importCsv(ファイルID, false)` で取り込む。

Excel・CSV・レポートには個人情報が含まれるため、このリポジトリにはコミットしません（`.gitignore` 済み）。
