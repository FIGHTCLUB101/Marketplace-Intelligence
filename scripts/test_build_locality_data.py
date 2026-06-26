import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

import contract

ROOT = Path(__file__).resolve().parents[1]


def test_contract_js_matches_py():
    js = (ROOT / "web" / "contract.js").read_text(encoding="utf-8")
    for action, hexv in contract.GTM_COLORS.items():
        assert f"'{action}':" in js and hexv in js, f"{action} {hexv} missing from contract.js"


def test_bundle_built_and_shaped():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_locality_data.py")],
                   check=True, cwd=ROOT / "scripts")
    df = pd.read_parquet(ROOT / contract.MASTER_PARQUET)
    n_geo = int(df["lat"].notna().sum())
    js = (ROOT / "web" / "data-localities.js").read_text(encoding="utf-8")
    data = json.loads(js[js.index("["): js.rindex("]") + 1])
    assert len(data) == n_geo
    assert all("color" in r and str(r["color"]).startswith("#") for r in data)
