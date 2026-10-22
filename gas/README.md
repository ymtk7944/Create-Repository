# 現金出納帳（タブ10）モジュール

はくさんだい後見事務所 管理システム（GAS）に追加する現金出納帳機能です。
既存システムのコードに依存しない部分をまとめています。

| ファイル | 内容 |
|---|---|
| `CashLedger.gs` | サーバー側処理（一覧・追加・修正・削除・PDF出力・初期設定・CSV取り込み） |
| `CashLedgerTab.html` | タブ10の画面部品 |
| `CashLedgerPrint.html` | 裁判所提出用PDFの様式 |
| `../tools/convert_xlsx.py` | ■現金出納.xlsx → 取り込み用CSV と照合レポート |

## 仕組み

- 出納帳のデータは本体とは別のスプレッドシートに「1取引 = 1行」で保存します。
- 追加はスクリプトロックをかけて1件ずつ追記するので、同時に入力しても上書きされません。
- 修正・削除は version を照合し、他の人が先に変更していたらエラーにします（上書きしない）。
- 削除は行を消さずに削除フラグを立てます。入力者・更新者・日時が残ります。
- 残高は保存せず、表示のたびに「日付 → 入力順」で計算します。
- タブ10を開いたときだけ、その利用者の行を読み込みます。

## 既存システムへの組み込み手順

1. 3つのファイルをGASプロジェクトに追加する。
2. エディタで `cashLedger_setup()` を1回実行する（データ用スプレッドシートが作られる）。
3. スクリプトプロパティ `CASH_LEDGER_ALLOWED_EMAILS` に、使う職員のメールアドレスをカンマ区切りで入れる。
4. 利用者詳細画面にタブ「10 現金出納帳」を追加し、`CashLedgerTab` を差し込む。
   タブを開いたときに `CashLedgerTab.open(利用者ID, 氏名, 作成者氏名)` を呼ぶ。
5. `cashLedger_resolveUserId_()` を既存の利用者マスタ（氏名 → 利用者ID）に接続する。
6. 既存システムの認証の仕組みがあれば、`cashLedger_assertAuthorized_()` をそれに合わせる。

## データ移行

```
python3 tools/convert_xlsx.py ■現金出納.xlsx migration_out/
```

1. `migration_out/report.md` で「要確認」と自動補正の内容を確認し、必要なら Excel を直して再実行する。
2. `migration_out/import.csv` をドライブに置き、`cashLedger_importCsv(ファイルID, true)` で事前チェックする。
3. 問題なければ `cashLedger_importCsv(ファイルID, false)` で取り込む。

Excel・CSV・レポートには個人情報が含まれるため、このリポジトリにはコミットしません（`.gitignore` 済み）。
