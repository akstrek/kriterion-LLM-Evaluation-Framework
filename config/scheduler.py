"""
config/scheduler.py
Producer-consumer DRR scheduler for (prompt, evaluator_model) pairs.

Topology:
    DRRScheduler ──fills──► BoundedPairQueue ──drained by──► N worker threads
                                                            (one per model, N=3)
Each worker pulls a pair, calls evaluator + judge via config.llm.call_model,
writes a parquet row, marks completion, loops.

Quota exhaustion (any HTB leaf's daily budget at 0) → orchestrator sleeps
until 00:01 UTC the next day, polling every 5 min (handles Windows
suspend/resume). On wake: HTBTree.reset_daily(); resume.

All multi-thread state mutations live behind a single threading.Lock.
"""
from __future__ import annotations

import datetime
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import timezone
from typing import Callable, Iterable

from config.llm import DailyQuotaExhausted, _HTB, _interruptible_sleep


# ── Bounded queue ────────────────────────────────────────────────────────────

class BoundedPairQueue:
    """Thin wrapper around queue.Queue holding (prompt_obj, model) tuples."""

    def __init__(self, maxsize: int = 50) -> None:
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)

    def put(self, item, timeout: float | None = None) -> None:
        self._q.put(item, timeout=timeout)

    def get(self, timeout: float | None = None):
        return self._q.get(timeout=timeout)

    def task_done(self) -> None:
        self._q.task_done()

    def empty(self) -> bool:
        return self._q.empty()

    def qsize(self) -> int:
        return self._q.qsize()

    def join(self) -> None:
        self._q.join()


# ── DRR scheduler ────────────────────────────────────────────────────────────

@dataclass
class _ModelLane:
    pending: list = field(default_factory=list)
    deficit: int = 0


class DRRScheduler:
    """Deficit Round-Robin over evaluator models, quantum=1 per round.

    next_pair(htb_check) returns the next eligible (prompt_obj, model) tuple
    or None if no model has both:
      - pending work, AND
      - HTB tokens currently available for its provider (per htb_check).
    A None return is the orchestrator's signal to sleep briefly.
    """

    def __init__(self, models: Iterable[str], quantum: int = 1) -> None:
        self.models: list[str] = list(models)
        if not self.models:
            raise ValueError("DRRScheduler needs at least one model")
        self.quantum = quantum
        self.lanes: dict[str, _ModelLane] = {m: _ModelLane() for m in self.models}
        self.lock = threading.Lock()
        self._cursor = 0

    def enqueue(self, model: str, pair) -> None:
        if model not in self.lanes:
            raise KeyError(f"Unknown model: {model}")
        with self.lock:
            self.lanes[model].pending.append(pair)

    def requeue_front(self, model: str, pair) -> None:
        """Push back to the head of the lane (for quota-exhaustion retries)."""
        with self.lock:
            self.lanes[model].pending.insert(0, pair)

    def has_work(self) -> bool:
        with self.lock:
            return any(lane.pending for lane in self.lanes.values())

    def pending_count(self, model: str | None = None) -> int:
        with self.lock:
            if model is None:
                return sum(len(l.pending) for l in self.lanes.values())
            return len(self.lanes[model].pending)

    def next_pair(self, htb_check: Callable[[str], bool] | None = None):
        """Return the next pair per DRR fairness, or None if nothing is eligible.

        htb_check(model) -> bool returns False if HTB currently has no tokens
        for that model's provider. Skipped lanes do NOT consume their quantum.
        """
        if htb_check is None:
            htb_check = lambda _m: True
        with self.lock:
            n = len(self.models)
            # Walk up to 2 full rounds to find an eligible lane.
            for _ in range(n * 2):
                m = self.models[self._cursor]
                self._cursor = (self._cursor + 1) % n
                lane = self.lanes[m]
                if not lane.pending:
                    lane.deficit = 0
                    continue
                if not htb_check(m):
                    # Provider has no tokens right now — don't add quantum,
                    # the scheduler thread will retry on the next pass.
                    continue
                lane.deficit += self.quantum
                if lane.deficit >= 1:
                    lane.deficit -= 1
                    return lane.pending.pop(0)
            return None


# ── Quota-exhausted sleep helper ─────────────────────────────────────────────

