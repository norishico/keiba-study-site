"""
DB→JSON エクスポートスクリプト
れいな担当：keiba.dbから学習サイト用JSONを生成する

使い方:
  python scripts/export_data.py --db path/to/keiba.db
"""
import argparse
import json
import os
import random
import sqlite3
import sys
from datetime import datetime


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def r3(v):
    """小数点3桁に丸める"""
    if v is None:
        return None
    return round(v, 3)


def dist_label(dist):
    if dist is None:
        return "不明"
    if dist <= 1400:
        return f"短距離（{dist}m）"
    if dist == 1600:
        return "マイル（1600m）"
    if 1800 <= dist <= 2000:
        return f"中距離（{dist}m）"
    if 2200 <= dist <= 2500:
        return f"中長距離（{dist}m）"
    return f"長距離（{dist}m）"


# ============================================================
# 出力1: pedigree.json
# ============================================================
def export_pedigree(cur, now_str):
    # 直近3年（2023〜）のデータでpedigreeを集計（2026年の予想に使える情報に限定）
    RECENT_FROM = "2023-01-01"

    # 直近3年の sire別 芝/ダート勝率・複勝率を results から直接集計
    cur.execute(f"""
        SELECT sire,
            COUNT(*) as total_n,
            AVG(CASE WHEN surface='芝' AND finish=1 THEN 1.0 WHEN surface='芝' THEN 0.0 END) AS turf_wr,
            AVG(CASE WHEN surface!='芝' AND finish=1 THEN 1.0 WHEN surface!='芝' THEN 0.0 END) AS dirt_wr,
            AVG(CASE WHEN finish<=3 THEN 1.0 ELSE 0.0 END) AS top3_rate
        FROM results
        WHERE date >= '{RECENT_FROM}'
          AND finish IS NOT NULL AND sire IS NOT NULL
        GROUP BY sire
        HAVING COUNT(*) >= 100
        ORDER BY COUNT(*) DESC
    """)
    sire_stats = {}
    for row in cur.fetchall():
        name, total_n, turf_wr, dirt_wr, top3_rate = row
        sire_stats[name] = {
            "turf_win_rate": r3(turf_wr),
            "dirt_win_rate": r3(dirt_wr),
            "top3_rate": r3(top3_rate),
            "total_n": total_n,
        }

    # 得意距離: 直近3年の results から sire×distance で勝率最大を選ぶ
    # 平地主要距離のみ（障害レースの半端な距離を除外）
    flat_dists = [1000,1200,1400,1600,1800,2000,2200,2400,2500,3000,3200,3600]
    flat_ph = ",".join(str(d) for d in flat_dists)
    cur.execute(f"""
        SELECT sire, distance,
            AVG(CASE WHEN finish=1 THEN 1.0 ELSE 0.0 END) AS wr,
            COUNT(*) AS n
        FROM results
        WHERE date >= '{RECENT_FROM}' AND finish IS NOT NULL AND sire IS NOT NULL
          AND distance IN ({flat_ph})
        GROUP BY sire, distance
        HAVING COUNT(*) >= 30
    """)
    best_dist = {}
    for name, dist, wr, n in cur.fetchall():
        if wr is None:
            continue
        if name not in best_dist or wr > best_dist[name][1]:
            best_dist[name] = (dist, wr)

    # 脚質
    cur.execute("SELECT sire, style, confidence FROM sire_running_style")
    style_map = {}
    for sire, style, conf in cur.fetchall():
        style_map[sire] = (style, conf)

    # 脚質ラベル変換（初心者向け）
    style_labels = {
        "先行": "先行（前の方で競馬する）",
        "差追": "差し・追込（後方から追い上げる）",
        "中団": "中団（真ん中あたりで待機）",
        "先団": "先団（前寄りの集団）",
        "後方": "追込（最後方から一気に）",
    }

    # 結合して total_n 降順上位50件（＝直近3年でメジャーな種牡馬優先）
    sires = []
    for name, st in sire_stats.items():
        bd = best_dist.get(name)
        rs = style_map.get(name)
        raw_style = rs[0] if rs else None
        sires.append({
            "name": name,
            "turf_win_rate": st["turf_win_rate"],
            "dirt_win_rate": st["dirt_win_rate"],
            "best_distance": bd[0] if bd else None,
            "best_distance_label": dist_label(bd[0] if bd else None),
            "top3_rate": st["top3_rate"],
            "total_n": st["total_n"],
            "running_style": raw_style,
            "running_style_label": style_labels.get(raw_style, raw_style) if raw_style else None,
        })

    sires.sort(key=lambda x: x["total_n"] or 0, reverse=True)
    sires = sires[:50]

    out = {"generated_at": now_str, "sires": sires}
    path = os.path.join(OUTPUT_DIR, "pedigree.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[OK] pedigree.json 生成完了：{len(sires)}件")


# ============================================================
# 出力2: course.json（会場別×馬場別、全枠・全脚質の勝率）
# ============================================================
def export_course(cur, now_str):
    venues = ["東京", "中山", "阪神", "京都", "中京", "新潟", "札幌", "函館", "福島", "小倉"]
    placeholders = ",".join("?" * len(venues))

    # 脚質ラベル変換
    style_labels = {"先団": "先行", "中団": "中団", "後方": "追込"}

    # 枠別勝率
    cur.execute(f"""
        SELECT venue, surface, gate_cat, AVG(win_rate) AS avg_wr
        FROM track_bias_bonus
        WHERE venue IN ({placeholders})
        GROUP BY venue, surface, gate_cat
    """, venues)
    gate_map = {}
    for venue, surface, gate_cat, avg_wr in cur.fetchall():
        key = (venue, surface)
        if key not in gate_map:
            gate_map[key] = {}
        gate_map[key][gate_cat] = r3(avg_wr)

    # 脚質別勝率
    cur.execute(f"""
        SELECT venue, surface, style_cat, AVG(win_rate) AS avg_wr
        FROM track_bias_bonus
        WHERE venue IN ({placeholders})
        GROUP BY venue, surface, style_cat
    """, venues)
    style_map_c = {}
    for venue, surface, style_cat, avg_wr in cur.fetchall():
        key = (venue, surface)
        if key not in style_map_c:
            style_map_c[key] = {}
        label = style_labels.get(style_cat, style_cat)
        style_map_c[key][label] = r3(avg_wr)

    courses = []
    for venue in venues:
        for surface in ["芝", "ダ"]:
            key = (venue, surface)
            gates = gate_map.get(key, {})
            styles = style_map_c.get(key, {})
            if not gates and not styles:
                continue
            surf_label = "芝" if surface == "芝" else "ダート"
            courses.append({
                "venue": venue,
                "surface": surf_label,
                "gates": {
                    "内枠": gates.get("内枠", 0),
                    "中枠": gates.get("中枠", 0),
                    "外枠": gates.get("外枠", 0),
                },
                "styles": {
                    "先行": styles.get("先行", 0),
                    "中団": styles.get("中団", 0),
                    "追込": styles.get("追込", 0),
                },
            })

    out = {"generated_at": now_str, "courses": courses}
    path = os.path.join(OUTPUT_DIR, "course.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[OK] course.json 生成完了：{len(courses)}件")


