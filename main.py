# -- coding: utf-8 --
"""
CCB PLUS 插件入口：仅负责命令注册与编排。
逻辑层见 core.py（状态/目标解析/自交演出），数据层见 storage.py（JSON读写/统计/迁移）。
"""
import time
import random
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp

from .back import time_long, volume
from .storage import (
    DataStore,
    a1, a2, a3, a4, a5, a8, a9, a10, d_num, d_vol, d_max, bh_num, bh_vol,
    hn_num, hn_vol, hn_max, hn_first,
)
from .core import StateKeeper, makeit, get_avatar

HELP_INFO = """
/ccb ccb，顾名思义，用来ccb 用法： ccb [@或QQ号]，如果不带有@某人则根据配置文件进行自交或者打胶
/ccbinfo  查询某人ccb信息：第一次对他ccb的人，被ccb的总次数，注入总量，用法：ccbinfo [@目标]
/ccbtop 按次数排行
/ccbmax 按max值排行并输出产生者
/ccbvol 按注入量排行
/xnn XNN榜 计算群中最xnn特质的群友
/dj 自交功能：按配置文件模式执行（B=扣B记录13水，d=打胶记录生命因子），不改变处女状态，可能昏厥（概率可配置）
/djtop 自交榜：按自交次数排行（数据按配置模式）
/djmax 自交榜：按单次最高排行（数据按配置模式）
/bh 百合：和群友互扣，被扣的人喷出B水并记录，用法：bh [@目标或QQ号]
/bhtop 百合榜：按被扣次数排行
/hn 喝奈：从目标汲取奶喝，无@时自取其乳，用法：hn [@或QQ号]（受禁C名单控制）
/hninfo  查询泌乳信息：初乳被谁喝了、单次最大泌乳、累计泌乳，用法：hninfo [@目标]
/hntop 泌乳榜：按喂养次数排行
/ccbclear   管理员指令：清除某人的所有 CCB 记录，用法：ccbclear [@目标]
/ccbnodo  管理员指令：切换目标禁C状态，用法：ccbnodo [@目标或QQ号]（禁C者不能主动C别人、也不能被C，但仍可自交）
/timeclear   管理员指令：强制结束指定用户的神罚/昏厥冷却，用法：timeclear [@目标或QQ号]（不带目标默认清除自己）

根据配置文件可调控炸膛的概率

享受赛博打胶与ccb吧🦌🦌🦌
"""


