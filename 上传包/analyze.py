"""主题分类 + 政策力度打分（纯规则，可复现，不需要任何 API）。

用法： python analyze.py     # 读取 policies 表，写入 analysis 表

方法（详见 METHODOLOGY.md）：
 1. 主题：每个主题有一组关键词。得分 = 标题命中次数 × 3 + 正文命中次数（每个词正文最多计 5 次，避免长文堆词）。
    得分最高且 ≥ 3 的为主主题；得分 ≥ 3 且不低于最高分 50% 的作为次要主题；都没有则归「其他」。
 2. 力度：0-100 分。= 100 × (0.4 × 文种强度 + 0.6 × 约束占比)
      文种强度：标题含 办法/规定/细则/规则/条例/标准 → 1.0；含 意见/方案/规划/行动计划/指南 → 0.6；其余（通知/函/公告）→ 0.3
      约束占比：约束词数 /（约束词数 + 鼓励词数），都为 0 时取 0.3
    约束词：应当、必须、不得、禁止、严禁、责令、处罚、罚款；鼓励词：鼓励、支持、推动、引导、探索、倡导、促进、培育
"""
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "policy.db"

TOPICS = {
    "乡村旅游与乡村振兴": ["乡村旅游", "乡村振兴", "美丽乡村", "农家乐", "民宿", "休闲农业", "乡村"],
    "文化遗产与非遗保护": ["非物质文化遗产", "非遗", "文物", "文化遗产", "传承人", "考古", "保护利用", "历史文化名城"],
    "红色旅游与革命文化": ["红色旅游", "革命文物", "红色", "革命老区", "长征"],
    "数字文旅与科技创新": ["数字化", "智慧旅游", "智慧", "数字文化", "云", "大数据", "人工智能", "技术创新", "科技创新", "互联网"],
    "演出与文艺市场": ["演出", "营业性演出", "剧本娱乐", "娱乐场所", "演艺", "艺术品", "网络表演", "经纪", "艺术"],
    "旅游市场监管与服务质量": ["旅行社", "导游", "不合理低价", "投诉", "服务质量", "市场秩序", "在线旅游", "监管", "旅游合同"],
    "公共文化服务与场馆": ["公共文化", "图书馆", "博物馆", "文化馆", "美术馆", "基层文化", "文化惠民", "公共服务"],
    "入境旅游与国际交流": ["入境", "出境", "国际旅游", "对外文化", "海外", "港澳台", "国际交流", "外国"],
    "文旅消费与夜间经济": ["消费", "夜间", "夜经济", "文化和旅游消费", "假日", "研学", "旅游演艺", "度假"],
    "景区管理与安全应急": ["景区", "A级", "安全", "应急", "疫情", "防控", "风险", "突发事件", "安全生产"],
    "人才培养与行业标准": ["人才", "资格", "培训", "标准化", "标准", "职业", "评定", "认定", "等级"],
    "综合规划与高质量发展": ["规划", "十四五", "十五五", "高质量发展", "纲要", "发展战略", "总体方案", "旅游强国", "文化强国"],
    "文化产业与融合发展": ["文化产业", "融合发展", "文化和旅游融合", "产业园区", "产业发展", "示范区", "创意", "动漫", "游戏"],
}
TOPIC_MIN = 3
BINDING = ["应当", "必须", "不得", "禁止", "严禁", "责令", "处罚", "罚款"]
ENCOURAGE = ["鼓励", "支持", "推动", "引导", "探索", "倡导", "促进", "培育"]
STRONG_TYPE = ["办法", "规定", "细则", "规则", "条例", "标准"]
MID_TYPE = ["意见", "方案", "规划", "行动计划", "指南", "纲要"]


def classify(title, body):
    scores = {}
    for topic, kws in TOPICS.items():
        s = 0
        for kw in kws:
            s += title.count(kw) * 3 + min(body.count(kw), 5)
        scores[topic] = s
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top, top_s = ranked[0]
    if top_s < TOPIC_MIN:
        return "其他", [], scores
    others = [t for t, s in ranked[1:] if s >= TOPIC_MIN and s >= 0.5 * top_s]
    return top, [top] + others, scores


def strength(title, body):
    b = sum(body.count(w) for w in BINDING)
    e = sum(body.count(w) for w in ENCOURAGE)
    if any(k in title for k in STRONG_TYPE):
        type_s = 1.0
    elif any(k in title for k in MID_TYPE):
        type_s = 0.6
    else:
        type_s = 0.3
    ratio = b / (b + e) if (b + e) else 0.3
    return round(100 * (0.4 * type_s + 0.6 * ratio), 1), b, e


# 事务性通知：名单、评选、会议、培训等，本身不含政策主张。标题命中任一词即标记 is_policy=0。
AFFAIR = ["名单", "公示", "遴选", "评选", "展演", "征集", "申报", "培训班", "会议", "召开", "举办", "开幕", "报名",
          "招聘", "招录", "录用", "拟任", "拟聘", "认定结果", "公布第", "命名", "表彰", "获奖", "入选", "推荐结果"]


def is_policy(title):
    return 0 if any(w in title for w in AFFAIR) else 1


def issuer_norm(issuer, title):
    """归并发文机关：文化和旅游部 / 部办公厅 / 部内各司局 / 联合发文（两个及以上单位）。"""
    name = re.sub(r"\s+", "", issuer or "")
    if not name:
        m = re.match(r"^(.*?)(关于|印发|公布|转发)", title)
        name = m.group(1) if m else ""
    if name in ("", "文化和旅游部"):
        return "文化和旅游部"
    if name == "文化和旅游部办公厅":
        return "文化和旅游部办公厅"
    m = re.match(r"^文化和旅游部([一-龥]{1,10}?(司|中心|办公室|局))$", name)
    if m and "部" not in m.group(1) and "委" not in m.group(1):
        return name
    return "联合发文"


def export_slim(con):
    """导出只含 policies + analysis 的精简库 data/dashboard.db（不含原始网页），供看板和线上部署使用。"""
    slim = DB_PATH.parent / "dashboard.db"
    if slim.exists():
        slim.unlink()
    con.execute(f"ATTACH DATABASE '{slim.as_posix()}' AS slim")
    con.execute("CREATE TABLE slim.policies AS SELECT * FROM main.policies")
    con.execute("CREATE TABLE slim.analysis AS SELECT * FROM main.analysis")
    con.commit()
    con.execute("DETACH DATABASE slim")


def main():
    con = sqlite3.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS analysis")
    con.execute(
        """CREATE TABLE analysis (
            id INTEGER PRIMARY KEY, issuer_norm TEXT, primary_topic TEXT, topics TEXT,
            strength REAL, binding_n INTEGER, encourage_n INTEGER, is_policy INTEGER)"""
    )
    for pid, title, body, issuer in con.execute("SELECT id,title,body,issuer FROM policies").fetchall():
        top, topics, _ = classify(title, body)
        s, b, e = strength(title, body)
        con.execute(
            "INSERT INTO analysis VALUES (?,?,?,?,?,?,?,?)",
            (pid, issuer_norm(issuer, title), top, "|".join(topics), s, b, e, is_policy(title)),
        )
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM analysis").fetchone()[0]
    other = con.execute("SELECT COUNT(*) FROM analysis WHERE primary_topic='其他'").fetchone()[0]
    export_slim(con)
    pol = con.execute("SELECT COUNT(*) FROM analysis WHERE is_policy=1").fetchone()[0]
    print(f"分析完成：{n} 份（政策性文件 {pol} 份，事务性通知 {n - pol} 份），其中归为「其他」{other} 份")


if __name__ == "__main__":
    main()
