"""文旅政策文本分析看板。运行： streamlit run app.py"""
import re
import sqlite3
from collections import Counter
from pathlib import Path

import jieba
import pandas as pd
import plotly.express as px
import streamlit as st

from analyze import TOPICS

_data = Path(__file__).parent / "data"
DB_PATH = _data / "dashboard.db" if (_data / "dashboard.db").exists() else _data / "policy.db"
st.set_page_config(page_title="文旅政策文本分析看板", page_icon="📊", layout="wide")

STOP = set(
    "的 和 与 及 或 等 在 对 为 将 把 是 有 以 其 并 要 应 由 于 中 上 下 各 个 年 月 日 号 条 款 项 第 一 二 三 四 五 "
    "进行 开展 加强 工作 相关 有关 通知 意见 办法 规定 文化 旅游 文化和旅游 部门 单位 机构 企业 要求 做好 按照 根据 "
    "以及 通过 实施 管理 服务 发展 推进 建设 全国 各地 本 该 不 可 应当 如 我 国家 省 市 县 区 自治区 直辖市 厅 局 "
    "办公厅 印发 现 附件 此 请 严格 切实 有效 持续 进一步 积极 提高 提升 完善 落实 组织 做 使 从 向 到 对于 关于".split()
)


@st.cache_data
def load(db_mtime):  # 数据库文件一变，db_mtime 就变，缓存自动失效
    if not DB_PATH.exists():
        return None
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT p.id,p.url,p.title,p.doc_no,p.pub_date,p.year,p.category,p.keywords_raw,p.body,p.body_len,p.short_body,"
        "a.issuer_norm,a.primary_topic,a.topics,a.strength,a.binding_n,a.encourage_n,a.is_policy "
        "FROM policies p JOIN analysis a ON a.id=p.id",
        con,
    )
    return df


df = load(DB_PATH.stat().st_mtime if DB_PATH.exists() else 0)
st.title("📊 文旅政策文本分析看板")
if df is None or df.empty:
    st.warning("还没有数据。请先依次运行：python crawler.py → python clean.py → python analyze.py")
    st.stop()

# ---------- 侧边栏筛选 ----------
st.sidebar.header("筛选条件")
y0, y1 = int(df.year.min()), int(df.year.max())
years = st.sidebar.slider("发布年份", y0, y1, (y0, y1))
topics_all = sorted(df.primary_topic.unique())
topics_sel = st.sidebar.multiselect("主题", topics_all, default=topics_all)
issuers_all = df.issuer_norm.value_counts().index.tolist()
issuers_sel = st.sidebar.multiselect("发文机关（默认全部）", issuers_all)
kw = st.sidebar.text_input("标题/正文关键词搜索", "")
drop_short = st.sidebar.checkbox("剔除正文过短（<50字）的文件", value=True)
only_policy = st.sidebar.checkbox("仅政策性文件（排除名单/评选/会议等事务性通知）", value=True)

f = df[(df.year.between(*years)) & (df.primary_topic.isin(topics_sel))]
if issuers_sel:
    f = f[f.issuer_norm.isin(issuers_sel)]
if kw.strip():
    f = f[f.title.str.contains(kw.strip(), regex=False) | f.body.str.contains(kw.strip(), regex=False)]
if drop_short:
    f = f[f.short_body == 0]
if only_policy:
    f = f[f.is_policy == 1]

c1, c2, c3, c4 = st.columns(4)
c1.metric("符合条件的文件数", len(f))
c2.metric("覆盖年份", f"{f.year.min()}–{f.year.max()}" if len(f) else "-")
c3.metric("平均力度分", f"{f.strength.mean():.1f}" if len(f) else "-")
c4.metric("发文机关数", f.issuer_norm.nunique() if len(f) else 0)
if f.empty:
    st.info("当前筛选下没有文件，请放宽条件。")
    st.stop()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 趋势", "🔑 关键词", "🧭 覆盖空白", "🏛 部门对比", "📄 原文列表"])

# ---------- 趋势 ----------
with tab1:
    cnt = f.groupby(["year", "primary_topic"]).size().reset_index(name="数量")
    st.subheader("各年份发文量（按主题堆叠）")
    st.plotly_chart(px.bar(cnt, x="year", y="数量", color="primary_topic", labels={"year": "年份", "primary_topic": "主题"}), width='stretch')
    a, b = st.columns(2)
    with a:
        st.subheader("主题占比")
        st.plotly_chart(px.pie(f.primary_topic.value_counts().reset_index(), names="primary_topic", values="count"), width='stretch')
    with b:
        st.subheader("政策力度年度均值")
        s = f.groupby("year").strength.mean().reset_index()
        st.plotly_chart(px.line(s, x="year", y="strength", markers=True, labels={"strength": "力度分(0-100)", "year": "年份"}), width='stretch')
    st.caption("力度分：文种强度 40% + 约束词占比 60%，规则见「方法说明」。分数越高，文件越偏强制性要求；越低越偏倡导鼓励。")

