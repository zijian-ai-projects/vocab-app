# V1.3.5 验收记录

## 结论

**通过。** 本记录只使用当前V1.3.5冻结源的新验收进程，不把V1.3.4/V1.3.3历史数字重标为本版。
归档时间：2026-11-09T18:37:31+08:00。

- 固定158不同词（小学47 / 初中136，25重叠）共183学段项已逐词审核。小学39修改/8保留，初中64修改/72保留；89不同词至少一学段短义变化，69词全部所属学段保留。
- 小学Alice为 `n.爱丽丝（人名）`，初中为 `n.爱丽丝（女名）`；Matt、Sam等按人物段恢复名字，小学BDS为北斗卫星导航系统。完整旧新义/理由/引用见 [158词台账](<school-meanings-review-v135.md>) 和 [校订表](<../data/school_meaning_reviews.json>)。
- 其它5,302行（包括未在本次审核内的773初中词组）与冻结V1.3.4显示值及来源元数据完全相同。原四输入、全部key、词书ID/成员顺序、记忆身份和真实记录不变。
- AI逐词编辑与交叉核验，不是官方词表审计或人类专家认证；名字用法/中文译写、原gloss/编辑选择和外部短引用明确区分。所有词表仍由民间整理。归档原始审查产物保留冻结字节，其旧措辞“人工决定/校订”不表示有人类专家参与；实际审核方式以随版本校订表的 `review_method` 为准。

## 同一冻结源的完整矩阵

| 分组 | 独立进程 | 本次结果 |
|---|---:|---|
| 组件 / 数据 / 来源 / 原学校UI | 25 | 270项unittest；学校UI 299项；社区成员21项；全部通过 |
| 集成离屏 V130 / V133 / V134 / V135 | 4 | 2495项检查，0失败 |
| Windows原生 V130 / V133 / V134 / V135 | 4 | 2512项检查，0失败 |
| 启动 normal / bare-path / bad-record / stale-lock | 4 | 全部通过；实际启动日志为1.3.5 |
| Windows原生刷词小窗 | 1 | 通过 |
| 总计 | **38 / 38** | 冻结源相同，全部进程exit 0 |

新增逐词数据回归12项：158/183精确范围和真实retain/replace、原183旧义、5,302旧行、773词组、55来源、专名/缩写/普通词、学校别名及所有原字段保护、缺失/重复/标签/来源SHA拒错。原释义完整性12项和词汇量事务34项同样重跑。

V135单套：离屏 **1193** 项、Windows原生 **1198** 项；全部183真实学段项均进入运行时短义/词形、真实书目录和悬停、四个唯一同学段选项。15个重点词以真实原书游标分别进入刷词/选择题，通过实际Qt鼠标按钮回答、翻面/反馈及Lv1稳定key检查；通用测量不借用学校Alice别名。

## 资料与来源保护

- 五组测试始终使用同一套148个冻结源码、资产、55个释义来源和审核输入/产物；各组前后及最终再次校验SHA。
- 36条真实进度、窗口、备份、临时恢复、锁和启动日志路径（包括不存在的路径）前后和组间指纹完全相同。没有运行真实清空，也没有把真实记录内容复制进报告。
- 每个进程显式指定独立 `VOCABAPP_DATA_DIR`；Qt学习用 `ui_test_support.Sandbox`。stdout/stderr写工作区文件，不通过Windows受限命名管道。原生UI/启动/小窗顺序执行，避免桌面窗口互扰。
- 解释器为Windows Anaconda Python 3.8.3 / PyQt5 / Qt 5.12.x。校订生成器默认/`--check`只读，仅显式`--write`重建。

| 输入 | 原始字节SHA-256 |
|---|---|
| [bank.json](<../data/bank.json>) | `e4f6d3283349a32076c5cc3fcc875d064ff5e5cfdb2d7310e5d0515ff0d9a126` |
| [books.json](<../data/books.json>) | `99648ed217329e33df69cb05462bd1e2d8a73c57e4407510cd2f54521f15705a` |
| [phrases.json](<../data/phrases.json>) | `9b9a060f87d13bcbe0bfb081b1c0ce5e45b810272f42404e45357ee5cc81b5f9` |
| [phrase_books.json](<../data/phrase_books.json>) | `350a9a5559d02d4f15ab4dc61e0e40a1bf52ffb7c9593bff1d9b6e7037f6b1f7` |

- [校订源](<../data/school_meaning_reviews.json>) SHA-256：`1273ea1530fe305afd47b9492b1e72ab5d512ed63983aee0ed1c2fdcb46f7d88`。
- [显示覆盖](<../data/level_meanings.json>) SHA-256：`960671eb308e1afed1947267ee1276e132e14d96d2c001737627a3a4cf685a8c`。
- 完整实现及命令见 [释义覆盖层说明](<level-meanings.md>)。

## 本次Windows原生预览

- [primary-alice-brush](<validation-v135/native-preview/primary-alice-brush.png>)
- [middleschool-alice-choice](<validation-v135/native-preview/middleschool-alice-choice.png>)
- [primary-bds-brush](<validation-v135/native-preview/primary-bds-brush.png>)
- [primary-bund-choice](<validation-v135/native-preview/primary-bund-choice.png>)
- [middleschool-ruby-brush](<validation-v135/native-preview/middleschool-ruby-brush.png>)

## 归档与复核

- [机器可读验收汇总](<validation-v135/acceptance-summary.json>)、[全部冻结文件指纹](<validation-v135/frozen-source-sha256.json>)。
- [25进程组件汇总](<validation-v135/pure/summary.json>)、[四套离屏汇总](<validation-v135/ui/summary.json>)、[四套原生汇总](<validation-v135/native-ui/summary.json>)、[四启动汇总](<validation-v135/launcher/summary.json>)、[原生小窗汇总](<validation-v135/compact/summary.json>)。各目录保存本次stdout及完整Qt检查报告。
- [原始V1.3.4显示层快照](<validation-v135/audit/v135-original-level-meanings.json>)仅作5,302行相同证明，不是第二套运行词库。[范围快照](<validation-v135/audit/v135-audit-scope.json>)和两份完整审核产物同样冻结。
- [本次独立验收生成器](<validation-v135/audit/make_final_tools_v135.py>)与审核合并/台账生成脚本均归档；历史 [V1.3.4验收](<acceptance-v134.md>)保持原文。

V1.3.3已有本地commit `a50eeaa` 和注释tag `v1.3.3`；本轮V1.3.4/V1.3.5保持未提交、未打tag、未push。