# ============================================================
# 出力3: affinity.json → 期待値条件（EV conditions）
# ============================================================
VENUES_ORDER = ["東京", "中山", "阪神", "京都", "中京", "新潟", "札幌", "函館", "福島", "小倉"]

def export_affinity(cur, now_str):
    # --- A: roi_hotspot から 血統×コース×距離×枠 の期待値条件（会場別） ---
    cur.execute("""
        SELECT sire, venue, surface, distance, gate_cat,
               n, win_rate, tansho_roi, fukusho_roi
        FROM roi_hotspot
        WHERE (tansho_roi > 100 OR fukusho_roi > 100)
          AND n >= 20
          AND sire IS NOT NULL
          AND distance IS NOT NULL
        ORDER BY tansho_roi DESC
    """)
    hotspots_by_venue = {v: [] for v in VENUES_ORDER}
    hotspots_other = []
    for row in cur.fetchall():
        sire, venue, surface, dist, gate, n, wr, t_roi, f_roi = row
        surf_label = "芝" if surface == "芝" else "ダート"
        item = {
            "sire": sire,
            "surface": surf_label,
            "distance": dist,
            "gate": gate or "全枠",
            "n": n,
            "win_rate_pct": r3(wr * 100) if wr and wr < 1 else r3(wr),
            "tansho_roi": r3(t_roi),
            "fukusho_roi": r3(f_roi),
        }
        if venue in hotspots_by_venue:
            hotspots_by_venue[venue].append(item)
        else:
            hotspots_other.append(item)

    # --- B: results から 血統×コース×距離（枠なし）の大粒度集計（会場別） ---
    cur.execute("""
        SELECT r.sire, r.venue, r.surface, r.distance,
            COUNT(*) as n,
            SUM(CASE WHEN r.finish=1 THEN 1 ELSE 0 END) as wins,
            ROUND(AVG(CASE WHEN r.finish=1 THEN r.odds ELSE 0 END)*100, 1) as tansho_roi,
            COUNT(CASE WHEN r.finish<=3 THEN 1 END) as top3,
            ROUND(COUNT(CASE WHEN r.finish<=3 THEN 1 END)*1.0/COUNT(*)*100, 1) as top3_rate,
            ROUND(
              SUM(CASE
                WHEN r.finish=1 THEN COALESCE(d.fukusho1_payout,0)
                WHEN r.finish=2 THEN COALESCE(d.fukusho2_payout,0)
                WHEN r.finish=3 THEN COALESCE(d.fukusho3_payout,0)
                ELSE 0 END) * 1.0 / COUNT(*), 1
            ) as fukusho_roi
        FROM results r
        LEFT JOIN dividends d ON r.race_id = d.race_id
        WHERE r.finish IS NOT NULL AND r.odds IS NOT NULL
        GROUP BY r.sire, r.venue, r.surface, r.distance
        HAVING COUNT(*) >= 30
          AND AVG(CASE WHEN r.finish=1 THEN r.odds ELSE 0 END)*100 > 100
        ORDER BY tansho_roi DESC
    """)
    broad_by_venue = {v: [] for v in VENUES_ORDER}
    for row in cur.fetchall():
        sire, venue, surface, dist, n, wins, t_roi, top3, top3_rate, f_roi = row
        surf_label = "芝" if surface == "芝" else "ダート"
        item = {
            "sire": sire,
            "surface": surf_label,
            "distance": dist,
            "n": n,
            "wins": wins,
            "tansho_roi": r3(t_roi),
            "fukusho_roi": r3(f_roi),
            "top3": top3,
            "top3_rate": r3(top3_rate),
        }
        if venue in broad_by_venue:
            broad_by_venue[venue].append(item)

    # --- C: 距離変更×血統 の期待値条件 ---
    cur.execute("""
        SELECT sire,
          CASE WHEN distance > prev_distance THEN '延長'
               WHEN distance < prev_distance THEN '短縮'
               ELSE '同距離' END as dist_chg,
          venue, surface, distance,
          COUNT(*) as n,
          SUM(CASE WHEN finish=1 THEN 1 ELSE 0 END) as wins,
          ROUND(AVG(CASE WHEN finish=1 THEN odds ELSE 0 END)*100, 1) as tansho_roi,
          COUNT(CASE WHEN finish<=3 THEN 1 END) as top3,
          ROUND(COUNT(CASE WHEN finish<=3 THEN 1 END)*1.0/COUNT(*)*100, 1) as top3_rate
        FROM results
        WHERE finish IS NOT NULL AND odds IS NOT NULL
          AND prev_distance IS NOT NULL AND prev_distance > 0
          AND distance != prev_distance
        GROUP BY sire, dist_chg, venue, surface, distance
        HAVING COUNT(*) >= 30
          AND AVG(CASE WHEN finish=1 THEN odds ELSE 0 END)*100 > 100
        ORDER BY tansho_roi DESC
    """)
    dist_change = {"延長": [], "短縮": []}
    for row in cur.fetchall():
        sire, chg, venue, surface, dist, n, wins, t_roi, top3, top3_rate = row
        surf_label = "芝" if surface == "芝" else "ダート"
        item = {
            "sire": sire,
            "venue": venue,
            "surface": surf_label,
            "distance": dist,
            "n": n,
            "wins": wins,
            "tansho_roi": r3(t_roi),
            "top3": top3,
            "top3_rate": r3(top3_rate),
        }
        if chg in dist_change:
            dist_change[chg].append(item)

    total_hotspot = sum(len(v) for v in hotspots_by_venue.values())
    total_broad = sum(len(v) for v in broad_by_venue.values())
    total_dc = sum(len(v) for v in dist_change.values())

    out = {
        "generated_at": now_str,
        "venues": VENUES_ORDER,
        "hotspots_by_venue": hotspots_by_venue,
        "broad_by_venue": broad_by_venue,
        "dist_change": dist_change,
    }
    path = os.path.join(OUTPUT_DIR, "affinity.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[OK] affinity.json 生成完了：hotspot {total_hotspot}件 / broad {total_broad}件 / 距離変更 {total_dc}件")


