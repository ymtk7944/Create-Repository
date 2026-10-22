"""
■現金出納.xlsx を出納帳データ取り込み用の CSV と照合レポートに変換する。

使い方:
    python3 tools/convert_xlsx.py ■現金出納.xlsx migration_out/

出力:
    migration_out/import.csv   cashLedger_importCsv() で取り込む CSV
    migration_out/report.md    利用者ごとの件数・残高照合・要確認事項

方針:
    - 1枚目の残高だけの行は「前期より繰越」として取り込む
    - 最初の取引で Excel の残高と計算が合わないときは、差額を「前期より繰越」として補う
    - 途中で合わないときは補正しない（Excel 側の計算ミスの可能性があるため要確認に出す）
    - 「■原本」などデータの無いシートは取り込まない
"""
import sys, json, datetime, re, warnings
warnings.filterwarnings('ignore')
import openpyxl

def norm(s):
    return re.sub(r'[\s　]', '', str(s)) if s is not None else ''

def num(v):
    if v is None or v == '': return None
    if isinstance(v, (int, float)): return float(v)
    s = re.sub(r'[¥,\s円]', '', str(v))
    try: return float(s)
    except: return None

Z2H = str.maketrans('０１２３４５６７８９／．', '0123456789/.')
def parse_date(v):
    t = norm(v).translate(Z2H).replace('.', '/')
    m = re.fullmatch(r'(\d{4})/(\d{1,2})/(\d{1,2})', t)
    if not m: return None
    y, mo, da = map(int, m.groups())
    if 200 <= y < 300: y += 1820  # 0205 -> 2025, 0206 -> 2026
    try: return datetime.date(y, mo, da)
    except ValueError: return None

def parse_sheet(ws):
    rows = list(ws.iter_rows(values_only=True))
    hdr = None
    for i, r in enumerate(rows[:15]):
        if any(norm(c) == '年月日' for c in r): hdr = i; break
    if hdr is None: return None, 'no header'
    name = None
    for r in rows[:hdr]:
        for j, c in enumerate(r):
            if norm(c) == '本人氏名':
                v = next((x for x in r[j+1:] if x not in (None, '')), None)
                name = None if norm(v).endswith('氏名') else v
    cols = {}
    for rr in (rows[hdr], rows[hdr+1] if hdr+1 < len(rows) else ()):
        for j, c in enumerate(rr):
            k = norm(c)
            if k == '年月日': cols.setdefault('date', j)
            elif k == '摘要': cols.setdefault('memo', j)
            elif k == '項目': cols.setdefault('cat', j)
            elif k == '収入': cols.setdefault('in', j)
            elif k == '支出': cols.setdefault('out', j)
            elif k == '現金残高': cols.setdefault('bal', j)
    need = {'date', 'memo', 'in', 'out', 'bal'}
    if not need <= cols.keys(): return None, f'missing cols {need - cols.keys()}'
    g = lambda r, k: r[cols[k]] if k in cols and cols[k] < len(r) else None
    tx, cur_date, issues, excel_diff = [], None, [], []
    last_bal = None
    running = None
    for i, r in enumerate(rows[hdr+2:], start=hdr+3):
        d, memo, cat = g(r, 'date'), g(r, 'memo'), g(r, 'cat')
        inc, out, bal = num(g(r, 'in')), num(g(r, 'out')), num(g(r, 'bal'))
        if bal is not None and (inc is not None or out is not None or memo not in (None, '')): last_bal = bal
        if isinstance(d, datetime.datetime): cur_date = d.date()
        elif norm(d) == '〃': pass
        elif norm(d) != '':
            pd = parse_date(d)
            if pd: cur_date = pd; issues.append(f'row{i}: 日付を補正 {d!r} -> {pd}')
            else: issues.append(f'row{i}: 日付を読めない {d!r}（前の行の日付 {cur_date} を仮採用）')
        if running is None and inc is None and out is None and bal is not None:
            tx.append(dict(row=i, date=str(cur_date), memo='前期より繰越' if memo in (None,'') else str(memo), cat='繰越', inc=bal, out=None))
            running = bal; continue
        if memo in (None, '') and inc is None and out is None:
            continue
        first = running is None
        if first: running = 0.0
        running += (inc or 0) - (out or 0)
        if bal is not None and abs(running - bal) > 0.5:
            diff = bal - running
            if first:
                tx.append(dict(row=i, date=str(cur_date), memo='前期より繰越', cat='繰越', inc=diff if diff > 0 else None, out=-diff if diff < 0 else None))
                issues.append(f'row{i}: 最初の残高に差額 {diff:+.0f} 円 → 「前期より繰越」として補正')
                running = bal
            elif not excel_diff or abs(excel_diff[-1] - diff) > 0.5:
                issues.append(f'row{i}: 残高不一致 Excel={bal:.0f} 計算={running:.0f}（差 {diff:+.0f}）※補正せず要確認')
                excel_diff.append(diff)
        tx.append(dict(row=i, date=str(cur_date), memo=None if memo is None else str(memo), cat=None if cat is None else str(cat), inc=inc, out=out))
    tx = [t for t in tx if t['inc'] or t['out']]  # 金額の無い行（メモ書き）は取り込まない
    split = []
    for t in tx:  # 1行に収入と支出が両方ある行は2行に分ける
        if t['inc'] and t['out']:
            split.append(dict(t, out=None)); split.append(dict(t, inc=None, cat=None if t['cat'] in ('通帳から', '本人から') else t['cat']))
        else:
            split.append(t)
    tx = split
    first_date = next((t['date'] for t in tx if t['date'] != 'None'), None)
    for t in tx:
        if t['date'] == 'None': t['date'] = first_date
        c = norm(t['cat'])
        if c in CATEGORIES:
            t['cat'] = c
            if not norm(t['memo']): t['memo'] = c
            continue
        if c and c not in ('0',):  # 項目欄を自由記入に使っている行は摘要に寄せる
            t['memo'] = f"{t['memo'] or ''}（{c}）" if norm(t['memo']) else c
        t['cat'] = classify(t['memo'], t['inc'])
        if not norm(t['memo']): t['memo'] = '（摘要なし）'
    return dict(name=name, tx=tx, final=running, excel_final=last_bal, issues=issues), None

