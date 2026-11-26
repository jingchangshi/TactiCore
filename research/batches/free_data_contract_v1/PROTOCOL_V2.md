# FREE_DATA_CONTRACT_V2 预注册协议

冻结时点以本协议在 `feat/drop-tushare` 首次单独提交的实际 Git 时间为准，不追溯至 V1。V2 只执行一次，不发布行情或凭据、不产生前瞻观测。唯一问题是免费源能否复现两个 R1 的历史目标日程，不比较收益。

## 1. 已观察到什么

`fa6eed9` 的 `PROTOCOL_V1.md` 与 `a21f226` 的 `EQUIVALENCE_RESULT_V1.json` 永久不改。V1 停在 `FAIL_CLOSED_NO_SNAPSHOT`：三只风险资产有上市后 category 11/12，按 V1 停止，既未跑 canonical 对照也未比较免费源。V1 的标签不是已观测到日程差异。下列是**停止后已知**的原始收盘比，不是盲测样本，也不是 V2 运行时间：

| 标的 | 事件日 | s（新份额/旧份额） | 后收盘/前收盘 | r × s（约） |
|---|---|---:|---:|---:|
| 510500.SS | 2015-04-15 | 0.28032482 | 7.818 / 2.243 | 0.977075 |
| 510500.SS | 2022-08-29 | 1.14539003 | 6.300 / 7.220 | 0.999440 |
| 513500.SS | 2022-03-30 | 2 | 1.390 / 2.735 | 1.016453 |
| 513100.SS | 2022-01-14 | 5 | 1.015 / 5.192 | 0.977465 |

V2 只补充数据事件的解释与拒绝歧义规则。阈值由架构师裁定；不得按结果修改阈值、方向、窗口、事件、源或策略，不能用 V2 重写 V1。

## 2. 门禁与输入（继承 V1）

- Canonical mapping：S2 是 200 有效观测月度趋势、等 sleeve + 国债 fallback；S4C 是 60 对齐收益的 ERC / risk budgeting，少于 6 个合格资产整组合 fallback。
- External tier 不变；external conclusion：文献不能证明供应商替换后日程相等；relevant contradictions：历史修订、缺失与独立复权可改变趋势临界点或 ERC 权重。
- Upstream implementation：只调用 `run_s2_rqalpha_validation.build_frozen_target_schedule` 和 `run_s4c_rqalpha_execution_review.build_frozen_schedule`，不重写信号、PIT、执行或求解器。
- Existing TactiCore evidence：两个 committed 日程及 `PORTABLE_REPRODUCTION_CONTRACT_V1`；remaining local gap：相同语义换源能否重现；research action：`LOCAL_ADJUDICATION`。
- PIT 六要素：以 `config/universe.csv` 的 12 只 ETF、各自 `start_date` 和原 `AssetLifetime` 为准；不替代资产、不使用上市前价格。fallback `511010.SS` 上市前沿用冻结语义和 S4C inception 裁剪；缺失执行价不填充；两个冻结首执行日均为 2013-04-01，S4C 末日 2026-08-03；S4C 每个正目标必须经原 `validate_execution_targets`，S2 不新增策略层过滤。价格只用 `<= 2026-08-31`（含当天），不裁剪至两源的公共交易日。无真实前瞻时钟继承。
- 输入固定为本协议父提交 `6bc99b8` 的 `config/{strategy.toml,universe.csv}`、`data/canonical/etf_adjusted_close.csv` 及 `research/results/{s2_v2_frozen_targets,s4c_pit_corrected_frozen_targets_v1}.csv`；运行留 SHA-256。禁止接入在线 Tushare。

## 3. 免费源契约与方向校验

