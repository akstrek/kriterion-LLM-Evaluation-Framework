"""DRR scheduler tests."""
from collections import Counter

from config.scheduler import DRRScheduler, BoundedPairQueue


def test_round_robin_fairness_balanced():
    sched = DRRScheduler(["m1", "m2", "m3"], quantum=1)
    # 60 pairs total, 20 per model — balanced.
    for i in range(20):
        for m in ("m1", "m2", "m3"):
            sched.enqueue(m, (f"p{i}", m))

    drained = Counter()
    while True:
        pair = sched.next_pair()
        if pair is None:
            break
        drained[pair[1]] += 1

    assert drained["m1"] == drained["m2"] == drained["m3"] == 20


def test_round_robin_fairness_under_quota_pressure():
    """Biased input: m1 has 100 pairs, m2 has 20, m3 has 5.
    During the first 15 picks (5 full rounds), each model should have been
    served roughly equally — within ±1."""
    sched = DRRScheduler(["m1", "m2", "m3"], quantum=1)
    for i in range(100): sched.enqueue("m1", (f"a{i}", "m1"))
    for i in range(20):  sched.enqueue("m2", (f"b{i}", "m2"))
    for i in range(5):   sched.enqueue("m3", (f"c{i}", "m3"))

    drained = Counter()
    for _ in range(15):
        pair = sched.next_pair()
        assert pair is not None
        drained[pair[1]] += 1

    counts = list(drained.values())
    assert max(counts) - min(counts) <= 1, f"Unfair: {drained}"


def test_next_pair_returns_none_when_no_pending():
    sched = DRRScheduler(["m1", "m2"], quantum=1)
    assert sched.next_pair() is None


def test_next_pair_returns_none_when_htb_blocks_all_models():
    sched = DRRScheduler(["m1", "m2"], quantum=1)
    sched.enqueue("m1", ("p1", "m1"))
    sched.enqueue("m2", ("p2", "m2"))
    # HTB blocks both providers.
    assert sched.next_pair(htb_check=lambda m: False) is None
    # Quantum was NOT consumed on skipped lanes, so unblocking gets us going.
    pair = sched.next_pair(htb_check=lambda m: True)
    assert pair is not None


def test_htb_block_on_one_model_still_serves_other():
    sched = DRRScheduler(["m1", "m2"], quantum=1)
    for i in range(5):
        sched.enqueue("m1", (f"a{i}", "m1"))
        sched.enqueue("m2", (f"b{i}", "m2"))
    # m1 blocked, m2 OK.
    served = []
    for _ in range(5):
        pair = sched.next_pair(htb_check=lambda m: m == "m2")
        assert pair is not None
        served.append(pair[1])
    assert all(m == "m2" for m in served)


def test_bounded_queue_basic():
    q = BoundedPairQueue(maxsize=3)
    assert q.empty()
    q.put(("a", "m1"))
    q.put(("b", "m1"))
    assert q.qsize() == 2
    item = q.get()
    q.task_done()
    assert item == ("a", "m1")


def test_requeue_front_preserves_order():
    sched = DRRScheduler(["m1"], quantum=1)
    sched.enqueue("m1", ("a", "m1"))
    sched.enqueue("m1", ("b", "m1"))
    sched.requeue_front("m1", ("urgent", "m1"))
    assert sched.next_pair()[0] == "urgent"
    assert sched.next_pair()[0] == "a"
    assert sched.next_pair()[0] == "b"
