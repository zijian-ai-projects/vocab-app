# -*- coding: utf-8 -*-
"""Derive separate V135 acceptance tools, preserving all historical V134 files."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
runner = (HERE / 'run_final_regression_v134.py').read_text(encoding='utf-8')
runner = runner.replace('V1.3.4最终验收', 'V1.3.5最终验收')
runner = runner.replace('final-v134-', 'final-v135-').replace('validate_final_v134.py', 'validate_final_v135.py')
runner = runner.replace('"version": "1.3.4"', '"version": "1.3.5"')
runner = runner.replace('    ("level-meanings", "test_level_meanings.py", []),',
                        '    ("level-meanings", "test_level_meanings.py", []),\n    ("school-reviews", "test_school_meaning_reviews.py", []),')
runner = runner.replace('            ("v134-offscreen", "test_v134_ui.py", [])],',
                        '            ("v134-offscreen", "test_v134_ui.py", []),\n           ("v135-offscreen", "test_v135_ui.py", [])],')
# Existing template spacing is 11 spaces rather than 12 before v134-offscreen.
if '("v135-offscreen"' not in runner:
    runner = runner.replace('           ("v134-offscreen", "test_v134_ui.py", [])],',
                            '           ("v134-offscreen", "test_v134_ui.py", []),\n           ("v135-offscreen", "test_v135_ui.py", [])],')
runner = runner.replace('                  ("v134-native", "test_v134_ui.py", ["--native"])],',
                        '                  ("v134-native", "test_v134_ui.py", ["--native"]),\n                  ("v135-native", "test_v135_ui.py", ["--native"])],')
runner = runner.replace('130|133|134', '130|133|134|135')
runner = runner.replace('"level-meanings.md", Path(__file__).resolve(),',
                        '"level-meanings.md", ROOT / "docs" / "school-meanings-review-v135.md", Path(__file__).resolve(),')
runner = runner.replace('    return sorted(set(paths))', '''    paths.extend(TEST_ROOT / name for name in (
        "v135-audit-scope.json", "v135-audit-primary-input.json", "v135-audit-middleschool-input.json",
        "v135-primary-review.json", "v135-middle-review.json", "v135-original-level-meanings.json",
        "freeze_scope_v135.py", "build_primary_review_v135.py", "merge_review_v135.py",
        "build_review_ledger_v135.py", "make_final_tools_v135.py"))
    return sorted(set(paths))''')
assert '("school-reviews"' in runner and '("v135-offscreen"' in runner and '("v135-native"' in runner
assert '("v134-offscreen"' in runner and '("v134-native"' in runner
assert '130|133|134|135' in runner

validator = (HERE / 'validate_final_v134.py').read_text(encoding='utf-8')
validator = validator.replace('V134', 'V135').replace('v134', 'v135').replace('1.3.4', '1.3.5')
validator = validator.replace('{"pure": 24, "ui": 3, "native-ui": 3, "launcher": 4, "compact": 1}',
                              '{"pure": 25, "ui": 4, "native-ui": 4, "launcher": 4, "compact": 1}')
validator = validator.replace('130|133|134', '130|133|134|135')
validator = validator.replace('{"130", "133", "134"}', '{"130", "133", "134", "135"}')
validator = validator.replace('"community-books", "windowing",', '"community-books", "school-reviews", "windowing",')
validator = validator.replace('result = {', '''root = TEST.parent / "vocab-app"
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
result = {''')
validator = validator.replace('    "scope_note": ', '''    "review_source_sha256": digest(root / "data" / "school_meaning_reviews.json"),
    "level_meanings_sha256": digest(root / "data" / "level_meanings.json"),
    "wordwise_review": {"unique_words": 158, "stage_items": 183, "stage_counts": {"primary": 47, "middleschool": 136},
                        "changed_unique_words": 89, "retained_unique_words": 69,
                        "replace_stage_items": 103, "retain_stage_items": 80,
                        "unchanged_out_of_scope_rows": unchanged, "unchanged_unreviewed_phrases": 773,
                        "source_inputs": len(current["sources"]), "review_method": review["review_method"]},
    "reviewed_word_ui_checks": {
        group: next(item["ui_checks"] for item in by_group[group][0]["results"] if item["name"].startswith("v135-"))
        for group in ("ui", "native-ui")},
    "scope_note": ''')
validator = validator.replace('School meanings are source-backed display overlays, not new keys or dictionary replacements.',
                              'Exactly 158 words / 183 stage items received AI-assisted editorial review; other 5302 rows including 773 phrases are unchanged. School meanings are traceable display overlays, not new keys, official-list audits, expert certification or dictionary replacements.')
assert '"pure": 25' in validator and '"135"' in validator and 'unchanged == 5302' in validator
for name, text in [('run_final_regression_v135.py', runner), ('validate_final_v135.py', validator)]:
    output = HERE / name
    assert not output.exists(), 'Do not overwrite unread acceptance tool: ' + name
    output.write_text(text, encoding='utf-8')
    print('V135_FINAL_TOOL_CREATED', name)
