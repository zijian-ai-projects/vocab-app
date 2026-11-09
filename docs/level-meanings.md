# 小学 / 初中释义覆盖层

V1.3.5 保留 [通用词库](<../data/bank.json>) 的唯一稳定词条及通用释义；[level_meanings.json](<../data/level_meanings.json>) 只提供小学/初中**显示覆盖**，不复制原库、不改 `w` 或跨书记忆：

- `main=primary` 的真实词书、分组并集和教材系列读取 `primary`；`main=middleschool` 读取 `middleschool`，包含中考词组书。
- 卡片正反面、目录与悬停提示、学习选择题正确项及三个干扰项均来自同一学段；界面不显示难度标签。
- 高中及以上、通用词汇量测量沿用原通用义。学校 `display_w`（如 `Alice` / `the Bund`）只是展示，不能产生新记忆 key，也不会泄漏到通用测量；原有非学校展示别名仍兼容。
- 缺失或损坏覆盖文件时安全回退通用义。原音标、词性字段、频次、难度、记忆等级、到期时间、历史及随机 seed 均不变；校订短义中的词性是显示内容，不改原 bank 字段。

| 学段 | 真实书（不含派生并集/系列） | 实际唯一成员 | 显示覆盖 |
|---|---:|---:|---:|
| 小学 | 28 | 1,478 | 1,478 / 1,478 |
| 初中 | 22（含中考词组书） | 4,007 | 4,007 / 4,007 |

覆盖率表示运行时无漏项，**不等于全部成员已完成语义审核**。中考词组书的773条仍沿用原显示值；不属于本次158词逐词审核。

## V1.3.5：固定158词逐词校订

原V1.3.4中，`general_first_sense_fallback` 的普通单词构成固定审核池：小学47项、初中136项，25个词跨学段重叠，共 **158个不同稳定key / 183学段项**。这不是“158个已证明错误”。

逐项核对原义、原词书成员位置和邻词、本地gloss、必要的补充材料后，将结果保存为随版本携带的 [校订表](<../data/school_meaning_reviews.json>) 和 [完整158词对照台账](<school-meanings-review-v135.md>)：

| 学段 | 审核项 | 修改短义（replace） | 原短义保留（retain） |
|---|---:|---:|---:|
| 小学 | 47 | 39 | 8 |
| 初中 | 136 | 64 | 72 |
| 学段项合计 | 183 | 103 | 80 |

按不同稳定词计：89词至少一个学段短义变化，69词在全部所属学段保留原短义。`replace`也包括补词性/姓名身份、修复残缺或过窄词义，不代表每条旧译全错。显示大小写可单独规范，因此 `retain`不一定没有 `display_w`。

- `Alice / Matt / Sam / John / Ruby` 等按具体词书的人物段取人名，不再套用接口、暗淡、账号管理器、厕所或红宝石普通义。
- 小学 `BDS` 由六上导航材料与北斗系统介绍确认“北斗卫星导航系统”，不是装帧缩写；`er`为思索时的“呃”，`Ms`为女士称谓。
- `app / word / Thanksgiving / X-ray / am` 等逐项修复适龄常用义；`Disneyland / Sydney / Taipei / RSVP / north` 等合适原义保留，不为凑数改译。
- 25个共享词的人名/地名译写一致；人名/男名/女名括注、`am / Ms / north / DVD`的说明或义组可按学段保留。
- 仅覆盖这183项；与冻结V1.3.4显示层比较，其余 **5,302行（含773词组）值和来源元数据完全相同**。原34,963 bank条目、词书ID、成员和顺序不变。

审核由两个限定范围的AI审查与Lead逐词合并/交叉核验完成，不是人类语言专家、出版社或官方词表认证。连续人物段可支持名字用法；没有完整人物课文时不推断具体角色或性别。缺失的中文译写、异译选择及补词性明确标记为编辑校订，不冒称历史源文字。

## 来源边界与可追溯性

所有单词/词组书仍统一注明**词表由民间整理**。学校释义有三类来源，合计55个已散列本地输入：

1. [逐词校订表](<../data/school_meaning_reviews.json>)：固定158词，包含每学段旧义、新义、retain/replace、类别、原因、显示词形、上下文书籍和短引用。原bank/邻词、历史gloss、外部词典/教材片段、编辑译写各自注明边界；37个实际采用的初中历史gloss对象已连同原路径、原始SHA和行范围嵌入，无需ignored目录。
2. [学校gloss快照](<../data/school_gloss/>)：49份既有民间本地墨墨/书籍导出原文；[索引](<../data/school_gloss/source-index.json>)保留历史路径与原始字节SHA。
3. [通用bank](<../data/bank.json>)、[真实词组](<../data/phrases.json>)及[词书](<../data/books.json>)/[词组书](<../data/phrase_books.json>)：未校订项沿用原片段选择与首义回退。

通用bank是历史混合数据：有道简明释义、ECDICT或词书gloss等，不能声称全部来自有道。输入SHA先将CRLF归一为LF以兼容checkout；历史raw SHA保留作引用元数据。每条输出记录`source / rule`；校订项使用 `reviewed_school_meaning_v135` 并直接指向已散列校订表，而非虚构旧源片段。

外部教材、字典和机构介绍仅核实本词含义，**不恢复官方词表完整性审计**。台账不把不可访问页面当证据，也不凭来源名称认定官方成员。

## 确定性规则与兼容

- 显式校订表优先；生成器强制原47/136集合指纹、158/183计数、四原输入归一化SHA、稳定key、实际书籍归属、已审状态、词性、中文长度/组数和证据字段。
- 校订名字允许明确“人名/姓氏”身份，但只能用于已审姓名类别；专业/俚语标签和未校订源的严格过滤仍保留。
- 未在校订表中的词不变：按本学段gloss及原词性选无专业/俚语标签的短义，或回退通用首义；小学最多32字符/一义组，初中最多58字符/两义组。
- V1.3.4的 `ruler / class / bear / can / rice` 等复核片段selector、初中 `present / plant / letter / mind / club / paper` 的已核实第二组、`china / march / may / miss` 的大小写折叠选择保持不变；只取已散列源中存在的文字，不凭selector写新翻译。
- 不按数量补词，不更换 [原民间词书](<../data/books.json>) 成员或顺序。旧 `alice / matt / bds` 缺口已实际校订，`review_required`为空仅表示这三个旧警告解决，不表示全部语义已认证。

## 生成和回归

默认/`--check`只读，**只有明确`--write`才更新显示文件**：

```powershell
python -B scripts/build_level_meanings.py --check
python -B scripts/build_level_meanings.py --write
python -B scripts/test_level_meanings.py
python -B scripts/test_school_meaning_reviews.py
python -B scripts/test_level_meanings_ui.py
python -B scripts/test_v135_ui.py
python -B scripts/test_v135_ui.py --native
```

[原覆盖回归](<../scripts/test_level_meanings.py>)验证全成员、短义、严格源片段/校订回查、SHA与幂等；[逐词校订回归](<../scripts/test_school_meaning_reviews.py>)检查全部158/183旧义和决定、5,302旧行、773未审词组、专名/普通词、来源与稳定身份及拒错；[原学校UI回归](<../scripts/test_level_meanings_ui.py>)覆盖全部真实/并集/系列/词组书及切书缓存；[V1.3.5 UI回归](<../scripts/test_v135_ui.py>)为全部183项检查真实目录/悬停/四选项，并用15个重点词实际Qt按钮测试刷词翻面、选择题、Lv1稳定key和通用测量学校别名隔离。全部Card资料写入Sandbox，不写真实学习记录。