@register("ccb", "Koikokokokoro", "和群友赛博sex的插件PLUS", "1.1.4")
class ccb(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.state = StateKeeper(config)                 # 逻辑层：冷却状态/目标解析/自交演出
        self.store = DataStore(self.state.dj_mode)       # 数据层：JSON读写/统计
        # 注意：旧版 data/ 相对路径的数据不会自动迁移，请参照 README 手动复制到 plugin_data 目录
        self.store.migrate_legacy_b_data()               # 旧版 ccb.json 中的B水字段迁移到 dj_b.json

    #  from issue 6
    async def _is_admin(self, event: AstrMessageEvent) -> bool:
        try:
            return bool(event.is_admin())
        except Exception:
            return False

    def _save_white_list(self):
        try:
            self.config["white_list"] = self.state.white_list
            save_fn = getattr(self.config, "save", None)
            if callable(save_fn):
                save_fn()
        except Exception as e:
            logger.warning(f"保存白名单失败: {e}")

    async def _get_nickname(self, event: AstrMessageEvent, user_id: str) -> str:
        """
        获取用户昵称：不再硬编码平台（napcat 的 aiocqhttp 只是其中一种）。
        只要 event 暴露 bot.api.call_action 就尝试：
        OneBot v11 用 get_stranger_info（返回 nick），OneBot v12 用 get_user_info（返回 user_name）。
        全部失败或平台不支持时回退为 QQ号。
        """
        nickname = user_id
        try:
            bot = getattr(event, "bot", None)
            api = getattr(bot, "api", None) if bot is not None else None
            if api is None or not hasattr(api, "call_action"):
                return nickname
            for action in ("get_stranger_info", "get_user_info"):
                try:
                    info = await api.call_action(action, user_id=user_id) or {}
                    # 字段兼容：nick=NapCat等兼容层字段，nickname=OneBot v11 标准字段（SnowLuma等），
                    # user_name/user_displayname=OneBot v12 字段
                    nick = (info.get("nick")
                            or info.get("nickname")
                            or info.get("user_name")
                            or info.get("user_displayname"))
                    if nick:
                        return str(nick)
                except Exception:
                    continue
        except Exception:
            pass
        return nickname

    # 获取目标用户ID（查询/管理命令用：优先@，默认自己，无需群验证）
    def _get_target_user_id(self, event: AstrMessageEvent) -> str:
        self_id = str(event.get_self_id())
        return next(
            (str(seg.qq) for seg in event.get_messages()
             if isinstance(seg, Comp.At) and str(seg.qq) != self_id),
            str(event.get_sender_id())
        )

    @filter.command("ccbhelp")
    async def get_help(self, event: AstrMessageEvent):
        """
        显示帮助信息
        """
        yield event.plain_result(HELP_INFO)

    @filter.command("ccb")
    async def ccb(self, event: AstrMessageEvent):
        """
        ccb，顾名思义，用来ccb
        用法： ccb [@或QQ号]
        """
        group_id = str(event.get_group_id())
        send_id = str(event.get_sender_id())
        user_name = str(event.get_sender_name())
        actor_id = send_id
        now = time.time()
        f_now = time.time()
        # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
        target_user_id, err = await self.state.resolve_target(event, str(event.message_str), group_id)
        if err:
            yield event.plain_result(err)
            return

        faint_time = self.state.faint_time()

        yw_prob_r1 = random.random()
        if yw_prob_r1 < self.state.yw_prob:
            yw_prob_r = yw_prob_r1
            faint_prob_r = 1.0
        else:
            faint_prob_r = random.random()
            yw_prob_r = 1.0

        # 神罚检查（独立）
        ban_msg = self.state.check_ban(actor_id, user_name)
        if ban_msg:
            yield event.plain_result(ban_msg)
            return
        # 昏厥检查（独立）
        faint_msg = self.state.check_faint(actor_id, user_name)
        if faint_msg:
            yield event.plain_result(faint_msg)
            return
        faint_end_target = self.state.faint_list.get(target_user_id, 0)

        # 滑窗限流（ccb/bh/dj 共用同一窗口计数与约束）
        rate_msg = self.state.rate_limit(actor_id, now)
        if rate_msg:
            yield event.plain_result(rate_msg)
            return

        # 自交（0721）：固定扣B，不改变处女状态。禁C名单用户也可自交
        if target_user_id == actor_id:
            if not self.state.selfdo:
                chain = [Comp.Plain(f"{user_name}，暂时不允许自交哦！")]
                yield event.chain_result(chain)
                return
            yield event.chain_result(self.state.self_play(self.store, group_id, send_id, user_name, faint_time))
            return

        # 禁C名单：名单内用户不能发起与他人的ccb（但可自交，也可/dj）
        if actor_id in self.state.white_list:
            yield event.plain_result("神明剥夺了你求偶的权力，你无法发起ccb/百合")
            return

        # 禁C名单：名单内用户不能被他人ccb
        if target_user_id in self.state.white_list:
            nickname = await self._get_nickname(event, target_user_id)
            yield event.plain_result(f"{nickname}对方拒绝了和你ccb/百合")
            return

        # CCB 逻辑
        duration = round(random.uniform(0.1, 60), 2)
        V = round(random.uniform(0.01, 100), 2)
        user_name = event.get_sender_name()
        is_log = self.state.is_log
        if random.random() < self.state.crit_prob:
            V = round(V * 2, 2)

        pic = get_avatar(target_user_id)

        all_data = self.store.read_ccb()
        group_data = all_data.get(group_id, [])

        mode = makeit(group_data, target_user_id)
        if mode == 1:
            # 已有记录，更新
            try:
                for item in group_data:
                    if item.get(a1) == target_user_id:
                        # 获取昵称
                        nickname = await self._get_nickname(event, target_user_id)

                        # 更新 num / vol / ccb_by
                        item[a2] = int(item.get(a2, 0)) + 1
                        item[a3] = round(float(item.get(a3, 0)) + V, 2)

                        # 添加逻辑：记录max值的产生者
                        ccb_by = item.get(a4, {}) or {}
                        if send_id in ccb_by:
                            ccb_by[send_id]["count"] = ccb_by[send_id].get("count", 0) + 1
                            ccb_by[send_id]["first"] = ccb_by[send_id].get("first", False)
                        else:
                            ccb_by[send_id] = {"count": 1, "first": False, "max": False}

                        # 计算max
                        raw_prev = item.get(a5, None)
                        prev_max = 0.0
                        if raw_prev is not None:
                            try:
                                prev_max = float(raw_prev)
                            except (TypeError, ValueError):
                                prev_max = 0.0
                        # 如果不存在合法的 max，使用平均值
                        if prev_max == 0.0:
                            try:
                                total_vol = float(item.get(a3, 0))
                                total_num = int(item.get(a2, 0))
                                if total_num > 0:
                                    prev_max = round(total_vol / total_num, 2)
                                else:
                                    prev_max = 0.0
                            except Exception:
                                prev_max = 0.0

                        if float(V) > prev_max:
                            item[a5] = round(float(V), 2)
                            for k in ccb_by:
                                ccb_by[k]["max"] = False
                            ccb_by[send_id]["max"] = True
                        else:
                            for k in ccb_by:
                                if "max" not in ccb_by[k]:
                                    ccb_by[k]["max"] = False

                        item[a4] = ccb_by
                        # 随机养胃
                        if yw_prob_r < self.state.yw_prob:
                            self.state.ban_list[actor_id] = now + self.state.ban_duration
                            m, s = divmod(int(self.state.ban_duration), 60)

                            chain = [
                                Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                                Comp.Image.fromURL(pic),
                                Comp.Plain(f"这是ta的第{item[a2]}次。ta被累积注入了{item[a3]}ml的生命因子。\n"),
                                Comp.Plain("-----------------------------\n"),
                                Comp.Plain(f"同时神明看你不顺眼，降下{m}分{s}秒的神罚")
                            ]
                            yield event.chain_result(chain)

                        # 目标正处于昏厥中（faint_end_target 为0表示从未昏厥，不满足 f_now <= 0）
                        elif f_now <= faint_end_target:
                            remain = int(faint_end_target - f_now)
                            m1, s1 = divmod(remain, 60)
                            chain = [
                                Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                                Comp.Image.fromURL(pic),
                                Comp.Plain(f"这是ta的第{item[a2]}次。ta被累积注入了{item[a3]}ml的生命因子。\n"),
                                Comp.Plain("-----------------------------\n"),
                                Comp.Plain(f"同时{nickname}现在正处于昏厥中,ta现在什么也干不了,剩余 {m1}分{s1}秒")
                            ]
                            yield event.chain_result(chain)

                        # 随机昏厥
                        elif faint_prob_r < self.state.faint_prob:
                            self.state.faint_list[target_user_id] = f_now + faint_time
                            # 注意：faint_end_target 是命令开头读取的旧值（目标此前未昏厥时为0），
                            # 触发后必须用本次的 faint_time 计算剩余时间，否则会出现负数
                            remain = int(faint_time)
                            m1, s1 = divmod(remain, 60)
                            chain = [
                                Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                                Comp.Image.fromURL(pic),
                                Comp.Plain(f"这是ta的第{item[a2]}次。ta被累积注入了{item[a3]}ml的生命因子。\n"),
                                Comp.Plain("----------------------------------\n"),
                                Comp.Plain(f"同时{nickname} 被 {user_name} C晕了,接下来ta将毫无还手之力,剩余 {m1}分{s1}秒")
                            ]
                            yield event.chain_result(chain)

                        else:
                            chain = [
                                Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                                Comp.Image.fromURL(pic),
                                Comp.Plain(f"这是ta的第{item[a2]}次。ta被累积注入了{item[a3]}ml的生命因子。")
                                ]
                            yield event.chain_result(chain)

                        # 是否保留完整日志
                        if is_log:
                            try:
                                self.store.append_log(group_id, send_id, target_user_id, duration, V)
                            except Exception as e:
                                logger.warning(f"记录日志失败: {e}")

                        # 写回数据
                        all_data[group_id] = group_data
                        self.store.write_ccb(all_data)
                        return
            except Exception as e:
                logger.error(f"报错: {e}")
                yield event.plain_result("对方拒绝了和你ccb")
                return

        else:
            # 新记录
            try:
                nickname = await self._get_nickname(event, target_user_id)

                # 随机养胃
                if yw_prob_r < self.state.yw_prob_first:
                    self.state.ban_list[actor_id] = now + self.state.ban_duration
                    m, s = divmod(int(self.state.ban_duration), 60)
                    chain = [
                    Comp.Plain(f"{user_name} 和 {nickname}发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                    Comp.Image.fromURL(pic),
                    Comp.Plain("这是ta的初体验~，你把人家的处给破了喵～要负责哦喵～\n"),
                    Comp.Plain("----------------------------------\n"),
                    Comp.Plain(f"同时神明看你不顺眼，降下{m}分{s}秒的神罚")
                    ]
                    yield event.chain_result(chain)

                # 随机昏厥
                elif faint_prob_r < self.state.faint_prob_first:
                    self.state.faint_list[target_user_id] = f_now + faint_time
                    chain = [
                    Comp.Plain(f"{user_name} 和 {nickname}发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                    Comp.Image.fromURL(pic),
                    Comp.Plain("这是ta的初体验~，你把人家的处给破了喵～要负责哦喵～\n"),
                    Comp.Plain("----------------------------------\n"),
                    Comp.Plain(f"同时{nickname}被{user_name}C晕了,接下来ta将毫无还手之力")
                    ]
                    yield event.chain_result(chain)

                else:
                    chain = [
                        Comp.Plain(f"{user_name} 和 {nickname}发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                        Comp.Image.fromURL(pic),
                        Comp.Plain("这是ta的初体验~，你把人家的处给破了喵～要负责哦喵～")
                    ]
                    yield event.chain_result(chain)

                # 保存首次被C记录：可能已存在只含B水统计的打胶记录，原地更新以保留B水数据
                existing = next((r for r in group_data if r.get(a1) == target_user_id), None)
                if existing is not None:
                    existing[a2] = 1
                    existing[a3] = round(V, 2)
                    existing[a4] = {send_id: {"count": 1, "first": True, "max": True}}
                    existing[a5] = round(V, 2)
                else:
                    group_data.append({
                        a1: target_user_id,
                        a2: 1,
                        a3: round(V, 2),
                        a4: {send_id: {"count": 1, "first": True, "max": True}},
                        a5: round(V, 2)
                    })
                all_data[group_id] = group_data
                self.store.write_ccb(all_data)

                # 是否保留完整日志
                if is_log:
                    try:
                        self.store.append_log(group_id, send_id, target_user_id, duration, V)
                    except Exception as e:
                        logger.warning(f"记录日志失败: {e}")
                return
            except Exception as e:
                logger.error(f"报错: {e}")
                yield event.plain_result("对方拒绝了和你ccb")
                return

    @filter.command("ccbtop")
    async def ccbtop(self, event: AstrMessageEvent):
        """
        按次数排行
        """
        group_id = str(event.get_group_id())
        group_data = self.store.read_ccb().get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        top5 = sorted(group_data, key=lambda x: int(x.get(a2, 0) or 0), reverse=True)[:5]
        msg = "被ccb排行榜 TOP5：\n"
        for i, r in enumerate(top5, 1):
            uid = r[a1]
            nick = await self._get_nickname(event, uid)
            msg += f"{i}. {nick} - 被超：{int(r.get(a2, 0) or 0)}次，累计被注入{float(r.get(a3, 0) or 0):.2f}ml\n"
        yield event.plain_result(msg)

    @filter.command("ccbvol")
    async def ccbvol(self, event: AstrMessageEvent):
        """
        按注入量排行
        """
        group_id = str(event.get_group_id())
        group_data = self.store.read_ccb().get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        top5 = sorted(group_data, key=lambda x: float(x.get(a3, 0)), reverse=True)[:5]
        msg = "被注入量排行榜 TOP5：\n"
        for i, r in enumerate(top5, 1):
            uid = r[a1]
            nick = await self._get_nickname(event, uid)
            msg += f"{i}. {nick} - 共被注入：{float(r[a3]):.2f}ml\n"
        yield event.plain_result(msg)

    @filter.command("ccbinfo")
    async def ccbinfo(self, event: AstrMessageEvent):
        """
        查询某人ccb信息：第一次对他ccb的人，被ccb的总次数，注入总量
        用法：ccbinfo [@目标]
        """
        group_id = str(event.get_group_id())
        target_user_id = self._get_target_user_id(event)

        # 读取群数据
        group_data = self.store.read_ccb().get(group_id, [])

        # 查找目标记录
        record = next((r for r in group_data if r.get(a1) == target_user_id), None)
        if not record:
            yield event.plain_result("该用户暂无ccb记录。")
            return

        # 总次数 & 总注入量
        total_num = int(record.get(a2, 0))
        total_vol = float(record.get(a3, 0))

        raw_max = record.get(a5, None)
        max_val = 0.0
        try:
            if raw_max is not None:
                max_val = float(raw_max)
            else:
                if total_num > 0:
                    max_val = round(total_vol / total_num, 2)
        except Exception:
            max_val = 0.0

        # 计算ccb次数
        cb_total = 0
        try:
            for rec in group_data:
                by = rec.get(a4, {}) or {}
                info = by.get(target_user_id)
                if info:
                    cb_total += int(info.get("count", 0))
        except Exception:
            cb_total = 0

        # 找出第一次的操作者
        ccb_by = record.get(a4, {})
        first_actor = None
        for actor_id, info in ccb_by.items():
            if info.get("first"):
                first_actor = actor_id
                break

        # 如果没标记 first，就选 count 最大的作为“首位”
        if not first_actor and ccb_by:
            first_actor = max(ccb_by.items(), key=lambda x: x[1].get("count", 0))[0]

        # 获取昵称
        first_nick = first_actor or "未知"
        if first_actor:
            first_nick = await self._get_nickname(event, first_actor)

        # 自交统计（按配置模式显示：扣B=13水，打胶=生命因子，数据来自独立文件）
        if self.state.dj_mode == "d":
            rec = self.store.get_group_data("dj.json", group_id).get(target_user_id, {})
            num_k, vol_k, max_k, label, unit = d_num, d_vol, d_max, "打胶", "生命因子"
        else:
            rec = self.store.get_group_data("dj_b.json", group_id).get(target_user_id, {})
            num_k, vol_k, max_k, label, unit = a10, a8, a9, "13水", "ml"
        dj_num = int(rec.get(num_k, 0) or 0)
        dj_vol = float(rec.get(vol_k, 0) or 0)
        dj_max = float(rec.get(max_k, 0) or 0)

        # 百合统计（互扣，独立于 dj_mode；单次最高直接复用扣B的B_max）
        bh_rec = self.store.get_group_data("bh.json", group_id).get(target_user_id, {})
        bh_n = int(bh_rec.get(bh_num, 0) or 0)
        bh_v = float(bh_rec.get(bh_vol, 0) or 0)
        bh_m = float(self.store.get_group_data("dj_b.json", group_id).get(target_user_id, {}).get(a9, 0) or 0)

        # 输出结果（第一行显示昵称而非QQ号）
        target_nick = await self._get_nickname(event, target_user_id)
        msg = (
            f"【{target_nick} 】\n"
            f"• 破壁人：{first_nick}\n"
            f"• ccb：被超:{total_num}(发起ccb:{cb_total},被注入:{total_vol:.2f}ml,MAX:{max_val:.2f}ml)"
        )
        if dj_num > 0:
            msg += f"\n• {label}：{dj_vol:.2f}{unit}（{dj_num}次，单次最高{dj_max:.2f}ml）"
        if bh_n > 0:
            msg += f"\n• 百合：{bh_v:.2f}ml（被扣{bh_n}次，单次最高{bh_m:.2f}ml）"
        yield event.plain_result(msg)

    # 单次注入排行榜
    @filter.command("ccbmax")
    async def ccbmax(self, event: AstrMessageEvent):
        """
        按max值排行并输出产生者
        """
        group_id = str(event.get_group_id())
        group_data = self.store.read_ccb().get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        # 计算max
        entries = []
        for r in group_data:
            raw_max = r.get(a5, None)
            max_val = 0.0
            try:
                if raw_max is not None:
                    max_val = float(raw_max)
                else:
                    total_vol = float(r.get(a3, 0))
                    total_num = int(r.get(a2, 0))
                    if total_num > 0:
                        max_val = round(total_vol / total_num, 2)
            except Exception:
                max_val = 0.0
            entries.append((r, float(max_val)))

        # 排序
        entries.sort(key=lambda x: x[1], reverse=True)
        top5 = entries[:5]

        msg = "单次最大注入排行榜 TOP5：\n"
        for i, (r, max_val) in enumerate(top5, 1):
            uid = r.get(a1)
            # 解析产生者
            producer_id = None
            ccb_by = r.get(a4, {}) or {}
            for actor_id, info in ccb_by.items():
                if info.get("max"):
                    producer_id = actor_id
                    break
            # 若没有显式标记，则回退选取count最大者
            if not producer_id and ccb_by:
                try:
                    producer_id = max(ccb_by.items(), key=lambda x: x[1].get("count", 0))[0]
                except Exception:
                    producer_id = None

            # 获取昵称
            nick = await self._get_nickname(event, uid)
            producer_nick = producer_id or "未知"
            if producer_id:
                producer_nick = await self._get_nickname(event, producer_id)

            msg += f"{i}. {nick} - MAX注入：{max_val:.2f}ml（{producer_nick}）\n"

        yield event.plain_result(msg)

    @filter.command("xnn")
    async def xnn(self, event: AstrMessageEvent):
        """
        XNN榜
        计算群中最xnn特质的群友
        """
        # 配置权重
        w_num = 1.0
        w_vol = 0.1
        w_action = 0.5

        group_id = str(event.get_group_id())
        group_data = self.store.read_ccb().get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        # 统计每个人对别人的操作次数
        actor_actions = {}
        for record in group_data:
            ccb_by = record.get(a4, {})
            for actor_id, info in ccb_by.items():
                actor_actions[actor_id] = actor_actions.get(actor_id, 0) + info.get("count", 0)

        # 计算xnn值
        ranking = []
        for record in group_data:
            uid = record.get(a1)
            num = int(record.get(a2, 0))
            vol = float(record.get(a3, 0))
            actions = actor_actions.get(uid, 0)
            xnn_value = num * w_num + vol * w_vol - actions * w_action
            ranking.append((uid, xnn_value))

        # 排序
        ranking.sort(key=lambda x: x[1], reverse=True)
        top5 = ranking[:5]

        # 构造输出
        msg = "💎 小南梁 TOP5 💎\n"
        for idx, (uid, xnn_val) in enumerate(ranking[:5], 1):
            nick = await self._get_nickname(event, uid)
            # 重新取该用户自己的统计数据（修复：不再引用循环外残留的最后一个记录的值）
            record = next((r for r in group_data if r.get(a1) == uid), None)
            num = int(record.get(a2, 0) or 0) if record else 0
            vol = float(record.get(a3, 0)) if record else 0.0
            actions = actor_actions.get(uid, 0)
            msg += (
                f"{idx}. {nick} - XNN值：{xnn_val:.2f} \n"
                f"(被ccb次数：{num}，容量：{vol:.2f}ml，对他人ccb：{actions})\n"
            )

        yield event.plain_result(msg)

    # issue 6
    @filter.command("ccbclear")
    async def ccbclear(self, event: AstrMessageEvent):
        """
        管理员指令：清除某人的所有 CCB 记录
        用法：ccbclear [@目标]
        """
        group_id = str(event.get_group_id())
        if not await self._is_admin(event):
            yield event.plain_result("无权限使用此命令")
            return

        target_user_id = self._get_target_user_id(event)

        all_data = self.store.read_ccb()
        group_data = all_data.get(group_id, [])
        if not isinstance(group_data, list):
            group_data = []

        before_len = len(group_data)
        group_data = [r for r in group_data if isinstance(r, dict) and r.get(a1) != target_user_id]
        removed_self = before_len - len(group_data)

        removed_from_others = 0
        modified_records = []
        for record in group_data:
            if not isinstance(record, dict):
                continue
            ccb_by = record.get(a4, {}) or {}
            if target_user_id in ccb_by:
                try:
                    removed_from_others += int(ccb_by[target_user_id].get("count", 0))
                except Exception:
                    removed_from_others += 0
                del ccb_by[target_user_id]
                record[a4] = ccb_by
                record[a2] = sum(
                    int(info.get("count", 0)) for info in ccb_by.values() if isinstance(info, dict)
                )
                modified_records.append(record)

        for record in modified_records:
            self.store.recalc_max(record)

        all_data[group_id] = group_data
        self.store.write_ccb(all_data)

        msg = (
            f"已清除 {target_user_id} 的 CCB 记录：\n"
            f"删除自身被CCB记录：{removed_self} 条\n"
            f"移除ccb他人记录：{removed_from_others} 次\n"
            f"相关记录已重新校准"
        )
        yield event.plain_result(msg)

    @filter.command("ccbnodo")
    async def ccbnodo(self, event: AstrMessageEvent):
        """
        管理员指令：切换目标防被 CCB 状态
        用法：ccbnodo [@目标或QQ号]
        """
        if not await self._is_admin(event):
            yield event.plain_result("无权限使用此命令")
            return

        group_id = str(event.get_group_id())
        # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
        target_user_id, err = await self.state.resolve_target(event, str(event.message_str), group_id)
        if err:
            yield event.plain_result(err)
            return
        nickname = await self._get_nickname(event, target_user_id)
        if target_user_id in self.state.white_list:
            self.state.white_list = [uid for uid in self.state.white_list if uid != target_user_id]
            self._save_white_list()
            yield event.plain_result(f"已解除 {nickname} 的保护状态：ta可以正常被C和C别人了")
        else:
            self.state.white_list.append(target_user_id)
            self._save_white_list()
            yield event.plain_result(f"已将 {nickname} 加入保护名单：ta无法被C和C别人了")

    @filter.command("timeclear")
    async def timeclear(self, event: AstrMessageEvent):
        """
        管理员指令：强制结束指定用户的神罚/昏厥冷却
        用法：timeclear [@目标或QQ号]，不带目标则默认清除自己
        """
        if not await self._is_admin(event):
            yield event.plain_result("无权限使用此命令")
            return

        group_id = str(event.get_group_id())
        # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
        target_user_id, err = await self.state.resolve_target(event, str(event.message_str), group_id)
        if err:
            yield event.plain_result(err)
            return
        self.state.ban_list.pop(target_user_id, None)
        self.state.faint_list.pop(target_user_id, None)
        nickname = await self._get_nickname(event, target_user_id)
        yield event.plain_result(f"已强制结束 {nickname} 的神罚/昏厥状态，ta又可以愉快的ccb了")

    @filter.command("dj")
    async def dj(self, event: AstrMessageEvent):
        """
        打胶：随机B水并记录（不影响被C记录与处女状态），可能随机昏厥
        禁C名单中的用户也可使用本命令
        """
        group_id = str(event.get_group_id())
        send_id = str(event.get_sender_id())
        user_name = event.get_sender_name()
        now = time.time()
        faint_time = self.state.faint_time()

        # 神罚检查（独立）
        ban_msg = self.state.check_ban(send_id, user_name)
        if ban_msg:
            yield event.plain_result(ban_msg)
            return
        # 昏厥检查（独立）
        faint_msg = self.state.check_faint(send_id, user_name)
        if faint_msg:
            yield event.plain_result(faint_msg)
            return

        # 滑窗限流（ccb/bh/dj 共用同一窗口计数与约束）
        rate_msg = self.state.rate_limit(send_id, now)
        if rate_msg:
            yield event.plain_result(rate_msg)
            return

        timep = round(random.uniform(1, 666), 2)
        V = round(random.uniform(0.01, 100), 2)

        # 按配置模式记录自交数据到独立文件（不改变被C记录，不改变处女状态）
        rec, (num_k, vol_k, _) = self.store.record_dj_stats(group_id, send_id, V)

        # 是否保留完整日志
        if self.state.is_log:
            try:
                self.store.append_log(group_id, send_id, send_id, timep, V)
            except Exception as e:
                logger.warning(f"记录日志失败: {e}")

        # 随机昏厥（概率可配置）
        if self.state.dj_mode == "d":
            # 打胶：打出生命因子，back.py 文案特供
            a = time_long(timep)
            b = volume(V)
            head = f"{user_name}, 你坚持了{timep}s哦，{a}.射出了{V:.2f}ml的生命因子,{b}!"
            stat = f"这是ta的第{rec[num_k]}次。ta累计射出了{rec[vol_k]}ml的生命因子。\n"
        else:
            # 扣B：13水，不使用 back.py 文案，正文带时长（与 ccb/bh 自交一致）
            duration = round(random.uniform(0.1, 60), 2)
            head = f"{user_name} 刚刚扣了{duration}min长的13 ，喷出了{V:.2f}ml的13水"
            stat = f"这是ta的第{rec[num_k]}次。ta累积喷出了{rec[vol_k]}ml的13水。\n"
        chain = [
            Comp.Plain(head),
            Comp.Plain(stat),
        ]
        if random.random() < self.state.dj_faint_prob:
            if self.state.dj_mode == "d":
                # 打胶：射空 → 被降下神罚
                self.state.ban_list[send_id] = now + self.state.ban_duration
                tail = f"同时{user_name}射空了，被降下{int(self.state.ban_duration // 60)}分钟的神罚"
            else:
                # 扣B：喷晕 → 昏厥，末尾显示昏厥时长
                self.state.faint_list[send_id] = now + faint_time
                remain = int(faint_time)
                m, s = divmod(remain, 60)
                tail = f"同时{user_name} 不小心扣晕了,接下来ta什么也做不了（剩余 {m}分{s}秒）"
            chain.append(Comp.Plain("----------------------------------\n"))
            chain.append(Comp.Plain(tail))
        yield event.chain_result(chain)

    @filter.command("djtop")
    async def djtop(self, event: AstrMessageEvent):
        """
        自交排行榜：按自交次数排行（数据与文案按配置模式：扣B=13水，打胶=生命因子）
        """
        group_id = str(event.get_group_id())
        group = self.store.get_self_stats(group_id)
        num_k, vol_k = (d_num, d_vol) if self.state.dj_mode == "d" else (a10, a8)
        name = "打胶" if self.state.dj_mode == "d" else "扣B"

        entries = [(uid, rec) for uid, rec in group.items() if int(rec.get(num_k, 0) or 0) > 0]
        if not entries:
            yield event.plain_result("当前群暂无自交记录。")
            return

        top5 = sorted(entries, key=lambda x: int(x[1].get(num_k, 0)), reverse=True)[:5]
        msg = f" {name}排行榜 TOP5 \n"
        for i, (uid, rec) in enumerate(top5, 1):
            nick = await self._get_nickname(event, uid)
            msg += f"{i}. {nick} - {name}：{int(rec.get(num_k, 0))}次，累计{float(rec.get(vol_k, 0) or 0):.2f}ml\n"
        yield event.plain_result(msg)

    @filter.command("djmax")
    async def djmax(self, event: AstrMessageEvent):
        """
        自交排行榜：按单次最高排行（数据与文案按配置模式：扣B=13水，打胶=生命因子）
        """
        group_id = str(event.get_group_id())
        group = self.store.get_self_stats(group_id)
        max_k = d_max if self.state.dj_mode == "d" else a9
        unit = "生命因子" if self.state.dj_mode == "d" else "13水"

        entries = [(uid, rec) for uid, rec in group.items() if float(rec.get(max_k, 0) or 0) > 0]
        if not entries:
            yield event.plain_result("当前群暂无自交记录。")
            return

        top5 = sorted(entries, key=lambda x: float(x[1].get(max_k, 0) or 0), reverse=True)[:5]
        msg = f"💦 单次最高{unit} TOP5 💦\n"
        for i, (uid, rec) in enumerate(top5, 1):
            nick = await self._get_nickname(event, uid)
            msg += f"{i}. {nick} - 单次最高：{float(rec.get(max_k, 0) or 0):.2f}ml\n"
        yield event.plain_result(msg)

    @filter.command("bh")
    async def bh(self, event: AstrMessageEvent):
        """
        百合：和群友互扣，被扣的人喷出B水并记录到独立数据
        用法：bh [@目标或QQ号]
        """
        group_id = str(event.get_group_id())
        send_id = str(event.get_sender_id())
        user_name = event.get_sender_name()
        now = time.time()
        # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
        target_user_id, err = await self.state.resolve_target(event, str(event.message_str), group_id)
        if err:
            yield event.plain_result(err)
            return

        # 发起者神罚检查（独立，与 /ccb 相同）
        ban_msg = self.state.check_ban(send_id, user_name)
        if ban_msg:
            yield event.plain_result(ban_msg)
            return
        # 发起者昏厥检查（独立）
        faint_msg = self.state.check_faint(send_id, user_name)
        if faint_msg:
            yield event.plain_result(faint_msg)
            return

        # 滑窗限流（ccb/bh/dj 共用同一窗口计数与约束，自交也计数）
        rate_msg = self.state.rate_limit(send_id, now)
        if rate_msg:
            yield event.plain_result(rate_msg)
            return

        # 无@自交：与 /ccb 0721 相同的自交逻辑（受 self_ccb 配置控制、白名单豁免）
        if target_user_id == send_id:
            if not self.state.selfdo:
                chain = [Comp.Plain(f"{user_name}，暂时不允许紫薇哦！")]
                yield event.chain_result(chain)
                return
            faint_time = self.state.faint_time()
            yield event.chain_result(self.state.self_play(self.store, group_id, send_id, user_name, faint_time))
            return

        # 禁C名单：不能发起百合
        if send_id in self.state.white_list:
            yield event.plain_result("神明剥夺了你求偶的权力，你无法发起ccb/百合")
            return
        # 禁C名单：不能被百合
        if target_user_id in self.state.white_list:
            nickname = await self._get_nickname(event, target_user_id)
            yield event.plain_result(f"{nickname}对方拒绝了和你ccb/百合")
            return

        duration = round(random.uniform(0.1, 60), 2)
        V_B = round(random.uniform(0.01, 100), 2)
        if random.random() < self.state.crit_prob:
            V_B = round(V_B * 2, 2)

        # 被扣者状态：当前是否已昏厥、昏厥时长（与全插件同一套可配置时长）
        faint_end_target = self.state.faint_list.get(target_user_id, 0)
        is_target_fainting = now <= faint_end_target
        faint_time = self.state.faint_time()

        # 记录被扣者的百合数据，并将最大值并入扣B的B_max
        rec = self.store.record_bh_stats(group_id, target_user_id, V_B)
        self.store.merge_b_max(group_id, target_user_id, V_B)
        nickname = await self._get_nickname(event, target_user_id)

        # 是否保留完整日志
        if self.state.is_log:
            try:
                self.store.append_log(group_id, send_id, target_user_id, duration, V_B)
            except Exception as e:
                logger.warning(f"记录日志失败: {e}")

        chain = [
            Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的百合互扣，{nickname}被扣出了{V_B:.2f}ml的13水"),
            Comp.Image.fromURL(get_avatar(target_user_id)),
            Comp.Plain(f"这是ta的第{rec[bh_num]}次被扣。ta被扣出了累计{rec[bh_vol]}ml的13水。\n"),
        ]
        # 被扣者昏厥：已在昏厥中则提示剩余，否则按概率触发昏厥（概率/时长与ccb互C一致）
        if is_target_fainting:
            remain = int(faint_end_target - now)
            m, s = divmod(remain, 60)
            tail = f"同时{nickname}现在正处于昏厥中,ta现在什么也干不了,剩余 {m}分{s}秒"
        elif random.random() < self.state.faint_prob:
            self.state.faint_list[target_user_id] = now + faint_time
            remain = int(faint_time)
            m, s = divmod(remain, 60)
            tail = f"同时{nickname}被{user_name}扣晕了,接下来ta将毫无还手之力,剩余 {m}分{s}秒"
        else:
            tail = None
        if tail:
            chain.append(Comp.Plain("----------------------------------\n"))
            chain.append(Comp.Plain(tail))
        yield event.chain_result(chain)

    @filter.command("bhtop")
    async def bhtop(self, event: AstrMessageEvent):
        """
        百合排行榜：按被扣次数排行
        """
        group_id = str(event.get_group_id())
        group = self.store.get_group_data("bh.json", group_id)

        entries = [(uid, rec) for uid, rec in group.items() if int(rec.get(bh_num, 0) or 0) > 0]
        if not entries:
            yield event.plain_result("当前群暂无百合记录。")
            return

        top5 = sorted(entries, key=lambda x: int(x[1].get(bh_num, 0)), reverse=True)[:5]
        b_data = self.store.get_group_data("dj_b.json", group_id)
        msg = "🌺 百合互扣排行榜 TOP5 🌺\n"
        for i, (uid, rec) in enumerate(top5, 1):
            nick = await self._get_nickname(event, uid)
            bmax = float(b_data.get(uid, {}).get(a9, 0) or 0)
            msg += (f"{i}. {nick} - 被扣：{int(rec.get(bh_num, 0))}次，"
                    f"累计喷出{float(rec.get(bh_vol, 0) or 0):.2f}ml，"
                    f"单次最高{bmax:.2f}ml\n")
        yield event.plain_result(msg)

    @filter.command("hn")
    async def hn(self, event: AstrMessageEvent):
        """
        喝奈：从目标汲取奶喝（泌乳），记录喂养次数与泌乳量
        用法：hn [@目标或QQ号]
        """
        group_id = str(event.get_group_id())
        send_id = str(event.get_sender_id())
        user_name = event.get_sender_name()
        now = time.time()
        # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
        target_user_id, err = await self.state.resolve_target(event, str(event.message_str), group_id)
        if err:
            yield event.plain_result(err)
            return

        # 神罚检查（独立）
        ban_msg = self.state.check_ban(send_id, user_name)
        if ban_msg:
            yield event.plain_result(ban_msg)
            return
        # 昏厥检查（独立）
        faint_msg = self.state.check_faint(send_id, user_name)
        if faint_msg:
            yield event.plain_result(faint_msg)
            return

        # 滑窗限流（与其他命令共用同一窗口计数与约束）
        rate_msg = self.state.rate_limit(send_id, now)
        if rate_msg:
            yield event.plain_result(rate_msg)
            return

        # 无@自交：自取其乳（受 self_ccb 配置控制、白名单豁免）
        if target_user_id == send_id:
            if not self.state.selfdo:
                chain = [Comp.Plain(f"{user_name}，暂时不允许自取其乳哦！")]
                yield event.chain_result(chain)
                return
            duration = round(random.uniform(0.1, 60), 2)
            V = round(random.uniform(0.01, 100), 2)
            if random.random() < self.state.crit_prob:
                V = round(V * 2, 2)
            rec, is_first = self.store.record_hn_stats(group_id, send_id, V, drinker=send_id)
            if self.state.is_log:
                try:
                    self.store.append_log(group_id, send_id, send_id, duration, V)
                except Exception as e:
                    logger.warning(f"记录日志失败: {e}")
            if is_first:
                head = f"{user_name}的{V:.2f}ml初乳被ta自己喝掉了"
            else:
                head = f"{user_name}花费{duration}min自取其乳{V:.2f}ml"
            yield event.chain_result([Comp.Plain(head)])
            return

        # 禁C名单：主动与被动统一受控（喝奈不在豁免范围）
        if send_id in self.state.white_list or target_user_id in self.state.white_list:
            target_nick = await self._get_nickname(event, target_user_id)
            yield event.plain_result(f"{target_nick}拒绝让你喝ta的奈奈")
            return

        duration = round(random.uniform(0.1, 60), 2)
        V = round(random.uniform(0.01, 100), 2)
        if random.random() < self.state.crit_prob:
            V = round(V * 2, 2)

        # 记录泌乳数据（hn.json），返回是否首次
        rec, is_first = self.store.record_hn_stats(group_id, target_user_id, V, drinker=send_id)
        target_nick = await self._get_nickname(event, target_user_id)

        # 是否保留完整日志
        if self.state.is_log:
            try:
                self.store.append_log(group_id, send_id, target_user_id, duration, V)
            except Exception as e:
                logger.warning(f"记录日志失败: {e}")

        if is_first:
            head = (f"{user_name}用{duration}min从{target_nick}那喝到了最有营养的{V:.2f}ml初乳，"
                    f"这是ta第一次喂养群友")
        else:
            head = (f"{user_name}从{target_nick}那用{duration}min喝到了{V:.2f}ml的奈奈，"
                    f"这是ta第{int(rec.get(hn_num, 0))}次喂养群友")

        chain = [
            Comp.Plain(head),
            Comp.Image.fromURL(get_avatar(target_user_id)),
        ]
        yield event.chain_result(chain)

    @filter.command("hntop")
    async def hntop(self, event: AstrMessageEvent):
        """
        泌乳排行榜：按喂养次数排行
        """
        group_id = str(event.get_group_id())
        group = self.store.get_group_data("hn.json", group_id)

        entries = [(uid, rec) for uid, rec in group.items() if int(rec.get(hn_num, 0) or 0) > 0]
        if not entries:
            yield event.plain_result("当前群暂无喝奈记录。")
            return

        top5 = sorted(entries, key=lambda x: int(x[1].get(hn_num, 0)), reverse=True)[:5]
        msg = "🍼 泌乳排行榜 TOP5 🍼\n"
        for i, (uid, rec) in enumerate(top5, 1):
            nick = await self._get_nickname(event, uid)
            msg += (f"{i}. {nick} 总共喂养了群友{int(rec.get(hn_num, 0))}次，"
                    f"累计泌乳{float(rec.get(hn_vol, 0) or 0):.2f}ml\n")
        yield event.plain_result(msg)

    @filter.command("hninfo")
    async def hninfo(self, event: AstrMessageEvent):
        """
        查询泌乳信息：初乳被谁喝了、被喝史、单次最大泌乳量、累计泌乳量
        用法：hninfo [@目标]
        """
        group_id = str(event.get_group_id())
        target_user_id = self._get_target_user_id(event)

        rec = self.store.get_group_data("hn.json", group_id).get(target_user_id, {})
        if int(rec.get(hn_num, 0) or 0) <= 0:
            yield event.plain_result("该用户暂无喝奈记录。")
            return

        # 初乳喝者（第一个喝到的人）
        first_id = rec.get(hn_first)
        first_nick = "未知"
        if first_id:
            first_nick = await self._get_nickname(event, first_id)
        target_nick = await self._get_nickname(event, target_user_id)

        msg = (
            f"【{target_nick} 】\n"
            f"• 初乳被喝：{first_nick}\n"
            f"• 喂养：{int(rec.get(hn_num, 0))}次\n"
            f"• 累计泌乳：{float(rec.get(hn_vol, 0) or 0):.2f}ml\n"
            f"• 单次最大泌乳：{float(rec.get(hn_max, 0) or 0):.2f}ml"
        )
        yield event.plain_result(msg)
