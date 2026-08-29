# -- coding: utf-8 --
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
from collections import deque
from astrbot.api import AstrBotConfig

import time
import json
import random
import os
from .back import time_long, volume
DATA_FILE = "data/ccb.json"

LOG_FILE = "data/ccb_log.json"

DJ_DATA_FILE = "data/dj.json"        # 打胶（生命因子）数据，独立文件

DJ_B_DATA_FILE = "data/dj_b.json"    # 扣B（13水）数据，独立文件

BH_DATA_FILE = "data/bh.json"        # 百合（互扣）数据，独立文件

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
/ccbclear   管理员指令：清除某人的所有 CCB 记录，用法：ccbclear [@目标]
/ccbnodo  管理员指令：切换目标禁C状态，用法：ccbnodo [@目标或QQ号]（禁C者不能主动C别人、也不能被C，但仍可自交）
/timeclean   管理员指令：强制结束指定用户的虚弱/昏厥冷却，用法：timeclean [@目标]（不带@默认清除自己）

根据配置文件可调控炸膛的概率

享受赛博打胶与ccb吧🦌🦌🦌
"""

a1 = "id"       # qq号
a2 = "num"      # 被C次数
a3 = "vol"      # 被注入量
a4 = "ccb_by"   # 被谁C了
a5 = "max"      # 单次最大注入量
a8 = "B_vol"    # 13水累计（扣B）
a9 = "B_max"    # 13水单次最高（扣B）
a10 = "B_num"   # 扣B次数
d_num = "d_num" # 打胶次数（生命因子）
d_vol = "d_vol" # 打胶累计（生命因子）
d_max = "d_max" # 打胶单次最高（生命因子）
bh_num = "bh_num" # 被扣次数（百合）
bh_vol = "bh_vol" # 被扣喷出B水累计（百合）




def get_avatar(user_id: str) -> bytes:
    return f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"

def makeit(group_data, target_user_id):
    """1 = 已被C过（处女状态已破），2 = 处女/无被C记录（只打过胶不算破处）"""
    for item in group_data:
        if item.get(a1) == target_user_id:
            return 1 if int(item.get(a2, 0) or 0) > 0 else 2
    return 2

@register("ccb", "Koikokokokoro", "和群友赛博sex的插件PLUS", "1.1.4")
class ccb(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.window = config.get("yw_window")                 # 滑动窗口长度（秒）
        self.threshold = config.get("yw_threshold")               # 窗口内最大允许动作次数
        self.ban_duration = config.get("yw_ban_duration")         # 禁用时长（秒）
        self.faint_duration = config.get("faint_ban_duration")    #晕倒时长（秒）
        self.faint_random_min = config.get("faint_random_min")    #晕倒随机最小时长（秒）
        self.faint_random_max = config.get("faint_random_max")    #晕倒随机最大时长（秒）
        self.action_times = {}
        self.ban_list = {}
        self.faint_list = {}
        self.yw_prob = config.get("yw_probability")               # 触发概率
        self.yw_prob_first = config.get("yw_prob_first")          #因为对方为处女而阳痿的概率
        self.faint_prob_first = config.get("faint_prob_first")          #首次晕倒的概率
        self.white_list  = config.get("white_list")
        self.selfdo = self.config.get("self_ccb", False)         # 0721 默认为否
        self.crit_prob = self.config.get("crit_prob")         #暴击概率
        self.faint_prob = self.config.get("faint_prob")          #晕倒概率
        self.dj_faint_prob = self.config.get("dj_faint_prob", 0.15)  #打胶/自扣昏厥概率
        self.dj_mode = self.config.get("dj_mode", "B")         # 自交模式："B"=扣B(13水)，"d"=打胶(生命因子)
        self.is_log = self.config.get("is_log", False)           # 完整日志，默认为false
        self._migrate_legacy_b_data()                          # 旧版 ccb.json 中的B水数据迁移到独立文件

    #  from issue 6
    async def _is_admin(self, event: AstrMessageEvent) -> bool:
        try:
            return bool(event.is_admin())
        except Exception:
            return False

    def _save_white_list(self):
        try:
            self.config["white_list"] = self.white_list
            save_fn = getattr(self.config, "save", None)
            if callable(save_fn):
                save_fn()
        except Exception as e:
            logger.warning(f"保存白名单失败: {e}")

    async def _get_nickname(self, event: AstrMessageEvent, user_id: str, strict_event: bool = False) -> str:
        nickname = user_id
        if event.get_platform_name() == "aiocqhttp":
            try:
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if strict_event:
                    assert isinstance(event, AiocqhttpMessageEvent)
                stranger_info = await event.bot.api.call_action(
                    'get_stranger_info', user_id=user_id
                )
                nickname = stranger_info.get("nick", nickname)
            except Exception:
                pass
        return nickname

    # 获取目标用户ID
    def _get_target_user_id(self, event: AstrMessageEvent) -> str:
        self_id = str(event.get_self_id())
        return next(
            (str(seg.qq) for seg in event.get_messages()
             if isinstance(seg, Comp.At) and str(seg.qq) != self_id),
            str(event.get_sender_id())
        )

    # 目标解析：优先@，其次命令参数中的QQ号（需验证在本群），默认自己。返回 (target_id, error_msg)
    async def _resolve_target(self, event: AstrMessageEvent, messages: str, group_id: str) -> tuple:
        for seg in event.get_messages():
            if isinstance(seg, Comp.At) and str(seg.qq) != str(event.get_self_id()):
                return str(seg.qq), None
        # 仅把5位及以上的纯数字视为QQ号（QQ号最低5位，过滤掉梗数字等短数字）
        parts = [p for p in str(messages).split() if p.isdigit() and len(p) >= 5]
        if parts:
            qq = parts[0]
            if not await self._is_in_group(event, group_id, qq):
                return None, f"{event.get_sender_name()}，神明的小本本没有记录id为{qq}的ta呢"
            return qq, None
        return str(event.get_sender_id()), None

    # 检查QQ号是否在本群（仅 aiocqhttp 平台可验证；其他平台无法验证时放行）
    async def _is_in_group(self, event: AstrMessageEvent, group_id: str, user_id: str) -> bool:
        if event.get_platform_name() != "aiocqhttp":
            return True
        try:
            await event.bot.api.call_action(
                'get_group_member_info', group_id=int(group_id), user_id=int(user_id)
            )
            return True
        except Exception:
            return False

    # 虚弱（阳痿）检查：处于虚弱期返回拦截消息（含触发用户昵称），否则返回 None（与昏厥检查相互独立）
    def _check_ban(self, user_id: str, user_name: str) -> str:
        now = time.time()
        ban_end = self.ban_list.get(user_id, 0)
        if now < ban_end:
            remain = int(ban_end - now)
            m, s = divmod(remain, 60)
            return f"{user_name}的虚弱还剩余 {m}分{s}秒"
        return None

    # 昏厥检查：处于昏厥期返回拦截消息（含触发用户昵称），否则返回 None
    def _check_faint(self, user_id: str, user_name: str) -> str:
        now = time.time()
        faint_end = self.faint_list.get(user_id, 0)
        if now < faint_end:
            remain = int(faint_end - now)
            m, s = divmod(remain, 60)
            return f"{user_name} 处于昏厥中剩余 {m}分{s}秒"
        return None

    # 重新计算由于clear导致的缺口
    def _recalc_max(self, record: dict):
        if not isinstance(record, dict):
            return
        ccb_by = record.get(a4, {}) or {}
        total_num = 0
        try:
            total_num = int(record.get(a2, 0))
        except Exception:
            total_num = 0
        try:
            total_vol = float(record.get(a3, 0))
        except Exception:
            total_vol = 0.0
        if total_num <= 0 or not ccb_by:
            record[a5] = 0.0
            for k, v in ccb_by.items():
                if isinstance(v, dict):
                    v["max"] = False
            record[a4] = ccb_by
            return
        record[a5] = round(total_vol / total_num, 2)
        try:
            best_id = max(
                ccb_by.items(),
                key=lambda x: int(x[1].get("count", 0)) if isinstance(x[1], dict) else 0
            )[0]
        except Exception:
            best_id = None
        if best_id:
            for k, v in ccb_by.items():
                if isinstance(v, dict):
                    v["max"] = (k == best_id)
        record[a4] = ccb_by

    def read_data(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"读取数据错误: {e}")
        return {}

    def write_data(self, data):
        try:
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入数据错误: {e}")

    def _read_dj_file(self, path: str) -> dict:
        """读取独立的自交数据文件（{群ID: {用户ID: {统计}}}, 打胶/扣B）"""
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"读取数据错误: {e}")
        return {}

    def _write_dj_file(self, path: str, data: dict):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入数据错误: {e}")

    # 记录日志
    def append_log(self, group_id: str, executor_id: str, target_id: str, time: float, vol: float):
        """
        记录日志，格式为：
        {"executor": "...", ````````}
        """
        try:
            # 读取日志，可能用于数据处理
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'r', encoding='utf-8') as lf:
                    try:
                        logs = json.load(lf)
                        if not isinstance(logs, list):
                            logs = []
                    except Exception:
                        logs = []
            else:
                logs = []

            # 追加日志内容
            entry = {
                "group": group_id,
                "executor": executor_id,
                "target": target_id,
                "time": time,
                "vol": str(round(float(vol), 2))
            }
            logs.append(entry)

            # 写回
            with open(LOG_FILE, 'w', encoding='utf-8') as lf:
                json.dump(logs, lf, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"append_log 失败: {e}")

    def _record_dj_stats(self, group_id: str, user_id: str, vol: float, mode: str = None) -> tuple:
        """
        记录自交数据，写入独立的 json 文件（打胶= dj.json，扣B= dj_b.json）。
        返回 (记录dict, 键元组(num键, vol键, max键)) 供消息构建使用。
        """
        mode = mode or self.dj_mode
        if mode == "d":
            file, num_k, vol_k, max_k = DJ_DATA_FILE, d_num, d_vol, d_max
        else:
            file, num_k, vol_k, max_k = DJ_B_DATA_FILE, a10, a8, a9
        data = self._read_dj_file(file)
        rec = data.setdefault(group_id, {}).setdefault(user_id, {})
        rec[num_k] = int(rec.get(num_k, 0)) + 1
        rec[vol_k] = round(float(rec.get(vol_k, 0)) + vol, 2)
        rec[max_k] = max(float(rec.get(max_k, 0) or 0), vol)
        self._write_dj_file(file, data)
        return rec, (num_k, vol_k, max_k)

    def _record_bh_stats(self, group_id: str, user_id: str, vol: float) -> dict:
        """记录百合（互扣）数据到 bh.json：被扣次数+1、喷水累计。单次最高直接并入扣B的B_max。返回记录dict"""
        data = self._read_dj_file(BH_DATA_FILE)
        rec = data.setdefault(group_id, {}).setdefault(user_id, {})
        rec[bh_num] = int(rec.get(bh_num, 0)) + 1
        rec[bh_vol] = round(float(rec.get(bh_vol, 0)) + vol, 2)
        self._write_dj_file(BH_DATA_FILE, data)
        return rec

    def _merge_b_max(self, group_id: str, user_id: str, vol: float):
        """百合喷水最大值并入扣B的B_max（dj_b.json），不影响扣B次数与累计"""
        data = self._read_dj_file(DJ_B_DATA_FILE)
        rec = data.setdefault(group_id, {}).setdefault(user_id, {})
        rec[a9] = max(float(rec.get(a9, 0) or 0), vol)
        self._write_dj_file(DJ_B_DATA_FILE, data)

    def _self_play(self, group_id: str, send_id: str, user_name: str, faint_time: float) -> list:
        """
        自扣（0721）：固定为扣B（13水）行为，触发后昏厥（扣晕），不跟随 dj_mode。
        不改变被C记录与处女状态。用于 ccb / bh 未指定目标且 self_ccb 开启时。返回待发送的消息链。
        """
        duration = round(random.uniform(0.1, 60), 2)
        V = round(random.uniform(0.01, 100), 2)
        now = time.time()

        rec, _ = self._record_dj_stats(group_id, send_id, V, mode="B")

        if self.is_log:
            try:
                self.append_log(group_id, send_id, send_id, duration, V)
            except Exception as e:
                logger.warning(f"记录日志失败: {e}")

        head = f"{user_name} 刚刚扣了{duration}min长的13 ，喷出了{V:.2f}ml的13水"
        stat = f"这是ta的第{rec[a10]}次。ta累积喷出了{rec[a8]}ml的13水。\n"
        tail = None
        if random.random() < self.dj_faint_prob:
            self.faint_list[send_id] = now + faint_time
            remain = int(faint_time)
            m, s = divmod(remain, 60)
            tail = f"同时{user_name}不小心扣晕了,接下来ta什么也干不了（剩余 {m}分{s}秒）"

        chain = [
            Comp.Plain(head),
            Comp.Image.fromURL(get_avatar(send_id)),
            Comp.Plain(stat),
        ]
        if tail:
            chain.append(Comp.Plain("----------------------------------\n"))
            chain.append(Comp.Plain(tail))
        return chain

    def _migrate_legacy_b_data(self):
        """把旧版 ccb.json 记录中的B水字段（B_vol/B_max/B_num）迁移到独立的 dj_b.json"""
        try:
            if not os.path.exists(DATA_FILE):
                return
            all_data = self.read_data()
            migrated = False
            b_data = self._read_dj_file(DJ_B_DATA_FILE)
            for gid, records in all_data.items():
                if not isinstance(records, list):
                    continue
                for r in records:
                    if not isinstance(r, dict):
                        continue
                    if r.get(a8) is None and r.get(a9) is None and r.get(a10) is None:
                        continue
                    uid = r.get(a1)
                    if not uid:
                        continue
                    b = b_data.setdefault(gid, {}).setdefault(uid, {})
                    b[a10] = int(r.get(a10, 0) or 0)
                    b[a8] = round(float(r.get(a8, 0) or 0), 2)
                    b[a9] = max(float(b.get(a9, 0) or 0), float(r.get(a9, 0) or 0))
                    for key in (a8, a9, a10):
                        r.pop(key, None)
                    migrated = True
            if migrated:
                self.write_data(all_data)
                self._write_dj_file(DJ_B_DATA_FILE, b_data)
                logger.info("已迁移旧版B水数据到 dj_b.json")
        except Exception as e:
            logger.warning(f"迁移旧版B水数据失败: {e}")

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
        用法： ccb [@]
        """

        group_id = str(event.get_group_id())
        send_id = str(event.get_sender_id())
        user_name = str(event.get_sender_name())
        actor_id = send_id
        faint_min = self.faint_random_min
        faint_max = self.faint_random_max
        now = time.time()
        f_now = time.time()
        # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
        target_user_id, err = await self._resolve_target(event, str(event.message_str), group_id)
        if err:
            yield event.plain_result(err)
            return

        if self.faint_duration >= 0:
            faint_time = self.faint_duration
        else:
            faint_time = round(random.uniform(faint_min, faint_max))

        yw_prob_r1 = random.random()
        if yw_prob_r1 < self.yw_prob:
            yw_prob_r = yw_prob_r1
            faint_prob_r = 1.0
        else:
            faint_prob_r = random.random()
            yw_prob_r = 1.0

        # 阳痿检查（独立）
        ban_msg = self._check_ban(actor_id, user_name)
        if ban_msg:
            yield event.plain_result(ban_msg)
            return
        # 昏厥检查（独立）
        faint_msg = self._check_faint(actor_id, user_name)
        if faint_msg:
            yield event.plain_result(faint_msg)
            return
        faint_end_target = self.faint_list.get(target_user_id, 0)

        # 窗口时间统计
        times = self.action_times.setdefault(actor_id, deque())
        while times and now - times[0] > self.window:
            times.popleft()
        times.append(now)

        # 超阈值禁用：统一进入虚弱（与 /bh 相同约束）
        if len(times) > self.threshold:
            self.ban_list[actor_id] = now + self.ban_duration
            times.clear()
            yield event.plain_result(f"神明阻止了你的行为并给你上了{int(self.ban_duration // 60)}分钟的虚弱")
            return

        if target_user_id == actor_id:
            if not self.selfdo:
                chain = [Comp.Plain(f"{user_name}，暂时不允许自交哦！")]
                yield event.chain_result(chain)
                return
            # 自交（0721）：跟随配置模式，不改变处女状态。禁C名单用户也可自交
            yield event.chain_result(self._self_play(group_id, send_id, user_name, faint_time))
            return

        # 禁C名单：名单内用户不能发起与他人的ccb（但可自交，也可/dj）
        if actor_id in self.white_list:
            yield event.plain_result("神明剥夺了你求偶的权力，你无法发起ccb/百合")
            return

        # 禁C名单：名单内用户不能被他人ccb
        if target_user_id in self.white_list:
            nickname = await self._get_nickname(event, target_user_id)
            yield event.plain_result(f"{nickname}受到了神明的庇护，你无法对其发起ccb/百合")
            return




        # CCB 逻辑
        duration = round(random.uniform(0.1, 60), 2)
        V = round(random.uniform(0.01, 100), 2)
        prob = self.crit_prob
        user_name = event.get_sender_name()
        is_log = self.is_log
        if random.random() < prob:
            V = round(V * 2, 2)

        pic = get_avatar(target_user_id)

        all_data = self.read_data()
        group_data = all_data.get(group_id, [])

        mode = makeit(group_data, target_user_id)
        if mode == 1:
            # 已有记录，更新
            try:
                for item in group_data:
                    if item.get(a1) == target_user_id:
                        # 获取昵称
                        nickname = await self._get_nickname(event, target_user_id, strict_event=True)

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

                        # 添加逻辑：记录max值

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
                        if yw_prob_r < self.yw_prob:
                            self.ban_list[actor_id] = now + self.ban_duration
                            m, s = divmod(int(self.ban_duration), 60)

                            chain = [
                                Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                                Comp.Image.fromURL(pic),
                                Comp.Plain(f"这是ta的第{item[a2]}次。ta被累积注入了{item[a3]}ml的生命因子。\n"),
                                Comp.Plain("----------------------------------\n"),
                                Comp.Plain(f"同时💥神明看你不顺眼，给你上了{m}分{s}秒的虚弱buff")
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
                        elif faint_prob_r < self.faint_prob:
                            self.faint_list[target_user_id] = f_now + faint_time
                            # 注意：faint_end_target 是本命令开头读取的旧值（目标此前未昏厥时为0），
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
                                self.append_log(group_id, send_id, target_user_id, duration, V)
                            except Exception as e:
                                logger.warning(f"记录日志失败: {e}")

                        # 写回数据
                        all_data[group_id] = group_data
                        self.write_data(all_data)
                        return
            except Exception as e:
                logger.error(f"报错: {e}")
                yield event.plain_result("对方拒绝了和你ccb")
                return

        else:
            # 新记录
            try:
                nickname = await self._get_nickname(event, target_user_id, strict_event=True)

                # 随机养胃
                if yw_prob_r < self.yw_prob_first:
                    self.ban_list[actor_id] = now + self.ban_duration
                    m, s = divmod(int(self.ban_duration), 60)
                    chain = [
                    Comp.Plain(f"{user_name} 和 {nickname}发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                    Comp.Image.fromURL(pic),
                    Comp.Plain("这是ta的初体验~，你把人家的处给破了喵～要负责哦喵～\n"),
                    Comp.Plain("----------------------------------\n"),
                    Comp.Plain(f"💥同时神明看你不顺眼，给你上了{m}分{s}秒的虚弱buff")
                    ]
                    yield event.chain_result(chain)

                # 随机昏厥
                elif faint_prob_r < self.faint_prob_first:
                    self.faint_list[target_user_id] = f_now + faint_time
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
                self.write_data(all_data)

                # 是否保留完整日志
                if is_log:
                    try:
                        self.append_log(group_id, send_id, target_user_id, duration, V)
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
        group_data = self.read_data().get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        top5 = sorted(group_data, key=lambda x: int(x.get(a2, 0) or 0), reverse=True)[:5]
        msg = "被ccb排行榜 TOP5：\n"
        for i, r in enumerate(top5, 1):
            uid = r[a1]
            nick = await self._get_nickname(event, uid)
            msg += f"{i}. {nick} - 次数：{r[a2]}\n"
        yield event.plain_result(msg)

    @filter.command("ccbvol")
    async def ccbvol(self, event: AstrMessageEvent):
        """
        按注入量排行
        """
        group_id = str(event.get_group_id())
        group_data = self.read_data().get(group_id, [])
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
        all_data = self.read_data()
        group_data = all_data.get(group_id, [])

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
            first_nick = await self._get_nickname(event, first_actor, strict_event=True)

        # 自交统计（按配置模式显示：扣B=13水，打胶=生命因子，数据来自独立文件）
        if self.dj_mode == "d":
            rec = self._read_dj_file(DJ_DATA_FILE).get(group_id, {}).get(target_user_id, {})
            num_k, vol_k, max_k, label, unit = d_num, d_vol, d_max, "打胶", "生命因子"
        else:
            rec = self._read_dj_file(DJ_B_DATA_FILE).get(group_id, {}).get(target_user_id, {})
            num_k, vol_k, max_k, label, unit = a10, a8, a9, "13水", "ml"
        dj_num = int(rec.get(num_k, 0) or 0)
        dj_vol = float(rec.get(vol_k, 0) or 0)
        dj_max = float(rec.get(max_k, 0) or 0)

        # 百合统计（互扣，独立于 dj_mode；单次最高直接复用扣B的B_max）
        bh_rec = self._read_dj_file(BH_DATA_FILE).get(group_id, {}).get(target_user_id, {})
        bh_n = int(bh_rec.get(bh_num, 0) or 0)
        bh_v = float(bh_rec.get(bh_vol, 0) or 0)
        bh_m = float(self._read_dj_file(DJ_B_DATA_FILE).get(group_id, {}).get(target_user_id, {}).get(a9, 0) or 0)

        # 输出结果
        msg = (
            f"【{record.get(a1)} 】\n"
            f"• 破壁人：{first_nick}\n"
            f"• 被超：{total_num}\n"
            f"• ccb：{cb_total}\n"
            f"• 被注入：{total_vol:.2f}ml\n"
            f"• MAX：{max_val:.2f}ml"
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
        group_data = self.read_data().get(group_id, [])
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
            nick = await self._get_nickname(event, uid, strict_event=True)
            producer_nick = producer_id or "未知"
            if producer_id:
                producer_nick = await self._get_nickname(event, producer_id, strict_event=True)

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
        all_data = self.read_data()
        group_data = all_data.get(group_id, [])
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
            nick = await self._get_nickname(event, uid, strict_event=True)
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

        all_data = self.read_data()
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
            self._recalc_max(record)

        all_data[group_id] = group_data
        self.write_data(all_data)

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
        用法：ccbnodo [@目标]
        """
        if not await self._is_admin(event):
            yield event.plain_result("无权限使用此命令")
            return

        group_id = str(event.get_group_id())
        # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
        target_user_id, err = await self._resolve_target(event, str(event.message_str), group_id)
        if err:
            yield event.plain_result(err)
            return
        nickname = await self._get_nickname(event, target_user_id)
        if target_user_id in self.white_list:
            self.white_list = [uid for uid in self.white_list if uid != target_user_id]
            self._save_white_list()
            yield event.plain_result(f"已解除 {nickname} 的禁C状态：ta可以正常被C和C别人了")
        else:
            self.white_list.append(target_user_id)
            self._save_white_list()
            yield event.plain_result(f"已将 {nickname} 加入禁C名单：ta不能主动C别人，也不能被C（仍可自交 /dj 和 /ccb 0721）")

    @filter.command("timeclean")
    async def timeclean(self, event: AstrMessageEvent):
        """
        管理员指令：强制结束指定用户的阳痿/昏厥冷却
        用法：timeclean [@目标]，不带@则默认清除自己
        """
        if not await self._is_admin(event):
            yield event.plain_result("无权限使用此命令")
            return

        target_user_id = self._get_target_user_id(event)
        self.ban_list.pop(target_user_id, None)
        self.faint_list.pop(target_user_id, None)
        nickname = await self._get_nickname(event, target_user_id)
        yield event.plain_result(f"已强制结束 {nickname} 的虚弱/昏厥状态，ta又可以愉快的ccb了")

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
        faint_time = self.faint_duration if self.faint_duration >= 0 else round(random.uniform(self.faint_random_min, self.faint_random_max))

        # 阳痿检查（独立）
        ban_msg = self._check_ban(send_id, user_name)
        if ban_msg:
            yield event.plain_result(ban_msg)
            return
        # 昏厥检查（独立）
        faint_msg = self._check_faint(send_id, user_name)
        if faint_msg:
            yield event.plain_result(faint_msg)
            return

        # 滑窗限流：与 /ccb、/bh 共用同一窗口计数与约束，超限统一进入虚弱
        times = self.action_times.setdefault(send_id, deque())
        while times and now - times[0] > self.window:
            times.popleft()
        times.append(now)
        if len(times) > self.threshold:
            self.ban_list[send_id] = now + self.ban_duration
            times.clear()
            yield event.plain_result(f"神明阻止了你的行为并给你上了{int(self.ban_duration // 60)}分钟的虚弱")
            return

        timep = round(random.uniform(1, 666), 2)
        V = round(random.uniform(0.01, 100), 2)

        # 按配置模式记录自交数据到独立文件（不改变被C记录，不改变处女状态）
        rec, (num_k, vol_k, _) = self._record_dj_stats(group_id, send_id, V)

        # 是否保留完整日志
        if self.is_log:
            try:
                self.append_log(group_id, send_id, send_id, timep, V)
            except Exception as e:
                logger.warning(f"记录日志失败: {e}")

        # 随机昏厥（概率可配置）
        if self.dj_mode == "d":
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
            Comp.Image.fromURL(get_avatar(send_id)),
            Comp.Plain(stat),
        ]
        if random.random() < self.dj_faint_prob:
            if self.dj_mode == "d":
                # 打胶：射空 → 被赋予虚弱buff
                self.ban_list[send_id] = now + self.ban_duration
                tail = f"同时{user_name}射空了，被赋予{int(self.ban_duration // 60)}分钟的虚弱buff"
            else:
                # 扣B：喷晕 → 昏厥，末尾显示昏厥时长
                self.faint_list[send_id] = now + faint_time
                remain = int(faint_time)
                m, s = divmod(remain, 60)
                tail = f"同时{user_name} 不小心扣晕了,接下来ta什么也做不了（剩余 {m}分{s}秒）"
            chain.append(Comp.Plain("----------------------------------\n"))
            chain.append(Comp.Plain(tail))
        yield event.chain_result(chain)

    def _get_self_stats(self, group_id: str) -> dict:
        """按配置模式读取当前群的自交统计数据（{用户ID: 记录dict}）"""
        file = DJ_DATA_FILE if self.dj_mode == "d" else DJ_B_DATA_FILE
        return self._read_dj_file(file).get(group_id, {})

    @filter.command("djtop")
    async def djtop(self, event: AstrMessageEvent):
        """
        自交排行榜：按自交次数排行（数据与文案按配置模式：扣B=13水，打胶=生命因子）
        """
        group_id = str(event.get_group_id())
        group = self._get_self_stats(group_id)
        num_k, vol_k = (d_num, d_vol) if self.dj_mode == "d" else (a10, a8)
        name = "打胶" if self.dj_mode == "d" else "扣B"

        entries = [(uid, rec) for uid, rec in group.items() if int(rec.get(num_k, 0) or 0) > 0]
        if not entries:
            yield event.plain_result("当前群暂无自交记录。")
            return

        top5 = sorted(entries, key=lambda x: int(x[1].get(num_k, 0)), reverse=True)[:5]
        msg = f"🦌 {name}排行榜 TOP5 🦌\n"
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
        group = self._get_self_stats(group_id)
        max_k = d_max if self.dj_mode == "d" else a9
        unit = "生命因子" if self.dj_mode == "d" else "13水"

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
        用法：bh [@目标]
        """
        group_id = str(event.get_group_id())
        send_id = str(event.get_sender_id())
        user_name = event.get_sender_name()
        now = time.time()
        # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
        target_user_id, err = await self._resolve_target(event, str(event.message_str), group_id)
        if err:
            yield event.plain_result(err)
            return

        # 发起者虚弱检查（独立，与 /ccb 相同）
        ban_msg = self._check_ban(send_id, user_name)
        if ban_msg:
            yield event.plain_result(ban_msg)
            return
        # 发起者昏厥检查（独立）
        faint_msg = self._check_faint(send_id, user_name)
        if faint_msg:
            yield event.plain_result(faint_msg)
            return

        # 滑窗限流：与 /ccb、/dj 共用同一窗口计数与约束（自交也计数），超限统一进入虚弱
        times = self.action_times.setdefault(send_id, deque())
        while times and now - times[0] > self.window:
            times.popleft()
        times.append(now)
        if len(times) > self.threshold:
            self.ban_list[send_id] = now + self.ban_duration
            times.clear()
            yield event.plain_result(f"神明阻止了你的行为并给你上了{int(self.ban_duration // 60)}分钟的虚弱")
            return

        # 无@自交：与 /ccb 0721 相同的自交逻辑（受 self_ccb 配置控制、白名单豁免）
        if target_user_id == send_id:
            if not self.selfdo:
                chain = [Comp.Plain(f"{user_name}，暂时不允许自交哦！")]
                yield event.chain_result(chain)
                return
            faint_time = self.faint_duration if self.faint_duration >= 0 else round(random.uniform(self.faint_random_min, self.faint_random_max))
            yield event.chain_result(self._self_play(group_id, send_id, user_name, faint_time))
            return

        # 禁C名单：不能发起百合
        if send_id in self.white_list:
            yield event.plain_result("神明剥夺了你求偶的权力，你无法发起ccb/百合")
            return
        # 禁C名单：不能被百合
        if target_user_id in self.white_list:
            nickname = await self._get_nickname(event, target_user_id)
            yield event.plain_result(f"{nickname}受到了神明的庇护，你无法对其发起ccb/百合")
            return

        duration = round(random.uniform(0.1, 60), 2)
        V_B = round(random.uniform(0.01, 100), 2)
        if random.random() < self.crit_prob:
            V_B = round(V_B * 2, 2)

        # 被扣者状态：当前是否已昏厥、昏厥时长（与全插件同一套可配置时长）
        faint_end_target = self.faint_list.get(target_user_id, 0)
        is_target_fainting = now <= faint_end_target
        faint_time = self.faint_duration if self.faint_duration >= 0 else round(random.uniform(self.faint_random_min, self.faint_random_max))

        # 记录被扣者的百合数据，并将最大值并入扣B的B_max
        rec = self._record_bh_stats(group_id, target_user_id, V_B)
        self._merge_b_max(group_id, target_user_id, V_B)
        nickname = await self._get_nickname(event, target_user_id)

        # 是否保留完整日志
        if self.is_log:
            try:
                self.append_log(group_id, send_id, target_user_id, duration, V_B)
            except Exception as e:
                logger.warning(f"记录日志失败: {e}")

        chain = [
            Comp.Plain(f"{user_name} 和 {nickname} 发生了百合互扣，{nickname}被扣出了{V_B:.2f}ml的13水"),
            Comp.Image.fromURL(get_avatar(target_user_id)),
            Comp.Plain(f"这是ta的第{rec[bh_num]}次被扣。ta被扣出了累计{rec[bh_vol]}ml的13水。\n"),
        ]
        # 被扣者昏厥：已在昏厥中则提示剩余，否则按概率触发昏厥（概率/时长与ccb互C一致）
        if is_target_fainting:
            remain = int(faint_end_target - now)
            m, s = divmod(remain, 60)
            tail = f"同时{nickname}现在正处于昏厥中,ta现在什么也干不了,剩余 {m}分{s}秒"
        elif random.random() < self.faint_prob:
            self.faint_list[target_user_id] = now + faint_time
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
        group = self._read_dj_file(BH_DATA_FILE).get(group_id, {})

        entries = [(uid, rec) for uid, rec in group.items() if int(rec.get(bh_num, 0) or 0) > 0]
        if not entries:
            yield event.plain_result("当前群暂无百合记录。")
            return

        top5 = sorted(entries, key=lambda x: int(x[1].get(bh_num, 0)), reverse=True)[:5]
        b_data = self._read_dj_file(DJ_B_DATA_FILE).get(group_id, {})
        msg = "🌺 百合互扣排行榜 TOP5 🌺\n"
        for i, (uid, rec) in enumerate(top5, 1):
            nick = await self._get_nickname(event, uid)
            bmax = float(b_data.get(uid, {}).get(a9, 0) or 0)
            msg += (f"{i}. {nick} - 被扣：{int(rec.get(bh_num, 0))}次，"
                    f"累计喷出{float(rec.get(bh_vol, 0) or 0):.2f}ml，"
                    f"单次最高{bmax:.2f}ml\n")
        yield event.plain_result(msg)
