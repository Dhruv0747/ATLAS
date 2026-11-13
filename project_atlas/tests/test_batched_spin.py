import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import atlas_batched_spin as B  # noqa: E402


class FakeExecutor:
    def __init__(self):
        self.calls = 0

    def _wait_for_ready_callbacks(self, *a, **k):
        self.calls += 1
        yield "cb1"
        yield "cb2"


def test_env_parsing(monkeypatch):
    monkeypatch.delenv("ATLAS_EXECUTOR_BATCH_S", raising=False)
    assert B.batch_from_env() == 0.0
    monkeypatch.setenv("ATLAS_EXECUTOR_BATCH_S", "0.05")
    assert B.batch_from_env() == 0.05
    monkeypatch.setenv("ATLAS_EXECUTOR_BATCH_S", "5")
    assert B.batch_from_env() == B.MAX_BATCH_S
    monkeypatch.setenv("ATLAS_EXECUTOR_BATCH_S", "nonsense")
    assert B.batch_from_env() == 0.0


def test_zero_batch_leaves_executor_untouched():
    ex = FakeExecutor()
    original = ex._wait_for_ready_callbacks
    assert B.make_batched(ex, 0.0) is ex
    assert ex._wait_for_ready_callbacks == original


def test_batched_yields_all_ready_callbacks_after_one_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(B.time, "sleep", lambda s: slept.append(s))
    ex = B.make_batched(FakeExecutor(), 0.05)
    assert list(ex._wait_for_ready_callbacks()) == ["cb1", "cb2"]
    assert slept == [0.05]
