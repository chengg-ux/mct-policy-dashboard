"""抽检核对小工具：一条条查看 50 份抽样文件，判断程序分类对不对。
运行： python -m streamlit run review_app.py --server.port 8502
结果自动保存到 data/review_labels.csv（关掉再开会接着上次的进度）。
"""
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from analyze import TOPICS

ROOT = Path(__file__).parent
DB = ROOT / "data" / "policy.db"
IDS = ROOT / "data" / "sample_ids.txt"
OUT = ROOT / "data" / "review_labels.csv"
TOPIC_LIST = list(TOPICS) + ["其他"]
st.set_page_config(page_title="抽检核对", page_icon="✅", layout="wide")

if not IDS.exists():
    st.error("没有找到抽样名单，请先运行：python make_sample.py")
    st.stop()


@st.cache_data
def load_sample():
    ids = [int(x) for x in IDS.read_text().split(",")]
    con = sqlite3.connect(DB)
    q = ",".join("?" * len(ids))
    df = pd.read_sql(
        f"SELECT p.id,p.title,p.pub_date,p.url,p.body,a.primary_topic,a.topics,a.strength "
        f"FROM policies p JOIN analysis a ON a.id=p.id WHERE p.id IN ({q})", con, params=ids)
    return df.set_index("id").loc[ids].reset_index()


def load_labels():
    if OUT.exists():
        return pd.read_csv(OUT).set_index("id").to_dict("index")
    return {}


def save_label(pid, verdict, correct_topic, note):
    labels = load_labels()
    labels[pid] = {"verdict": verdict, "correct_topic": correct_topic, "note": note}
    pd.DataFrame.from_dict(labels, orient="index").rename_axis("id").reset_index().to_csv(OUT, index=False, encoding="utf-8-sig")


df = load_sample()
labels = load_labels()
n = len(df)
if "i" not in st.session_state:
    # 从第一条还没判断的开始
    todo = [k for k, pid in enumerate(df.id) if pid not in labels]
    st.session_state.i = todo[0] if todo else 0
i = st.session_state.i
row = df.iloc[i]
done = sum(pid in labels for pid in df.id)

# ---------- 侧边栏：进度与准确率 ----------
st.sidebar.header("进度")
st.sidebar.progress(done / n, text=f"已核对 {done} / {n}")
judged = [labels[p] for p in df.id if p in labels and labels[p]["verdict"] in ("正确", "错误")]
if judged:
    ok = sum(1 for j in judged if j["verdict"] == "正确")
    st.sidebar.metric("当前准确率（不含“不确定”）", f"{ok / len(judged):.0%}", f"{ok}/{len(judged)} 条正确")
unsure = sum(1 for p in df.id if p in labels and labels[p]["verdict"] == "不确定")
if unsure:
    st.sidebar.caption(f"另有 {unsure} 条标为不确定")
jump = st.sidebar.number_input("跳到第几条", 1, n, i + 1)
if st.sidebar.button("跳转"):
    st.session_state.i = int(jump) - 1
    st.rerun()
if OUT.exists():
    st.sidebar.download_button("下载核对结果 CSV", OUT.read_bytes(), "review_labels.csv", "text/csv")

# ---------- 主区域：当前这条 ----------
st.title("✅ 分类抽检核对")
st.caption(f"第 {i + 1} / {n} 条　·　{row.pub_date}")
st.subheader(row.title)
c1, c2, c3 = st.columns(3)
c1.metric("程序判定的主题", row.primary_topic)
c2.metric("次要主题", row.topics.replace("|", "、").replace(row.primary_topic + "、", "").replace(row.primary_topic, "") or "无")
c3.metric("力度分", row.strength)
st.link_button("🔗 打开原文", row.url)
with st.expander("正文开头（前 500 字）", expanded=True):
    st.write(row.body[:500] + ("……" if len(row.body) > 500 else ""))

prev = labels.get(row.id, {})
verdict = st.radio("你的判断", ["正确", "错误", "不确定"], horizontal=True,
                   index=["正确", "错误", "不确定"].index(prev["verdict"]) if prev else None, key=f"v{i}")
correct, note = "", ""
if verdict == "错误":
    default = TOPIC_LIST.index(prev["correct_topic"]) if prev and prev.get("correct_topic") in TOPIC_LIST else 0
    correct = st.selectbox("应该属于哪个主题？", TOPIC_LIST, index=default, key=f"t{i}")
note = st.text_input("备注（可选）", value=(prev.get("note") if prev and isinstance(prev.get("note"), str) else ""), key=f"n{i}")

b1, b2, b3 = st.columns([1, 1, 4])
if b1.button("⬅ 上一条", disabled=i == 0):
    st.session_state.i = i - 1
    st.rerun()
if b2.button("保存并下一条 ➡", type="primary", disabled=verdict is None):
    save_label(int(row.id), verdict, correct, note)
    st.session_state.i = min(i + 1, n - 1)
    st.rerun()
if done == n:
    st.success("全部核对完成！把准确率和错判的序号告诉我，我来调整词典。")
