# 文旅政策文本分析看板

对文化和旅游部官网公开发布的政策文件（2020–2026）做抓取、清洗、主题分类、力度打分，并用 Streamlit 做成可交互网页：按年份、发文机关、主题筛选，看趋势、关键词、**政策覆盖空白**，并能一键跳回原文。

- 数据：文旅部官网「政务公开 → 政府信息公开目录」下的规范性文件、意见、规划计划、通知四个栏目
- 规模：抓取 1,121 个页面 → 清洗去重后 890 份（2020–2026）→ 其中政策性文件 474 份
- 方法：纯关键词规则，不依赖大模型 API，结果可完全复现。详见 [METHODOLOGY.md](METHODOLOGY.md)

## 一、安装（只需做一次）

需要 Python 3.10 及以上。在项目文件夹里打开终端，运行：

```bash
python -m pip install -r requirements.txt
```

## 二、运行看板（一条命令）

仓库里已经带了处理好的数据（`data/dashboard.db`，约 4.5 MB，只含清洗和分析结果），所以直接运行：

```bash
python -m streamlit run app.py
```

浏览器会自动打开 http://localhost:8501 。

> 第一次运行 Streamlit 会提示 `Email:`，**直接按回车**跳过即可。如果浏览器没有自动打开，手动访问上面的地址；终端窗口要一直开着，关掉终端页面就打不开了。

分类抽检核对工具（可选）：`python -m streamlit run review_app.py --server.port 8502`，地址 http://localhost:8502 。

## 三、从零重新生成数据（可选）

```bash
python crawler.py   # 抓取原始网页，约 30 分钟（每次请求间隔 2.5 秒，已抓过的会跳过）
python clean.py     # 清洗、去重，写入 policies 表
python analyze.py   # 主题分类 + 力度打分，写入 analysis 表
```

试跑可以用 `python crawler.py --limit 5`（每个栏目只抓 5 条）。

## 四、文件说明

| 文件 | 作用 |
|---|---|
| `crawler.py` | 抓取列表页和正文页，原始 HTML 存入 SQLite |
| `clean.py` | 提取标题/文号/发文机关/日期/正文，去重，限定 2020 年及以后 |
| `analyze.py` | 13 个文旅主题的关键词词典、力度打分规则、事务性通知识别 |
| `app.py` | Streamlit 看板 |
| `METHODOLOGY.md` | 一页方法说明（来源、样本、方法、局限） |

## 五、免费部署（Streamlit Community Cloud）

1. 把 `上传包` 文件夹里的内容上传到一个 GitHub 公开仓库。原始网页库 `data/policy.db`（约 42 MB）不需要上传，`python crawler.py` 可以重新生成。
2. 打开 https://share.streamlit.io ，用 GitHub 登录，选择该仓库，入口文件填 `app.py`，点 Deploy。
3. 本项目不需要任何密钥。如果以后加入大模型分类，密钥只放在 Streamlit 的 Secrets 或环境变量里，**不要写进代码**。

## 六、合规说明

- 只抓取公开页面，请求间隔 2.5 秒，请求头里标明是学术研究用途。
- 抓取前已检查：文旅部站点未设置 robots.txt（返回 404）；国家发改委站点对自动访问返回 403，因此未抓取；国务院政策库搜索接口无法访问，未使用。
- 原文版权归发布机关所有。看板只展示标题、元数据和跳转链接，不转载全文。
