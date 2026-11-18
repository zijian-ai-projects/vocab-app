# dsh-vocab-app 内部契约（协作基线，不是发行文档）

## 0. 版本与边界
- 插件版本 **0.1.11**（由 package.json 派生）；功能/测评基线 **V1.4.3**，记录 APP_VERSION 保留既有 assessment baseline，Lead 另行决定是否升级。Windows 包版本目标为 V1.4.4。
- Host为Node ESM，宿主能力一律经ctx；Client为ModuleLoader工厂内单文件React.createElement，只require react。不启动替代Web server。
- 业务计算、持久化在Host；Client只渲染view/发送action。
- 五份只读data资产、CAT及其它Core保持；新规则为其它4个首次新词回答后才展示忘记/改判/选错的新词，无书末早退；到期重试即使没有候选也显示，且到期复习优先。daily policy/ledger 不参与新规则且作为不透明字段保留。学校暂停门禁保留。

## 1. 文档与安全
```js
{schema:1, revision:1, updatedAt:1799999999,
 progress:{/* 原学习、测评及未知扩展 */},
 window:{version:2,size:'mini'|'small'}} // 旧格式只读兼容为mini，不做窗口字段迁移写回
```
- namespace仍为 `dsh-vocab-app/vocab_app_default`，路径遵循原Store环境规则。
- progress保留states/cursors/orders/study_records/study_mode/learning_policy/daily_new_ledger/theme/book/school_knowledge/theta/prediction_state/memory_schema/book_confirmed/history/quiz_session及未知字段。
- 0.1.0兼容仍只清理退役keybindings/_v136_defaults_pending和窗口几何偏好；0.1.1旧medium/large、0.1.4 small均只读归一为mini。不清学习/历史/暂停测评，不增revision或改写旧窗口偏好。
- 原memory_schema=2、_v142_test_reset的一次性迁移保持，不对已有完成标记重做清理。
- 新迁移只在显式 `retry_gap=3` 时运行：有效 future retry deadline 迁移为 deadline+1（四个其它首次新词）；ready retry 不变；缺失/未知标记不变；完成后写入4确保幂等。
- 保存：克隆→计算→同目录临时/fsync/原子替换→rev+1→替换内存。失败不推进队列或内存。
- .bak保留上一份有效原文，主损坏可恢复；无有效源拒绝启动。进程锁、安全接管、加载/关闭竞争及卸载清理保持。
- 删除公开恢复/清空接口不等于删除内部备份恢复。

## 2. HTTP
- GET /api/vocab-app/state → {rev,view}。
- POST /api/vocab-app/action {rev,type,payload} → {ok,rev,view} 或 {ok:false,code,message,rev,view}。
- exact ctx.connection.fetch.register两路由，methods为GET/POST，requestBody:'buffered'，fetch接收单WHATWG Request。
- body≤64KiB，无任意文件路径；code stale/invalid/conflict/failed。
- 未知或退役动作freshrev一律invalid，不改文档/revision/磁盘；stale仍遵循原冲突校验次序。

## 3. View与窗口
```js
{screen:'welcome'|'front'|'back'|'empty'|'choice'|'choice_back'|'settings'|
        'books'|'catalog'|'history'|'quiz'|'result'|'summary'|'building',
 theme:'dark'|'light'|'sepia'|'green', status:'',
 keys:{remember:'Enter',forget:'Space',choice1:'1',choice2:'2',choice3:'3',choice4:'4',unknown:'Space',next:'Enter'},
 keyCaptions:{/* 空格/Enter等固定提示 */},
 windowSize:'mini',
 windowPresets:[{key:'mini',label:'迷你',width:400,height:400}],
 storageNote:'',busy:false}
```
- 每次 Client 挂载默认仅渲染 ClosedEntry 浮动图标（包括首次安装/重新打开/刷新）；GET 成功/失败均不自动展开。单击才打开；关闭/拖动沿用原行为。hidden 仅存在 React 内存，不新增展开偏好、资料迁移或写回；隐藏时不唤醒复习 POST，也不对已锁定测验自动发送 next；展开后保留原 350ms 自动进入下一题。关闭动作通过即时 hiddenRef 同步阻止未提交 React 渲染前的定时回调。
- 固定迷你 400×400；移除设置页窗口选项。windowSize动作不再接受任何值。既有small/medium/large只读显示为mini，不落盘改窗口字段；不保存自定义几何。
- Client窄视口可fit，恢复后按档位；长内容可滚动，固定操作不可被裁切。
- 窗口/入口共享会话内角锚点，均从同一锚点派生；完整窗左/右侧关闭到原矩形左下/右下，拖入口后沿同锚点还原。当前档位/视口变化一致夹紧，位置仍只在React内存，不新增localStorage。标题栏拖动，无边框resize。入口左键单击打开，pointerdown即开始抓取，pointermove即时更新位置，无长按timer；4px仅用于防误开，不阻止小位移跟手。取消/blur/unmount清理监听及capture。
- empty保留15s GET只读刷新，due到期时发送正常串行POST next自动取复习；busy/stale/错误退避可重试，hidden/切屏/卸载清timer，不在未答题时强制换词。
- 删除header品牌图标（保留关闭后的入口图标）；原学习页设置移左。NAV返回SVG与标题统一垂直中心。
- 无compact/compactPreferred/keyBindings/canReset/studyCaption/动态键位编辑状态。

