"""FinanceMCP `fees-2.0.0` → VectorBT / RQAlpha 费用映射。

本模块存在的理由：两个引擎的费用参数与 FinanceMCP 的费用模型**不是同一件事**，
把一边的数字塞进另一边的参数里会静默改变研究结论。因此这里逐项列出映射关系，
并把**无法映射的差异显式记录下来**，而不是悄悄对齐。

任务书 WP2.3 原文要求：
> 把 FinanceMCP `fees-2.0.0` 映射到两个引擎，逐项列明佣金率/最低佣金/印花税/过户费/
> 滑点/交易单位/现金约束/卖出资金可用时点/结算规则/公司行动。
> TactiCore 现有 `build_rqalpha_config` 只有 fees+slippage 且 `tax_multiplier=0`、
> `stock_min_commission=0`，**差异必须显式记录**，不得静默对齐。

权威来源（只读，不修改）：
- FinanceMCP `src/portfolio/rules.ts:38` `DEFAULT_FEE_RULES` / `FEE_RULE_VERSION='fees-2.0.0'`
- FinanceMCP `src/portfolio/rules.ts:105` `DEFAULT_STOCK_RULES`
- TactiCore `tacticore/engines/rqalpha_adapter.py:16` `build_rqalpha_config`
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: FinanceMCP 费用模型版本。与源码常量保持一致；不一致时映射必须被拒绝。
FINANCE_FEE_MODEL_VERSION = "fees-2.0.0"

#: ETF 默认费率（FinanceMCP DEFAULT_FEE_RULES，rules.ts:38-44）。
ETF_COMMISSION_RATE = 0.00025  # 万 2.5
ETF_COMMISSION_MIN_CENTS = 500  # 5 元
ETF_TRANSFER_FEE_RATE = 0.0  # ETF 无过户费
ETF_STAMP_DUTY_RATE = 0.0  # ETF 免印花税
ETF_SLIPPAGE_RATE_PER_SIDE = 0.0005  # 万 5

#: A 股默认费率（FinanceMCP DEFAULT_STOCK_RULES，rules.ts:105-119）。
STOCK_COMMISSION_RATE = 0.00025  # 万 2.5
STOCK_COMMISSION_MIN_CENTS = 500  # 5 元
STOCK_TRANSFER_FEE_RATE = 0.00001  # 十万分之一（双边，假设）
STOCK_STAMP_DUTY_RATE = 0.0005  # 万分之五（仅卖出，假设）
STOCK_SLIPPAGE_RATE_PER_SIDE = 0.0005  # 万 5

#: 交易单位（FinanceMCP DEFAULT_LOT_RULES / DEFAULT_STOCK_RULES）。
LOT_SIZE = 100


@dataclass(frozen=True)
class UnmappedDifference:
    """一个**无法**在引擎参数中表达的差异。

    `item` 是费用项名，`finance_mcp` 是权威侧的值或语义，`engine` 是引擎实际行为，
    `impact` 说明这个差异会让研究结果偏向哪个方向。
    """

    item: str
    finance_mcp: str
    engine: str
    impact: str


@dataclass(frozen=True)
class EngineFeeMapping:
    """一个引擎的费用映射结果。"""

    engine: str
    version: str
    parameters: dict[str, float | int | bool]
    #: 显式记录的、未映射的差异。空列表表示完全映射（当前不存在这种情况）。
    unmapped: tuple[UnmappedDifference, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


def map_fees_to_vectorbt(*, asset_class: str = "ETF") -> EngineFeeMapping:
    """映射到 VectorBT `run_target_weights(fees=..., slippage=...)`。

    VectorBT 的 `fees` 是**单边按成交额比例**收费，`slippage` 同样按比例。
    因此映射是直接的，但有三项必须记录为未映射：

    1. **最低佣金 5 元**：本适配器只传比例费用，未表达每笔最低佣金。
       按 0.025% 计算，单笔成交额低于 2 万元时最低佣金生效；账户总额
       约 7.6 万元也可能拆成多笔低于该门槛的交易。
    2. **印花税仅卖出**：VectorBT 的 `fees` 对买卖同向收取。把卖出印花税折进
       单边费率会让买入也付印花税，方向性错误。因此**不折入**，记为未映射。
    3. **过户费**：ETF 为 0 无影响；A 股为双边十万分之一，同样方向性不同，不折入。
    """
    if asset_class == "ETF":
        commission, stamp, transfer, slippage = (
            ETF_COMMISSION_RATE,
            ETF_STAMP_DUTY_RATE,
            ETF_TRANSFER_FEE_RATE,
            ETF_SLIPPAGE_RATE_PER_SIDE,
        )
    elif asset_class == "STOCK":
        commission, stamp, transfer, slippage = (
            STOCK_COMMISSION_RATE,
            STOCK_STAMP_DUTY_RATE,
            STOCK_TRANSFER_FEE_RATE,
            STOCK_SLIPPAGE_RATE_PER_SIDE,
        )
    else:
        raise ValueError(f"未知资产类别: {asset_class!r}（可用: ETF, STOCK）")

    unmapped = [
        UnmappedDifference(
            item="commission_min_cents",
            finance_mcp="500 分（5 元）每笔最低佣金",
            engine="当前适配器只传比例费率，未映射每笔最低佣金",
            impact=(
                "按 0.025% 计算，单笔成交额低于 2 万元时最低佣金生效；"
                "账户总额约 7.6 万元也可能拆分为多笔小额交易，不能据账户规模排除影响"
            ),
        ),
    ]
    if stamp:
        unmapped.append(
            UnmappedDifference(
                item="stamp_duty_rate",
                finance_mcp=f"{stamp} 仅卖出收取",
                engine="fees 对买入与卖出同向收取",
                impact="若折入 fees 会让买入也付印花税，成本被高估、换手被惩罚；因此不折入",
            )
        )
    if transfer:
        unmapped.append(
            UnmappedDifference(
                item="transfer_fee_rate",
                finance_mcp=f"{transfer} 双边收取（过户费）",
                engine="无独立过户费参数",
                impact="不折入；对约 7.6 万元账户影响约 7.6 元/完整往返，量级可忽略但方向未表达",
            )
        )

    return EngineFeeMapping(
        engine="vectorbt",
        version=FINANCE_FEE_MODEL_VERSION,
        parameters={"fees": commission, "slippage": slippage},
        unmapped=tuple(unmapped),
        notes=(
            "VectorBT fees/slippage 均为单边按成交额比例；最低佣金、印花税方向性、"
            "过户费均未映射，见 unmapped。",
            f"lot_size={LOT_SIZE} 由 VectorBT 的 size_type='targetpercent' 隐式忽略："
            "目标权重是百分比，不是股数，因此一手交易约束在本引擎中不存在。",
        ),
    )


def map_fees_to_rqalpha(*, asset_class: str = "ETF") -> EngineFeeMapping:
    """映射到 RQAlpha `build_rqalpha_config(fees=..., slippage=...)`。

    RQAlpha 的费用模型与 FinanceMCP **结构性不同**，这是必须显式记录的核心差异：

    - `build_rqalpha_config`（`rqalpha_adapter.py:16`）只接受 `fees` 与 `slippage`，
      内部换算成 `stock_commission_multiplier = fees / 0.0008`。
      RQAlpha 的 `stock_commission_multiplier` 是**相对于自身默认佣金率 0.0008 的倍数**，
      不是绝对费率。因此传入 `fees=0.00025` 得到 `multiplier=0.3125`，
      即实际佣金率 = 0.0008 × 0.3125 = 0.00025。数值上等价，但语义上是一次乘法。
    - `tax_multiplier = 0`：**印花税被关掉了**。FinanceMCP A 股模型有卖出
      万分之五印花税。这是一个真实的、方向明确的成本低估。
    - `stock_min_commission = 0`：**最低佣金被关掉了**。同上。
    - `slippage` 用 `PriceRatioSlippage` 模型，按价格比例，与 FinanceMCP 的
      `slippage_rate_per_side` 同向，可映射。
    """
    if asset_class == "ETF":
        commission, slippage = ETF_COMMISSION_RATE, ETF_SLIPPAGE_RATE_PER_SIDE
        stamp = ETF_STAMP_DUTY_RATE
    elif asset_class == "STOCK":
        commission, slippage = STOCK_COMMISSION_RATE, STOCK_SLIPPAGE_RATE_PER_SIDE
        stamp = STOCK_STAMP_DUTY_RATE
    else:
        raise ValueError(f"未知资产类别: {asset_class!r}（可用: ETF, STOCK）")

    # RQAlpha 的默认佣金率。这是 rqalpha_adapter.py:31 换算公式的分母，
    # 写在这里而不是引用 rqalpha 包，避免为了一个常数引入运行时依赖。
    RQALPHA_DEFAULT_COMMISSION = 0.0008
    multiplier = commission / RQALPHA_DEFAULT_COMMISSION

    unmapped = [
        UnmappedDifference(
            item="tax_multiplier",
            finance_mcp=(f"stamp_duty_rate={stamp}（仅卖出）" if stamp else "ETF 免印花税（0）"),
            engine="build_rqalpha_config 固定写入 tax_multiplier=0，印花税被关闭",
            impact=(
                "A 股卖出成本被低估万分之五；ETF 无差异（本就得 0）。"
                "这是既有适配器的行为，本次不修改 rqalpha_adapter.py。"
            ),
        ),
        UnmappedDifference(
            item="stock_min_commission",
            finance_mcp="500 分（5 元）每笔最低佣金",
            engine="build_rqalpha_config 固定写入 stock_min_commission=0，最低佣金被关闭",
            impact=(
                "单笔成交额低于 2 万元时佣金被低估；账户总额约 7.6 万元"
                "也可能拆分为多笔小额交易，不能据账户规模排除影响"
            ),
        ),
        UnmappedDifference(
            item="transfer_fee_rate",
            finance_mcp=(
                f"A 股双边 {STOCK_TRANSFER_FEE_RATE}" if asset_class == "STOCK" else "ETF 0"
            ),
            engine="RQAlpha 无独立过户费参数",
            impact="未映射；A 股双向十万分之一，量级可忽略但方向未表达",
        ),
        UnmappedDifference(
            item="settlement_and_cash_availability",
            finance_mcp="卖出资金可用时点与结算规则在 rules.ts 中未定义为可执行约束",
            engine="RQAlpha 默认 T+1 资金可用、A 股 T+1 交易约束（t_plus_one=true）",
            impact=(
                "FinanceMCP DEFAULT_STOCK_RULES 声明 t_plus_one=true，"
                "与 RQAlpha 的 A 股行为一致；但**卖出资金可用时点**两侧都没有"
                "可执行参数，属未建模而非已对齐"
            ),
        ),
        UnmappedDifference(
            item="corporate_actions",
            finance_mcp="本导出不含公司行动（拆分/合并/分红）重建数据",
            engine="RQAlpha 依赖 bundle 中的复权与除权数据",
            impact=(
                "若 bundle 的公司行动与 FinanceMCP 快照的复权口径不一致，"
                "两套账的差异无法归因到费用，必须单独审计；无法重建时返回 DATA_INSUFFICIENT"
            ),
        ),
    ]

    return EngineFeeMapping(
        engine="rqalpha",
        version=FINANCE_FEE_MODEL_VERSION,
        parameters={
            "fees": commission,
            "slippage": slippage,
            "stock_commission_multiplier": multiplier,
            "tax_multiplier": 0,
            "stock_min_commission": 0,
        },
        unmapped=tuple(unmapped),
        notes=(
            f"fees={commission} 经 rqalpha_adapter.py:31 换算为 "
            f"stock_commission_multiplier={multiplier}（RQAlpha 默认佣金率 "
            f"{RQALPHA_DEFAULT_COMMISSION} 的倍数），实际佣金率数值等价。",
            "本模块只做映射与差异记录，不修改 tacticore/engines/rqalpha_adapter.py。",
        ),
    )


def describe_mapping(mapping: EngineFeeMapping) -> str:
    """人类可读的映射报告，用于实验记录归档。"""
    lines = [
        f"引擎: {mapping.engine}    费用模型: {mapping.version}",
        f"映射参数: {mapping.parameters}",
    ]
    if mapping.notes:
        lines.append("说明:")
        lines.extend(f"  - {note}" for note in mapping.notes)
    lines.append(f"未映射差异（{len(mapping.unmapped)} 项，必须随结果一起阅读）:")
    for difference in mapping.unmapped:
        lines.append(f"  - {difference.item}")
        lines.append(f"      FinanceMCP: {difference.finance_mcp}")
        lines.append(f"      引擎实际:   {difference.engine}")
        lines.append(f"      影响:       {difference.impact}")
    return "\n".join(lines)


__all__ = [
    "ETF_COMMISSION_MIN_CENTS",
    "ETF_COMMISSION_RATE",
    "ETF_SLIPPAGE_RATE_PER_SIDE",
    "ETF_STAMP_DUTY_RATE",
    "ETF_TRANSFER_FEE_RATE",
    "FINANCE_FEE_MODEL_VERSION",
    "LOT_SIZE",
    "STOCK_COMMISSION_MIN_CENTS",
    "STOCK_COMMISSION_RATE",
    "STOCK_SLIPPAGE_RATE_PER_SIDE",
    "STOCK_STAMP_DUTY_RATE",
    "STOCK_TRANSFER_FEE_RATE",
    "EngineFeeMapping",
    "UnmappedDifference",
    "describe_mapping",
    "map_fees_to_rqalpha",
    "map_fees_to_vectorbt",
]
