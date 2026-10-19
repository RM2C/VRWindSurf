#!/usr/bin/env python3
"""試行毎アンケートの回答を Log/Cube の試行ログに静的に結びつける。

対応付けルール:
  1. 回答者の氏名を参加者ID（ログフォルダ名の先頭）に変換する（NAME_TO_PARTICIPANT）。
  2. 練習試行（Wave-Half_Act-66）は対象外とする。
  3. 各回答について、同じ参加者の「直前の回答以降に開始し、かつ今回の回答時刻までに終了した」
     ログを候補とし、その中で最も遅く開始したものを採用する。
     （途中で中断してやり直した試行は、やり直し後のログが選ばれる）
  ログの終了時刻 = フォルダ名の開始時刻 + cube_position.csv の最終 time_sec。

使い方:
  python3 link_survey_to_logs.py            # 結果CSVを出力し、検証結果を表示
"""

import csv
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SURVEY_CSV = HERE / "[VRWS]試行毎のアンケート（回答） - フォームの回答 1.csv"
LOG_DIR = HERE / "Log" / "Cube"
OUTPUT_CSV = HERE / "[VRWS]試行毎のアンケート（回答） - 条件付き.csv"

PRACTICE_CONDITION = ("Half", "66")

# アンケートの氏名 -> ログの参加者ID
NAME_TO_PARTICIPANT = {
    "しちじょ": "nanajo",
    "近藤　孝宣": "kondo",
    "小島": "kojima",
    "熊澤": "kumazawa",
    "原和希": "hara",
    "太田怜志": "ota",
    "杉江鎌": "sugie",
    "manji": "tanahashi",
    "秋葉直人": "Akiba",
    "西井大樹": "Nishii",
    "中野剛": "Nakano",
    "加藤蒼惟": "Kato",
    "米澤正真": "Yonezawa",
    "服部圭吾": "Hattori",
    "新美　秀人": "Nimi",
    "偉大なる黒瀬御大": "Kurose",
    "齊藤": "Saito",
    "板垣良摩": "Itagaki",
    "小西真結": "Konishi",
    "久保田翔帆": "Kubota",
}

LOG_NAME_RE = re.compile(r"^(?P<pid>.+)_Wave-(?P<wave>[^_]+)_Act-(?P<act>\d+)_(?P<ts>\d{8}_\d{6})$")


def load_logs():
    logs = []
    for d in sorted(LOG_DIR.iterdir()):
        m = LOG_NAME_RE.match(d.name)
        if not d.is_dir() or not m:
            continue
        start = datetime.strptime(m["ts"], "%Y%m%d_%H%M%S")
        with open(d / "cube_position.csv", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        duration = float(rows[-1][0]) if len(rows) > 1 else 0.0
        logs.append({
            "name": d.name,
            "pid": m["pid"],
            "wave": m["wave"],
            "act": m["act"],
            "start": start,
            "end": start + timedelta(seconds=duration),
            "duration": duration,
        })
    return logs


def main():
    logs = load_logs()
    with open(SURVEY_CSV, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header, answers = rows[0], rows[1:]

    prev_answer_time = {}
    out_rows = []
    problems = []
    for row in answers:
        answered = datetime.strptime(row[0], "%Y/%m/%d %H:%M:%S")
        pid = NAME_TO_PARTICIPANT.get(row[1])
        if pid is None:
            problems.append(f"氏名が未登録: {row[1]}")
            out_rows.append(row + ["", "", ""])
            continue
        since = prev_answer_time.get(pid, datetime.min)
        candidates = [
            l for l in logs
            if l["pid"] == pid
            and (l["wave"], l["act"]) != PRACTICE_CONDITION
            and since <= l["start"] and l["end"] <= answered
        ]
        prev_answer_time[pid] = answered
        if not candidates:
            problems.append(f"対応ログなし: {row[0]} {row[1]} {row[2]}")
            out_rows.append(row + ["", "", ""])
            continue
        chosen = max(candidates, key=lambda l: l["start"])
        chosen["matched"] = True
        if len(candidates) > 1:
            skipped = ", ".join(f'{l["name"]}({l["duration"]:.0f}s)' for l in candidates if l is not chosen)
            print(f"[info] {row[0]} {row[1]}: 複数候補 → {chosen['name']} を採用（除外: {skipped}）")
        out_rows.append(row + [chosen["name"], chosen["wave"], chosen["act"]])

    # 検証: 参加者ごとに6条件が重複なく揃っているか
    by_pid = {}
    for row in out_rows:
        if row[-3]:
            by_pid.setdefault(NAME_TO_PARTICIPANT[row[1]], []).append((row[-2], row[-1]))
    for pid, conds in by_pid.items():
        if len(conds) != 6 or len(set(conds)) != 6:
            problems.append(f"条件の重複/欠落: {pid} {conds}")

    # 回答に結びつかなかった本試行ログ（参考表示）
    participants = set(NAME_TO_PARTICIPANT.values())
    for l in logs:
        if l["pid"] in participants and (l["wave"], l["act"]) != PRACTICE_CONDITION and not l.get("matched"):
            print(f"[info] 回答と結びつかないログ: {l['name']}（{l['duration']:.0f}s）")

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header + ["LogFile", "Wave", "Act"])
        w.writerows(out_rows)

    print(f"出力: {OUTPUT_CSV}（{len(out_rows)} 行）")
    if problems:
        print("\n".join(f"[warn] {p}" for p in problems))
        sys.exit(1)
    print("検証OK: 全回答がログに対応し、各参加者で6条件が重複なく揃っています")


if __name__ == "__main__":
    main()
