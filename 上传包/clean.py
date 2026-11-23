"""清洗：从 raw_pages 的原始网页中提取标题/文号/发文机关/日期/分类/正文，去重后写入 policies 表。

用法： python clean.py
规则：
  1. 只保留发布日期在 2020-01-01 之后的文件；
  2. 标题规范化后（去空白和标点）重复的只留最早抓到的一条；文号相同的也视为重复；
  3. 正文少于 50 字的（多为只有附件的页面）仍保留，但标记 short_body=1，分析时可剔除。
"""
import re
import sqlite3
from pathlib import Path

from bs4 import BeautifulSoup

DB_PATH = Path(__file__).parent / "data" / "policy.db"
START_DATE = "2020-01-01"


def squash(s):
    return re.sub(r"\s+", "", s or "")


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    meta = {}
    for dl in soup.select(".content_head dl"):
        dt, dd = dl.find("dt"), dl.find("dd")
        if dt and dd:
            key = squash(dt.get_text()).rstrip("：:")
            meta[key] = re.sub(r"\s+", " ", dd.get_text(" ", strip=True))
    h2 = soup.select_one("h2.xxgk_title")
    title = squash(h2.get_text()) if h2 else squash(meta.get("标题", ""))
    body_node = soup.select_one(".gsj_htmlcon_bot")
    if body_node:
        for t in body_node.find_all(["style", "script"]):
            t.decompose()
        body = body_node.get_text("\n", strip=True)
        body = body.replace("\xa0", " ")
        # 去掉部分页面正文开头混入的「发布时间…字体：[大中小]打印」页眉
        body = re.sub(r"^.{0,300}?字体：\s*\[大中小\]\s*打印\s*", "", body, flags=re.S)
    else:
        body = ""
    return {
        "title": title,
        "doc_no": meta.get("文号", "") or (soup.select_one("p.fileNum").get_text(strip=True) if soup.select_one("p.fileNum") else ""),
        "issuer": meta.get("发文机关", ""),
        "pub_date": meta.get("发布日期", ""),
        "category": meta.get("分类", "").replace(";", "/"),
        "keywords_raw": meta.get("主题词", ""),
        "body": body,
    }


def main():
    con = sqlite3.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS policies")
    con.execute(
        """CREATE TABLE policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, title TEXT, doc_no TEXT,
            issuer TEXT, pub_date TEXT, year INTEGER, category TEXT, keywords_raw TEXT,
            body TEXT, body_len INTEGER, short_body INTEGER)"""
    )
    rows = con.execute("SELECT url, list_title, list_date, html FROM raw_pages ORDER BY fetched_at").fetchall()
    seen_title, seen_no = set(), set()
    stats = dict(total=len(rows), old=0, dup=0, kept=0)
    for url, ltitle, ldate, html in rows:
        p = parse(html)
        # 列表页的标题最干净；个别正文页 HTML 不规范，页内标题会混入正文，所以优先用列表页标题
        title = squash(ltitle) or p["title"]
        date = p["pub_date"] or ldate
        if date < START_DATE:
            stats["old"] += 1
            continue
        key = re.sub(r"[^\w]", "", title)
        no = squash(p["doc_no"])
        if key in seen_title or (no and no in seen_no):
            stats["dup"] += 1
            continue
        seen_title.add(key)
        if no:
            seen_no.add(no)
        body = p["body"]
        con.execute(
            "INSERT INTO policies (url,title,doc_no,issuer,pub_date,year,category,keywords_raw,body,body_len,short_body)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (url, title, p["doc_no"], p["issuer"], date, int(date[:4]), p["category"],
             p["keywords_raw"], body, len(body), int(len(body) < 50)),
        )
        stats["kept"] += 1
    con.commit()
    print("清洗结果：", stats)


if __name__ == "__main__":
    main()
