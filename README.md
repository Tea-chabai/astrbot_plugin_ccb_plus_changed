# C C B PLUS!!!

和 QQ 群群友发生赛博 sex 的 AstrBot 插件，基于 [Koikokokokoro / ccbPlus](https://github.com/Koikokokokoro/astrbot_plugin_ccb_plus) 与 [tnno1174 / dajiao](https://github.com/tenno1174/astrbot_plugin_dajiao) 融合改进。

## ✨ 功能特色

1. 新增百合互扣（`/bh`），被扣者喷出 B 水并计入独立数据
2. 后接 QQ 号即可发起 ccb/百合，无需 @（有人反馈被 @ 很烦）
3. 独立自交（`/dj`），可配置扣B / 打胶两种模式，数据分文件存储
4. 优化了部分露骨文字**（太容易被销号了😋）**
5. 优化了部分石山~~（claude 倾情提供）~~

## 📖 命令列表

### 📊 每日统计（当日数据，每日自动重置）

| 命令 | 说明 |
|---|---|
| `/ccbtop` `/ccbvol` `/ccbmax` | 今日被C次数 / 今日注入量 / 今日单次MAX |
| `/ccbinfo [@]` | 今日统计（被超/发起/注入/MAX/13水/百合/喝奈） |
| `/xnn` | 今日小南梁榜 |
| `/djtop` `/djmax` | 今日自交次数 / 今日单次最高（按配置模式） |
| `/bhtop` | 今日百合被扣榜 |
| `/hntop` `/hninfo [@]` | 今日泌乳榜 / 今日泌乳查询 |

### 🗃️ 累计统计（长期数据，不重置）

| 命令 | 说明 |
|---|---|
| `/ccbtopall` `/ccbvolall` `/ccbmaxall` | 累计被C次数 / 累计注入量 / 累计单次MAX |
| `/ccbinfoall [@]` | 累计统计查询 |
| `/xnnall` | 累计小南梁榜 |
| `/djtopall` `/djmaxall` | 累计自交榜（按配置模式） |
| `/bhtopall` | 累计百合榜 |
| `/hntopall` `/hninfoall [@]` | 累计泌乳榜 / 累计泌乳查询 |

### 🎮 行为命令

| 命令 | 说明 |
|---|---|
| `/ccb [@或QQ号]` | 和群友互C；不带目标时为自交（0721） |
| `/dj` | 自交（按配置：B=扣B记13水，d=打胶记生命因子） |
| `/bh [@或QQ号]` | 百合互扣；不带目标时为自交 |
| `/hnn [@或QQ号]` | 喝奈奈：从目标汲取奶喝，无@时自取其乳（受禁C名单控制） |
| `/ccbclear [@或QQ号]` | 管理员：清除互C记录（dj_mode=d 时连带打胶数据） |
| `/bhclear [@或QQ号]` | 管理员：清除百合记录（dj_mode=B 时连带自扣13水数据） |
| `/hnclear [@或QQ号]` | 管理员：清除喝奈记录（含他人记录中的痕迹） |
| `/ccbnodo [@或QQ号]` | 管理员：禁C名单切换（双向禁C，仍可自交） |
| `/timeclear [@或QQ号]` | 管理员：强制结束指定用户的神罚/昏厥冷却 |

## ⚙️ 配置

AstrBot 配置面板可调：阳痿/昏厥概率与时长、窗口限流（次数/时长）、暴击概率、`dj_mode`（扣B/打胶）、打胶昏厥概率、禁C名单、完整日志开关、头像显示（`show_avatar` 对他人互动 / `show_self_avatar` 自交）等。

## 💾 数据文件

存放于 `data/plugin_data/astrbot_plugin_ccb_plus_changed/`：

| 文件 | 内容 |
|---|---|
| `ccb.json` | 互C记录（生命因子） |
| `dj.json` | 打胶记录（生命因子） |
| `dj_b.json` | 扣B记录（13水 / B_max） |
| `bh.json` | 百合被扣记录 |
| `hn.json` | 喝奈/泌乳记录 |
| `ccb_log.json` | 完整日志（可选，`is_log` 开启时写入） |
| `daily.db` | 每日统计（sqlite，次日自动重置） |

## 🔄 数据迁移

> ⚠️ **更新前建议备份数据文件**，可能出现意料外的错误。

旧版数据存放在 `data/` 目录下。本版本起数据不再自动迁移，请手动操作：

1. 停止 AstrBot
2. 将旧目录下的文件复制到上述新目录：
   - `data/ccb.json` → `ccb.json`（互C记录）
   - `data/ccb_log.json` → `ccb_log.json`（如有）
   - `data/dj.json`、`data/dj_b.json`、`data/bh.json`（如有）
3. 启动 AstrBot，旧 ccb.json 中残留的 B 水字段会自动拆分到 `dj_b.json`

新装用户无需任何操作，目录会自动创建。

## 📥 安装

1. 获取插件：直接 git clone / download zip ~~才不是 release 懒得更新~~ 
2. AstrBot 管理面板 → 插件管理 → 本地插件安装，选择 zip 包

> 此插件目前仍在更新，想要什么功能去 [issues](https://github.com/Koikokokokoro/astrbot_plugin_ccb_plus/issues) 提，能满足的尽量满足。

## ⚠️ 风险提示

内容比较露骨，~~过不了插件市场审核呜呜~~，使用请注意封号风险😋
