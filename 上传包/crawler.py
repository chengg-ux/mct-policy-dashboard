"""抓取文旅部「政策法规」栏目的公开文件，原始网页存入 SQLite（data/policy.db）。

用法：  python crawler.py            # 抓全部栏目
        python crawler.py --limit 5  # 每个栏目只抓前 5 条，用来试跑

礼貌抓取：每次请求间隔 DELAY 秒；已抓过的网址不会重复抓；遇到错误只跳过不硬闯。
"""
import argparse
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://zwgk.mct.gov.cn/zfxxgkml/zcfg/"
# 栏目名 -> (栏目路径, 列表页文件名前缀)。列表按日期倒序，翻到 2020 年以前就停止翻页。
# 批复、公告等个案性文件不算政策文本，未纳入；行政法规/法律栏目条目极少且多为全国人大/国务院制定，也未纳入。
ZW = "https://zwgk.mct.gov.cn/zfxxgkml/"
SECTIONS = {
    "规范性文件": (ZW + "zcfg/gfxwj/", "index"),
    "意见": (ZW + "503/509/", "index_3081"),
    "规划计划": (ZW + "447/464/", "index_3081"),
    "通知": (ZW + "503/510/", "index_3081"),
}
STOP_BEFORE = "2020-01-01"
DELAY = 2.5
HEADERS = {"User-Agent": "Mozilla/5.0 (academic research project; polite crawler; contact: student)"}
DB_PATH = Path(__file__).parent / "data" / "policy.db"

session = requests.Session()
session.headers.update(HEADERS)


def get(url):
    time.sleep(DELAY)
    r = session.get(url, timeout=30)
    r.encoding = "utf-8"
    r.raise_for_status()
    return r.text


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS raw_pages (
            url TEXT PRIMARY KEY, section TEXT, list_title TEXT, list_date TEXT,
            html TEXT, fetched_at TEXT)"""
    )
    return con


def list_pages(base, stem):
    """逐页返回 (网址, 标题, 日期)。页数从列表页里的 countPage 读取；整页都早于 2020 年则停止。"""
    first = f"{base}{stem}.html"
    html = get(first)
    m = re.search(r"countPage\s*=\s*(\d+)", html)
    total = int(m.group(1)) if m else 1
    for i in range(total):
        url = first if i == 0 else f"{base}{stem}_{i}.html"
        if i > 0:
            try:
                html = get(url)
            except requests.RequestException as e:
                print("列表页失败，跳过：", url, e)
                continue
        items = re.findall(
            r'<a href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>\s*<span class="date">([\d-]+)</span>', html
        )
        for href, title, date in items:
            if date >= STOP_BEFORE:
                yield urljoin(url, href), title.strip(), date
        if items and max(d for _, _, d in items) < STOP_BEFORE:
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="每个栏目最多抓几条（0=不限）")
    args = ap.parse_args()
    con = init_db()
    for name, (base, stem) in SECTIONS.items():
        print(f"== 栏目：{name}", flush=True)
        n = 0
        for url, title, date in list_pages(base, stem):
            if args.limit and n >= args.limit:
                break
            n += 1
            if con.execute("SELECT 1 FROM raw_pages WHERE url=?", (url,)).fetchone():
                continue
            try:
                html = get(url)
            except requests.RequestException as e:
                print("  失败，跳过：", url, e)
                continue
            con.execute(
                "INSERT OR REPLACE INTO raw_pages VALUES (?,?,?,?,?,datetime('now'))",
                (url, name, title, date, html),
            )
            con.commit()
            print(f"  [{n}] {date} {title[:30]}", flush=True)
    total = con.execute("SELECT COUNT(*) FROM raw_pages").fetchone()[0]
    print("完成，库中原始网页共", total, "份")


if __name__ == "__main__":
    main()
