# 架构

## 系统边界

TactiCore 当前只有一条研究链路：规范化复权收盘价 → Global Dual Momentum 月末信号 → 下一交易日目标权重 → VectorBT 快速研究 / RQAlpha 权威验证。没有数据库、调度器、UI、broker abstraction、provider framework 或自研记账模块。

```text
config/universe.csv      config/strategy.toml
          \                 /
           薄 CSV 数据读取层
                   |
     共享的动量排名与目标权重规则
              /                 \
      VectorBT adapter       RQAlpha adapter
      探索与指标计算          事件/交易语义验证
```

## 各层职责

### 数据

`tacticore.data` 只验证并读取当前策略需要的 universe 元数据和 `date × symbol` 复权收盘价 CSV。它不下载数据，也不抽象 provider。新增数据能力必须由具体策略 blocker 驱动。

### 策略

`tacticore.strategies.global_dual_momentum` 是经济逻辑的唯一来源：252 个交易日绝对动量过滤、相对动量排名、等权持有 top K、无合格风险资产时转入防御资产。VectorBT 和 RQAlpha 共享 `select_assets`，避免两份排名规则漂移。

VectorBT 路径在月末收盘后产生信号，并把订单目标移到下一观测日，防止同一收盘价既生成信号又执行。

### 引擎

- VectorBT：消费 canonical prices，执行目标百分比订单，返回组合净值、交易和研究指标。它用于 idea exploration、参数扫描和稳健性研究。
- RQAlpha：在每月第一个交易日用不含当日的历史收盘价计算目标，交给 RQAlpha 处理订单、现金、费用和市场规则。它是中国市场语义的权威验证路径。

两条路径无需 bit-for-bit 一致。后续差异应按执行时点、价格约定、费用、停牌、复权与取整解释，禁止增加第三套引擎仲裁。

### 组合

当前不创建内部 portfolio package。权重生成属于策略；现金、持仓和成交由现有引擎负责。

## 有意保留的简单性

所有配置集中在两个文件，但没有建立配置框架。所有数据通过一个明确 CSV contract 进入系统。只有一条已实现策略线，因此没有 strategy plugin 或基类。这个结构直接服务于 M2，且每层都能由经济正确性测试覆盖。
