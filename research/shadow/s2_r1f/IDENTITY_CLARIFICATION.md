# S2_R1F 身份日期说明

`eligible_since = 2026-11-25` 是**身份存在的下界**，不是第一个合格决策日。手工 `decide` 必须先通过真实当日收盘与输入封存检查，再检查受信月末。2026-11-25 的结果为 `NOT_MONTH_END`；该日只有 `VINTAGE_ONLY_NOT_OBSERVATION`，无决策、无执行、无前瞻观测。S2_R1F 的时钟从首个真实封存的 S2_R1F 月度决策起算，绝不从身份日期、历史复现、非决策 vintage 或 R1 观测起算。

**first_eligible_decision = 2026-11-30**：对下列受信文件作只读查询，11 月开市日期中包含 11-30，且其为该月最大值。这只是最早可以判断的日历日期，不表示届时已有合规价格、已封存决策或已授权交易；若错过，不得回填。

辅助日历为 `/home/jcshi/.rqalpha/bundle/trading_dates.npy`，SHA-256 `57dd7f539d1cdbefb528978a6c7bd79b118790f933ce63c37b10747b999f9585`；文件含 5,587 个日期（2005-01-04 至 2027-12-31）。它是冻结 RQAlpha bundle 产物，**不是 TDX 数据，也不是交易所官方公告的证明**。仅信任 2026 年、只判月末，不参与价格、公司行动、历史对照或等价性。2026-12-31 之后，无受信日历的入口拒绝决策，不用最后一根 bar 代替月末。

Git 只存程序、合成测试、无行情明细的候选身份与说明。真实 vintage 位于本地私有目录 `/home/jcshi/workspace/TactiCore-wt/drop-tushare/research/output/s2_r1f/vintages/2026-11-25/`，目录创建于 2026-11-25T10:04:02.128108377Z，目录 0700、文件 0600；这是本地状态，不是 Git 中的行情证据。身份 manifest SHA-256 `da91b3008c130ab70d7ed56ee342551d5892563687c4ef4935f98e100b2c4e14`；该日 `seal.json` SHA-256 `fdfba2d58c280178c7621efc476794725c1284129709524dcff76a861b032b93`。本说明不改写二者、不重新封存。

V2 的 `ATTEMPT_V2.json` 是**最小 attempt 标记**，仅含 `protocol_commit`、`runner_commit`、`started_utc`，未内嵌协议 SHA 或主站/参数。完整 manifest 在私有 `/home/jcshi/workspace/free-v2-private/snapshot/manifest.json`，含协议提交及摘要、实际获取 UTC 起止、主站与请求参数、逐资产行数和逐文件 SHA-256。`EQUIVALENCE_RESULT_V2.json` 以 `attempt_sha256` 和 `snapshot_sha256` 分别绑定两者字节，并以 `private_file_hashes_sha256` 绑定私有清单。该记录位置差异已披露，由架构师接受，不构成重跑理由。
