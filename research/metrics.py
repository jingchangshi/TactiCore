"""研究决策共享的有符号指标语义。"""


def drawdown_better(candidate: float, comparator: float) -> bool:
    return candidate > comparator


def drawdown_no_worse(candidate: float, comparator: float) -> bool:
    return candidate >= comparator
