"""
Mapping validation tests.

Runs against the live API (default http://localhost:8000).
Usage:
    python test_mappings.py [--base-url http://localhost:8000]
"""

import argparse
import json
import sys
import urllib.request

passed = 0
failed = 0
BASE = "http://localhost:8000"


def get(path: str):
    url = f"{BASE}{path}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        msg = f" ({detail})" if detail else ""
        print(f"  FAIL  {name}{msg}")


def mapping_ids(control_id: str, framework_id: int) -> set[str]:
    data = get(f"/api/mappings/{control_id}?framework_id={framework_id}")
    return {m["control_id"] for m in data.get("mappings", [])}


def test_framework_counts():
    print("\n--- Framework counts ---")
    fws = get("/api/frameworks")
    fw_map = {f["short_name"]: f for f in fws}
    check("3 frameworks exist", len(fws) == 3, f"got {len(fws)}")
    check("ISO27001 exists", "ISO27001" in fw_map)
    check("C5 exists", "C5" in fw_map)
    check("BSI exists", "BSI" in fw_map)
    check("C5 has 121 controls", fw_map["C5"]["control_count"] == 121,
          f"got {fw_map.get('C5', {}).get('control_count')}")
    iso_count = fw_map["ISO27001"]["control_count"]
    check("ISO27001 has 93+ Annex A controls", iso_count >= 93,
          f"got {iso_count}")
    return fw_map


def test_search_exact_match():
    print("\n--- Search exact match ordering ---")
    results = get("/api/controls?q=A.5.1")
    check("Search A.5.1 returns results", len(results) > 0)
    if results:
        check("Exact match A.5.1 is first result",
              results[0]["control_id"] == "A.5.1",
              f"first was {results[0]['control_id']}")


def test_c5_to_iso_mappings(fw_map: dict):
    """Verify specific C5 controls map to the correct ISO controls."""
    print("\n--- C5-to-ISO mapping correctness ---")
    c5_id = fw_map["C5"]["id"]

    expected = {
        "OIS-01": {"4.1", "10.2"},
        "IDM-01": {"A.5.15", "A.8.3", "A.8.5"},
        "CRY-01": {"A.5.14", "A.5.31", "A.8.24"},
        "SIM-01": {"A.5.24", "A.5.25", "A.5.26", "A.5.27", "A.6.8"},
    }

    for ctrl_id, expected_iso in expected.items():
        actual = mapping_ids(ctrl_id, c5_id)
        check(f"{ctrl_id} -> {sorted(expected_iso)}",
              actual == expected_iso,
              f"got {sorted(actual)}")


def test_reverse_mappings(fw_map: dict):
    """Verify ISO controls reverse-map to the correct C5 controls."""
    print("\n--- ISO reverse-mapping to C5 ---")
    iso_id = fw_map["ISO27001"]["id"]

    actual = mapping_ids("A.5.1", iso_id)
    expected_c5 = {"OIS-02", "SP-01", "SP-02"}
    check("A.5.1 has C5 mappings (OIS-02, SP-01, SP-02)",
          expected_c5.issubset(actual),
          f"got {sorted(actual)}")
    check("A.5.1 has BSI mappings",
          any(m.startswith("ISMS") or m.startswith("ORP") for m in actual),
          f"got {sorted(actual)}")

    actual_a8_24 = mapping_ids("A.8.24", iso_id)
    check("A.8.24 has C5 mappings", len(actual_a8_24) > 0,
          f"got {len(actual_a8_24)} mappings")


def test_unmapped_controls(fw_map: dict):
    """Verify controls that should have no mapping indeed have none."""
    print("\n--- Unmapped controls ---")
    c5_id = fw_map["C5"]["id"]

    unmapped_expected = ["PSS-01", "INQ-01", "INQ-02", "SP-03"]
    for ctrl_id in unmapped_expected:
        actual = mapping_ids(ctrl_id, c5_id)
        check(f"{ctrl_id} has 0 mappings", len(actual) == 0,
              f"got {len(actual)}")


def test_coverage(fw_map: dict):
    """Verify coverage analysis endpoint."""
    print("\n--- Coverage analysis ---")
    c5_id = fw_map["C5"]["id"]
    iso_id = fw_map["ISO27001"]["id"]

    cov = get(f"/api/coverage?source={c5_id}&target={iso_id}")
    check("Coverage total = 121", cov["total_source_controls"] == 121,
          f"got {cov['total_source_controls']}")
    check("Mapped >= 90", cov["mapped_controls"] >= 90,
          f"got {cov['mapped_controls']}")
    check("Coverage >= 75%", cov["coverage_percentage"] >= 75.0,
          f"got {cov['coverage_percentage']}%")
    check("Unmapped list populated", len(cov["unmapped_control_ids"]) > 0)
    check("Gap controls list populated", len(cov["gap_controls"]) > 0)


def test_clause_titles(fw_map: dict):
    """Verify ISO clause controls have real titles (not placeholders)."""
    print("\n--- ISO clause titles ---")
    results = get("/api/controls?q=4.1&framework_id=" + str(fw_map["ISO27001"]["id"]))
    clause_41 = [r for r in results if r["control_id"] == "4.1"]
    if clause_41:
        title = clause_41[0]["title"]
        check("Clause 4.1 has real title",
              title != "ISO 4.1" and "organization" in title.lower(),
              f"title is '{title}'")
    else:
        check("Clause 4.1 exists", False, "not found")


def main():
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    BASE = args.base_url.rstrip("/")

    print(f"Testing against {BASE}")

    try:
        fw_map = test_framework_counts()
        test_search_exact_match()
        test_c5_to_iso_mappings(fw_map)
        test_reverse_mappings(fw_map)
        test_unmapped_controls(fw_map)
        test_coverage(fw_map)
        test_clause_titles(fw_map)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(2)

    print(f"\n{'='*40}")
    print(f"  {passed} passed, {failed} failed")
    print(f"{'='*40}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