1. 复用 V1 `fetch_tdx_history.py` 的 TDX category 9 日线、页长 800、xdxr 解析和 `.SS→1/.SZ→0`+前六位映射。仅连接阶段按原 `DEFAULT_HOSTS` 顺序选第一个握手成功的主站；选定后不换站、不重新拉取。价格是实际下载时供应商的当前视图，不是历史 vintage；交易日收盘价在上海时间该日 15:00 后可用。
2. 比较区间为每资产 `[start_date, 2026-08-31]`。更早和更晚的 bar/事件不参与因子或交叉检查，原始记录仅本地留存。有效 bar 需成交量、收盘价有限且均 > 0；不补零、不插值、不前填。若资产无有效价格、请求缺数致未取得整只资产、日期无效或事件归属无法确定，则不产出合规快照。市场日内停牌/零成交保留为空，不用 canonical 补缺。
3. 只接受 category 1、11、12。对区间内事件 `e`（含上市日与截止日），`pre` 是严格早于 `e` 的最后一个有效 bar，`post` 是日期 ≥ `e` 的首个有效 bar，均不得越过区间边界。无 pre / post（包括首个有效 bar 上的事件）、同一 post 有多个事件（含分红叠加、重复拆合股）、未知类别，一律记录标的、日期、原因，停止。区间外事件不移到区间内。
4. 后复权：起始因子 1。从 `post`（含）起乘入事件因子，历史更早价格不变。category 1 沿用 `ref=(pre.close×10−fenhong+peigu×peigujia)/(10+songzhuangu+peigu)`，因子乘 `pre.close/ref`，不四舍五入；非有限、非正参考价或无效分母停止。category 11/12 的 `s=suogu` 表示每旧份额对应的新份额；理论原始价格跳变为 `1/s`，所以**后复权因子乘 s，不除以 s**。保持 `adjusted_close = raw_close × cumulative_factor`；CSV 沿用 V1 八位小数（不在比较前再舍入权重）。
5. 每个拆合股必须有有限且正的 `s`。令 `r=post.close/pre.close`，按 `|r/(1/s)−1| = |r×s−1|` 验证。严格大于 5% 停止，等于 5% 通过；使用十进制原始收盘价及解码后的 s 作交叉乘法 `abs(post.close*s−pre.close) <= 0.05*pre.close`，不先舍入 r。记录 pre/post 日期、s、r、偏差。该偏差包含真实市场涨跌，只是数据交叉检查，不证明因子正确，也不允许以涨跌为由豁免。累积因子和有效后复权价格须有限且正。
6. 本地私有目录保存原始日线/xdxr、复权宽表、manifest：合约、协议提交/摘要、实际 UTC 起止时刻、主站/请求参数、来源与可得时点、逐资产行数/首末日、全部事件及实际应用事件、每个数据文件 SHA-256。部分下载与日志不是合规快照；不得上传这些数据。

## 4. 唯一裁决（V1 §4 原判据优先）

先有合规快照，再以同一段比较代码对 canonical 重推两个日程；任一对照未通过即 `BLOCKED_CONTROL`，不比较任何免费源。对照通过后，逐候选将免费源重推日程与其 committed 参照比较。不能把 fitted control 当参照，不能排序/补齐/丢弃不匹配的行列来通过门禁。

- **S2_R1**：执行日集合及顺序精确一致（103 行），资产列集合及顺序精确一致，每个权重 `|Δw| <= 1e-8`。
- **S4C_R1**：执行日集合及顺序精确一致（161 行，2013-04-01 至 2026-08-03），资产列集合及顺序精确一致；逐行正权重 support 和最大权重资产身份精确一致；每行和 `round(12)==1`；每个权重 `|Δw| <= 1e-4`，相对容差 0。
- 全部满足才 `EQUIVALENT`；已完成可判定比较且任一条件失败为 `NOT_EQUIVALENT`（比较不等价）。记录首个/最大差异日期、资产；日期集不同先列缺/多日，再在共有行列上作诊断（绝不作为通过依据）。对价格层列逐资产日收益差、缺失差异、事件对照；canonical 无可用因子明细须标未知，不能推定归因。无合规快照、控制失败或无法实际生成/比较则明确 `NOT_COMPARED`（尚未比较）与阶段/原因，而不是断言不等价。

## 5. 单次执行与后继

本协议先单独本地提交；再提交运行程序并用合成输入测边界（不得读取真实日程计算结果或试拉行情）。只启动一次真实 V2；不因网络错误、代码错误、缺数、对照失败、差异而重跑。记录实际开始/结束、协议与程序提交、环境、输入/快照/日志哈希、阶段及各候选结论于本目录新文件 `EQUIVALENCE_RESULT_V2.json`；V1 不覆盖。日志与快照只存本地私有目录，Git 只存协议、代码/测试与不含行情明细的结果摘要。

仅 `EQUIVALENT` 的候选可在新目录建立独立 `S2_R1F` / `S4C_R1F` 并进行真实可用防回填演练：当前日收盘后同日封存、拒绝过去/未来日期、已有 vintage 不覆盖、无输入不伪造、只从首个真实决策起算；不继承 R1 observation。未通过则止于证据，不建后继、不做形式化演练。全程不部署、不写生产、不新建定时器、不改冻结身份或已签文件。