# ---------- 关键词 ----------
with tab2:
    @st.cache_data
    def top_words(texts_key, texts):
        c = Counter()
        for t in texts:
            for w in jieba.cut(t):
                w = w.strip()
                if len(w) >= 2 and w not in STOP and re.match(r"^[一-龥A-Za-z]+$", w):
                    c[w] += 1
        return c

    key = (tuple(f.id.tolist()))
    c = top_words(hash(key), f.title.str.cat(sep="。").split("。") + f.body.str[:3000].tolist())
    top = pd.DataFrame(c.most_common(40), columns=["关键词", "出现次数"])
    a, b = st.columns([1, 1])
    with a:
        st.subheader("高频关键词 Top 40")
        st.plotly_chart(px.bar(top.iloc[::-1], x="出现次数", y="关键词", orientation="h", height=800), width='stretch')
    with b:
        st.subheader("单个关键词的年度热度")
        word = st.text_input("输入关键词（如：数字化、非遗、研学、夜间）", "数字化")
        if word:
            g = f.assign(命中=f.body.str.contains(word, regex=False) | f.title.str.contains(word, regex=False))
            g = g.groupby("year").agg(提及文件数=("命中", "sum"), 文件总数=("命中", "size")).reset_index()
            g["提及占比%"] = (100 * g["提及文件数"] / g["文件总数"]).round(1)
            st.plotly_chart(px.line(g, x="year", y="提及占比%", markers=True, hover_data=["提及文件数", "文件总数"]), width='stretch')
            st.dataframe(g, hide_index=True, width='stretch')

# ---------- 覆盖空白 ----------
with tab3:
    st.subheader("哪些方面的政策供给偏少？（主题 × 年份文件数）")
    st.caption("颜色越浅/数字越小，说明该主题在该年份的文件越少，可能是政策空白或研究机会。注意：样本只来自文旅部官网公开栏目（规范性文件、意见、规划计划、通知），不代表全部政策。")
    heat = f.pivot_table(index="primary_topic", columns="year", values="id", aggfunc="count", fill_value=0)
    st.plotly_chart(px.imshow(heat, text_auto=True, aspect="auto", color_continuous_scale="Blues", labels={"x": "年份", "y": "主题", "color": "文件数"}), width='stretch')
    # 关键词词典覆盖度：词典里哪些主题的文件总数最少
    tot = f.primary_topic.value_counts().reindex(list(TOPICS) + ["其他"], fill_value=0).reset_index()
    tot.columns = ["主题", "文件数"]
    st.subheader("主题文件总量排名（越靠后越欠缺）")
    st.dataframe(tot.sort_values("文件数"), hide_index=True, width='stretch')

# ---------- 部门对比 ----------
with tab4:
    st.subheader("发文机关对比")
    top_iss = f.issuer_norm.value_counts().head(10).index
    g = f[f.issuer_norm.isin(top_iss)].groupby(["issuer_norm", "primary_topic"]).size().reset_index(name="数量")
    st.plotly_chart(px.bar(g, x="数量", y="issuer_norm", color="primary_topic", orientation="h", labels={"issuer_norm": "发文机关", "primary_topic": "主题"}), width='stretch')
    st.caption("本版数据来源为文旅部，因此对比单位是「发文机关/司局」。地区对比需要接入各省文旅厅数据，见方法说明中的后续计划。")

# ---------- 原文列表 ----------
with tab5:
    show = f.sort_values("pub_date", ascending=False)[["pub_date", "title", "issuer_norm", "primary_topic", "strength", "doc_no", "url"]]
    show.columns = ["发布日期", "标题", "发文机关", "主主题", "力度分", "文号", "原文链接"]
    st.dataframe(show, hide_index=True, width='stretch', column_config={"原文链接": st.column_config.LinkColumn("原文链接", display_text="打开")})
    st.download_button("下载当前筛选结果 (CSV)", show.to_csv(index=False).encode("utf-8-sig"), "policies_filtered.csv", "text/csv")
