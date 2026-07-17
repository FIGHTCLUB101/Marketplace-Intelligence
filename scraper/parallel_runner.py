"""
Generic parallel-worker supervisor for the Blinkit/Zepto oats scrapers.
Splits the locality list into N shards, launches one worker subprocess per
shard, restarts any that crash (capped), and periodically merges the shard
output files into the single combined file each scraper normally produces
at scraper/output/{scraper_name}_data.xlsx.

Usage:
    python parallel_runner.py blinkit_oats --workers 3
    python parallel_runner.py zepto_oats --workers 3

See docs/superpowers/specs/2026-07-17-scraper-parallelization-design.md
for the full design rationale.
"""
import importlib
import subprocess
import sys
import time
from pathlib import Path

from _merge import merge_shards

ROOT = Path(__file__).resolve().parent
MAX_RESTARTS_PER_WORKER = 5
RESTART_BACKOFF_S = 10
STAGGER_S = 20
MERGE_INTERVAL_S = 300
MIN_FREE_RAM_MB = 1024

SCRAPER_CONFIGS = {
    "blinkit_oats": {
        "build_localities": lambda mod: mod.build_target_localities(),
        "make_sort_key_fn": lambda mod, localities: mod.make_sort_key_fn(localities),
    },
    "zepto_oats": {
        "build_localities": lambda mod: mod.load_localities(str(mod.MAGICBRICKS_FILE)),
        "make_sort_key_fn": lambda mod, localities: mod.make_sort_key_fn(localities),
    },
    "swiggy_oats": {
        "build_localities": lambda mod: mod.build_target_localities(),
        "make_sort_key_fn": lambda mod, localities: mod.make_sort_key_fn(localities),
    },
}


def free_ram_mb():
    import psutil
    return psutil.virtual_memory().available / (1024 * 1024)


def wait_for_ram(min_mb=MIN_FREE_RAM_MB, check_fn=free_ram_mb, sleep_fn=time.sleep, max_wait_s=120):
    """Blocks (with a warning) until free RAM clears min_mb, or max_wait_s
    elapses -- whichever first. Never raises; a psutil import failure or
    any other error just skips the check (better to proceed than to hang
    the whole run over an optional safety check)."""
    waited = 0.0
    while waited < max_wait_s:
        try:
            free = check_fn()
        except Exception:
            return
        if free >= min_mb:
            return
        print(f"⚠️  Low RAM ({free:.0f}MB free, want {min_mb}MB) — pausing before next launch...", flush=True)
        sleep_fn(5)
        waited += 5


def launch_worker(scraper_name, shard_index, num_shards, popen_fn=subprocess.Popen):
    script = str(ROOT / f"{scraper_name}.py")
    args = [sys.executable, script, "--shard-index", str(shard_index), "--num-shards", str(num_shards)]
    creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    return popen_fn(args, creationflags=creationflags)


def _classify_worker_result(exit_code, restarts, max_restarts):
    """Given a worker's poll() result and how many times it's already been
    restarted, decides what the supervisor should do next. Pure/stateless
    so the crash-cap policy itself can be tested without any real or fake
    subprocess machinery."""
    if exit_code is None:
        return "still_running"
    if exit_code == 0:
        return "done"
    if restarts >= max_restarts:
        return "give_up"
    return "restart"


class WorkerHandle:
    def __init__(self, shard_index, popen):
        self.shard_index = shard_index
        self.popen = popen
        self.restarts = 0


def _try_merge(shard_paths, final_output, columns, sort_key_fn, merge_fn=merge_shards):
    try:
        n = merge_fn(shard_paths, final_output, columns, sort_key_fn)
        print(f"🔀 Merged {n} rows → {final_output}", flush=True)
    except PermissionError:
        print(f"⚠️  {final_output} is open elsewhere — merge skipped this cycle.", flush=True)


def run_worker_pool(scraper_name, workers, shard_paths, final_output, columns, sort_key_fn,
                     popen_fn=subprocess.Popen, sleep_fn=time.sleep, ram_check_fn=free_ram_mb,
                     time_fn=time.monotonic, merge_interval_s=MERGE_INTERVAL_S,
                     max_restarts=MAX_RESTARTS_PER_WORKER, merge_fn=merge_shards):
    handles = {}
    for i in range(workers):
        wait_for_ram(check_fn=ram_check_fn, sleep_fn=sleep_fn)
        print(f"🚀 Launching worker {i} ({scraper_name}, shard {i}/{workers})...", flush=True)
        handles[i] = WorkerHandle(i, launch_worker(scraper_name, i, workers, popen_fn=popen_fn))
        if i < workers - 1:
            sleep_fn(STAGGER_S)

    last_merge = time_fn()
    try:
        while handles:
            sleep_fn(5)
            for i in list(handles.keys()):
                h = handles[i]
                code = h.popen.poll()
                result = _classify_worker_result(code, h.restarts, max_restarts)

                if result == "still_running":
                    continue
                if result == "done":
                    print(f"✅ Worker {i} finished its shard.", flush=True)
                    del handles[i]
                    continue
                if result == "give_up":
                    print(f"❌ Worker {i} crashed {h.restarts} times — giving up on this shard.", flush=True)
                    del handles[i]
                    continue

                # result == "restart"
                h.restarts += 1
                print(f"🔁 Worker {i} crashed (exit {code}) — restart {h.restarts}/{max_restarts}...", flush=True)
                sleep_fn(RESTART_BACKOFF_S)
                wait_for_ram(check_fn=ram_check_fn, sleep_fn=sleep_fn)
                handles[i] = WorkerHandle(i, launch_worker(scraper_name, i, workers, popen_fn=popen_fn))
                handles[i].restarts = h.restarts

            if time_fn() - last_merge >= merge_interval_s:
                _try_merge(shard_paths, final_output, columns, sort_key_fn, merge_fn=merge_fn)
                last_merge = time_fn()
    except KeyboardInterrupt:
        print("\n⛔ Stopping all workers...", flush=True)
        for h in handles.values():
            try:
                h.popen.terminate()
            except Exception:
                pass

    _try_merge(shard_paths, final_output, columns, sort_key_fn, merge_fn=merge_fn)
    print(f"✅ Final merge → {final_output}", flush=True)


def supervise(scraper_name, workers, output_dir=None, **kwargs):
    config = SCRAPER_CONFIGS[scraper_name]
    mod = importlib.import_module(scraper_name)
    all_localities = config["build_localities"](mod)
    sort_key_fn = config["make_sort_key_fn"](mod, all_localities)

    if output_dir is None:
        output_dir = ROOT / "output"
    output_dir = Path(output_dir)
    shard_dir = output_dir / "_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    shard_paths = [shard_dir / f"{scraper_name}_shard{i}.xlsx" for i in range(workers)]
    final_output = output_dir / f"{scraper_name}_data.xlsx"

    run_worker_pool(scraper_name, workers, shard_paths, final_output, mod.COLUMNS, sort_key_fn, **kwargs)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("scraper", choices=list(SCRAPER_CONFIGS.keys()))
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    if args.workers < 1:
        parser.error("--workers must be at least 1")

    supervise(args.scraper, args.workers)