# ============================================================
# 出力4: quiz.json（100問規模）
# ============================================================

def _make_q(qid, cat, src, question, choices, answer, explanation):
    """問題テンプレート"""
    return {"id": qid, "category": cat, "source": src,
            "question": question, "choices": choices,
            "answer": answer, "explanation": explanation}


def _pick_wrongs(cur, sql, params, correct, n=3):
    """不正解肢をランダムに取得"""
    cur.execute(sql, params)
    wrongs = [r[0] for r in cur.fetchall() if r[0] != correct]
    random.shuffle(wrongs)
    return wrongs[:n]


def _shuffle_choices(correct, wrongs):
    """選択肢シャッフルして正解indexを返す"""
    choices = [correct] + wrongs
    random.shuffle(choices)
    return choices, choices.index(correct)


def export_quiz(cur, now_str):
    questions = []
    qid = 1
    venues_all = ["東京", "中山", "阪神", "京都", "中京", "新潟", "札幌", "函館", "福島", "小倉"]

    # メジャー種牡馬リスト（出走500件以上 & 2025年以降も出走あり）
    cur.execute("""
        SELECT sire FROM results
        GROUP BY sire
        HAVING COUNT(*) >= 500
          AND MAX(date) >= '2025-01-01'
    """)
    major_sires = set(r[0] for r in cur.fetchall())

    # ================================================================
    # タイプ1: 血統×距離 — 勝率1位の父（10問）
    # ================================================================
    cur.execute("""
        SELECT DISTINCT surface, dist_bucket FROM bloodline_stats
        WHERE col_type = 'sire' AND dist_bucket IS NOT NULL
    """)
    combos = cur.fetchall()
    random.shuffle(combos)
    for surface, dist_bucket in combos:
        if qid > 10:
            break
        sl = "芝" if surface == "芝" else "ダート"
        cur.execute("""
            SELECT name, win_rate FROM bloodline_stats
            WHERE col_type='sire' AND surface=? AND dist_bucket=? AND n>=30
            ORDER BY win_rate DESC LIMIT 10
        """, (surface, dist_bucket))
        top = None
        for row in cur.fetchall():
            if row[0] in major_sires:
                top = row
                break
        if not top:
            continue
        wrongs = _pick_wrongs(cur, """
            SELECT name FROM bloodline_stats
            WHERE col_type='sire' AND surface=? AND dist_bucket=? AND name!=? AND n>=20
            ORDER BY RANDOM() LIMIT 20
        """, (surface, dist_bucket, top[0]), top[0])
        wrongs = [w for w in wrongs if w in major_sires]
        if len(wrongs) < 3:
            continue
        ch, ai = _shuffle_choices(top[0], wrongs[:3])
        questions.append(_make_q(qid, "血統×距離", "db_auto",
            f"{sl}{dist_bucket}mで最も勝率が高い父は？", ch, ai,
            f"過去7年のデータで、{sl}{dist_bucket}mでは{top[0]}産駒の勝率{r3(top[1])}が最も高い結果が出ています。"))
        qid += 1

    # ================================================================
    # タイプ2: コースバイアス — 有利な枠（10問：全10場）
    # ================================================================
    random.shuffle(venues_all)
    for venue in venues_all:
        if qid > 20:
            break
        surface = random.choice(["芝", "ダ"])
        sl = "芝" if surface == "芝" else "ダート"
        cur.execute("""
            SELECT gate_cat, AVG(win_rate) AS avg_wr FROM track_bias_bonus
            WHERE venue=? AND surface=? GROUP BY gate_cat ORDER BY avg_wr DESC
        """, (venue, surface))
        rows = cur.fetchall()
        if not rows or rows[0][0] not in ["内枠", "中枠", "外枠"]:
            continue
        ch = ["内枠", "中枠", "外枠", "枠の影響なし"]
        ai = ch.index(rows[0][0])
        questions.append(_make_q(qid, "コースバイアス", "db_auto",
            f"{venue}{sl}コースで最も有利な枠は？", ch, ai,
            f"過去7年のデータで、{venue}{sl}では{rows[0][0]}（平均勝率{r3(rows[0][1])}%）が最も有利です。"))
        qid += 1

    # ================================================================
    # タイプ3: 血統×コース相性 — ボーナス上位（10問）
    # ================================================================
    random.shuffle(venues_all)
    for venue in venues_all:
        if qid > 30:
            break
        cur.execute("""
            SELECT sire, AVG(bonus) AS avg_b FROM venue_sire_bonus
            WHERE venue=? GROUP BY sire ORDER BY avg_b DESC LIMIT 10
        """, (venue,))
        top = None
        for row in cur.fetchall():
            if row[0] in major_sires:
                top = row
                break
        if not top:
            continue
        wrongs = _pick_wrongs(cur, """
            SELECT sire FROM venue_sire_bonus WHERE venue=? AND sire!=?
            GROUP BY sire ORDER BY RANDOM() LIMIT 20
        """, (venue, top[0]), top[0])
        wrongs = [w for w in wrongs if w in major_sires]
        if len(wrongs) < 3:
            continue
        ch, ai = _shuffle_choices(top[0], wrongs[:3])
        questions.append(_make_q(qid, "血統×コース", "db_auto",
            f"{venue}競馬場で最も好走率が高い父は？", ch, ai,
            f"過去7年のデータで、{venue}では{top[0]}産駒の好走率が他の種牡馬より明確に高い結果が出ています。"))
        qid += 1

    # ================================================================
    # タイプ4: 期待値条件 — 回収率上位の種牡馬（10問）
    # ================================================================
    cur.execute("""
        SELECT sire, venue, surface, distance, tansho_roi FROM roi_hotspot
        WHERE tansho_roi > 200 AND n >= 30 AND sire IS NOT NULL AND distance IS NOT NULL
        ORDER BY RANDOM() LIMIT 80
    """)
    ev_rows = [(s,v,sf,d,t) for s,v,sf,d,t in cur.fetchall() if s in major_sires]
    random.shuffle(ev_rows)
    for sire, venue, surface, dist, t_roi in ev_rows:
        if qid > 40:
            break
        sl = "芝" if surface == "芝" else "ダート"
        wrongs = _pick_wrongs(cur, """
            SELECT DISTINCT sire FROM roi_hotspot
            WHERE venue=? AND surface=? AND distance=? AND sire!=? AND sire IS NOT NULL
            ORDER BY RANDOM() LIMIT 20
        """, (venue, surface, dist, sire), sire)
        wrongs = [w for w in wrongs if w in major_sires]
        if len(wrongs) < 3:
            continue
        ch, ai = _shuffle_choices(sire, wrongs[:3])
        questions.append(_make_q(qid, "期待値", "db_auto",
            f"{venue}{sl}{dist}mで単勝回収率が最も高い父は？", ch, ai,
            f"過去7年のデータで、{venue}{sl}{dist}mでは{sire}産駒の単勝回収率が{r3(t_roi)}%と突出しています。"))
        qid += 1

    # ================================================================
    # タイプ5: 距離変更 — 延長/短縮で好成績の父（10問）
    # ================================================================
    cur.execute("""
        SELECT sire,
          CASE WHEN distance > prev_distance THEN '延長' ELSE '短縮' END as chg,
          venue, surface, distance,
          ROUND(AVG(CASE WHEN finish=1 THEN odds ELSE 0 END)*100, 1) as t_roi
        FROM results
        WHERE finish IS NOT NULL AND odds IS NOT NULL
          AND prev_distance IS NOT NULL AND prev_distance > 0
          AND distance != prev_distance
        GROUP BY sire, chg, venue, surface, distance
        HAVING COUNT(*) >= 30 AND AVG(CASE WHEN finish=1 THEN odds ELSE 0 END)*100 > 200
        ORDER BY RANDOM() LIMIT 40
    """)
    dc_rows = [(s,c,v,sf,d,t) for s,c,v,sf,d,t in cur.fetchall() if s in major_sires]
    for sire, chg, venue, surface, dist, t_roi in dc_rows:
        if qid > 50:
            break
        sl = "芝" if surface == "芝" else "ダート"
        wrongs = _pick_wrongs(cur, """
            SELECT DISTINCT sire FROM results
            WHERE venue=? AND surface=? AND distance=? AND sire!=?
              AND prev_distance IS NOT NULL AND prev_distance > 0
            GROUP BY sire HAVING COUNT(*) >= 20
            ORDER BY RANDOM() LIMIT 20
        """, (venue, surface, dist, sire), sire)
        wrongs = [w for w in wrongs if w in major_sires]
        if len(wrongs) < 3:
            continue
        ch, ai = _shuffle_choices(sire, wrongs[:3])
        questions.append(_make_q(qid, "距離変更", "db_auto",
            f"距離{chg}で{venue}{sl}{dist}mに出走した時、最も回収率が高い父は？", ch, ai,
            f"過去7年のデータで、距離{chg}時の{venue}{sl}{dist}mでは{sire}産駒の単勝回収率が{r3(t_roi)}%です。"))
        qid += 1

    # ================================================================
    # タイプ6: 脚質 — 種牡馬の得意脚質（5問）
    # ================================================================
    cur.execute("""
        SELECT sire, style, confidence FROM sire_running_style
        WHERE confidence >= 0.5 ORDER BY RANDOM() LIMIT 40
    """)
    style_rows = [(s,st,c) for s,st,c in cur.fetchall() if s in major_sires]
    for sire, style, conf in style_rows:
        if qid > 55:
            break
        all_styles = ["先行", "差追", "中団", "後方"]
        if style not in all_styles:
            continue
        others = [s for s in all_styles if s != style]
        random.shuffle(others)
        ch = [style] + others[:3]
        random.shuffle(ch)
        ai = ch.index(style)
        questions.append(_make_q(qid, "脚質", "db_auto",
            f"{sire}産駒に最も多い脚質は？", ch, ai,
            f"過去7年のデータで、{sire}産駒は{style}で好走するケースが最も多い傾向があります。"))
        qid += 1

    # ================================================================
    # 手書き問題（80問：血統25+コース20+馬場10+EV5+血統×コース20）
    # ================================================================
    manual_questions = [
        # --- 血統基礎（25問） ---
        {"category": "血統基礎", "question": "サンデーサイレンス系の特徴として正しいものは？", "choices": ["短距離に強い", "晩成型が多い", "瞬発力が高く末脚が切れる", "ダートを得意とする"], "answer": 2, "explanation": "サンデーサイレンス系は瞬発力に優れ、直線での末脚の切れが最大の武器。"},
        {"category": "血統基礎", "question": "ロードカナロア産駒の得意条件は？", "choices": ["芝の長距離", "ダートのマイル", "芝の短距離〜マイル", "重馬場の中距離"], "answer": 2, "explanation": "ロードカナロアはスプリント王。産駒も芝の短距離〜マイルで好成績。アーモンドアイは例外的な中距離馬。"},
        {"category": "血統基礎", "question": "ハーツクライ産駒の特徴は？", "choices": ["仕上がりが早い", "短距離が得意", "晩成型が多い", "ダート専用"], "answer": 2, "explanation": "ハーツクライ産駒は晩成型が多く、3歳秋〜古馬で本格化。東京の中〜長距離が主戦場。"},
        {"category": "血統基礎", "question": "ミスタープロスペクター系の特徴は？", "choices": ["スタミナ特化", "スピードとパワーを兼備", "重馬場専門", "長距離のみ"], "answer": 1, "explanation": "MP系はスピードとパワーを兼備。ダート戦で特に強く、芝でも短距離〜マイルで活躍。"},
        {"category": "血統基礎", "question": "ノーザンダンサー系が最も得意とする条件は？", "choices": ["東京の高速馬場", "重馬場や洋芝", "ダートの短距離", "新馬戦"], "answer": 1, "explanation": "ND系は欧州型のスタミナ・パワー血統。重馬場や洋芝（札幌・函館）で真価を発揮。"},
        {"category": "血統基礎", "question": "ディープインパクト産駒が苦手な条件は？", "choices": ["東京芝2400m", "京都芝1600m", "重馬場・不良馬場", "阪神外回り"], "answer": 2, "explanation": "ディープ産駒は良馬場で真価を発揮するが、重馬場ではパワー不足で成績が落ちる傾向。"},
        {"category": "血統基礎", "question": "エピファネイア産駒の強みは？", "choices": ["スプリント専門", "パワーとスタミナを兼備し道悪もこなす", "ダートのみ", "4歳以降のみ活躍"], "answer": 1, "explanation": "エピファネイアはロベルト系の血を持ち、パワーとスタミナを兼備。道悪も苦にしない。"},
        {"category": "血統基礎", "question": "ヘニーヒューズ産駒が最も得意な条件は？", "choices": ["芝の中距離", "ダートの短距離", "芝の長距離", "洋芝"], "answer": 1, "explanation": "ヘニーヒューズはダートの王様。ダート短距離〜マイルが主戦場。2歳ダートで特に強い。"},
        {"category": "血統基礎", "question": "キズナ産駒の最大の特徴は？", "choices": ["芝専門", "芝・ダート両方こなす万能型", "ダート専門", "スプリンター"], "answer": 1, "explanation": "キズナはディープ直仔。芝・ダート両方こなす万能型で、父より馬場を問わない柔軟性がある。"},
        {"category": "血統基礎", "question": "ゴールドシップ産駒の特徴は？", "choices": ["仕上がりが早い", "気性が荒いがスタミナ抜群", "ダート専門", "良馬場のマイラー"], "answer": 1, "explanation": "ゴールドシップは気性が荒いが底力抜群。中山・阪神の急坂コースで真価を発揮。"},
        {"category": "血統基礎", "question": "出馬表で予想に最も重要な血統情報は？", "choices": ["馬の毛色", "父と母父の2つ", "母の成績", "兄弟の戦績"], "answer": 1, "explanation": "予想で最も重要なのは「父」と「母父」の2つ。この2つで血統予想の8割はカバーできる。"},
        {"category": "血統基礎", "question": "シニスターミニスター産駒の特徴は？", "choices": ["芝のクラシック", "ダート中距離のスペシャリスト", "洋芝専門", "マイルの先行馬"], "answer": 1, "explanation": "ダート中距離のスペシャリスト。重馬場でさらに成績アップし、穴馬候補の常連。"},
        {"category": "血統基礎", "question": "ダイワメジャー産駒の得意な競馬スタイルは？", "choices": ["追い込み", "先行して粘る", "大逃げ", "最後方から一気に"], "answer": 1, "explanation": "マイル〜短距離の先行力が武器。仕上がりが早く直線の短いコースで好成績。"},
        {"category": "血統基礎", "question": "ドゥラメンテ産駒のG1馬として正しいのは？", "choices": ["ドウデュース", "リバティアイランド", "イクイノックス", "ソダシ"], "answer": 1, "explanation": "リバティアイランドはドゥラメンテ産駒で2023年牝馬三冠を達成。"},
        {"category": "血統基礎", "question": "「非主流血統」が予想で重要な理由は？", "choices": ["常に勝率が高い", "人気になりにくく回収率が高くなりやすい", "血統表が華やか", "調教が良い"], "answer": 1, "explanation": "非主流血統は人気にならないため、好走時の配当が大きい。期待値が高くなりやすい。"},
        {"category": "血統基礎", "question": "キタサンブラック産駒の特徴は？", "choices": ["短距離専門", "芝中〜長距離でスタミナとパワーに優れる", "ダート専門", "仕上がりが遅い"], "answer": 1, "explanation": "キタサンブラックは自身G1を7勝。産駒はスタミナとパワーに優れ、イクイノックスを輩出。"},
        {"category": "血統基礎", "question": "モーリス産駒が最も得意な距離帯は？", "choices": ["1000〜1200m", "1600〜2000m", "2400〜3000m", "3000m以上"], "answer": 1, "explanation": "モーリスは自身がマイルCS・安田記念を制したマイラー。産駒もマイル〜中距離がベスト。"},
        {"category": "血統基礎", "question": "ルーラーシップ産駒の特徴は？", "choices": ["スプリント専門", "安定感があり大崩れしにくい万能型", "気性難で扱いにくい", "ダート専門"], "answer": 1, "explanation": "キングカメハメハの後継で万能型。芝中〜長距離がメインだが安定感があり大崩れしにくい。"},
        {"category": "血統基礎", "question": "ドレフォン産駒の特徴は？", "choices": ["芝の長距離専門", "ダート短距離〜マイルで好成績、芝スプリントも可", "重馬場専門", "晩成型"], "answer": 1, "explanation": "米国スプリントG1馬。ダート短距離〜マイルで好成績。芝でもスプリント戦なら対応可能。"},
        {"category": "血統基礎", "question": "ハービンジャー産駒の最大の武器は？", "choices": ["高速馬場での瞬発力", "洋芝・重馬場での圧倒的な適性", "ダートでの爆発力", "スプリント力"], "answer": 1, "explanation": "欧州ND系の代表格。洋芝・重馬場で無類の強さ。母父としても大きな影響力を持つ。"},
        {"category": "血統基礎", "question": "オルフェーヴル産駒が得意なレースタイプは？", "choices": ["高速馬場のスプリント", "スタミナ勝負の消耗戦", "平坦コースのマイル", "ダート短距離"], "answer": 1, "explanation": "三冠馬の血統力。気性の激しさと底力が特徴で、消耗戦やタフな馬場で真価を発揮。"},
        {"category": "血統基礎", "question": "アーモンドアイの父は？", "choices": ["ディープインパクト", "ロードカナロア", "キングカメハメハ", "ハーツクライ"], "answer": 1, "explanation": "アーモンドアイは父ロードカナロア。スプリント王の産駒ながら中距離でも活躍した例外的な名馬。"},
        {"category": "血統基礎", "question": "コントレイルの父は？", "choices": ["キズナ", "エピファネイア", "ディープインパクト", "ハーツクライ"], "answer": 2, "explanation": "コントレイルは父ディープインパクト。2020年に無敗の三冠を達成した。"},
        {"category": "血統基礎", "question": "テーオーケインズの父は？", "choices": ["ヘニーヒューズ", "シニスターミニスター", "ゴールドアリュール", "ドレフォン"], "answer": 1, "explanation": "テーオーケインズは父シニスターミニスター。チャンピオンズカップなどダートG1を複数勝利。"},
        {"category": "血統基礎", "question": "ソングラインの父は？", "choices": ["ディープインパクト", "モーリス", "キズナ", "エピファネイア"], "answer": 2, "explanation": "ソングラインは父キズナ。安田記念を連覇したマイルの名牝。"},

        # --- コース知識（20問） ---
        {"category": "コース知識", "question": "東京競馬場の芝コースの最大の特徴は？", "choices": ["直線525m（日本最長級）", "急坂が3つある", "右回り", "洋芝"], "answer": 0, "explanation": "東京は直線525mと日本最長級。末脚の持続力が問われ、差し・追い込みが有利。"},
        {"category": "コース知識", "question": "中山競馬場の芝コースの特徴は？", "choices": ["直線が長く差し有利", "急坂を登るパワーとスタミナが重要", "平坦でスピード勝負", "洋芝"], "answer": 1, "explanation": "中山は直線310mで急坂が2回。パワーが重要で先行力型が有利。有馬記念の舞台。"},
        {"category": "コース知識", "question": "阪神の外回りと内回りの違いは？", "choices": ["外回りが先行有利", "外回りが差し有利、内回りはパワー型有利", "どちらも同じ", "外回りはダート専用"], "answer": 1, "explanation": "阪神外回りは直線473mで差し有利。内回りは直線356mで中山に近くパワー型有利。"},
        {"category": "コース知識", "question": "札幌・函館の芝の特徴は？", "choices": ["野芝で高速", "洋芝で時計がかかりやすい", "ダートのみ", "急坂が多い"], "answer": 1, "explanation": "北海道は洋芝で時計がかかりやすい。欧州型血統（ハービンジャー等）が適性を示す。"},
        {"category": "コース知識", "question": "新潟外回りの直線の長さは？", "choices": ["310m", "473m", "525m", "659m（日本最長）"], "answer": 3, "explanation": "新潟外回りは日本最長の直線659m。坂がなく完全な瞬発力勝負。"},
        {"category": "コース知識", "question": "有馬記念のコースは？", "choices": ["東京芝2400m", "阪神芝2200m", "中山芝2500m", "京都芝3000m"], "answer": 2, "explanation": "有馬記念は中山芝2500m。小回りで先行力とスタミナが求められる。"},
        {"category": "コース知識", "question": "京都の「淀の坂」とは？", "choices": ["ゴール前の急坂", "3コーナーの下り坂", "スタート直後の上り", "バックストレッチの坂"], "answer": 1, "explanation": "京都の淀の坂は3コーナーの下り坂。スピードが乗りやすく差し追込が決まりやすい。"},
        {"category": "コース知識", "question": "ダート重馬場の特徴は？", "choices": ["時計がかかる", "砂が締まり時計が速くなる（芝と逆）", "中止になる", "影響なし"], "answer": 1, "explanation": "ダート重馬場は砂が締まり時計が速くなる。芝と逆の傾向でスピード型が有利。"},
        {"category": "コース知識", "question": "小倉競馬場の特徴は？", "choices": ["直線が長く差し有利", "洋芝", "平坦で時計が速く先行有利", "急坂あり"], "answer": 2, "explanation": "小倉は平坦で時計が速い。先行馬が有利でスプリント血統が台頭しやすい。"},
        {"category": "コース知識", "question": "ダートの外枠が有利な理由は？", "choices": ["距離が短い", "砂をかぶらない", "コーナーが近い", "芝スタート"], "answer": 1, "explanation": "ダートでは先行馬の砂が後方に飛ぶ。外枠は砂を被りにくく有利。"},
        {"category": "コース知識", "question": "日本ダービーのコースは？", "choices": ["中山芝2500m", "東京芝2400m", "阪神芝2400m", "京都芝2400m"], "answer": 1, "explanation": "日本ダービーは東京芝2400m。長い直線で末脚勝負になりやすい。"},
        {"category": "コース知識", "question": "桜花賞のコースは？", "choices": ["東京芝1600m", "阪神芝1600m（外回り）", "中山芝1600m", "京都芝1600m"], "answer": 1, "explanation": "桜花賞は阪神芝1600m外回り。直線473mで差しが決まりやすい。"},
        {"category": "コース知識", "question": "天皇賞春のコースは？", "choices": ["東京芝2400m", "中山芝3200m", "京都芝3200m", "阪神芝3200m"], "answer": 2, "explanation": "天皇賞春は京都芝3200m。圧倒的なスタミナが求められる長距離G1。"},
        {"category": "コース知識", "question": "中京競馬場の特徴は？", "choices": ["平坦で小回り", "直線412mで急坂あり、左回り", "洋芝", "右回り"], "answer": 1, "explanation": "中京は直線412mで急坂あり。東京に次ぐ長い直線で差し馬が台頭しやすい。"},
        {"category": "コース知識", "question": "マイルとは何mのこと？", "choices": ["1200m", "1400m", "1600m", "1800m"], "answer": 2, "explanation": "マイル＝1600m。安田記念・マイルCSなどマイルG1は最も層が厚い距離帯。"},
        {"category": "コース知識", "question": "スプリントとは何mのこと？", "choices": ["1000〜1200m", "1400〜1600m", "1800〜2000m", "2400m以上"], "answer": 0, "explanation": "スプリント＝1000〜1200m。純粋なスピードが求められる距離帯。"},
        {"category": "コース知識", "question": "福島競馬場の特徴は？", "choices": ["直線が長い", "小回りで器用さが問われ、荒れ馬場になりやすい", "洋芝", "急坂がきつい"], "answer": 1, "explanation": "福島は小回りで器用さが重要。開催後半は馬場が荒れやすく非主流血統の穴場。"},
        {"category": "コース知識", "question": "函館競馬場が特殊な理由は？", "choices": ["日本唯一のダート専門場", "洋芝＋小回りの独特なコース", "直線が600m以上", "標高が高い"], "answer": 1, "explanation": "函館は洋芝＋小回りの独特なコース。先行力と洋芝適性の両立が求められる。"},
        {"category": "コース知識", "question": "「上がり3F」とは何のこと？", "choices": ["スタートから600mのタイム", "ゴールまで残り600mのタイム", "調教のタイム", "馬場の硬さ"], "answer": 1, "explanation": "上がり3F＝ゴールまで残り600mのタイム。末脚の切れ味を測る最重要指標。"},
        {"category": "コース知識", "question": "宝塚記念のコースは？", "choices": ["東京芝2200m", "阪神芝2200m（内回り）", "京都芝2200m", "中山芝2200m"], "answer": 1, "explanation": "宝塚記念は阪神芝2200m内回り。急坂があり先行力とスタミナが問われる。"},

        # --- 馬場状態（10問） ---
        {"category": "馬場状態", "question": "良馬場で最も有利な血統は？", "choices": ["ロベルト系", "サンデーサイレンス系", "ハービンジャー系", "シニスターミニスター系"], "answer": 1, "explanation": "良馬場ではサンデー系の瞬発力が最大限に活きる。特にディープ系が強い。"},
        {"category": "馬場状態", "question": "重馬場で激走しやすい血統は？", "choices": ["ディープ系", "ロードカナロア系", "ロベルト系・欧州ND系", "ダイワメジャー系"], "answer": 2, "explanation": "重馬場ではパワーが求められ、ロベルト系やハービンジャー等の欧州ND系が台頭。"},
        {"category": "馬場状態", "question": "クッション値とは？", "choices": ["馬の体重", "馬場の硬さ", "調教の強度", "騎手の体重"], "answer": 1, "explanation": "JRAが発表する馬場の硬さ指標。高いほど硬く、スピード型が有利になる傾向。"},
        {"category": "馬場状態", "question": "雨が降った時の予想で最も重要な視点は？", "choices": ["人気馬を信頼", "血統の馬場適性をチェック", "前走の着順だけ", "調教タイム重視"], "answer": 1, "explanation": "馬場変化で有利不利の血統が入れ替わる。「人気馬凡走→非主流激走」の多くは馬場変化が原因。"},
        {"category": "馬場状態", "question": "洋芝（札幌・函館）で有利な血統は？", "choices": ["ディープ系", "ロードカナロア系", "ハービンジャー系・欧州ND系", "ダイワメジャー系"], "answer": 2, "explanation": "洋芝は欧州型の芝で時計がかかりやすい。ハービンジャー系など欧州型が圧倒的に有利。"},
        {"category": "馬場状態", "question": "馬場状態の4段階を軽い順に並べると？", "choices": ["良→稍重→重→不良", "不良→重→稍重→良", "良→重→稍重→不良", "稍重→良→重→不良"], "answer": 0, "explanation": "良（最も軽い）→稍重→重→不良（最も重い）の順。雨が降るほど重くなる。"},
        {"category": "馬場状態", "question": "芝の重馬場とダートの重馬場の違いは？", "choices": ["どちらも時計がかかる", "芝は遅くなりダートは速くなる", "どちらも速くなる", "影響は同じ"], "answer": 1, "explanation": "芝は重馬場で時計がかかるが、ダートは砂が締まり時計が速くなる。全く逆の傾向。"},
        {"category": "馬場状態", "question": "稍重馬場で有利になりやすい血統は？", "choices": ["高速馬場専門型", "体力型のサンデー系", "スプリント専門", "ダート専門型"], "answer": 1, "explanation": "稍重はやや力がいる馬場。スピード一辺倒より体力のあるタイプが浮上しやすい。"},
        {"category": "馬場状態", "question": "ディープインパクト産駒の重馬場成績は？", "choices": ["良馬場と変わらない", "回収率が落ちる傾向がある", "重馬場の方が得意", "データがない"], "answer": 1, "explanation": "ディープ産駒は良馬場で強いが重馬場では成績が落ちる傾向。人気になりやすいので割引が必要。"},
        {"category": "馬場状態", "question": "クッション値が高い（硬い馬場）で有利な血統は？", "choices": ["パワー型・欧州系", "スピード型・サンデー系", "ダート血統", "関係ない"], "answer": 1, "explanation": "硬い馬場はスピードが活きやすい。サンデー系やロードカナロア系の瞬発力が有利。"},

        # --- EV思考（5問） ---
        {"category": "EV思考", "question": "「ディープ産駒は東京芝が得意」の予想での価値は？", "choices": ["非常に高い", "オッズに織り込み済みで美味しくない場合が多い", "穴情報", "ダートでも使える"], "answer": 1, "explanation": "有名すぎる情報はオッズに織り込み済み。大衆が知っている情報は期待値を生みにくい。"},
        {"category": "EV思考", "question": "期待値が高い馬券の条件は？", "choices": ["人気馬を買う", "大衆が見落とした条件で好走する馬を買う", "いつも同じ馬", "配当が低い馬券"], "answer": 1, "explanation": "「実力に対してオッズが高い」馬券が高EV。大衆が見落とした情報にEVが生まれる。"},
        {"category": "EV思考", "question": "回収率100%の意味は？", "choices": ["全的中", "投資額と同額が返ってきた", "必ず儲かる", "勝率100%"], "answer": 1, "explanation": "回収率100%＝プラスマイナスゼロ。100%超なら長期的にプラス収支。"},
        {"category": "EV思考", "question": "距離延長で期待値が上がりやすい血統は？", "choices": ["スプリント専門型", "スタミナ型", "2歳馬", "ダート専門型"], "answer": 1, "explanation": "スタミナ型は距離延長で上昇しやすい。逆張り条件（延長でスプリント血統好走）は高EV。"},
        {"category": "EV思考", "question": "出走数が少ないデータの扱い方は？", "choices": ["全額賭ける", "参考程度にとどめる", "無視する", "少ないほど信頼"], "answer": 1, "explanation": "出走数が少ないほど偶然の可能性が高い。30回以上を最低ライン、50回以上はより信頼できる。"},

        # --- 血統×コース（20問） ---
        {"category": "血統×コース", "question": "母父が重要視される理由は？", "choices": ["見た目に影響", "母系を通じてスタミナや気性が伝わる", "騎手が乗りやすい", "毛色に直結"], "answer": 1, "explanation": "母父は父との組み合わせで相乗効果が出ることがある。特定コースで強く影響するケースも。"},
        {"category": "血統×コース", "question": "東京芝G1で強い血統系統は？", "choices": ["ロベルト系", "サンデーサイレンス系", "シニスターミニスター系", "ハービンジャー系"], "answer": 1, "explanation": "東京の長い直線ではサンデー系の瞬発力が活きる。"},
        {"category": "血統×コース", "question": "中山芝で浮上しやすい非主流血統は？", "choices": ["ディープ系", "ロードカナロア系", "ロベルト系・ステイゴールド系", "ダイワメジャー系"], "answer": 2, "explanation": "中山は急坂×小回りでパワーと根性が必要。ロベルト系やステイゴールド系が台頭。"},
        {"category": "血統×コース", "question": "雨の日にハービンジャー母父を注目する理由は？", "choices": ["雨が嫌い", "重馬場で激走しやすい", "出走取消が多い", "晴れ専門"], "answer": 1, "explanation": "ハービンジャーは重馬場適性が非常に高く、母父としても重馬場で大きな影響力を持つ。"},
        {"category": "血統×コース", "question": "ドウデュースの父は？", "choices": ["ディープインパクト", "ハーツクライ", "ロードカナロア", "エピファネイア"], "answer": 1, "explanation": "ドウデュースは父ハーツクライ。2022年・2024年の日本ダービーを制覇。"},
        {"category": "血統×コース", "question": "イクイノックスの母父は？", "choices": ["キングカメハメハ", "キングヘイロー", "ディープインパクト", "ブラックタイド"], "answer": 1, "explanation": "イクイノックスは父キタサンブラック×母父キングヘイロー。"},
        {"category": "血統×コース", "question": "阪神外回り（桜花賞）で有利な血統は？", "choices": ["パワー型", "ディープ系・エピファネイア産駒", "ダート血統", "スプリンター"], "answer": 1, "explanation": "阪神外回りは直線473mで差しが決まりやすい。瞬発力型の血統が活きる。"},
        {"category": "血統×コース", "question": "リバティアイランドが三冠を取れた血統的理由は？", "choices": ["騎手の力", "父ドゥラメンテのパワー×母父のスタミナ", "運が良かった", "調教が良い"], "answer": 1, "explanation": "父ドゥラメンテ（MP系）のパワー×母父マンハッタンカフェ（SS系）のスタミナの万能型。"},
        {"category": "血統×コース", "question": "ブローザホーンが2024宝塚記念を勝てた要因は？", "choices": ["実績", "母父ハービンジャーの重馬場適性", "枠順", "1番人気だった"], "answer": 1, "explanation": "稍重馬場で母父ハービンジャーの重馬場適性がはまった。"},
        {"category": "血統×コース", "question": "夏の北海道で穴馬になりやすい血統は？", "choices": ["ディープ系", "ロードカナロア系", "ハービンジャー系・欧州ND系", "ダイワメジャー系"], "answer": 2, "explanation": "夏の洋芝コースでは欧州型が台頭。サンデー系が苦手な条件で穴をあける。"},
        {"category": "血統×コース", "question": "ダートの重賞で強い血統系統は？", "choices": ["サンデー系", "ノーザンダンサー系", "ミスタープロスペクター系", "ガリレオ系"], "answer": 2, "explanation": "ダートではMP系のパワーとスピードが活きる。ヘニーヒューズ・シニスターミニスターが代表格。"},
        {"category": "血統×コース", "question": "京都芝3000m（菊花賞）で重要な能力は？", "choices": ["スプリント力", "圧倒的なスタミナ", "砂かぶりへの耐性", "ゲートの速さ"], "answer": 1, "explanation": "菊花賞は3000mの長距離。折り合いとスタミナが最重要。ステイゴールド系などが適性を示す。"},
        {"category": "血統×コース", "question": "東京ダート1600m（フェブラリーS）で有利な枠は？", "choices": ["内枠", "中枠", "外枠", "枠の影響なし"], "answer": 2, "explanation": "ダートの東京1600mは外枠有利。砂を被らないため先行しやすい。"},
        {"category": "血統×コース", "question": "中山ダート1800mで強い血統は？", "choices": ["ディープ系", "シニスターミニスター・ヘニーヒューズ", "ハービンジャー系", "ダイワメジャー系"], "answer": 1, "explanation": "中山ダート1800mはパワーが求められる。ダート血統のシニスターミニスターやヘニーヒューズが好成績。"},
        {"category": "血統×コース", "question": "新潟芝1000m（直線コース）の特徴は？", "choices": ["先行有利", "コーナーがなく純粋なスピード勝負", "長距離", "差し有利"], "answer": 1, "explanation": "新潟の直線1000mはコーナーが一切ない特殊なコース。純粋なスピードだけが問われる。"},
        {"category": "血統×コース", "question": "スクリーンヒーロー産駒が得意なコースは？", "choices": ["東京芝", "中山芝", "ダート全般", "洋芝"], "answer": 1, "explanation": "スクリーンヒーローはロベルト系。中山の急坂コースでパワーを活かした好走が多い。"},
        {"category": "血統×コース", "question": "キタサンブラック産駒が2026年クラシックで注目される理由は？", "choices": ["産駒が少ないから", "直近3年で出走数急増＋勝率が高いから", "ダート専門だから", "短距離専門だから"], "answer": 1, "explanation": "キタサンブラックは2026年クラシック世代の父として大注目。芝中〜長距離で高い勝率を記録中。"},
        {"category": "血統×コース", "question": "サートゥルナーリア産駒が2026年に注目される理由は？", "choices": ["引退が近いから", "初年度産駒がデビューし早くもG1馬を輩出", "ダート専門だから", "産駒が少ないから"], "answer": 1, "explanation": "サートゥルナーリアは2025年デビューの初年度産駒からカヴァレリッツォがフューチュリティS制覇。"},
        {"category": "血統×コース", "question": "ミュージアムマイルが2025年有馬記念を勝てた血統的背景は？", "choices": ["ディープ産駒だから", "父リオンディーズ（MP系）のパワーが中山の急坂で活きた", "洋芝適性", "スプリント力"], "answer": 1, "explanation": "リオンディーズはキングカメハメハの孫世代。MP系のパワーが中山2500mの急坂で活きた。"},
        {"category": "血統×コース", "question": "コスタノヴァが2026年フェブラリーSを勝てた血統的背景は？", "choices": ["ハービンジャー産駒だから", "ゴールドシップ産駒だから", "父ロードカナロアのスピードがダートでも活きた", "ステイゴールド産駒だから"], "answer": 2, "explanation": "コスタノヴァは父ロードカナロア。スプリント王のスピードが東京ダート1600mでも活きた。"},
    ]
    for mq in manual_questions:
        mq["source"] = "manual"
        mq["id"] = qid
        questions.append(mq)
        qid += 1

    # ジャンルタグ付与
    blood_cats = {"血統基礎", "血統×距離", "脚質"}
    course_cats = {"コース知識", "コースバイアス"}
    # 残り（血統×コース, 期待値, 距離変更, 馬場状態, EV思考）は複合
    for q in questions:
        if q["category"] in blood_cats:
            q["genre"] = "血統"
        elif q["category"] in course_cats:
            q["genre"] = "コース"
        else:
            q["genre"] = "総合"

    out = {"generated_at": now_str, "questions": questions}
    path = os.path.join(OUTPUT_DIR, "quiz.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[OK] quiz.json 生成完了：{len(questions)}件")


# ============================================================
# メイン
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="keiba.db → 学習サイト用JSON生成")
    parser.add_argument("--db", required=True, help="keiba.db のパス")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"エラー: DBファイルが見つかりません: {args.db}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for name, fn in [
        ("pedigree", export_pedigree),
        ("course", export_course),
        ("affinity", export_affinity),
        ("quiz", export_quiz),
    ]:
        try:
            fn(cur, now_str)
        except Exception as e:
            print(f"[NG] {name}.json 生成エラー: {e}")

    conn.close()
    print("\nれいな：全JSON生成完了。data/ フォルダを確認してください。")


if __name__ == "__main__":
    main()
