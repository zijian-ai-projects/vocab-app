# V1.4.4 / DSH 0.1.11 发布准备记录

状态：准备中；尚未构建、打包、安装或在 live app 验证。本文不记录未执行的测试结果、哈希或制品路径。

## 目标

- Windows 构建版本为 V1.4.4；DSH manifest 版本为 0.1.11。
- DSH 以 Windows V1.4.3 为评测基线。`APP_VERSION` 的评测基线不由插件版本号推断，本轮由 Lead 评估是否调整。
- 新词 forget、correct（认识后改判）和 wrong-choice（选错）进入 retry，只有在同一本书再回答 4 个其它首次新词后才 eligible。计数跨日；retry、到期旧词复习、跳过和展示不计数。书末没有提前 retry。
- 到期复习优先于新词和 retry。eligible retry 即使当前没有候选，也允许出现。
- 不提供每日目标 UI、门禁或记账。旧 `learning_policy` 与 `daily_new_ledger` 保留为不透明字段，不初始化、读取校验、记账或清除；学校暂停条件保留。
- 迁移仅对显式 `retry_gap=3` 标记有效：有效且未来的 deadline 加 1；ready retry 不变；缺失/未知标记不动；迁移后写入 4，重复启动幂等。

## 构建器约束

- Windows staging、work、spec/config 分别使用 `.build/win-dist-v1.4.4`、`.build/win-work-v1.4.4`、`.build/win-config-v1.4.4`。插件 staging 使用 `.build/plugin-package-v0.1.11`；所有路径均为版本隔离，脚本不得清理或复用已存在路径。
- Windows 发行目标为 `vocab-app-releases/v1.4.4/`。DSH 归档目标也限定在此新版本目录。任何目标目录、归档、临时归档、校验文件已存在时必须失败，不得覆盖或删除。
- 发布包只含显式运行资产白名单；源码树和拷贝后的资产树检查链接/特殊文件。个人资料、恢复文件、日志、备份、锁、测试和开发资料不得进入运行包。
- Plugin tar 使用固定系统路径并校验预期版本：Windows `System32/tar.exe` / bsdtar 3.7.7；Unix `/usr/bin/tar` / GNU tar 1.35。版本不匹配即失败，不从 PATH 解析备用 tar。
- 归档先以唯一 `.tmp` 名称创建，再用同目录硬链接执行 create-only 发布；校验文件采用版本专用新路径。

## 尚待 Lead 完成

- 检查并确认活跃代码、测试及迁移实现；确定是否调整 assessment APP_VERSION。
- 仅在新版本目标为空时执行隔离构建与独立包内容/哈希/启动验证；不得更改或删除旧档案和历史。
- 完成验证后更新本记录和安装说明。当前没有构建或测试结论。

本准备任务没有运行构建或安装，没有启动/改动 live app，没有 commit、tag 或 push。
