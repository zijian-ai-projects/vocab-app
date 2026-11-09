# -*- coding: utf-8 -*-
"""Read-only catalog/dictionary validation. Reports need explicit --output.

Historical bank-only entries are deliberately preserved after source corrections.
The community-compiled catalog is validated without any official-source audit
payload or network access.
"""
import argparse
import io
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")


def validate(data_dir=DATA):
    out, fails = [], []
    def check(ok, message):
        out.append(("  OK   " if ok else "  FAIL ") + message)
        if not ok:
            fails.append(message)
    with io.open(os.path.join(data_dir, "bank.json"), encoding="utf-8") as f:
        bank = json.load(f)
    with io.open(os.path.join(data_dir, "books.json"), encoding="utf-8") as f:
        catalog = json.load(f)
    keys = [entry["w"] for entry in bank]
    check(len(keys) >= 30000, "Dictionary has %d entries; no rounded maximum quota" % len(keys))
    check(len(set(keys)) == len(keys), "Dictionary keys are unique")
    check(keys == sorted(keys, key=lambda word: (word.casefold(), word)), "Dictionary keeps deterministic casefold/key ordering")
    check(all(entry.get("s") for entry in bank), "All entries have sourced card definitions")
    out.append("  INFO Missing IPA: %d; never fabricate pronunciation" % sum(not x.get("ipa") for x in bank))
    valid_levels = all(type(x.get("lvl")) is int and 0 <= x["lvl"] <= 14 for x in bank)
    check(valid_levels, "Difficulty levels remain integers in [0,14]")
    levels = [sum(x.get("lvl") == n for x in bank) for n in range(15)]
    check(all(levels), "All 15 difficulty levels are nonempty: %s" % levels)
    check(all(type(x.get("b")) in (int, float) and math.isfinite(x["b"]) and -3.2 <= x["b"] <= 3.2 for x in bank),
          "Difficulty b is finite and in [-3.2,3.2]")
    check(all(isinstance(x.get("pos"), list) for x in bank), "POS remains a list")
    check(catalog.get("schema") == 2, "Catalog schema remains 2")
    mains = catalog.get("mains", [])
    check(len(mains) == 8, "Eight stable catalog mains")
    bank_set, all_words, all_ids = set(keys), set(), set()
    for main in mains:
        for group in main.get("groups", []):
            union = group["union"]
            expect, seen = [], set()
            check(union["id"] not in all_ids, "Unique union ID: " + union["id"])
            all_ids.add(union["id"])
            for item in group.get("items", []):
                words = item["words"]
                check(type(item["count"]) is int and item["count"] == len(words), "Item count: " + item["id"])
                check(len(words) == len(set(words)), "Item unique keys: " + item["id"])
                check(set(words) <= bank_set, "Complete item bank coverage: " + item["id"])
                check(bool(item.get("name")), "Nonempty item name: " + item["id"])
                check(item["id"] not in all_ids, "Unique item ID: " + item["id"])
                all_ids.add(item["id"])
                all_words.update(words)
                for word in words:
                    if word not in seen:
                        seen.add(word)
                        expect.append(word)
            check(union["words"] == expect and type(union["count"]) is int and union["count"] == len(expect),
                  "Ordered first-occurrence union: " + group["id"])
            check(set(union["words"]) <= bank_set, "Complete union bank coverage: " + group["id"])
            check(bool(group.get("union_name")), "Nonempty union name: " + group["id"])
    check(all_words <= bank_set, "All books are covered; %d historical/dictionary-only keys are valid" % len(bank_set - all_words))
    return out, fails


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only check (default)")
    parser.add_argument("--data-dir", default=DATA,
                        help="Optional explicit isolated dictionary/catalog directory; profile overrides do not change the bank")
    parser.add_argument("--output", help="Explicit optional report path; never writes a default sidecar")
    args = parser.parse_args()
    try:
        out, fails = validate(os.path.abspath(args.data_dir))
    except (OSError, KeyError, TypeError, ValueError) as error:
        print("BANK CHECK FAIL: " + str(error), file=sys.stderr)
        return 1
    if args.output:
        with io.open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out + ["", "FAILS %d" % len(fails)]) + "\n")
    print("BANK CHECK: checks=%d fails=%d (read-only%s)" %
          (len(out), len(fails), "; explicit report" if args.output else ""))
    for failure in fails:
        print("FAIL: " + failure)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
