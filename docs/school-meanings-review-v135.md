# V1.3.5 · 158词逐词释义对照

本台账逐项列出固定审核池的稳定key、原短义、新短义和判定理由；完整字段与可携带短引用见 [已散列校订源](<../data/school_meaning_reviews.json>)。学校卡片、目录和学习四选项读取 [显示覆盖](<../data/level_meanings.json>)。

## 结果与范围

| 口径 | 小学 | 初中 | 合计 |
|---|---:|---:|---:|
| 已逐项审核 | 47 | 136 | 183学段项 / 158词 |
| 新短义不同（replace） | 39 | 64 | 103学段项 |
| 原短义保留（retain） | 8 | 72 | 80学段项 |

**按不同词计：89词至少一个学段短义变化；69词在所属全部学段保留原短义。** 158是原V1.3.4来源规则回退池，不是158个已证明错误；replace包括补词性/身份、修复残缺、补完整常用义或必要译写，不等于每条原译全错。25个共享词的人名/地名中文字面一致，姓名括注/义组可按学段不同；DVD的“数字化视频光盘/数字视频光盘”同义。

未改原34,963 bank key、书籍ID、成员或顺序，不重置进度、排期、历史。其它5,302学段行（包含773初中词组）值与原来源元数据完全不变；773词组不属于本次逐词审核。高中/通用词汇量测量继续使用原通用义。

## 证据说明

- 原bank中文字、原词书成员位置/邻词、已有gloss和外部短引用分开保存。人物段支持名字用法，不冒称完整教材人物全文；无人物依据不推断具体角色或性别。
- 新译写/词性/标签明确是编辑校订；不能把新译名伪装为旧gloss原文。历史本地引用附原路径、SHA和行范围并嵌入校订源，外部字典/教材/机构材料只作含义旁证，不是官方词表审计。
- 全部词表仍由民间整理。审核是限定范围的AI逐词审查与Lead合并/交叉核验，不等同于人类专家或出版机构认证，也不保证范围外全部语义。
- “—”表示该词不在本次该学段47/136集合，不能据此认定该学段没收录。保留释义时仍可规范仅显示的大小写；稳定key保持原文。

## 全部158词