def next_utc_reset(now: datetime.datetime | None = None) -> datetime.datetime:
    now = now or datetime.datetime.now(timezone.utc)
    tomorrow = now + datetime.timedelta(days=1)
    return tomorrow.replace(hour=0, minute=1, second=0, microsecond=0)


def sleep_until_reset(stop_event: threading.Event,
                      poll_secs: float = 300.0,
                      reset_at: datetime.datetime | None = None) -> bool:
    """Sleep until reset_at (default next 00:01 UTC), polling every poll_secs
    so a Windows suspend/resume doesn't miss the wake. Returns True on natural
    wake, False if stop_event tripped first."""
    target = reset_at or next_utc_reset()
    while not stop_event.is_set():
        remaining = (target - datetime.datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            return True
        _interruptible_sleep(min(poll_secs, max(remaining, 1.0)))
    return False


# ── Orchestrator ─────────────────────────────────────────────────────────────

@dataclass
class _RunStats:
    completed: int = 0
    failed: int = 0
    quota_sleeps: int = 0


class EvalOrchestrator:
    """Wires a DRRScheduler + BoundedPairQueue + N=len(models) workers together.

    process_pair_fn(prompt_obj, model) is supplied by the caller (batch_eval.py).
    It must do the eval + judge calls and persist the result row. Raising
    DailyQuotaExhausted signals the orchestrator to sleep until the next reset.
    """

    def __init__(
        self,
        models: list[str],
        process_pair_fn: Callable[[dict, str], None],
        queue_maxsize: int = 50,
    ) -> None:
        self.models = models
        self.process = process_pair_fn
        self.queue = BoundedPairQueue(queue_maxsize)
        self.drr = DRRScheduler(models, quantum=1)
        self.stats = _RunStats()
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.quota_event = threading.Event()

    def enqueue_all(self, pairs: Iterable[tuple[dict, str]]) -> None:
        for prompt_obj, model in pairs:
            self.drr.enqueue(model, (prompt_obj, model))

    def _htb_has_tokens(self, model: str) -> bool:
        provider = model.split("/")[0]
        with _HTB.lock:
            leaf = _HTB.providers.get(provider)
            if leaf is None:
                return False
            for n in leaf.path_to_root():
                n.refill()
            if any(n.daily_remaining <= 0 for n in leaf.path_to_root()):
                return False
            return all(n.tokens >= 1.0 for n in leaf.path_to_root())

    def _scheduler_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.quota_event.is_set():
                # Workers finish in-flight while we wait for reset.
                self.queue.join()
                self.stats.quota_sleeps += 1
                woke = sleep_until_reset(self.stop_event)
                if not woke:
                    return
                _HTB.reset_daily()
                self.quota_event.clear()
                print("[scheduler] daily HTB budget reset — resuming",
                      flush=True)
                continue

            if not self.drr.has_work():
                # Drain workers, then exit.
                self.queue.join()
                self.stop_event.set()
                return

            pair = self.drr.next_pair(htb_check=self._htb_has_tokens)
            if pair is None:
                time.sleep(0.5)
                continue
            try:
                self.queue.put(pair, timeout=1.0)
            except queue.Full:
                # Push back to front, retry next loop.
                self.drr.requeue_front(pair[1], pair)
                time.sleep(0.1)

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                pair = self.queue.get(timeout=0.5)
            except queue.Empty:
                if self.quota_event.is_set() or self.stop_event.is_set():
                    return
                continue
            prompt_obj, model = pair
            try:
                self.process(prompt_obj, model)
                with self.state_lock:
                    self.stats.completed += 1
            except DailyQuotaExhausted:
                # Requeue and signal scheduler to enter the sleep path.
                self.drr.requeue_front(model, pair)
                self.quota_event.set()
            except Exception as exc:  # noqa: BLE001
                with self.state_lock:
                    self.stats.failed += 1
                print(f"[worker] error on {prompt_obj.get('id', '?')}/{model}: {exc}",
                      flush=True)
            finally:
                self.queue.task_done()

    def run(self) -> _RunStats:
        workers = [
            threading.Thread(target=self._worker_loop, daemon=True, name=f"worker-{i}")
            for i in range(len(self.models))
        ]
        for w in workers:
            w.start()
        try:
            self._scheduler_loop()
        except KeyboardInterrupt:
            self.stop_event.set()
            raise
        finally:
            self.stop_event.set()
            for w in workers:
                w.join(timeout=10.0)
        return self.stats
