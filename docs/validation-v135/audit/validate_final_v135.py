# -*- coding: utf-8 -*-
"""Combine fresh V135 final groups without overwriting historical acceptance.

Usage: python -B .vocab-ui-tests/validate_final_v135.py --groups <five final-v135 directories>
Reads protected-file hashes only; never writes user data, source, lock or logs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re

TEST = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--groups", nargs=5, required=True)
parser.add_argument("--output", default=str(TEST / "v135-final-acceptance.json"))
args = parser.parse_args()


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


paths = [(Path(value) if Path(value).is_absolute() else TEST / value).resolve()
         for value in args.groups]
assert len(set(paths)) == 5, "duplicate final group directories"
for path in paths:
    assert path.parent == TEST and path.name.startswith("final-v135-"), "not a fresh V135 group"
summaries = [json.loads((path / "summary.json").read_text(encoding="utf-8")) for path in paths]
by_group = {summary["group"]: (summary, path) for summary, path in zip(summaries, paths)}
assert set(by_group) == {"pure", "ui", "native-ui", "launcher", "compact"}
expected_processes = {"pure": 25, "ui": 4, "native-ui": 4, "launcher": 4, "compact": 1}
core = by_group["pure"][0]["core_hashes"]
protected = None
counts = {}
for group, (summary, path) in by_group.items():
    assert summary["version"] == "1.3.5"
    assert summary["core_hashes"] == core, "different frozen code/resources across groups: " + group
    assert summary["frozen_core_unchanged"] and summary["real_records_unchanged"], group
    assert summary["changed_paths"] == [], group
    assert len(summary["results"]) == expected_processes[group], "incomplete process coverage: " + group
    assert all(item["exit"] == 0 for item in summary["results"]), "failed subprocess: " + group
    before = json.loads((path / "records-before.json").read_text(encoding="utf-8"))
    after = json.loads((path / "records-after.json").read_text(encoding="utf-8"))
    assert before == after and len(before) == summary["records_protected"] and len(before) >= 36
    if protected is None:
        protected = before
    assert before == protected, "protected files changed between final groups: " + group
    if group in ("ui", "native-ui"):
        total = 0
        versions = set()
        for item in summary["results"]:
            text = Path(item["report"]).read_text(encoding="utf-8", errors="replace")
            found = re.search(r"V(130|133|134|135) CHECKS (\d+) FAILS (\d+)", text)
            assert found and found.group(3) == "0", item["name"]
            checks = int(found.group(2))
            assert checks == item["ui_checks"] and checks > 0
            versions.add(found.group(1))
            total += checks
        assert versions == {"130", "133", "134", "135"}, "missing integrated regression version"
        counts[group] = total
for filename, expected in core.items():
    assert digest(Path(filename)) == expected, "source changed after final tests: " + filename
for filename, expected in protected.items():
    path = Path(filename)
    current = digest(path) if path.is_file() else None
    assert current == expected, "protected file changed after final tests: " + filename
required = {"bank", "level-meanings-build", "level-meanings", "level-meanings-ui",
            "community-books", "school-reviews", "windowing",
            "dock-animation", "theme", "catalog", "pronunciation"}
assert required <= {item["name"] for item in by_group["pure"][0]["results"]}
root = TEST.parent / "vocab-app"
review = json.loads((root / "data" / "school_meaning_reviews.json").read_text(encoding="utf-8"))
current = json.loads((root / "data" / "level_meanings.json").read_text(encoding="utf-8"))
old_path = TEST / "v135-original-level-meanings.json"
assert digest(old_path) == review["scope"]["origin_overlay_sha256"]
old = json.loads(old_path.read_text(encoding="utf-8"))
assert review["scope"]["unique_words"] == len(review["entries"]) == 158
assert review["scope"]["stage_items"] == 183
reviews = {stage: {item["w"]: item["levels"][stage] for item in review["entries"] if stage in item["levels"]}
           for stage in ("primary", "middleschool")}
assert {stage: len(values) for stage, values in reviews.items()} == {"primary": 47, "middleschool": 136}
assert len(set(reviews["primary"]) & set(reviews["middleschool"])) == 25
unchanged = 0
for stage, rows in current["levels"].items():
    assert set(rows) == set(old["levels"][stage])
    for word, row in rows.items():
        if word not in reviews[stage]:
            assert row == old["levels"][stage][word], "out-of-scope change: " + stage + "/" + word
            unchanged += 1
        else:
            reviewed = reviews[stage][word]
            assert reviewed["old_meaning"] == old["levels"][stage][word]["meaning"]
            assert row["meaning"] == reviewed["meaning"]
            assert row["provenance"]["rule"] == "reviewed_school_meaning_v135"
            assert reviewed["action"] == ("retain" if reviewed["old_meaning"] == reviewed["meaning"] else "replace")
assert unchanged == 5302
phrases = json.loads((root / "data" / "phrase_books.json").read_text(encoding="utf-8"))
phrase_book = next(row for row in phrases["items"] if row["id"] == "zk-phrases")
assert len(phrase_book["words"]) == 773 and set(phrase_book["words"]).isdisjoint(reviews["middleschool"])
for word in phrase_book["words"]:
    assert current["levels"]["middleschool"][word] == old["levels"]["middleschool"][word]
for name, expected in review["scope"]["original_inputs_raw_sha256"].items():
    assert digest(root / "data" / name) == expected
for stage, expected in review["scope"]["completed_review_sha256"].items():
    filename = "v135-primary-review.json" if stage == "primary" else "v135-middle-review.json"
    assert digest(TEST / filename) == expected
assert review["summary"] == {
    "stage_decisions": {"primary": {"replace": 39, "retain": 8}, "middleschool": {"replace": 64, "retain": 72}},
    "replace_stage_items": 103, "retain_stage_items": 80, "changed_unique_words": 89, "retained_unique_words": 69}
result = {
    "version": "1.3.5", "all_passed": True,
    "successful_processes": sum(len(summary["results"]) for summary in summaries),
    "component_processes": len(by_group["pure"][0]["results"]),
    "unittest_cases": sum(item["unit_tests"] or 0 for item in by_group["pure"][0]["results"]),
    "offscreen_ui_checks": counts["ui"], "native_ui_checks": counts["native-ui"],
    "launcher_scenarios": len(by_group["launcher"][0]["results"]), "compact_native_passed": True,
    "protected_real_paths": len(protected), "real_records_still_unchanged": True,
    "same_frozen_source_across_all_groups": True, "source_still_unchanged": True,
    "source_and_provenance_files_frozen": len(core),
    "community_wordlists_preserved": True,
    "school_meanings": {
        stage: stats["meanings"] for stage, stats in json.loads(
            (TEST.parent / "vocab-app" / "data" / "level_meanings.json").read_text(encoding="utf-8"))["stats"].items()
    },
    "school_ui_checks": next(item["ui_checks"] for item in by_group["pure"][0]["results"]
                             if item["name"] == "level-meanings-ui"),
    "groups": {group: path.name for group, (_, path) in by_group.items()},
    "review_source_sha256": digest(root / "data" / "school_meaning_reviews.json"),
    "level_meanings_sha256": digest(root / "data" / "level_meanings.json"),
    "wordwise_review": {"unique_words": 158, "stage_items": 183, "stage_counts": {"primary": 47, "middleschool": 136},
                        "changed_unique_words": 89, "retained_unique_words": 69,
                        "replace_stage_items": 103, "retain_stage_items": 80,
                        "unchanged_out_of_scope_rows": unchanged, "unchanged_unreviewed_phrases": 773,
                        "source_inputs": len(current["sources"]), "review_method": review["review_method"]},
    "reviewed_word_ui_checks": {
        group: next(item["ui_checks"] for item in by_group[group][0]["results"] if item["name"].startswith("v135-"))
        for group in ("ui", "native-ui")},
    "scope_note": "All word and phrase books are community compilations. V1.3.3 bank, members and order are preserved; no official-list audit was performed. Exactly 158 words / 183 stage items received AI-assisted editorial review; other 5302 rows including 773 phrases are unchanged. School meanings are traceable display overlays, not new keys, official-list audits, expert certification or dictionary replacements.",
}
output = Path(args.output).resolve()
assert output.parent == TEST and output.name.startswith("v135-final-acceptance"), "unexpected output target"
assert not output.exists(), "do not overwrite an existing acceptance report"
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
print("REPORT", output)
