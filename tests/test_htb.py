"""HTB tree unit tests. No real network calls."""
import time

import pytest

from config.llm import HTBNode, HTBTree, DailyQuotaExhausted


def _build_tree(root_rate=1.0, root_ceil=2.0, root_rpd=10,
                a_rate=0.5, a_rpd=4, b_rate=0.5, b_rpd=4) -> HTBTree:
    """Bare tree without going through HTBTree.__init__ so we can pick budgets."""
    tree = HTBTree.__new__(HTBTree)
    import threading
    tree.lock = threading.Lock()
    tree.root = HTBNode("root", root_rate, root_ceil, root_rpd)
    tree.providers = {
        "a": HTBNode("a", a_rate, root_ceil, a_rpd, parent=tree.root),
        "b": HTBNode("b", b_rate, root_ceil, b_rpd, parent=tree.root),
    }
    return tree


def test_refill_rate_is_continuous():
    n = HTBNode("x", rate_per_sec=2.0, ceil_per_sec=5.0, daily_budget=100)
    n.tokens = 0.0
    n.last_refill = time.monotonic() - 1.0
    n.refill()
    # After 1s at 2/s we expect ~2 tokens.
    assert 1.8 <= n.tokens <= 2.2


def test_refill_caps_at_burst():
    n = HTBNode("x", rate_per_sec=10.0, ceil_per_sec=3.0, daily_budget=100, burst=3.0)
    n.tokens = 0.0
    n.last_refill = time.monotonic() - 5.0
    n.refill()
    assert n.tokens == pytest.approx(3.0)


def test_acquire_takes_one_token_from_each_path_node():
    tree = _build_tree()
    # Pre-fill leaf 'a' so it has plenty; root starts full.
    tree.providers["a"].tokens = 5.0
    tree.root.tokens = 5.0
    tree.acquire("a")
    # Both leaf and root should have lost one token.
    assert tree.providers["a"].tokens == pytest.approx(4.0, abs=0.05)
    assert tree.root.tokens == pytest.approx(4.0, abs=0.05)
    # And both daily counts should drop by one.
    assert tree.providers["a"].daily_remaining == 3
    assert tree.root.daily_remaining == 9


def test_sibling_idle_allows_borrowing_up_to_root_ceil():
    """Leaf 'a' has rate 0.5/s but ceil = root_ceil = 2.0. With root having
    burst budget, 'a' should be able to consume multiple tokens quickly."""
    tree = _build_tree(root_rate=2.0, root_ceil=4.0, root_rpd=100,
                       a_rate=0.5, a_rpd=100, b_rate=0.5, b_rpd=100)
    tree.providers["a"].tokens = 4.0
    tree.root.tokens = 4.0
    # Burn 3 in quick succession — must succeed without long waits.
    t0 = time.monotonic()
    for _ in range(3):
        tree.acquire("a")
    assert time.monotonic() - t0 < 0.5


def test_daily_budget_decrements_on_every_attempt():
    tree = _build_tree(a_rpd=3)
    tree.providers["a"].tokens = 100.0
    tree.root.tokens = 100.0
    for _ in range(3):
        tree.acquire("a")
    assert tree.providers["a"].daily_remaining == 0
    with pytest.raises(DailyQuotaExhausted):
        tree.acquire("a")


def test_reset_daily_clears_counters():
    tree = _build_tree(a_rpd=2)
    tree.providers["a"].tokens = 100.0
    tree.root.tokens = 100.0
    tree.acquire("a")
    tree.acquire("a")
    assert tree.providers["a"].daily_remaining == 0
    tree.reset_daily()
    assert tree.providers["a"].daily_remaining == 2
    assert tree.root.daily_remaining == tree.root.daily_budget


def test_default_tree_budgets_sum_to_root():
    """Provider daily budgets should total to the eval+judge1+judge2 split (650+300+350=1300)."""
    tree = HTBTree()
    total = sum(n.daily_budget for n in tree.providers.values())
    assert total == 1300
    assert tree.root.daily_budget == 1300
    # nvidia gets the full judge allocation.
    assert tree.providers["nvidia"].daily_budget == 300
    # poolside (judge2) gets its own allocation.
    assert tree.providers["poolside"].daily_budget == 350
    # eval providers sum to 650.
    eval_total = sum(tree.providers[p].daily_budget
                     for p in ("openai", "moonshotai", "google"))
    assert eval_total == 650