## 4. 学习与固定按键
- front/back/choice/choice_back的studyStatus作为标题，不重复下方状态。quiz计数状态条保留。
- 刷词front的word.meaning固定空；显示释义控件/点词揭示/flip实现与ep.revealed状态退役。Enter认识、Space不认识。
- 刷词back有释义；刚回答认识时两槽同宽，左透明“选错了 [空格]”correct可点击，右下一个。刚回答不认识时不渲染选错了，仅长条“下一个 [空格 / Enter]”；Next标签与键位提示紧邻、整组居中，不把键位固定到最右侧。
- canCorrect:true时Space→correct，Enter→next；不能改判Space/Enter→next。correct保留单向认识→不认识且推进下一张，不是undo。
- Z改判与Ctrl+Z业务undo仍保留，不画撤销按钮；纯undo返回未答状态。
- choice/choice_back仅四真实选项，数字提示显示[1]…[4]，键语义仍1…4；Space不认识。答后Space/Enter next。
- 无法出四选一：unavailable:true、locked:true、options:[]，不退回front、不泄露meaning；Next/Space/Enter临时跳过，不判定学习状态，不丢pending retry；跳过键仅内存。
- 输入框/IME/repeat/modifier保护保持。
- 回答、选项、改判、下一词等按钮都有四主题搭配的淡1px边框；reset特异度不得覆盖控件主题。

## 5. 其它UI
- Books保持三级导航/系列伪id/词序/统计。末级Host row.text只传display/name，不附加bookQuantity，右侧count/countText保留一份真实数量。lead在scroll外顶部，中央列表可滚动，已学统计在列表下，底部横行左词序/顺序/乱序，右浏览词条/开始。
- 设置保留背景、学习模式、学校范围、词书、历史/测试；学校范围额外说明小字删除。底部版本显示V0.1.9（不是APP_VERSION）；历史页不显示趋势标题小字，图表与结果页说明保持。
- method页面/入口/结果descriptor/handler/返回元数据全退役；评测方法和Windows等级0…10解释进入readme。
- Catalog移除可见“共…条”和“按记忆等级排序”控件；真实等级、虚拟化、筛选/查询、批量学习保持。内部catalogSort API未新增公开UI。
- History保持归档/比较/删除单条；每行details外右侧放普通记录底色的“删除”（无警示色），折叠时可见、展开后仍顶端对齐且不触发展开。保留确认与原始index，取消不发送动作，无index不渲染删除；result/summary保留分层详情、预测策略与既有解释。
- 通用actions至少允许back/books/quizStart/prediction/bands/settings；不得误删bands或summary确认入口。退役method/flip不渲染。
- quizStart点击当轮立即显示加载页，不改本地权威view/rev；building左上角标题为空，中央提示保留，不显示百分比文字。进度条从0开始，只按Host真实构建进度向右增长，CSS平滑宽度过渡（减少动态效果时无过渡），不往返、不按时间模拟。请求未完成不启动building轮询；确认building后100ms只读轮询，busy禁止重叠请求；真实view转quiz时填满100并短留300ms让宽度过渡完成，再退出加载，不接受答题动作；warm路径不增加此停留。完成计时器随卸载清理；失败直接恢复。busy同步防连点。
- 冷FrequencyBank经Node模块URL worker构建，保留原Core算法，线程只接公共词库；Map/Set structured clone后恢复FrequencyBank与items空原型，指纹/seed题序/摘要一致。构建在原串行链内await，GET与主线程心跳不被CPU堵住；初次building HTTP响应先返回（不承诺socket flush时序）。构建中动作即时conflict。卸载先取消线程/释放锁，await后再次检查closed，失败/取消不提交记录、不增rev；成功后才启动并保存测评。同步getQuizBank保留供已缓存路径，构建中禁止另起同步构建。
- Quiz 40–80题、暂停/续测、不给实时对错；四选项下面增加第五行“不认识 [空格]”，居中无E，仍发送quizDontknow，不增加IRT猜测选项。
- Quiz所有分支提供unknownPicked布尔；true只表示锁定且picked=-1；第五行锁定后保留/禁用，Next在选项组外。未知结果与答错同为未识别证据，resp原值-1仍保留。

