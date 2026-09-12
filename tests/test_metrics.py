from research.metrics import drawdown_better, drawdown_no_worse


def test_signed_drawdown_semantics() -> None:
    assert drawdown_better(-0.10, -0.20)
    assert not drawdown_better(-0.20, -0.10)
    assert drawdown_no_worse(-0.10, -0.10)
    assert drawdown_no_worse(-0.10, -0.20)
    assert not drawdown_no_worse(-0.20, -0.10)
