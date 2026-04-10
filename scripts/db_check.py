"""
DB確認スクリプト
れいな担当：keiba.dbの中身を把握してPhase 2の設計に使う

使い方:
  python scripts/db_check.py --db path/to/keiba.db
"""
import argparse
import os
import sqlite3
import sys

# 血統関連キーワード
PEDIGREE_KEYWORDS = ["父", "母", "系統", "blood", "pedigree", "sire", "dam", "broodmare", "種牡馬", "繁殖"]

# コース関連キーワード
COURSE_KEYWORDS = ["場", "距離", "回り", "track", "course", "distance", "芝", "ダート", "surface", "馬場"]

LINE = "=" * 70
THIN_LINE = "-" * 70


def get_tables(cur):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cur.fetchall()]


def get_row_count(cur, table):
    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
    return cur.fetchone()[0]


def get_columns(cur, table):
    cur.execute(f'PRAGMA table_info("{table}")')
    return [(row[1], row[2]) for row in cur.fetchall()]  # (name, type)


def get_sample_rows(cur, table, columns, limit=3):
    col_names = [c[0] for c in columns]
    cur.execute(f'SELECT * FROM "{table}" LIMIT {limit}')
    rows = cur.fetchall()
    return col_names, rows


def match_keywords(col_name, keywords):
    lower = col_name.lower()
    return any(kw.lower() in lower for kw in keywords)


def format_sample_value(val):
    if val is None:
        return "NULL"
    s = str(val)
    if len(s) > 50:
        return s[:50] + "..."
    return s


def main():
    parser = argparse.ArgumentParser(description="keiba.db 確認スクリプト")
    parser.add_argument("--db", required=True, help="keiba.db のパス")
    args = parser.parse_args()

    db_path = args.db
    if not os.path.exists(db_path):
        print(f"エラー: DBファイルが見つかりません: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    tables = get_tables(cur)
    if not tables:
        print("エラー: テーブルが存在しません。")
        conn.close()
        sys.exit(1)

    output_lines = []

    def out(text=""):
        print(text)
        output_lines.append(text)

    out(LINE)
    out("  keiba.db レポート")
    out(f"  DB: {db_path}")
    out(LINE)

    # 1. テーブル一覧
    out("")
    out("【1】テーブル一覧")
    out(THIN_LINE)
    out(f"  {'テーブル名':<30} {'レコード数':>10}")
    out(THIN_LINE)
    table_counts = {}
    for t in tables:
        count = get_row_count(cur, t)
        table_counts[t] = count
        out(f"  {t:<30} {count:>10,}")
    out(THIN_LINE)
    out(f"  合計 {len(tables)} テーブル")
    out("")

    # 2. 各テーブルのカラム・サンプル
    out("【2】各テーブルのカラム・サンプル値（先頭3件）")
    out(LINE)

    pedigree_hits = []  # (table, col_name)
    course_hits = []

    for t in tables:
        columns = get_columns(cur, t)
        col_names, rows = get_sample_rows(cur, t, columns)

        out(f"\n■ {t}  ({table_counts[t]:,} 件)")
        out(THIN_LINE)

        # カラムヘッダー
        for i, (cname, ctype) in enumerate(columns):
            # サンプル値を集める
            samples = []
            all_null = True
            for row in rows:
                val = row[i]
                if val is not None:
                    all_null = False
                samples.append(format_sample_value(val))

            sample_str = "サンプルなし" if all_null else " | ".join(samples)
            out(f"  {cname:<25} {ctype:<12} {sample_str}")

            # キーワードマッチ
            if match_keywords(cname, PEDIGREE_KEYWORDS):
                pedigree_hits.append((t, cname))
            if match_keywords(cname, COURSE_KEYWORDS):
                course_hits.append((t, cname))

        out(THIN_LINE)

    # 3. 血統関連カラム
    out("")
    out("【3】血統関連と思われるカラム")
    out(THIN_LINE)
    if pedigree_hits:
        for tbl, col in pedigree_hits:
            out(f"  {tbl}.{col}")
    else:
        out("  該当なし")
    out("")

    # 4. コース関連カラム
    out("【4】コース関連と思われるカラム")
    out(THIN_LINE)
    if course_hits:
        for tbl, col in course_hits:
            out(f"  {tbl}.{col}")
    else:
        out("  該当なし")
    out("")

    conn.close()

    # レポートファイル保存
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    out(LINE)
    out(f"れいな：確認完了。db_report.txtを見てPhase 2の設計を始めます")
    out(f"  保存先: {report_path}")
    out(LINE)


if __name__ == "__main__":
    main()
