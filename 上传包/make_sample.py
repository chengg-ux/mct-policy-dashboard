"""随机抽 50 份政策性文件，生成人工核对表 sample_check.md（固定随机种子，可复现）。"""
import random
import sqlite3
from pathlib import Path

root = Path(__file__).parent
con = sqlite3.connect(root / "data" / "policy.db")
rows = con.execute(
    "SELECT p.id,p.title,p.pub_date,a.primary_topic FROM policies p JOIN analysis a ON a.id=p.id "
    "WHERE a.is_policy=1 ORDER BY p.id"
).fetchall()
random.seed(2026)
pick = sorted(random.sample(rows, 50), key=lambda r: r[0])
lines = ["| 序号 | 日期 | 标题 | 程序判定的主题 | 你的判断（对/错，错的写应属主题） |", "|---|---|---|---|---|"]
for i, (pid, title, date, topic) in enumerate(pick, 1):
    lines.append(f"| {i} | {date} | {title} | {topic} | |")
(root / "sample_check.md").write_text("\n".join(lines), encoding="utf-8")
(root / "data" / "sample_ids.txt").write_text(",".join(str(r[0]) for r in pick))
print("\n".join(lines))