| # | 稳定key / 显示词形 | 小学：旧 → 新 | 初中：旧 → 新 | 逐词判定与记录 |
|---:|---|---|---|---|
| 1 | `alan` / Alan | — | n.艾伦（保留） | 初中：gina/jenny/alan/tom连续人物段；原bank.raw明确男子名，原短义已正确，不追加其他义。<br>[逐词记录](<../data/school_meaning_reviews.json#L59>) |
| 2 | `alfred` / Alfred | — | n.阿尔弗雷德（保留） | 初中：paula/alfred/billy/candy/jerry为单元末人物段；采用bank.s现有姓名译写，不引入阿尔弗雷德大帝义。<br>[逐词记录](<../data/school_meaning_reviews.json#L90>) |
| 3 | `alice` / Alice | 应用语言接口转换与扩充 → **n.爱丽丝（人名）** | 应用语言接口转换与扩充 → **n.爱丽丝（女名）** | 小学：xx-yle1/2 尾段 alice 与 alex/ann/anna/ben 连续列在人名段；按用户明确要求用爱丽丝人名，排除应用语言接口专业缩写。<br>初中：alice/bob/cindy/dale/eric连续初一人物段；用户明确Alice为爱丽丝人名，教材梳理也给女名，计算机接口义排除。<br>[逐词记录](<../data/school_meaning_reviews.json#L127>) |
| 4 | `allen` / Allen | — | n.艾伦（保留） | 初中：位于truth后、alabama前的单元专名段；原bank.raw明确男子名，保留姓名，不改w为Alan。<br>[逐词记录](<../data/school_meaning_reviews.json#L214>) |
| 5 | `am` | v.是（保留） | v.是；abbr.上午 → **v.是（be的第一人称单数形式）** | 小学：xx2-1 的 am/i'm 开篇自我介绍、xx3-1 的 are/you/yes/am 以及 be/am/is/are 词段都指 be 的第一人称单数现在时；原小学义已经正确，严格原样保留。<br>初中：how/are/you/am/fine问候段以及be/am/is/are并列，原raw明确be第一人称单数；本词不是a.m.上午缩写。<br>[逐词记录](<../data/school_meaning_reviews.json#L245>) |
| 6 | `amy` / Amy | — | n.艾米（保留） | 初中：clark/amy/molly在learn后为人物段；原bank.raw明确女子名，原短义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L342>) |
| 7 | `andy` / Andy | — | n.安迪（保留） | 初中：relationship后andy/ken/hemingway/kelly专名段；原raw为男子名，保留，不把Andrew昵称说明扩成长义。<br>[逐词记录](<../data/school_meaning_reviews.json#L373>) |
| 8 | `ann` / Ann | n.安 → **n.安（女名）** | — | 小学：xx-yle1/2 中 Ann 位于 Alice/Anna/Ben 等连续人名段；原bank.raw 已明示安（女子名），沿用安并补回女名标签，避免把单字安当通用义。<br>[逐词记录](<../data/school_meaning_reviews.json#L404>) |
| 9 | `anna` / Anna | n.安娜 → **n.安娜（女名）** | n.安娜（保留） | 小学：xx-yle1/2 的 Ann/Anna/Ben 人名邻段与原bank.raw 的女子名一致；保留安娜译写，仅明确女名。<br>初中：set后anna/david与下单元where/table分界；原raw明确女子名，原义保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L447>) |
| 10 | `annie` / Annie | — | n.安妮（保留） | 初中：wisely后annie为单元人物名；bank.raw与本地Annie女名一致，原义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L516>) |
| 11 | `app` | 应用 → **n.应用程序** | 应用 → **n.应用程序** | 小学：xx-yle2 的 tablet/app/music/CD 生活及电子媒介语境指应用程序；原应用过于含混，选原bank已有的应用程序并明确名词，不取相联并行处理器。<br>初中：app/application/appear词段为常用软件词；原raw已有应用程序，原短义只写应用且无词性过泛，不取相联并行处理器。<br>[逐词记录](<../data/school_meaning_reviews.json#L553>) |
| 12 | `august` / August | n.八月（保留） | n.八月；adj.威严的 → **n.八月** | 小学：xx1-6 的 July/August/September 连续月份段及 xx3-6 月份邻段均支持八月；原小学义正确，保留，不带 august 的威严形容词义。<br>初中：april/may/june/july/august/september连续月份段；本地August为八月，排除小写august的威严形容词义。<br>[逐词记录](<../data/school_meaning_reviews.json#L620>) |
| 13 | `bds` / BDS | abbr.用硬纸板作封面 → **abbr.北斗卫星导航系统** | — | 小学：xx1-7 的 restaurant/pizza/street/get/BDS/gave/give/feature/follow 导航邻段，与 PEP 六上 Robin 用 BDS 引路的可读配套课件一致；课件与北斗官网均明确 BeiDou Navigation Satellite System，替换硬纸板封面义。<br>[逐词记录](<../data/school_meaning_reviews.json#L703>) |
| 14 | `becky` / Becky | — | n.上挂钩 → **n.贝基（女名）** | 初中：julie/becky在over后为人物段；外部姓名词条确认Becky及贝基女名译写，不采用通用上挂钩义。<br>[逐词记录](<../data/school_meaning_reviews.json#L753>) |
| 15 | `ben` / Ben | n.内室 → **n.本（人名）** | n.内室 → **n.本（男名）** | 小学：xx-yle1/2 中 Ben 连在 Anna/Bill/Eva 人名尾段；这里应是人名，不是苏格兰内室或植物贝昂。<br>初中：karen/ben/michael/laura/mills/robert连续人物段；外部Ben词条给本（男子名），内室和医药植物义不适用。<br>[逐词记录](<../data/school_meaning_reviews.json#L796>) |
| 16 | `bert` / Bert | — | n.伯特（保留） | 初中：disappoint后bert/holly为人物段；原raw及本地Bert都是男名，保留现有短义。<br>[逐词记录](<../data/school_meaning_reviews.json#L877>) |
| 17 | `bill` / Bill | n.账单 → **n.比尔（男名）** | — | 小学：xx-yle1/2 的 Ben/Bill/Eva 人名尾段排除普通账单义；原bank.raw 已列比尔(男名)，采用该明确人名义。<br>[逐词记录](<../data/school_meaning_reviews.json#L914>) |
| 18 | `billy` / Billy | — | n.警棍 → **n.比利（男名）** | 初中：paula/alfred/billy/candy/jerry/emily连续人物段；本地Billy明确比利男名，不是警棍或公山羊。<br>[逐词记录](<../data/school_meaning_reviews.json#L957>) |
| 19 | `bob` / Bob | — | vt.剪短；vi.振动 → **n.鲍勃（男名）** | 初中：alice/bob/cindy/dale/eric为Starter人物名；教材梳理明确鲍勃男名，剪短和振动是通用词义误套。<br>[逐词记录](<../data/school_meaning_reviews.json#L999>) |
| 20 | `brian` / Brian | — | n.布莱恩（保留） | 初中：luke/brian/griffin/trent毕业单元人物段；原bank明确布莱恩男子名，沿用既有译写，不冒称本地布赖恩字面。<br>[逐词记录](<../data/school_meaning_reviews.json#L1042>) |
| 21 | `bund` / the Bund | 同盟 → **n.外滩（上海地名）** | — | 小学：xx3-7 位于 holiday/call/bund 邻段，译林六上 Holiday fun 配套学案明确 the Bund 外滩并置于上海景点语境；这里不是政治同盟。<br>[逐词记录](<../data/school_meaning_reviews.json#L1079>) |
| 22 | `carla` / Carla | — | n.卡拉（保留） | 初中：stonehenge后carla/victor/jean人物段；原bank及本地Carla女名均支持卡拉，保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L1122>) |
| 23 | `carmen` / Carmen | — | n.卡门（保留） | 初中：titanic/spider-man后carmen为人物专名；原raw和本地Carmen明确女名，不据歌剧名另增第二义。<br>[逐词记录](<../data/school_meaning_reviews.json#L1159>) |
| 24 | `carol` / Carol | — | n.颂歌；v.唱 → **n.卡罗尔（人名）** | 初中：hear后carol处于单元末人物名位置，本地大写Carol给卡罗尔；不是颂歌或唱歌动词。<br>[逐词记录](<../data/school_meaning_reviews.json#L1196>) |
| 25 | `cathy` / Cathy | — | n.凯茜（保留） | 初中：perhaps后cathy/taylor为人物段；原raw明确女子名，沿用凯茜，不推断别的人物身份。<br>[逐词记录](<../data/school_meaning_reviews.json#L1238>) |
| 26 | `cba` / CBA | — | abbr.中国篮球协会（保留） | 初中：professional/nearly/berlin/nba/cba篮球单元段；原bank首义为中国篮球协会，正确保留，排除成本效益分析。<br>[逐词记录](<../data/school_meaning_reviews.json#L1269>) |
| 27 | `cinderella` / Cinderella | — | n.灰姑娘（保留） | 初中：lead/voice/brave/claudia/cinderella童话单元收尾；原bank灰姑娘正确，不替换为无关技术或泛指人。<br>[逐词记录](<../data/school_meaning_reviews.json#L1300>) |
| 28 | `cindy` / Cindy | — | n.辛迪（保留） | 初中：alice/bob/cindy/dale/eric连续人名；原bank.raw明确女子名，现有辛迪正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L1331>) |
| 29 | `claire` / Claire | — | n.克莱儿（保留） | 初中：point后claire/sue为人物段；原bank.raw明确女子名，既有克莱儿译写可保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L1362>) |
| 30 | `clara` / Clara | — | n.克拉拉（保留） | 初中：clara/scrooge处于单元人物段；原raw及本地Clara女名支持克拉拉，不追加Santa Clara地名。<br>[逐词记录](<../data/school_meaning_reviews.json#L1393>) |
| 31 | `clare` / Clare | n.克莱尔 → **n.克莱尔（女名）** | — | 小学：xx-yle2 中 Clare 处于 Charlie/Daisy/Fred 连续人名段，原bank.raw 也标女子名；沿用克莱尔并明确身份。<br>[逐词记录](<../data/school_meaning_reviews.json#L1430>) |
| 32 | `clark` / Clark | — | n.克拉克（保留） | 初中：learn后clark/amy/molly人物段；原bank克拉克为人名，现有短义可涵盖人物称谓，保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L1466>) |
| 33 | `claudia` / Claudia | — | n.克劳迪娅（保留） | 初中：brave后claudia/cinderella为单元末专名；原raw明确女子名，既有译写正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L1497>) |
| 34 | `cm` | — | 厘米 → **abbr.厘米** | 初中：cm/centimeter/centimetre及centimetre/cm并列明确度量单位；原义厘米正确但需补规范词性，不取中央存储器或锔。<br>[逐词记录](<../data/school_meaning_reviews.json#L1528>) |
| 35 | `daisy` / Daisy | n.雏菊 → **n.黛西（人名）** | — | 小学：xx-yle2 中 Daisy 连在 Clare/Fred/Jack 人名尾段，应取人名而非花卉雏菊义。<br>[逐词记录](<../data/school_meaning_reviews.json#L1565>) |
| 36 | `dale` / Dale | — | n.小谷 → **n.戴尔（男名）** | 初中：alice/bob/cindy/dale/eric/frank连续人名；教材梳理给戴尔男名，排除小谷地形义。<br>[逐词记录](<../data/school_meaning_reviews.json#L1601>) |
| 37 | `dave` / Dave | — | n.戴夫（保留） | 初中：true后dave为单元末人物名；原raw明确男子名，原短义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L1644>) |
| 38 | `david` / David | — | n.大卫（保留） | 初中：set/anna/david位于单元人物段；原raw有大卫/戴维男子名，选择现有大卫不并列重复译名。<br>[逐词记录](<../data/school_meaning_reviews.json#L1675>) |
| 39 | `dean` / Dean | — | n.院长 → **n.迪安（姓）** | 初中：johnny/dean、tina/jackson成对的人物段支持姓名而非院长；迪安来自本地Dean，姓标签是语境复核并非gloss原字。<br>[逐词记录](<../data/school_meaning_reviews.json#L1706>) |
| 40 | `dennis` / Dennis | — | n.丹尼斯（保留） | 初中：greg/danny/eliza/vera/dennis连续人名；原raw明确男子名，原义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L1748>) |
| 41 | `disneyland` / Disneyland | n.迪斯尼乐园（保留） | n.迪斯尼乐园（保留） | 小学：xx3-8 中 Disneyland 与 Taipei/photo/travel 相邻，指旅行目的地迪斯尼乐园；原bank和原小学义正确，不无谓改换既有中文译名。<br>初中：location/disneyland/singapore旅游专名段；原bank迪斯尼乐园正确，保留既有译写。<br>[逐词记录](<../data/school_meaning_reviews.json#L1779>) |
| 42 | `dvd` / DVD | abbr.数字化视频光盘（保留） | abbr.数字化视频光盘；n.光盘 → **abbr.数字视频光盘** | 小学：xx2-7 的 snake/DVD/bamboo 影音学习语境和 xx-yle2 的 CD/comic/dance/DVD/film 媒介词段均支持视频光盘；原小学义准确且短，保留。<br>初中：dvd/actor/tale/dinosaur影视语境；原raw提供完整数字视频光盘含义，压缩重复且泛化的光盘第二组，保留明确缩写词性。<br>[逐词记录](<../data/school_meaning_reviews.json#L1841>) |
| 43 | `e-friend` | 网友 → **n.网友** | — | 小学：xx3-5 的 e-friend/send/email/live 网络交友语境与原bank.s 网友一致；中文不改义，只补正确名词词性。<br>[逐词记录](<../data/school_meaning_reviews.json#L1915>) |
| 44 | `e-mail` | — | n.电子邮件；v.给…发电子邮件（保留） | 初中：e-mail/email/at/call联系信息段；原bank的名词及常用发邮件动词都正确，原两组保留，不附加通信协议术语。<br>[逐词记录](<../data/school_meaning_reviews.json#L1957>) |
| 45 | `eliza` / Eliza | — | n.伊莱扎（保留） | 初中：greg/danny/eliza/vera/dennis连续人物段；原raw明确女子名，保留既有伊莱扎，不冒充其他译写。<br>[逐词记录](<../data/school_meaning_reviews.json#L1991>) |
| 46 | `emily` / Emily | — | n.埃米莉（保留） | 初中：alfred/billy/candy/jerry/emily人物段；原bank与本地Emily女名均支持埃米莉，保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L2022>) |
| 47 | `er` | 铒 → **int.呃（表示犹豫）** | — | 小学：xx2-5 的 list/er/need 邻段对应外研五上 Module 2；可读配套课件明确这是思索说什么时的呃声，替换化学元素铒义。<br>[逐词记录](<../data/school_meaning_reviews.json#L2059>) |
| 48 | `eric` / Eric | — | abbr.科教资源信息中心 → **n.埃里克（男名）** | 初中：alice/bob/cindy/dale/eric/frank人物段；教材梳理明确埃里克男名，科教资源中心和遥控缩写均非教材义。<br>[逐词记录](<../data/school_meaning_reviews.json#L2102>) |
| 49 | `eva` / Eva | n.伊娃 → **n.伊娃（女名）** | — | 小学：xx-yle1/2 的 Bill/Eva/Jill/Kim 人名尾段与原bank.raw 女子名一致；保留伊娃译写并补回女名说明。<br>[逐词记录](<../data/school_meaning_reviews.json#L2145>) |
| 50 | `frank` / Frank | — | adj.坦率的；vt.盖邮资已付印记 → **n.弗兰克（男名）** | 初中：bob/cindy/dale/eric/frank/grace/helen连续人物段；教材梳理给弗兰克男名，不用坦率或邮资印记义。<br>[逐词记录](<../data/school_meaning_reviews.json#L2188>) |
| 51 | `fred` / Fred | n.佛瑞德 → **n.弗雷德（男名）** | — | 小学：xx-yle2 的 Daisy/Fred/Jack 人名段且原bank.raw 标男子名；采用常用弗雷德译写，明确属于对原佛瑞德的编辑译写校订。<br>[逐词记录](<../data/school_meaning_reviews.json#L2231>) |
| 52 | `georgetown` / Georgetown | — | n.乔治城（保留） | 初中：malaysia/malaysian/georgetown旅游段指马来西亚城市；保留bank.s正确短译乔治城，不采用raw圭亚那首都限定，课本例句亦译乔治城。<br>[逐词记录](<../data/school_meaning_reviews.json#L2267>) |
| 53 | `gina` / Gina | — | n.吉娜（保留） | 初中：gina/jenny/alan/tom/mike连续人名；bank.s的吉娜译写正确保留，raw所称男子名不作为性别证据，也不复制到释义。<br>[逐词记录](<../data/school_meaning_reviews.json#L2305>) |
| 54 | `god` | — | n.上帝；vt.使神化 → **n.神，上帝** | 初中：shoot/stone/weak/god/remind故事段；本地god为上帝、神，保留普通名词概念，去掉不适合此处的使神化动词义。<br>[逐词记录](<../data/school_meaning_reviews.json#L2336>) |
| 55 | `grace` / Grace | — | n.优美；vt.为增色 → **n.格雷丝（女名）** | 初中：dale/eric/frank/grace/helen连续人物段；教材梳理明确格雷丝女名，不用优美或增色动词义。<br>[逐词记录](<../data/school_meaning_reviews.json#L2379>) |
| 56 | `greg` / Greg | — | n.格雷格（保留） | 初中：crowded后greg/danny/eliza/vera/dennis人物段；原raw明确男名，原义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L2422>) |
| 57 | `griffin` / Griffin | — | n.希腊神话中半狮半鹫的怪兽 → **n.格里芬（姓）** | 初中：luke/brian/griffin/trent毕业单元人物段；本地Griffin与教材词汇摘录明确格里芬姓氏，排除半狮半鹫怪兽或新手义。<br>[逐词记录](<../data/school_meaning_reviews.json#L2453>) |
| 58 | `hayes` / Hayes | — | n.海耶斯 → **n.海斯（姓）** | 初中：jason/hayes/jessica处于环保单元末人物段；本地Hayes明确海斯（姓），本次采用该译写和姓标签，不把raw男子名或美国总统当教材人物。<br>[逐词记录](<../data/school_meaning_reviews.json#L2502>) |
| 59 | `hb` / HB | — | abbr.厚膛壁身管 → **abbr.（铅笔芯）硬黑** | 初中：hb/cd/bbc为Starter字母缩写学习段；教材梳理逐字给HB（铅笔芯）硬黑，不猜军事Heavy Barrel含义。<br>[逐词记录](<../data/school_meaning_reviews.json#L2544>) |
| 60 | `helen` / Helen | — | n.海伦（保留） | 初中：eric/frank/grace/helen人物段；原raw明确女子名，海伦译写正确保留，不添加词源火把说明。<br>[逐词记录](<../data/school_meaning_reviews.json#L2587>) |
| 61 | `hemingway` / Hemingway | — | 海明威 → **n.海明威（美国作家）** | 初中：andy/ken/hemingway/kelly人物与阅读讨论段；原raw及冻结本地gloss明确Ernest美国小说家，补n.并保留教材相关身份。<br>[逐词记录](<../data/school_meaning_reviews.json#L2618>) |
| 62 | `here's` | abbr.干杯 → **abbr.这是（here is的缩约）** | — | 小学：xx2-1 的 birthday/here/here's/present 赠礼语境和两份本地gloss =here is 均指 here is 的缩约，不是 Here's to you 的干杯祝酒句。<br>[逐词记录](<../data/school_meaning_reviews.json#L2660>) |
| 63 | `holly` / Holly | — | n.冬青树 → **n.霍莉（女名）** | 初中：disappoint/bert/holly/unexpected在单元分界；本地大写Holly明确霍莉女名，排除冬青树。<br>[逐词记录](<../data/school_meaning_reviews.json#L2715>) |
| 64 | `internet` | — | n.互联网（保留） | 初中：twice/internet/program及customer/internet/check等生活和上网语境；原bank首义互联网正确，保留，不追加技术网络分型。<br>[逐词记录](<../data/school_meaning_reviews.json#L2757>) |
| 65 | `jack` / Jack | n.千斤顶 → **n.杰克（人名）** | n.千斤顶；vt.用千斤顶托起 → **n.杰克（男名）** | 小学：xx-yle2 的 Fred/Jack/Jane/Jim 连续人名尾段应取 Jack 人名，不是千斤顶或插座。<br>初中：jenny/alan/tom/mike/jack/mary/miller连续人名；可见词表文段给Jack杰克男名，机械千斤顶义排除。<br>[逐词记录](<../data/school_meaning_reviews.json#L2794>) |
| 66 | `jackson` / Jackson | — | n.杰克逊（保留） | 初中：johnny/dean/tina/jackson成对人物段；本地Jackson和bank.s支持杰克逊，保留短译，不采用raw美国城市或男子名限定。<br>[逐词记录](<../data/school_meaning_reviews.json#L2868>) |
| 67 | `jake` / Jake | — | adj.满意的；n.乡下佬 → **n.杰克（男名）** | 初中：ted/may/vince/steen/jake/susan连续人物段；外部Jake姓名释义及本册签名例句确认杰克，不用满意的或乡下佬。<br>[逐词记录](<../data/school_meaning_reviews.json#L2905>) |
| 68 | `james` / James | — | n.詹姆斯（保留） | 初中：word后nick/james/white人物段；原raw有詹姆斯人名，保留现有译写，不追加圣经雅各书。<br>[逐词记录](<../data/school_meaning_reviews.json#L2948>) |
| 69 | `jane` / Jane | n.简 → **n.简（女名）** | n.简（保留） | 小学：xx-yle2 中 Jane 位于 Jack/Jim/Julia 人名段，原bank.raw 明示简（女子名）；补回女名标签，使单字简不被当普通形容词。<br>初中：mary/miller/linda/jane/smith人物段；原raw明确女子名，原短义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L2979>) |
| 70 | `jason` / Jason | — | n.杰森（保留） | 初中：wwf后jason/hayes/jessica人物段；bank.s已有杰森人名译写，保留，不冒称本地贾森字面或神话伊阿宋。<br>[逐词记录](<../data/school_meaning_reviews.json#L3041>) |
| 71 | `jean` / Jean | — | n.牛仔裤 → **n.琼（女名）** | 初中：carla/victor/jean在单元末人物段；本地大写Jean明确琼女名，排除牛仔裤或斜纹布。<br>[逐词记录](<../data/school_meaning_reviews.json#L3072>) |
| 72 | `jeff` / Jeff | — | n.杰夫（保留） | 初中：joe/jeff后接moscow/toronto/boston人物与地名段；原raw和本地Jeff支持杰夫，保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L3114>) |
| 73 | `jenny` / Jenny | — | n.纺纱机 → **n.珍妮（女名）** | 初中：gina/jenny/alan/tom/mike连续人物段；外部Jenny明确珍妮女名，机械纺纱机或母驴义不适用。<br>[逐词记录](<../data/school_meaning_reviews.json#L3151>) |
| 74 | `jerry` / Jerry | — | n.〈英 → **n.杰里（男名）** | 初中：paula/alfred/billy/candy/jerry/emily连续人物段；本地Jerry给杰里男名，修复旧义n.〈英残缺串，不使用偷工减料义。<br>[逐词记录](<../data/school_meaning_reviews.json#L3194>) |
| 75 | `jessica` / Jessica | — | n.杰西卡（保留） | 初中：jason/hayes/jessica人物段；原bank.raw明确女子名，保留原杰西卡，不冒称本地杰茜卡为本次字面出处。<br>[逐词记录](<../data/school_meaning_reviews.json#L3236>) |
| 76 | `jim` / Jim | n.吉姆 → **n.吉姆（人名）** | n.吉姆（保留） | 小学：xx-yle2 的 Jane/Jim/Julia 人名尾段且原bank.raw 明示吉姆（人名）；保留吉姆中文并补人名身份。<br>初中：rick/jim/scott/tony连续人物段；原raw明确人名，吉姆正确保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L3267>) |
| 77 | `jimmy` / Jimmy | — | n.铁撬；vt.撬 → **n.吉米（男名）** | 初中：mario/jimmy在单元末人物段；外部本册课本例句译吉米，选该人名译写，不采用词条上杰米异译或铁撬动词义。<br>[逐词记录](<../data/school_meaning_reviews.json#L3329>) |
| 78 | `joe` / Joe | — | n.家伙 → **n.乔（男名）** | 初中：joe/jeff人物段；原bank.raw明确乔（男子名），本地Joe也给乔，改掉bank.s误取的家伙义。<br>[逐词记录](<../data/school_meaning_reviews.json#L3372>) |
| 79 | `john` / John | — | n.盥洗室 → **n.约翰（男名）** | 初中：sally/kate/paul/john连续人物段；外部John明确约翰男子名，不能使用盥洗室、厕所或俚语人群义。<br>[逐词记录](<../data/school_meaning_reviews.json#L3414>) |
| 80 | `johnny` / Johnny | — | n.男子 → **n.约翰尼（人名）** | 初中：johnny/dean、tina/jackson为人物段；bank.s已有约翰尼，本地Johnny同译，替换泛指男子/家伙，人物标签为语境校订。<br>[逐词记录](<../data/school_meaning_reviews.json#L3457>) |
| 81 | `julia` / Julia | n.朱莉娅 → **n.朱莉娅（女名）** | — | 小学：xx-yle2 中 Julia 连在 Jim/Lily/Mary 人名段，原bank.raw 为女子名；沿用朱莉娅并明确女名。<br>[逐词记录](<../data/school_meaning_reviews.json#L3499>) |
| 82 | `julie` / Julie | — | n.朱莉（保留） | 初中：julie/becky人物段；原raw明确朱莉女子名，保留；本地Julie行混入Thompson/Whitcomb文字，不把混串当本项字面依据。<br>[逐词记录](<../data/school_meaning_reviews.json#L3535>) |
| 83 | `karen` / Karen | — | n.凯伦（保留） | 初中：karen/ben/michael/laura/mills连续人物段；原raw凯伦人名支持现有译写，不取缅甸克伦邦。<br>[逐词记录](<../data/school_meaning_reviews.json#L3566>) |
| 84 | `kate` / Kate | — | n.凯特（保留） | 初中：sally/kate/paul/john连续人物段；原raw明确女子名，原义正确，不追加Catherine昵称解释。<br>[逐词记录](<../data/school_meaning_reviews.json#L3597>) |
| 85 | `katie` / Katie | — | n.卡蒂 → **n.凯蒂（女名）** | 初中：maria/katie/sato/marie人物段；本地Katie明确凯蒂女名，本次采用该教材译写，而非原bank卡蒂异译。<br>[逐词记录](<../data/school_meaning_reviews.json#L3628>) |
| 86 | `ken` / Ken | — | n.视野范围 → **n.肯（男名）** | 初中：andy/ken/hemingway/kelly人物段；本地大写Ken给肯男名，不用视野或知识范围。<br>[逐词记录](<../data/school_meaning_reviews.json#L3670>) |
| 87 | `kevin` / Kevin | — | n.凯文（保留） | 初中：matt/kevin/carl连续人物段；原raw及本地Kevin为凯文男名，原义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L3712>) |
| 88 | `kim` / Kim | n.金姆 → **n.金姆（人名）** | — | 小学：xx-yle1/2 的 Jill/Kim/Lucy 连续人名段且原bank.raw 标人名；沿用金姆译写，不无据改名或指定性别。<br>[逐词记录](<../data/school_meaning_reviews.json#L3749>) |
| 89 | `laura` / Laura | — | n.劳拉（保留） | 初中：两册分别为steve/laura、karen/ben/michael/laura/mills人物段；原raw明确女子名，保留劳拉。<br>[逐词记录](<../data/school_meaning_reviews.json#L3792>) |
| 90 | `lily` / Lily | n.百合 → **n.莉莉（人名）** | — | 小学：xx-yle2 的 Julia/Lily/Mary/Paul 人名尾段表明此处是 Lily 人名，不是百合植物或纯洁形容词。<br>[逐词记录](<../data/school_meaning_reviews.json#L3824>) |
| 91 | `linda` / Linda | — | n.琳达（保留） | 初中：mary/miller/linda/jane/smith连续人物段；原raw明确女子名，原义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L3860>) |
| 92 | `lisa` / Lisa | — | n.丽莎（保留） | 初中：musician后lisa/jill/peter人物段；原raw明确女子名，保留现有短义。<br>[逐词记录](<../data/school_meaning_reviews.json#L3891>) |
| 93 | `lucy` / Lucy | n.露西 → **n.露西（女名）** | n.露西（保留） | 小学：xx-yle1/2 的 Kim/Lucy/Mark 人名尾段及原bank.raw 女子名支持露西；仅补回女名，不取bank.s中另混的古人类化石说明。<br>初中：ear后lucy在词书末尾人物位置；原raw和本地Lucy均支持露西人名，不追加古人类化石义。<br>[逐词记录](<../data/school_meaning_reviews.json#L3922>) |
| 94 | `luke` / Luke | — | n.卢克（保留） | 初中：luke/brian/griffin/trent毕业单元人物段；原bank和本地Luke支持卢克男名，不追加路加福音。<br>[逐词记录](<../data/school_meaning_reviews.json#L3997>) |
| 95 | `mandy` / Mandy | — | n.曼蒂（保留） | 初中：judy/nancy/mandy人物段；原raw首义明确女子名，保留曼蒂，不带镇静片或药名。<br>[逐词记录](<../data/school_meaning_reviews.json#L4034>) |
| 96 | `marie` / Marie | — | n.玛丽（保留） | 初中：maria/katie/sato/marie人物段；原raw及本地Marie支持玛丽女名，保留，不指定玛丽·居里。<br>[逐词记录](<../data/school_meaning_reviews.json#L4065>) |
| 97 | `mario` / Mario | — | n.马里奥（保留） | 初中：sir/madam后mario/jimmy人物段；原raw明确男子名，保留原译，不据同名游戏添义。<br>[逐词记录](<../data/school_meaning_reviews.json#L4102>) |
| 98 | `mark` / Mark | n.痕迹 → **n.马克（人名）** | — | 小学：xx-yle1/2 的 Lucy/Mark/Matt/May 连续人名段应取 Mark 人名，不是痕迹或做记号动词。<br>[逐词记录](<../data/school_meaning_reviews.json#L4133>) |
| 99 | `mary` / Mary | n.玛丽 → **n.玛丽（女名）** | n.玛丽（保留） | 小学：xx-yle2 的 Lily/Mary/Paul/Peter 人名尾段与原bank.raw 女子名一致；沿用玛丽并补回女名。<br>初中：tom/mike/jack/mary/miller人物段；原raw明确女子名，原义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L4176>) |
| 100 | `matt` / Matt | adj.表面暗淡的 → **n.马特（人名）** | adj.表面暗淡的 → **n.马特（男名）** | 小学：xx-yle1/2 的 Mark/Matt/May/Nick 人名尾段应是 Matt 人名，不是表面暗淡无光泽形容词。<br>初中：matt/kevin/carl连续人物段；外部Matt明确马特男子名，表面暗淡或无光泽的形容词非本段含义。<br>[逐词记录](<../data/school_meaning_reviews.json#L4238>) |
| 101 | `michael` / Michael | — | n.迈克尔（保留） | 初中：karen/ben/michael/laura/mills/robert连续人物段；原raw明确男子名，迈克尔正确保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L4319>) |
| 102 | `mike` / Mike | — | vi.偷懒；n.休息 → **n.迈克（男名）** | 初中：gina/jenny/alan/tom/mike/jack/mary连续人名；外部Mike明确迈克男子名，不用偷懒、休息或话筒义。<br>[逐词记录](<../data/school_meaning_reviews.json#L4350>) |
| 103 | `miller` / Miller | — | n.厂主 → **n.米勒（姓）** | 初中：mary/miller/linda/jane/smith人物姓名段；可见词表文段明确Miller米勒姓，不取厂主、蛾或铣床。<br>[逐词记录](<../data/school_meaning_reviews.json#L4393>) |
| 104 | `mills` / Mills | — | n.米尔斯（保留） | 初中：karen/ben/michael/laura/mills/robert/hunt连续人物段；原raw确认米尔斯人名，外部词条确认姓氏译写，原短义正确保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L4436>) |
| 105 | `molly` / Molly | — | n.懦夫 → **n.莫莉（女名）** | 初中：clark/amy/molly人物段；外部姓名词条及课本例句确认人名，采用例句莫莉译写而非词条莫利，排除贬损俚语懦夫义。<br>[逐词记录](<../data/school_meaning_reviews.json#L4474>) |
| 106 | `ms` / Ms | abbr.毫秒 → **abbr.女士（用于女子姓名前）** | abbr.毫秒 → **n.女士（不指明婚姻状况）** | 小学：xx2-1 的日常问候及 xx-dg/xx-dg2011 的 Mr/Mrs/Ms 称谓段，配套课件 I’m Ms Smart 与词典姓名前称谓义一致；替换毫秒义。<br>初中：from/where/year/about/ms及mr/mrs/ms并列明确女性称谓；本地Ms和外部称谓义支持女士，不是毫秒、手稿或微软。<br>[逐词记录](<../data/school_meaning_reviews.json#L4517>) |
| 107 | `nancy` / Nancy | — | n.女性化的男人；adj.女性化的 → **n.南希（女名）** | 初中：judy/nancy/mandy连续人物段；外部Nancy明确南希女子名，排除原通用贬损俚语及形容词义。<br>[逐词记录](<../data/school_meaning_reviews.json#L4627>) |
| 108 | `nashville` / Nashville | — | n.那什维尔（保留） | 初中：record/introduce/line/alex/nashville/tennessee音乐与地名段；原raw明确田纳西州首府，原短义正确保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L4670>) |
| 109 | `nba` / NBA | — | abbr.全美篮球协会（保留） | 初中：Starter缩写段及professional/nba/cba篮球单元段；原raw完整National Basketball Association匹配，原义正确保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L4701>) |
| 110 | `nick` / Nick | n.监狱 → **n.尼克（人名）** | n.监狱；v.刻痕于 → **n.尼克（人名）** | 小学：xx-yle1/2 的 May/Nick/Pat/Sam 连续人名尾段应是 Nick 人名，不是监狱、警察局或刻痕。<br>初中：word后nick/james/white人物段；外部Nick人名例句译尼克，译名为语境校订，不把同页通用监狱/刻痕主释义当教材义。<br>[逐词记录](<../data/school_meaning_reviews.json#L4733>) |
| 111 | `north` | n.北（保留） | n.北；adj.北方的（保留） | 小学：xx2-6 的 east/north 方向词语境和原bank的北/北方名词义一致；原小学义正确，严格保留而不无谓简化或扩成多词性组。<br>初中：north/south/west、north/west/south/east及地图方向段明确方位；原名词和形容词两组均正确，原样保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L4814>) |
| 112 | `olympics` / Olympics | — | n.奥林匹克运动会（保留） | 初中：enjoyable/olympics/stadium体育段；原bank运动会义正确，不译为单一场地或其他组织。<br>[逐词记录](<../data/school_meaning_reviews.json#L4882>) |
| 113 | `pacific` / Pacific | — | n.太平洋；adj.太平洋的（保留） | 初中：pacific/ocean地理段以及旅游语境；原太平洋名词及形容词正确保留，不追加爱和平或平息等通用小写义。<br>[逐词记录](<../data/school_meaning_reviews.json#L4915>) |
| 114 | `pam` / Pam | — | 脉冲幅度调制 → **n.帕姆（人名）** | 初中：marcus/pam在单元专名段；外部Pam明确帕姆人名，不能把脉冲幅度调制或解磷定药名当教材义。<br>[逐词记录](<../data/school_meaning_reviews.json#L4949>) |
| 115 | `pat` / Pat | v.轻拍 → **n.帕特（人名）** | — | 小学：xx-yle1/2 中 Pat 连在 Nick/Sam/Sue 人名尾段；应取名字，不是轻拍动词或名词。<br>[逐词记录](<../data/school_meaning_reviews.json#L4992>) |
| 116 | `paul` / Paul | n.保罗 → **n.保罗（男名）** | n.保罗（保留） | 小学：xx-yle2 的 Mary/Paul/Peter 人名尾段与原bank.raw 男子名一致；保留保罗译写并补身份。<br>初中：sally/kate/paul/john连续人名；原raw明确男子名，保罗正确保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L5035>) |
| 117 | `paula` / Paula | — | n.宝拉（保留） | 初中：paula/alfred/billy/candy/jerry/emily连续人物段；采用bank.s已有宝拉，不冒称raw保拉或本地葆拉为本次字面出处。<br>[逐词记录](<../data/school_meaning_reviews.json#L5097>) |
| 118 | `peter` / Peter | vi.逐渐消失 → **n.彼得（人名）** | vi.逐渐消失 → **n.彼得（男名）** | 小学：xx-yle2 的 Paul/Peter/Sally/Vicky 连续人名段应是 Peter 名字，不是逐渐消失的 peter out 动词义。<br>初中：lisa/jill/peter人物段；外部Peter明确彼得男子名，逐渐消失是通用动词误套。<br>[逐词记录](<../data/school_meaning_reviews.json#L5128>) |
| 119 | `pole` | — | n.杆；v.用篙撑 → **n.杆，柱；n.极（点）** | 初中：两本拓展词书plain/platform/plough/poet/pole/polish词段不指人物；原raw有杆、柱、极点普通名词，选适合初中的两组，去掉罕用撑篙动词。<br>[逐词记录](<../data/school_meaning_reviews.json#L5202>) |
| 120 | `polish` | — | v.擦亮；n.上光剂（保留） | 初中：heat/polish/complete工艺段和拓展词表均支持擦亮；bank.raw也有上光剂，两组普通词义正确保留，不误判为Polish波兰语。<br>[逐词记录](<../data/school_meaning_reviews.json#L5239>) |
| 121 | `rick` / Rick | — | n.草堆；vt.把…堆成垛 → **n.里克（男名）** | 初中：rick/jim/scott/tony连续人物段；外部Rick明确里克男子名，草堆和堆垛动词不适用。<br>[逐词记录](<../data/school_meaning_reviews.json#L5272>) |
| 122 | `roy` / Roy | — | n.罗伊（保留） | 初中：nba/cba后roy/ruby人物段；原raw明确男子名，原短义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L5315>) |
| 123 | `rsvp` / RSVP | abbr.请回复（保留） | — | 小学：xx1-6 的 Christmas/game/riddle/act/RSVP/by 邀请活动词段且本地gloss明示请回复 Répondez s'il vous plaît；原小学义正确，严格保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L5346>) |
| 124 | `ruby` / Ruby | — | n.红宝石；adj.深红色的 → **n.鲁比（女名）** | 初中：roy/ruby在单元末人物段；BBC中文文章实际以Ruby对应女子名鲁比，采用该译写而非同页/通用词条红宝石、深红色义。<br>[逐词记录](<../data/school_meaning_reviews.json#L5388>) |
| 125 | `saint` | — | n.圣者；v.把…正式封为圣者 → **n.圣人，圣徒** | 初中：ruler/boil/remain/smell/saint发明与历史段；本地saint明确圣人、圣徒，去掉不适合本处的正式封圣动词义。<br>[逐词记录](<../data/school_meaning_reviews.json#L5431>) |
| 126 | `sally` / Sally | n.突击 → **n.萨莉（人名）** | n.突击；vi.突击 → **n.萨莉（女名）** | 小学：xx-yle2 的 Peter/Sally/Vicky/Zoe 连续人名尾段表明 Sally 名字，不是突击出击义。<br>初中：sally/kate/paul/john连续人名；外部Sally明确萨莉女子名，不用突击/出击。<br>[逐词记录](<../data/school_meaning_reviews.json#L5475>) |
| 127 | `sam` / Sam | 安全性帐户管理器 → **n.萨姆（人名）** | 安全性帐户管理器 → **n.萨姆（男名）** | 小学：xx-yle1/2 的 Pat/Sam/Sue/Tom 连续人名尾段应是 Sam 人名，不是安全性帐户管理器专业缩写。<br>初中：tara/sam/nelly/larry连续人名；与小学定稿统一萨姆译写，外部Sam人物例句实际使用萨姆异译；不冒称八上例句山姆为相同字面，排除安全账户管理器义。<br>[逐词记录](<../data/school_meaning_reviews.json#L5549>) |
| 128 | `sandy` / Sandy | — | adj.沙地的 → **n.桑迪（人名）** | 初中：unfair后sandy为单元人物名；外部本册课本例句Sandy and her mom译桑迪，人名译写取例句并编辑标注，不取该页含沙形容词。<br>[逐词记录](<../data/school_meaning_reviews.json#L5630>) |
| 129 | `sato` / Sato | — | abbr.自对准厚氧化物层 → **n.佐藤（日本姓）** | 初中：maria/katie/sato/marie连续人物段；本地Sato及外部姓名词条明确佐藤日本姓氏，绝非自对准厚氧化物层缩写。<br>[逐词记录](<../data/school_meaning_reviews.json#L5673>) |
| 130 | `scott` / Scott | — | n.斯科特（保留） | 初中：rick/jim/scott/tony连续人物段；原raw明确男子名，原义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L5722>) |
| 131 | `scrooge` / Scrooge | — | n.吝啬鬼 → **n.斯克鲁奇（小说人物）** | 初中：clara/scrooge单元专名段；本地给斯克鲁奇译名，教材阅读研究明确为圣诞欢歌主人翁，优先人物义，不只呈现泛称吝啬鬼。<br>[逐词记录](<../data/school_meaning_reviews.json#L5753>) |
| 132 | `smith` / Smith | — | n.铁匠 → **n.史密斯（姓）** | 初中：mary/miller/linda/jane/smith人物姓名段；可见词表文段明确Smith史密斯姓，不能按职业铁匠释义。<br>[逐词记录](<../data/school_meaning_reviews.json#L5802>) |
| 133 | `steen` / Steen | — | adj.许许多多的 → **n.斯蒂恩（姓）** | 初中：ted/may/vince/steen/jake/susan连续人物段；外部词条明确斯蒂恩姓氏且本册Ms. Steen例句证实人物称谓，不取umpteen俚语或乱猜译姓。<br>[逐词记录](<../data/school_meaning_reviews.json#L5845>) |
| 134 | `steve` / Steve | — | n.史蒂夫（保留） | 初中：living后steve/laura人物段；原raw明确男子名，原短义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L5888>) |
| 135 | `sue` / Sue | vt.控告 → **n.苏（人名）** | vt.控告；vi.提出诉讼 → **n.苏（人名）** | 小学：xx-yle1/2 的 Sam/Sue/Tom 人名尾段应取 Sue 名字，不是控告起诉动词。<br>初中：claire/sue在point后为人物段；外部课本例句you are Sue译苏，明确人名而非诉讼动词；不无证添加具体人物身份。<br>[逐词记录](<../data/school_meaning_reviews.json#L5919>) |
| 136 | `susan` / Susan | — | n.苏珊（保留） | 初中：vince/steen/jake/susan人物段；原raw明确女子名，原义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L6000>) |
| 137 | `sydney` / Sydney | n.悉尼（保留） | — | 小学：xx1-4 的 London/Moscow/Singapore/Sydney 城市段与 xx3-8 的 kangaroo/koala/Sydney/visitor 澳大利亚旅行语境都指悉尼城市；原小学义正确，保留而非误作同名人物。<br>[逐词记录](<../data/school_meaning_reviews.json#L6031>) |
| 138 | `taipei` / Taipei | n.台北（保留） | — | 小学：xx3-8 的 Disneyland/Taipei/photo/travel 旅行目的地邻段指台北；原bank及原小学义正确，严格保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L6074>) |
| 139 | `tara` / Tara | — | int.再会！ → **n.塔拉（女名）** | 初中：tara/sam/nelly/larry连续人名；外部Tara词条及本册Tina比较身高例句明确塔拉女名，不用再会感叹词。<br>[逐词记录](<../data/school_meaning_reviews.json#L6110>) |
| 140 | `taylor` / Taylor | — | n.泰勒（保留） | 初中：cathy/taylor在perhaps后为人物姓名段；原bank泰勒译写正确，保留人名，不追加数学专名或猜人物身份。<br>[逐词记录](<../data/school_meaning_reviews.json#L6153>) |
| 141 | `ted` / Ted | — | vt.翻晒 → **n.特德（男名）** | 初中：ted/may/vince/steen/jake/susan连续人物段；外部Ted明确特德男子名，翻晒动词不是该段教材义。<br>[逐词记录](<../data/school_meaning_reviews.json#L6184>) |
| 142 | `thanksgiving` / Thanksgiving | n.感恩 → **n.感恩节** | n.感恩 → **n.感恩节** | 小学：xx1-6 中 American/Thanksgiving/Christmas 和 xx2-7 的 special/meal 节日语境指感恩节；原bank.raw 已为感恩节，恢复被bank.s截成感恩而丢掉的节字。<br>初中：turkey/lettuce/piece/thanksgiving/traditional/autumn/celebrate节日食物段；原bank.raw是感恩节，修复旧义丢失节字，拒绝本地普通感谢义套用。<br>[逐词记录](<../data/school_meaning_reviews.json#L6227>) |
| 143 | `they're` | abbr.他们是 → **abbr.他们（她们、它们）是** | — | 小学：xx2-2 和 xx3-2 两份本地gloss均为 = they are，且邻段 monkey/zoo/pig/cow 有动物；原仅他们是偏窄，补齐同一复数代词义的她们/它们，仍是一组缩约义。<br>[逐词记录](<../data/school_meaning_reviews.json#L6303>) |
| 144 | `tim` / Tim | — | n.蒂姆（保留） | 初中：italian/tim/humorous单元人物分界；原raw及本地Tim为蒂姆男名，原义正确。<br>[逐词记录](<../data/school_meaning_reviews.json#L6358>) |
| 145 | `tina` / Tina | — | n.蒂娜（保留） | 初中：johnny/dean/tina/jackson人物姓名段；原raw及本地Tina支持蒂娜，保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L6395>) |
| 146 | `tom` / Tom | n.雄性动物 → **n.汤姆（人名）** | n.雄性动物 → **n.汤姆（男名）** | 小学：xx-yle1/2 的 Sam/Sue/Tom 人名尾段应为 Tom 人名，而非雄性动物或雄猫。<br>初中：gina/jenny/alan/tom/mike/jack/mary连续人物段；外部Tom明确汤姆男子名，雄性动物/雄猫不是该段教材义。<br>[逐词记录](<../data/school_meaning_reviews.json#L6432>) |
| 147 | `tony` / Tony | — | adj.高贵的 → **n.托尼（男名）** | 初中：rick/jim/scott/tony连续人物段；外部Tony明确托尼男子名，不用高贵的、时髦的形容词。<br>[逐词记录](<../data/school_meaning_reviews.json#L6513>) |
| 148 | `toronto` / Toronto | — | n.多伦多（保留） | 初中：moscow/toronto/boston连续地名段；原raw与本地Toronto明确加拿大城市，保留正确短义。<br>[逐词记录](<../data/school_meaning_reviews.json#L6556>) |
| 149 | `trent` / Trent | — | n.特伦特（保留） | 初中：luke/brian/griffin/trent毕业单元人物段；本地Trent明确姓氏，原短译特伦特正确保留，不采raw男子名限定或河流义。<br>[逐词记录](<../data/school_meaning_reviews.json#L6593>) |
| 150 | `vera` / Vera | — | abbr.通用实验性反应堆装置 → **n.维拉（女名）** | 初中：greg/danny/eliza/vera/dennis连续人物段；外部Vera明确维拉女子名，反应堆装置缩写不适用。<br>[逐词记录](<../data/school_meaning_reviews.json#L6630>) |
| 151 | `vicky` / Vicky | n.维姬 → **n.维姬（女名）** | — | 小学：xx-yle2 的 Sally/Vicky/Zoe 人名尾段与原bank.raw 女子名一致；沿用维姬并补回女名说明。<br>[逐词记录](<../data/school_meaning_reviews.json#L6673>) |
| 152 | `victor` / Victor | — | n.胜利者 → **n.维克托（男名）** | 初中：carla/victor/jean连续人物段；本地大写Victor明确维克托男名，不用胜利者的普通名词义。<br>[逐词记录](<../data/school_meaning_reviews.json#L6709>) |
| 153 | `vince` / Vince | — | n.文斯（保留） | 初中：ted/may/vince/steen/jake/susan连续人物段；原raw明确男子名，文斯正确保留。<br>[逐词记录](<../data/school_meaning_reviews.json#L6751>) |
| 154 | `westerner` / Westerner | — | n.西方人（保留） | 初中：fork/spoon/cheeseburger/italian/westerner/west/serve餐桌文化段；原西方人义正确保留，不增美国西部居民义。<br>[逐词记录](<../data/school_meaning_reviews.json#L6782>) |
| 155 | `word` | n.字 → **n.单词，词** | n.字；vt.措辞 → **n.单词，词** | 小学：xx1-7 的 dictionary/comic/word 读写购书语境和 xx-yle1/2 的 teacher/tell/understand/word/write 学习语境指单词、词；原仅字易误解为字母字符，恢复原bank.raw已有的词/单词。<br>初中：pair/correct/spelling/word/practise/match/meaning学习词汇语境；原raw有词、单词，修复过窄字义并去掉罕用措辞动词。<br>[逐词记录](<../data/school_meaning_reviews.json#L6813>) |
| 156 | `wwf` / WWF | — | abbr.世界野生动物基金 → **abbr.世界自然基金会** | 初中：iron/work/metal/creativity/wwf环保单元段；机构中文名称与环保用例确认世界自然基金会，补完整机构名，不引入摔跤联合会或雨天流量。<br>[逐词记录](<../data/school_meaning_reviews.json#L6920>) |
| 157 | `x-ray` / X-ray | — | n.射线；v.用 X 光拍片 → **n.X射线，X光；n.X光照片** | 初中：fever/rest/cough/x-ray/toothache医疗段及coal/energy/x-ray/experiment科学段；原raw含X射线、X光照片，修复丢X的射线，选择初中常用两组名词。<br>[逐词记录](<../data/school_meaning_reviews.json#L6970>) |
| 158 | `zoe` / Zoe | n.生命 → **n.佐伊（人名）** | — | 小学：xx-yle2 的 Paul/Peter/Sally/Vicky/Zoe 人名尾段表明 Zoe 名字；原生命是词源或别义，不能作为这里的人名释义。<br>[逐词记录](<../data/school_meaning_reviews.json#L7012>) |

## 使用与验证

生成器严格固定158/183集合和四原始输入指纹；只有明确 `--write` 才生成覆盖。校订行的来源指向本校订表，未校订行仍按原片段回查。完整实现说明和回归命令见 [覆盖层说明](<level-meanings.md>)；本轮独立隔离/原生验收见 [V1.3.5验收记录](<acceptance-v135.md>)。
