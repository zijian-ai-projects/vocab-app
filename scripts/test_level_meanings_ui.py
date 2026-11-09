# -*- coding: utf-8 -*-
"""小学/初中学段释义显示链路隔离回归（离屏 + Sandbox，不启动真实数据 app）。"""
import io
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import test_v130_ui as base
from PyQt5.QtCore import Qt

import level_meanings
import study_options
from entries import meaning as entry_meaning

PRIMARY = "fixture-primary"
PRIMARY_SMALL = "fixture-primary-small"
MIDDLE = "fixture-middle"
OTHER = "fixture-other"
PRIMARY_UNION = "fixture-primary-all"


class StageBooks(base.FrozenBooks):
    """FrozenBooks + 真实形状的主分类/分组 union/系列字段。"""

    DEFAULT = PRIMARY
    LEGACY = {}

    def __init__(self):
        self.BY_ID = {}
        keys = list(base.KEYS)
        for bid, main, group, words, is_union, series, label in (
                (PRIMARY, "primary", "primary-group", keys, False, "PEP", "小学隔离"),
                (PRIMARY_SMALL, "primary", "primary-group", keys[:1], False, "", "小学单词夹具"),
                (MIDDLE, "middleschool", "middle-group", keys, False, "PEP", "初中隔离"),
                (OTHER, "university", "other-group", keys[:2], False, "", "高中隔离"),
                (PRIMARY_UNION, "primary", "primary-group", keys, True, "", "小学并集")):
            self.BY_ID[bid] = {
                "id": bid, "name": label, "display": label, "count": len(words),
                "words": list(words), "type": "word", "kind": "fixture",
                "series": series, "is_union": is_union, "group": group,
                "main": main, "path": ["主类", group],
            }
        self.GROUPS = {}
        for gid, main, items, series in (
                ("primary-group", "primary",
                 [PRIMARY, PRIMARY_SMALL, PRIMARY_UNION], ["PEP"]),
                ("middle-group", "middleschool", [MIDDLE], ["PEP"]),
                ("other-group", "university", [OTHER], [])):
            self.GROUPS[gid] = {
                "id": gid, "name": gid, "main": main,
                "items": [self.BY_ID[bid] for bid in items],
                "union": self.BY_ID[items[0]], "series": series,
                "count": len(items),
            }
        self.MAINS = [
            {"id": "primary", "name": "小学", "groups": [self.GROUPS["primary-group"]]},
            {"id": "middleschool", "name": "初中",
             "groups": [self.GROUPS["middle-group"]]},
            {"id": "university", "name": "高中",
             "groups": [self.GROUPS["other-group"]]},
        ]

    def groups(self, main_id=None):
        if main_id is None:
            return [g for m in self.MAINS for g in m["groups"]]
        for m in self.MAINS:
            if m["id"] == main_id:
                return m["groups"]
        return []

    def get(self, bid):
        return self.BY_ID.get(bid, self.BY_ID[PRIMARY])


