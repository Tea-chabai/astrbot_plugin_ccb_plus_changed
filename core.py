# -- coding: utf-8 --
"""
逻辑层：状态管理（神罚/昏厥/滑窗限流）、目标解析、自交演出。
不直接读写文件——数据操作通过 DataStore 实例完成。
"""
import random
import time
from collections import deque
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp
from .storage import a1, a2, a8, a9, a10, d_num, d_vol


def get_avatar(user_id: str) -> bytes:
    return f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"


def makeit(group_data, target_user_id):
    """1 = 已被C过（处女状态已破），2 = 处女/无被C记录（只打过胶不算破处）"""
    for item in group_data:
        if item.get(a1) == target_user_id:
            return 1 if int(item.get(a2, 0) or 0) > 0 else 2
    return 2


class StateKeeper:
    """冷却状态（神罚/昏厥/滑窗）与公共逻辑，运行时常驻内存"""

    def __init__(self, config):
        self.action_times = {}
        self.ban_list = {}
        self.faint_list = {}
        self.window = config.get("yw_window")                 # 滑动窗口长度（秒）
        self.threshold = config.get("yw_threshold")           # 窗口内最大允许动作次数
        self.ban_duration = config.get("yw_ban_duration")     # 神罚时长（秒）
        self.faint_duration = config.get("faint_ban_duration")    # 昏厥时长（秒，-1为随机）
        self.faint_random_min = config.get("faint_random_min")    # 昏厥随机最小时长（秒）
        self.faint_random_max = config.get("faint_random_max")    # 昏厥随机最大时长（秒）
        self.yw_prob = config.get("yw_probability")           # 阳痿概率
        self.yw_prob_first = config.get("yw_prob_first")      # 首次阳痿概率
        self.faint_prob_first = config.get("faint_prob_first")    # 首次昏厥概率
        self.faint_prob = config.get("faint_prob")            # 昏厥概率
        self.dj_faint_prob = config.get("dj_faint_prob", 0.15)    # 打胶/自扣昏厥概率
        self.dj_mode = config.get("dj_mode", "B")             # 自交模式："B"=扣B，"d"=打胶
        self.crit_prob = config.get("crit_prob")              # 暴击概率
        self.selfdo = config.get("self_ccb", False)           # 是否允许自交（0721）
        self.white_list = config.get("white_list")            # 禁C名单
        self.is_log = config.get("is_log", False)             # 完整日志

    # ---- 冷却检查 ----
    def check_ban(self, user_id: str, user_name: str) -> str:
        """神罚（阳痿）检查：处于神罚期返回拦截消息（含触发用户昵称），否则返回 None"""
        now = time.time()
        ban_end = self.ban_list.get(user_id, 0)
        if now < ban_end:
            remain = int(ban_end - now)
            m, s = divmod(remain, 60)
            return f"{user_name}正承受神罚，剩余 {m}分{s}秒"
        return None

    def check_faint(self, user_id: str, user_name: str) -> str:
        """昏厥检查：处于昏厥期返回拦截消息（含触发用户昵称），否则返回 None"""
        now = time.time()
        faint_end = self.faint_list.get(user_id, 0)
        if now < faint_end:
            remain = int(faint_end - now)
            m, s = divmod(remain, 60)
            return f"{user_name} 处于昏厥中剩余 {m}分{s}秒"
        return None

    def faint_time(self) -> float:
        """昏厥时长：配置固定值或随机区间"""
        if self.faint_duration >= 0:
            return self.faint_duration
        return round(random.uniform(self.faint_random_min, self.faint_random_max))

    # ---- 滑窗限流（ccb/dj/bh 共用同一窗口计数与约束）----
    def rate_limit(self, user_id: str, now: float) -> str:
        """计入一次动作；超限则写入神罚并返回提示消息，否则返回 None"""
        times = self.action_times.setdefault(user_id, deque())
        while times and now - times[0] > self.window:
            times.popleft()
        times.append(now)
        if len(times) > self.threshold:
            self.ban_list[user_id] = now + self.ban_duration
            times.clear()
            return f"神明阻止了你的行为并降下神罚，{int(self.ban_duration // 60)}分钟内无法行动"
        return None

    # ---- 目标解析 ----
    async def resolve_target(self, event: AstrMessageEvent, messages: str, group_id: str) -> tuple:
        """目标解析：优先@，其次5位以上QQ号（需验证在本群），默认自己。返回 (target_id, error_msg)"""
        for seg in event.get_messages():
            if isinstance(seg, Comp.At) and str(seg.qq) != str(event.get_self_id()):
                return str(seg.qq), None
        parts = [p for p in str(messages).split() if p.isdigit() and len(p) >= 5]
        if parts:
            qq = parts[0]
            if not await self.is_in_group(event, group_id, qq):
                return None, f"{event.get_sender_name()}，神明的小本本没有记录id为{qq}的ta呢"
            return qq, None
        return str(event.get_sender_id()), None

    async def is_in_group(self, event: AstrMessageEvent, group_id: str, user_id: str) -> bool:
        """检查QQ号是否在本群（仅 aiocqhttp 平台可验证；其他平台无法验证时放行）"""
        if event.get_platform_name() != "aiocqhttp":
            return True
        try:
            await event.bot.api.call_action(
                'get_group_member_info', group_id=int(group_id), user_id=int(user_id)
            )
            return True
        except Exception:
            return False

    # ---- 自交演出（0721，固定扣B）----
    def self_play(self, store, group_id: str, send_id: str, user_name: str, faint_time: float) -> list:
        """
        自扣（0721）：固定为扣B（13水）行为，触发后昏厥（扣晕），不跟随 dj_mode。
        不改变被C记录与处女状态。用于 ccb / bh 未指定目标且 self_ccb 开启时。返回待发送的消息链。
        """
        duration = round(random.uniform(0.1, 60), 2)
        V = round(random.uniform(0.01, 100), 2)
        now = time.time()

        rec, _ = store.record_dj_stats(group_id, send_id, V, mode="B")

        if self.is_log:
            try:
                store.append_log(group_id, send_id, send_id, duration, V)
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
            Comp.Plain(stat),
        ]
        if tail:
            chain.append(Comp.Plain("----------------------------------\n"))
            chain.append(Comp.Plain(tail))
        return chain
