import subprocess
import sys

import parallel_runner as pr


def test_classify_worker_result_still_running_when_no_exit_code():
    assert pr._classify_worker_result(None, restarts=0, max_restarts=5) == "still_running"


def test_classify_worker_result_done_on_clean_exit():
    assert pr._classify_worker_result(0, restarts=2, max_restarts=5) == "done"


def test_classify_worker_result_restarts_on_crash_under_cap():
    assert pr._classify_worker_result(1, restarts=2, max_restarts=5) == "restart"


def test_classify_worker_result_gives_up_at_cap():
    assert pr._classify_worker_result(1, restarts=5, max_restarts=5) == "give_up"


def test_launch_worker_builds_expected_argv(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "ROOT", tmp_path)
    calls = []

    def fake_popen(args, **kwargs):
        calls.append(args)
        return object()

    pr.launch_worker("blinkit_oats", shard_index=1, num_shards=3, popen_fn=fake_popen)

    assert len(calls) == 1
    args = calls[0]
    assert args[1] == str(tmp_path / "blinkit_oats.py")
    assert args[2:] == ["--shard-index", "1", "--num-shards", "3"]


def test_wait_for_ram_returns_immediately_when_ram_is_sufficient():
    slept = []
    pr.wait_for_ram(min_mb=100, check_fn=lambda: 2000, sleep_fn=slept.append)
    assert slept == []


def test_wait_for_ram_pauses_until_ram_frees_up():
    readings = iter([50, 50, 200])
    slept = []
    pr.wait_for_ram(min_mb=100, check_fn=lambda: next(readings), sleep_fn=slept.append)
    assert len(slept) == 2


def test_wait_for_ram_gives_up_after_max_wait():
    slept = []
    pr.wait_for_ram(min_mb=100, check_fn=lambda: 10, sleep_fn=slept.append, max_wait_s=12)
    assert len(slept) == 3  # bounded, not infinite -- 3 attempts at 5s bookkeeping each


def test_wait_for_ram_never_raises_if_check_fn_fails():
    def broken():
        raise RuntimeError("psutil not installed")
    pr.wait_for_ram(min_mb=100, check_fn=broken, sleep_fn=lambda s: None)  # must not raise


def test_run_worker_pool_gives_up_after_max_restarts():
    launches = []

    class AlwaysCrashingPopen:
        def poll(self):
            return 1  # always reports "crashed"

        def terminate(self):
            pass

    def fake_popen_fn(args, **kwargs):
        launches.append(args)
        return AlwaysCrashingPopen()

    merges = []

    def fake_merge_fn(shard_paths, output_path, columns, sort_key_fn):
        merges.append(1)
        return 0

    pr.run_worker_pool(
        "blinkit_oats", workers=1,
        shard_paths=["shard0.xlsx"],
        final_output="combined.xlsx",
        columns=["City"], sort_key_fn=lambda r: 0,
        popen_fn=fake_popen_fn, sleep_fn=lambda s: None,
        ram_check_fn=lambda: 9999, time_fn=lambda: 0,
        merge_interval_s=999999, max_restarts=5, merge_fn=fake_merge_fn,
    )

    # 1 initial launch + 5 restarts = 6 total launches, then the worker is
    # dropped -- proves the cap is actually reachable, not silently reset
    # by the restart-counter carry-forward on each replacement WorkerHandle.
    assert len(launches) == 6
    # the final merge always runs once the pool drains, regardless of outcome
    assert len(merges) == 1


def test_workers_below_one_is_rejected_by_cli(tmp_path):
    result = subprocess.run(
        [sys.executable, str(pr.ROOT / "parallel_runner.py"), "blinkit_oats", "--workers", "0"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0
    assert "--workers must be at least 1" in result.stderr