class LevelSuite(base.Suite):
    def __init__(self, sandbox):
        super().__init__(sandbox)
        self.books = StageBooks()

    def stage_card(self, book, mapping_path, study_mode="brush"):
        data = base.progress(book=book, cursors={book: 0},
                             orders={book: {"mode": "seq", "seed": 42}},
                             study_mode=study_mode)
        with patch.object(level_meanings, "DEFAULT_PATH", mapping_path):
            level_meanings.clear_cache()
            return self.card(data)

    def real_school_books(self):
        """Read real bank/catalog, but every Card write still stays in Sandbox."""
        real_books = base.app_main.bk
        primary_ids = [bid for bid, meta in real_books.BY_ID.items()
                       if meta.get("main") == "primary" and not meta.get("is_union")]
        middle_ids = [bid for bid, meta in real_books.BY_ID.items()
                      if meta.get("main") == "middleschool" and not meta.get("is_union")]
        w = self.card(base.progress(
            book=primary_ids[0], history=[], study_mode="choice", states={},
            orders={primary_ids[0]: {"mode": "seq", "seed": 42}},
            cursors={primary_ids[0]: 0}))
        original = deepcopy(w.bank_map)
        states_before, history_before = deepcopy(w.states), deepcopy(w.progress["history"])
        series_ids = {stage: [] for stage in level_meanings.STAGES}
        allowed = {}
        for stage in level_meanings.STAGES:
            mapping = w.level_meanings[stage]
            allowed[stage] = {value["display_s"] for value in mapping.values()}
            pool = w._level_option_pool(stage).prepare()
            expected_keys = {key for group in real_books.groups(stage)
                             for item in real_books.items(group["id"])
                             for key in real_books.words(item["id"])}
            self.check({entry["w"] for entry in pool.entries} == expected_keys == set(mapping),
                       stage + " 全学段池覆盖全部运行时成员，包括补入的词组")
            ids = [bid for bid, meta in real_books.BY_ID.items()
                   if meta.get("main") == stage]
            for group in real_books.groups(stage):
                for series in group.get("series", []):
                    sid = base.app_main.series_pseudo_id(group["id"], series)
                    ids.append(sid)
                    series_ids[stage].append(sid)
            for bid in ids:
                entries = w._book_words(bid)
                self.check(w._book_level(bid) == stage
                           and [entry["w"] for entry in entries] == w._book_word_strs(bid)
                           and all(entry is not w.bank_map[entry["w"]]
                                   and entry_meaning(entry) == mapping[entry["w"]]["display_s"]
                                   for entry in entries),
                           bid + " 学段/原成员顺序/浅拷贝/每条释义一致")
                self.check("词表由民间整理" in w._book_meta(bid).get("source_note", ""),
                           bid + " 真实/并集/系列来源提示统一")
                target = entries[0]
                try:
                    question = study_options.make_options(
                        target, w._book_level_option_pool(bid, stage), base.app_main.random)
                except ValueError:
                    question = study_options.make_options(target, pool, base.app_main.random)
                self.check(len(question["options"]) == 4
                           and all(text in allowed[stage] for text in question["options"])
                           and question["options"][question["correct"]] == entry_meaning(target),
                           bid + " 正确项与三个干扰项全来自该学段")
                w.catalog.set_book(bid, "隔离真实书检查", entries, w.states, set())
                row = w.catalog.model.rows[0]
                self.check(w.catalog.model.data(w.catalog.model.index(0, 1), Qt.DisplayRole)
                           == mapping[row["w"]]["display_s"]
                           and w.catalog.model.data(w.catalog.model.index(0, 1), Qt.ToolTipRole)
                           == base.app_main.word_caption(row) + "\n" + mapping[row["w"]]["display_s"],
                           bid + " 目录与悬停提示采用同一短释义")
        self.check("zk-phrases" in middle_ids
                   and real_books.size("zk-phrases") == 773,
                   "773词中考词组书属于初中覆盖而非通用高级释义")
        high_id = next(bid for bid, meta in real_books.BY_ID.items()
                       if meta.get("main") == "highschool" and not meta.get("is_union"))
        middle_union = next(bid for bid, meta in real_books.BY_ID.items()
                            if meta.get("main") == "middleschool" and meta.get("is_union"))
        switches = [primary_ids[0], middle_ids[0], "zk-phrases", middle_union,
                    series_ids["primary"][0], series_ids["middleschool"][0],
                    high_id, primary_ids[0]]
        for bid in switches:
            w.open_books("settings")
            w._pick_book(bid)
            w._start_learning()
            base.pump(2)
            target = w.queue[w.qi]["w"]
            stage = w._book_level(bid)
            question = w.choice_question
            self.check(w.mode == "choice"
                       and question["options"][question["correct"]] == entry_meaning(target)
                       and (stage is None or all(text in allowed[stage]
                                                 for text in question["options"])),
                       bid + " 实际选书后的卡片/四选项缓存不串学段")
            self.check((stage is not None) == bool(target.get("display_s")),
                       bid + " 高中只用通用义，小学初中自动短义")
        self.check(w.states == states_before and w.progress["history"] == history_before,
                   "真实小学/初中/高中切换不改记忆states与历史")
        self.check(w.bank_map == original
                   and not any("display_s" in entry or "level_s" in entry
                               for entry in w.bank_map.values()),
                   "全量bank/phrases逐字段未被显示层与池缓存修改")
        w.study_mode = "brush"
        w._new_session()
        current = w.queue[w.qi]["w"]
        self.check(w.mode == "front" and w.meaning.text() == entry_meaning(current),
                   "回到真实小学刷词正面短义同步")
        w._set_mode("back")
        self.check(w.meaning.text() == entry_meaning(current), "翻面短义与选择题/目录一致")


def write_json(path, data):
    with io.open(path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False)


