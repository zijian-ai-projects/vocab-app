# Windows V1.4.3 / DSH 0.1.9 联合交付（历史）

> 本文保留 `389a1ec` / `dsh-vocab-app-v0.1.9` 标签快照的历史验收；当前默认最小化补丁与最新包见 [DSH 0.1.10](<release-dsh0110.md>)。下文发行清单为当时状态，不代表当前交付目录；旧 TGZ 可从原标签快照取得。

日期：2026-11-17。本次将此前已完成的 Windows 便携发行、五分钟复习与主题按钮调整、V1.4.3 冗余清理，以及 DSH 移植和 0.1.9 界面优化集中提交到本地 Git。注释标签使用 `V1.4.3` 与 `dsh-vocab-app-v0.1.9`，指向同一最终快照；不推送、不修改旧标签或重写历史。

## 发行目录

仅保留两个压缩包，以及 [安装说明](<../vocab-app-releases/v1.4.3/安装说明.txt>) 和 [SHA-256 清单](<../vocab-app-releases/v1.4.3/SHA256SUMS.txt>)。

| 发行包 | SHA-256 |
| --- | --- |
| [Windows 1.4.3](<../vocab-app-releases/v1.4.3/VocabApp-1.4.3-windows-x64.zip>) | `7bbb174e4dd02108f0c8b221088d7865b9d7743cf78b2015d6646955603165b3` |
| DSH 0.1.9（原标签快照内 TGZ） | `779cf3b8013642b3b843c2d0aaff7ca41cf00b6795b9ee63b8badbb5d0aecb61` |

Windows 包由指定的 `patch-20261116-ui.zip` 仅改外层名称得到，41,257,550 字节、178 个文件；内部目录名仍带补丁后缀。DSH 包保持 4,694,468 字节、32 个运行文件。均不重建、重压缩或修改运行代码；包内历史说明关于旧包保留策略的文字由外部安装说明替代。

清理精确删除 12 个旧发行文件、3 个旧解压目录。事先向用户指出两个解压目录含 userdata，用户明确答复“直接删除”，因此这些目录中的资料也随目录删除，未解析其内容。未触及源码版资料、DSH 主记录/备份或其他插件。不删除 `.build` 构建环境及插件外审计/回退证据；这些不属于交付目录，也不进入 Git。

## 行为与验证

Windows 保留独立便携资料路径、锁/原子保存、只读资源路径及运行库隔离。刷词“不认识”使用主题中性色；1–9 级旧词忘记后保级，300 秒后到期；不重算现有 due。DSH 保留独立 namespace、固定 400×400 小窗、紧凑历史删除和精简设置。首次测试即时呈现 0% 加载，后台模块 Worker 使用公共词库按真实阶段回报进度，左上角不重复显示加载标题；100% 短留 300ms 后进入题目，期间不接受答题。缓存题库不人为等待。

本次重新运行的检查：

| 范围 | 结果 |
| --- | --- |
| DSH 完整 Node 测试 | 246/246，通过，0 失败、0 跳过 |
| Windows scheduler | 14/14，通过 |
| Windows study queue | 32/32，通过 |
| Windows storage | 60/60，通过 |
| Windows launcher | 21/21，通过 |
| Windows reset 隔离测试 | 16 项，15 通过、1 项按环境条件跳过，无失败；不执行真实清空 |
| 冻结路径/布局/junction/资料隔离 | 14/14，通过 |

Windows 合计 157 项，156 通过、1 跳过。检查使用已有隔离 Python 环境和临时合成资料，不启动真实学习会话。源码语法及发行归档完整性、仅两份校验、Git 提交白名单另做静态核对。构建缓存、运行态资料、日志/锁/恢复文件不入提交。

此前 DSH 0.1.9 已完成公共 20,000 词实测、安装目录 32 文件比对、已安装模块 URL Worker 构建、主记录和原备份各自不透明字节核对以及合成升级保存检查。浏览器离线实际 CSS/渲染器覆盖四主题、两尺寸与实际单向宽度动画。现有真实 GUI 在自动化浏览器中仍要求认证，因此不声称登录态人工点击端到端通过。

[V1.4.3 清理验收](<acceptance-v143.md>) 是历史阶段记录：当时 29 个入口为 22 通过、7 个既有失败。涉及排序、合成历史、词序和旧数据来源校验，未在本次修复，也未删除/放宽断言掩盖。上述定向通过结果不代表全部 Windows 历史测试全绿。

## SmartScreen

已对指定 Windows 解压程序做 Authenticode 只读核对，状态为 **NotSigned**。未签名/低信誉的新 EXE 可能触发“未识别应用”；“目前无法访问 SmartScreen”表示此次联网检查未完成，不代表检查通过。没有读用户安全历史或推断具体网络原因。

Windows 在应用启动前做信誉检查，不能通过程序内部 Python 补丁保证消除。没有配置可信签名证书或服务，没有自签冒充可信发布者，没有关闭 Defender/SmartScreen、添加排除或自动解除下载来源标记。仅在用户已确认来源、完整性并决定信任的前提下，外部安装说明介绍单文件手动“属性→解除锁定”的可选操作；它不是签名或安全认证。具体恶意软件/隔离告警应停止运行。

长期改善可考虑合法受信任代码签名和一致发布身份，或合适的商店发行；OV/EV 签名也不能保证新版本免警告。依据 [微软应用信誉说明](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)、[解除锁定说明](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/unblock-file?view=powershell-7.5)、[SmartScreen 在线检查端点](https://learn.microsoft.com/en-us/defender-endpoint/streamlined-device-connectivity-urls-commercial#common-endpoints)。

本次仅本地提交和标签，项目仍 private/UNLICENSED；不改变第三方组件及词库的许可边界。