## 6. 动作白名单
```text
answer{action:'remember'|'forget'}, next{}, choice{index:0..3}, dontknow{}, correct{}, undo{},
settings{}, closeSettings{}, theme{key}, studyMode{key:'brush'|'choice'}, school{level},
books{from}, book{id,order}, nav{id}, start{}, catalog{}, catalogFilter{category,query}, catalogSort{byLevel}, bulkLearn{keys},
quizStart{fresh}, quizAnswer{index}, quizDontknow{}, quizPause{}, history{}, deleteHistory{index}, prediction{strategy}, bands{}, back{}
```
- windowSize/compact/keys/resetSettings/resetRecords/method/flip已退役，原合法payload也invalid，不推进rev。

## 7. 数值硬约束（测评与其它Core不修改）
- scheduler/study_queue/school_knowledge/prediction/entries/books/level_meanings保持各自API；学习 policy / daily ledger 不再参与活动队列，不初始化、校验、记账或清除，但原值作为扩展字段保留。新词 forget/correct/wrong-choice 重现需4个其它 first-new answers，同书跨日计数；retry/review/skip/show不计数；无书末早退。到期旧词优先。已 eligible retry 在无候选时也可显示。0级 retry 本身不成为每日新词目标或门禁。
- ALGORITHM=vst-cat-v143-web，MEASUREMENT_SCHEMA=3，SESSION_SCHEMA=2，UNIT=frequency_ranked_entries。
- 3PL A=1.4、C=0.25；先验N(0,2²)，theta -5…7 step.05，b=ln((rank+100)/1000)；EAP/Fisher/band/停止规则不变。
- SHA-256 counter DRBG、canonical指纹、BigInt exactSum不变；同指纹/种子/记录序列同题序。
- 不改变历史兼容、五JSON及其它Windows资产，不导入他插件词库/发音/快捷键。

## 8. 验收/发行
- node --test test/*.mjs，不是node --test test/；真实Hook/handler/清理、固定迷你/小视口、返回中心、主题边框和退休动作回归。
- 原0.1.4本地包与既有合成资料在假DSH_HOME升0.1.5，检查学习/排期/未知字段/历史/暂停会话；从不读本机个人记录做测试。
- 历次补丁构建时曾保持旧回滚包原字节；2026-11-17 按用户要求清理发行目录，仅保留 UI 补丁原 ZIP 字节（统一外层名称）与最新 DSH，不重打包 Windows。0.1.10 是 0.1.9 启动最小化小补丁，安全安装验证后以新包替代交付目录中的旧 TGZ。旧 Git 历史/标签保留，不自动 commit/tag；随包 readme 已同步最新包策略。Windows VERSION仍1.4.3，刷词forget专用objectName与中性色QSS、五分钟scheduler按当前源码保留。
- 当前准备 Windows V1.4.4 / DSH 0.1.11；构建和验证尚未完成。版本化 builder staging/work/config 路径不得清理既有目录；发布目标、归档、校验文件存在时必须失败，绝不覆盖/删除旧档案。Lead负责批准后的实际构建；本任务不安装、不触碰live app、不commit/tag/push。
- 本地tgz仅运行白名单+readme.md；不含测试/审计/开发文档/脚本/个人资料/日志/锁/缓存。
- 仅授权desktop更新，不公开上传；private:true/UNLICENSED及原许可边界保持。