CATEGORIES = ['繰越', '通帳から', '本人から', '生活費', '施設費', '医療費', '公共料金',
              '報酬', '保険・税', '手数料', '日用品', 'その他']
RULES = [
    ('報酬', ['報酬']), ('施設費', ['施設', '利用料', '家賃', '入居']), ('医療費', ['病院', '医院', '薬', 'クリニック', '医療']),
    ('公共料金', ['電気', '電力', 'ガス', '水道', '灯油', '電話', 'NTT', 'ドコモ', 'au', 'ソフトバンク']),
    ('保険・税', ['保険', '税', '年金']), ('手数料', ['手数料', '振込']), ('生活費', ['生活費', '小遣い', '本人へ']),
]
def classify(memo, inc):
    m = memo or ''
    if inc is not None:
        if '通帳' in m: return '通帳から'
        if '本人' in m: return '本人から'
        return 'その他'
    for cat, words in RULES:
        if any(w in m for w in words): return cat
    return 'その他'

def main(src, outdir):
    import csv, os
    os.makedirs(outdir, exist_ok=True)
    wb = openpyxl.load_workbook(src, data_only=True)
    rows, report, warn = [], [], []
    for ws in wb:
        res, err = parse_sheet(ws)
        if not res: warn.append(f'- {ws.title}: 読み込めませんでした（{err}）'); continue
        if not any(t['inc'] or t['out'] for t in res['tx']): warn.append(f'- {ws.title}: 取引が無いため取り込みません'); continue
        name = re.sub(r'様$', '', norm(res['name'] or ws.title).replace('■', ''))
        for t in res['tx']:
            rows.append([name, t['date'], t['memo'] or '', t['cat'], fmt(t['inc']), fmt(t['out'])])
        ok = res['excel_final'] is not None and abs(res['final'] - res['excel_final']) < 0.5
        report.append((ws.title, name, len(res['tx']), res['excel_final'], res['final'], ok, res['issues']))
    with open(os.path.join(outdir, 'import.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['userName', 'date', 'memo', 'category', 'income', 'expense']); w.writerows(rows)
    ng = [r for r in report if not r[5]]
    with open(os.path.join(outdir, 'report.md'), 'w', encoding='utf-8') as f:
        f.write(f'# 現金出納帳 移行レポート\n\n- 対象シート: {len(report)} 名分 / 取引 {len(rows)} 件\n')
        f.write(f'- 最終残高が Excel と一致: {len(report) - len(ng)} 名 / 不一致: {len(ng)} 名\n\n')
        f.write('## 利用者ごとの照合\n\n| シート | 氏名 | 件数 | Excel最終残高 | 移行後の残高 | 照合 |\n|---|---|---:|---:|---:|---|\n')
        for t, n, c, e, fin, ok, _ in report:
            f.write(f"| {t} | {n} | {c} | {yen(e)} | {yen(fin)} | {'一致' if ok else '**要確認**'} |\n")
        f.write('\n## 要確認・自動補正の内容\n\n')
        for t, n, c, e, fin, ok, issues in report:
            for i in issues: f.write(f'- {t} {i}\n')
        f.write('\n'.join([''] + warn) + '\n')
    print(f'{len(report)} 名 / {len(rows)} 件 / 不一致 {len(ng)} 名 → {outdir}')

def fmt(v):
    return '' if v is None else str(int(round(v)))

def yen(v):
    return '' if v is None else f'¥{v:,.0f}'

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