def main():
    sb = base.Sandbox(base.app_main, "level-meanings")
    suite = LevelSuite(sb)
    path = sb.path("level_meanings.json")
    missing = sb.path("missing_level_meanings.json")
    corrupt = sb.path("corrupt_level_meanings.json")
    write_json(path, {
        "primary": {key: "甲" + key for key in base.KEYS},
        "middleschool": {key: "乙" + key for key in base.KEYS},
    })
    write_json(corrupt, "{not-json")

    with patch.dict(os.environ, {"VOCABAPP_DATA_DIR": sb.dir}):
        with sb:
            with suite.fixture_scope():
                with patch.object(level_meanings, "DEFAULT_PATH", path):
                    level_meanings.clear_cache()

                    # 1. schema / loader / entries / signature
                    top = level_meanings.load(path)
                    suite.run("loader", lambda: (
                        suite.check(top["primary"]["alpha"]["display_s"] == "甲alpha",
                                    "顶层 primary 字符串释义加载"),
                        suite.check(top["middleschool"]["alpha"]["display_s"] == "乙alpha",
                                    "顶层 middleschool 字符串释义加载"),
                        suite.check(level_meanings.stage_for_main("primary") == "primary"
                                    and level_meanings.stage_for_main("middleschool") == "middleschool"
                                    and level_meanings.stage_for_main("university") is None,
                                    "main 分类 -> 学段映射"),
                    ))
                    levels_file = sb.path("levels_schema.json")
                    write_json(levels_file, {"levels": {
                        "primary": {"alpha": {"display_s": "P", "level_s": "P2"}},
                        "middleschool": {"alpha": "M"},
                    }})
                    levels_data = level_meanings.load(levels_file)
                    suite.check(levels_data["primary"]["alpha"]["display_s"] == "P"
                                and levels_data["middleschool"]["alpha"]["display_s"] == "M",
                                "levels.primary/middleschool schema 兼容")
                    suite.check(level_meanings.load(missing) == {"primary": {}, "middleschool": {}},
                                "缺失文件安全回退")
                    suite.check(level_meanings.load(corrupt) == {"primary": {}, "middleschool": {}},
                                "损坏 JSON 安全回退")
                    suite.run("entries", lambda: (
                        suite.check(entry_meaning({"w": "x", "s": "通用", "display_s": "学段"}) == "学段",
                                    "meaning 优先 display_s"),
                        suite.check(entry_meaning({"w": "x", "s": "通用", "level_s": "学段2"}) == "学段2",
                                    "meaning 回退 level_s"),
                        suite.check(entry_meaning({"w": "x", "s": "通用", "display_s": " ", "level_s": ""}) == "通用",
                                    "异常空覆盖回退 s/raw"),
                        suite.check(entry_meaning({"w": "x", "raw": "原义", "display_s": None}) == "原义",
                                    "非法类型覆盖回退 raw"),
                    ))
                    sig_a = study_options._signature({"w": "x", "s": "s", "raw": "r",
                                                      "display_s": "A"})
                    sig_b = study_options._signature({"w": "x", "s": "s", "raw": "r",
                                                      "display_s": "B"})
                    suite.check(sig_a != sig_b and sig_a[-2:] == ("A", None),
                                "OptionPool 签名包含覆盖字段")

                    # 2. main 分类 / union / series / 其他类别
                    w = suite.stage_card(PRIMARY, path)
                    suite.current = "stage-detect"
                    suite.check(w._book_level(PRIMARY) == "primary", "真实形状词书 -> primary")
                    suite.check(w._book_level(PRIMARY_UNION) == "primary", "分组 union -> primary")
                    suite.check(w._book_level(MIDDLE) == "middleschool", "初中学段词书")
                    suite.check(w._book_level("series:primary-group:PEP") == "primary",
                                "系列伪 ID -> 分组 main")
                    suite.check(w._book_level(OTHER) is None, "其他分类返回 None")
                    suite.current = "no-mutate"
                    suite.check("display_s" not in w.bank_map["alpha"]
                                and "level_s" not in w.bank_map["alpha"],
                                "bank_map 原始词条不被修改")
                    suite.check(w.book_words[0] is not w.bank_map[w.book_words[0]["w"]],
                                "_book_words 返回浅拷贝")
                    suite.check(w.book_words[0].get("display_s") == "甲alpha",
                                "_book_words 附加学段释义")

                    # 3. front/back/catalog 显示（在切到初中卡前完成）
                    p_text = entry_meaning(w.book_words[0])
                    p_key = w.book_words[0]["w"]
                    suite.check(w.mode in ("front", "back") and w.meaning.text() == p_text,
                                "刷词卡释义显示同学段释义")
                    w.open_catalog(PRIMARY, "settings")
                    base.pump()
                    row = next((i for i, item in enumerate(w.catalog.model.rows)
                                if item["w"] == "alpha"), -1)
                    suite.check(row >= 0
                                and w.catalog.model.data(
                                    w.catalog.model.index(row, 1), Qt.DisplayRole) == p_text,
                                "catalog 释义列显示同学段释义")
                    suite.check("display_s" not in w.bank_map["alpha"],
                                "catalog 不污染通用 bank")

                    # 4. 同 key 跨学段、学习 state key 不变
                    m = suite.stage_card(MIDDLE, path)
                    m_text = entry_meaning(m.book_words[0])
                    suite.check(p_key == m.book_words[0]["w"] == "alpha"
                                and p_text != m_text
                                and "甲" in p_text and "乙" in m_text,
                                "同 key 小学/初中显示不同、稳定 w 不变")
                    suite.check(set(m.states) == set(),
                                "切换学段学习状态未被重写")

                    # 5. choice 四个选项均来自同学段池，切书隔离
                    pc = suite.stage_card(PRIMARY, path, study_mode="choice")
                    primary_pool = pc._level_option_pool("primary")
                    primary_pool.prepare()
                    p_allowed = {choice.text for choice in primary_pool._choices}
                    p_opts = list(pc.choice_question["options"])
                    suite.check(p_opts and all(opt in p_allowed for opt in p_opts),
                                "小学选择题 A-D 全部小学学段释义")
                    small = suite.stage_card(PRIMARY_SMALL, path, study_mode="choice")
                    small_opts = list(small.choice_question["options"])
                    suite.check(len(small_opts) == 4 and all(opt in p_allowed for opt in small_opts),
                                "当前书池不足时仅回退同一小学主分类池")
                    mc = suite.stage_card(MIDDLE, path, study_mode="choice")
                    middle_pool = mc._level_option_pool("middleschool")
                    middle_pool.prepare()
                    m_allowed = {choice.text for choice in middle_pool._choices}
                    m_opts = list(mc.choice_question["options"])
                    suite.check(m_opts and all(opt in m_allowed for opt in m_opts),
                                "初中选择题 A-D 全部初中学段释义")
                    suite.check(not (set(p_opts) & m_allowed),
                                "切书池按学段独立，无跨学段选项")
                    suite.check(pc._level_option_pool("primary")
                                is not mc._level_option_pool("middleschool"),
                                "primary/middleschool 池对象隔离")

                    # 6. 缺失/损坏默认文件时 UI 安全回退
                    with patch.object(level_meanings, "DEFAULT_PATH", missing):
                        level_meanings.clear_cache()
                        miss = suite.card(base.progress(
                            book=PRIMARY, cursors={PRIMARY: 0},
                            orders={PRIMARY: {"mode": "seq", "seed": 42}}))
                        expected_missing = entry_meaning(miss.bank_map["alpha"])
                        suite.check(miss.book_words[0].get("display_s") is None
                                    and miss.meaning.text() == expected_missing,
                                    "缺失默认学段文件安全回退通用释义：got=%r display=%r expect=%r" %
                                    (miss.meaning.text(),
                                     miss.book_words[0].get("display_s"),
                                     expected_missing))
                    with patch.object(level_meanings, "DEFAULT_PATH", corrupt):
                        level_meanings.clear_cache()
                        bad = suite.card(base.progress(
                            book=PRIMARY, cursors={PRIMARY: 0},
                            orders={PRIMARY: {"mode": "seq", "seed": 42}}))
                        suite.check(bad.book_words[0].get("display_s") is None,
                                    "损坏默认学段文件安全回退")
                    with patch.object(level_meanings, "DEFAULT_PATH", path):
                        level_meanings.clear_cache()

                    suite.check(sb.verify_real(), "真实 progress/window/bak/tmp 未变")
                    suite.out.append("LEVEL_MEANINGS_CHECKS %d; FAILS %d" %
                                     (suite.checks, len(suite.fails)))
            level_meanings.clear_cache()
            suite.run("real-school-books", suite.real_school_books, fake=False)
            suite.check(sb.verify_real(), "全量真实学段回归后个人资料未变")
    code = sb.finish(suite.out, suite.fails, "test_level_meanings_ui.txt")
    print("LEVEL MEANINGS CHECKS", suite.checks, "FAILS", len(suite.fails) + len(sb.errors))
    return code


if __name__ == "__main__":
    sys.exit(main())
