"""The published main.py and dcf_model.py are the code QuantConnect re-ran.

README.md and docs/data-checks.md state that the two files in the repository root are the ones the
refactored re-run (backtest 4dbfbc74cea08eaceca427b01447a19d) executed, and that this re-run
reproduced every order and trade of the recorded base run. QuantConnect stored the code of that
backtest, and results/raw/rerun__dcf_base.json.gz holds it, with one docstring paragraph rewritten
to leave out the names of the other 2024 team members. results/provenance/code_hashes.json records
the SHA-256 of every code file as it ran on QuantConnect and as published.

These tests keep the statements true: any edit to either file, even to a comment or a docstring,
fails them, and so does a provenance record that does not match the published code.
"""

import csv
import gzip
import hashlib
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results"
RAW = RESULTS / "raw"
RERUN = RAW / "rerun__dcf_base.json.gz"
CODE_HASHES = RESULTS / "provenance" / "code_hashes.json"
REPO_CODE = ["main.py", "dcf_model.py"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((RAW / "MANIFEST.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw_code(manifest) -> dict[str, dict[str, str]]:
    """The code stored with every raw export that has any, by export key, each export checked
    against its SHA-256 in the manifest."""
    code = {}
    for name, entry in manifest["files"].items():
        data = gzip.decompress((RAW / name).read_bytes())
        assert sha256(data) == entry["sha256"], f"{name} does not match results/raw/MANIFEST.json"
        if name == "charts.json.gz":
            continue
        export = json.loads(data)
        if isinstance(export, dict) and export.get("code"):
            code[name.removesuffix(".json.gz")] = export["code"]
    return code


@pytest.fixture(scope="module")
def code_hashes(manifest) -> dict:
    entry = manifest["provenance"]["provenance/code_hashes.json"]
    data = CODE_HASHES.read_bytes().replace(b"\r\n", b"\n")
    assert sha256(data) == entry["sha256"], (
        "results/provenance/code_hashes.json does not match its SHA-256 in MANIFEST.json")
    return json.loads(data)


@pytest.fixture(scope="module")
def stored_code(raw_code) -> dict:
    if not RERUN.exists():
        pytest.skip("results/raw/rerun__dcf_base.json.gz is not present")
    return raw_code["rerun__dcf_base"]


@pytest.mark.parametrize("name", REPO_CODE)
def test_published_file_is_byte_identical_to_the_re_run_code(stored_code, name):
    assert name in stored_code, f"the re-run export holds no {name}"
    published = (REPO / name).read_bytes()
    assert published == stored_code[name].encode("utf-8"), (
        f"{name} differs from the published copy of the file QuantConnect ran in backtest "
        f"4dbfbc74...; the README's statement that the published code is the code that re-ran "
        f"no longer holds")


@pytest.mark.parametrize("name", REPO_CODE)
def test_repository_code_has_a_recorded_as_run_hash(code_hashes, name):
    entry = code_hashes["rerun__dcf_base"][name]
    assert entry["published"] == sha256((REPO / name).read_bytes())
    # The as-run file differs from the published one in the rewritten docstring paragraph only;
    # its hash is recorded so the file QuantConnect ran can still be identified.
    assert entry["names_removed"] is True
    assert entry["as_run"] != entry["published"]
    assert re.fullmatch(r"[0-9a-f]{64}", entry["as_run"])


def test_published_hashes_match_the_code_in_results_raw(raw_code, code_hashes):
    assert set(raw_code) <= set(code_hashes), "an export with code has no provenance entry"
    for key, files in raw_code.items():
        assert set(code_hashes[key]) == set(files), key
        for name, text in files.items():
            entry = code_hashes[key][name]
            assert entry["published"] == sha256(text.encode("utf-8")), f"{key}/{name}"
            assert (entry["as_run"] != entry["published"]) == entry["names_removed"], f"{key}/{name}"


def test_runs_csv_carries_both_hashes(raw_code, code_hashes):
    with (RESULTS / "runs.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows and "code_sha256" not in rows[0]
    for cells in rows:
        key = cells["key"]
        assert cells["code_sha256_as_run"] == code_hashes[key]["main.py"]["as_run"], key
        assert cells["code_sha256_published"] == sha256(raw_code[key]["main.py"].encode("utf-8")), key


def test_derived_code_copies_are_the_published_code(raw_code):
    copies = {
        "prototype_2023/code/main.py": ("dcf__prototype_2023", "main.py"),
        "reference/basket_2023/code/main.py": ("audit__basket_2023", "main.py"),
        "checks/data/code/probe_main.py": ("probe2__2012", "main.py"),
        "checks/data/code/cap_probe_main.py": ("capprobe2__2019", "main.py"),
    }
    assert {p.relative_to(RESULTS).as_posix() for p in RESULTS.glob("**/code/*.py")} == set(copies)
    for rel, (key, name) in copies.items():
        on_disk = (RESULTS / rel).read_bytes().replace(b"\r\n", b"\n")
        assert on_disk == raw_code[key][name].encode("utf-8"), rel


def test_received_prototype_code_is_the_code_its_final_backtest_ran(raw_code, code_hashes):
    received = (REPO / "received" / "main.py").read_bytes().replace(b"\r\n", b"\n")
    assert received == raw_code["dcf__prototype_2023"]["main.py"].encode("utf-8")
    assert code_hashes["dcf__prototype_2023"]["main.py"]["as_run"] == sha256(received)
