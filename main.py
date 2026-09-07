# -- coding: utf-8 --
"""
CCB PLUS 插件入口：命令注册与编排（薄壳）。
AstrBot 只把「与 Star 类同一模块」中定义的 @filter.command 方法绑定到插件实例，
所以带装饰器的方法必须留在本文件；具体逻辑委托给 logic/ 子包：
  logic.actions = 行为命令演出（ccb/dj/bh/hnn）
  logic.stats   = 每日/累计排行与查询构建（20 个 top/info）
  logic.admin   = 管理员命令（clear/nodo/timeclear）
  logic.state / logic.storage / logic.text = 状态层 / 数据层 / 文案层
"""
import asyncio

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp

from .logic import actions, stats, admin
from .logic.state import StateKeeper
from .logic.storage import DataStore, a4

HELP_INFO = """
/ccb ccb，顾名思义，用来ccb 用法： ccb [@或QQ号]，如果不带有@某人则根据配置文件进行自交或者打胶
每日统计（当日数据，每日自动重置）：
/ccbinfo  查询某人今日统计（被超/发起/注入/MAX/13水/百合/喝奈），用法：ccbinfo [@目标]
/ccbtop 今日被C次数榜 | /ccbvol 今日注入量榜 | /ccbmax 今日单次MAX榜 | /xnn 今日小南梁榜
/djtop 今日自交次数榜 | /djmax 今日单次最高榜（按配置模式）
/bhtop 今日百合被扣榜 | /hntop 今日泌乳榜 | /hninfo 查询今日泌乳，用法：hninfo [@目标]
累计统计（长期数据，不重置）：
/ccbinfoall 查询某人累计统计（用法同 ccbinfo）
/ccbtopall 累计被C次数榜 | /ccbvolall 累计注入量榜 | /ccbmaxall 累计单次MAX榜 | /xnnall 累计小南梁榜
/djtopall 累计自交次数榜 | /djmaxall 累计单次最高榜（按配置模式）
/bhtopall 累计百合榜 | /hntopall 累计泌乳榜 | /hninfoall 查询累计泌乳
行为命令：
/dj 自交功能：按配置文件模式执行（B=扣B记录13水，d=打胶记录生命因子），不改变处女状态，可能昏厥（概率可配置）
/bh 百合：和群友互扣，被扣的人喷出B水并记录，用法：bh [@目标或QQ号]
/hnn 喝奈奈：从目标汲取奶喝，无@时自取其乳，用法：hnn [@或QQ号]（受禁C名单控制）
/ccbclear   管理员：清除某人的互C记录（dj_mode=d 时连带打胶），用法：ccbclear [@或QQ号]
/bhclear   管理员：清除某人的百合记录（dj_mode=B 时连带自扣13水），用法：bhclear [@或QQ号]
/hnclear   管理员：清除某人的喝奈记录（含他人记录中的痕迹），用法：hnclear [@或QQ号]
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
        self.state = StateKeeper(config)                 # 状态层：冷却/目标解析/自交演出
        self.store = DataStore(self.state.dj_mode)       # 数据层：JSON读写/每日统计
        self._cmd_lock = asyncio.Lock()                  # 串行化命令执行，防并发读写JSON丢更新
        # 注意：旧版 data/ 相对路径的数据不会自动迁移，请参照 README 手动复制到 plugin_data 目录
        self.store.migrate_legacy_b_data()               # 旧版 ccb.json 中的B水字段迁移到 dj_b.json

    async def _run(self, fn, event: AstrMessageEvent):
        """在全局锁内执行命令逻辑并转发结果（防止两个命令交错读写同一 JSON 造成丢失更新）"""
        async with self._cmd_lock:
            async for r in fn(self, event):
                yield r

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
             if isinstance(seg, Comp.At) and getattr(seg, "qq", None) is not None
             and str(seg.qq) != self_id),
            str(event.get_sender_id())
        )

    def _daily_agg(self, action: str, group_id: str, count_self: bool = True) -> dict:
        """当日行为记录聚合：{用户ID: {num, vol, max, first, max_actor}}
        count_self=False 时（喝奈自取）：user==actor 的自取行为不计入次数，
        但泌乳量/单次最高/当日首喝仍纳入统计。"""
        rows = self.store.daily.rows(action, group_id)
        agg = {}
        for user_id, actor, vol in rows:
            d = agg.setdefault(user_id, {"num": 0, "vol": 0.0, "max": 0.0, "first": None, "max_actor": None})
            if count_self or user_id != actor:
                d["num"] += 1
            d["vol"] = round(d["vol"] + float(vol), 2)
            if float(vol) > d["max"]:
                d["max"] = round(float(vol), 2)
                d["max_actor"] = actor
            if d["first"] is None:
                d["first"] = actor
        return agg

    @staticmethod
    def _all_tip(cmd: str) -> str:
        """每日统计命令的尾巴提示：引导查看对应的 all（累计）版本"""
        return f"\n💡如果想看总数据，可以使用此命令的 all 版本（/{cmd}all）"

    @staticmethod
    def _json_first_actor(record: dict):
        """从 ccb.json 记录取破壁人：a4 中带 first 标记的操作者，无标记则取 count 最大者兜底"""
        if not isinstance(record, dict):
            return None
        ccb_by = record.get(a4, {}) or {}
        if not isinstance(ccb_by, dict):
            return None
        for actor_id, info in ccb_by.items():
            if isinstance(info, dict) and info.get("first"):
                return actor_id
        try:
            return max(
                ccb_by.items(),
                key=lambda x: int(x[1].get("count", 0)) if isinstance(x[1], dict) else 0
            )[0]
        except Exception:
            return None

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
        async for r in self._run(actions.ccb, event):
            yield r

    @filter.command("ccbtop")
    async def ccbtop(self, event: AstrMessageEvent):
        """今日被ccb次数排行"""
        async for r in self._run(stats.ccbtop, event):
            yield r

    @filter.command("ccbtopall")
    async def ccbtopall(self, event: AstrMessageEvent):
        """
        按次数排行
        """
        async for r in self._run(stats.ccbtopall, event):
            yield r

    @filter.command("ccbvol")
    async def ccbvol(self, event: AstrMessageEvent):
        """今日被注入量排行"""
        async for r in self._run(stats.ccbvol, event):
            yield r

    @filter.command("ccbvolall")
    async def ccbvolall(self, event: AstrMessageEvent):
        """
        按注入量排行
        """
        async for r in self._run(stats.ccbvolall, event):
            yield r

    @filter.command("ccbinfo")
    async def ccbinfo(self, event: AstrMessageEvent):
        """查询某人今日统计：被超/发起/注入/MAX/13水/百合/喝奈
        用法：ccbinfo [@目标]
        """
        async for r in self._run(stats.ccbinfo, event):
            yield r

    @filter.command("ccbinfoall")
    async def ccbinfoall(self, event: AstrMessageEvent):
        """
        查询某人ccb信息：第一次对他ccb的人，被ccb的总次数，注入总量
        用法：ccbinfo [@目标]
        """
        async for r in self._run(stats.ccbinfoall, event):
            yield r

    # 单次注入排行榜
    @filter.command("ccbmax")
    async def ccbmax(self, event: AstrMessageEvent):
        """今日单次最大注入排行（含产生者）"""
        async for r in self._run(stats.ccbmax, event):
            yield r

    @filter.command("ccbmaxall")
    async def ccbmaxall(self, event: AstrMessageEvent):
        """
        按max值排行并输出产生者
        """
        async for r in self._run(stats.ccbmaxall, event):
            yield r

    @filter.command("xnn")
    async def xnn(self, event: AstrMessageEvent):
        """今日XNN榜"""
        async for r in self._run(stats.xnn, event):
            yield r

    @filter.command("xnnall")
    async def xnnall(self, event: AstrMessageEvent):
        """
        XNN榜
        计算群中最xnn特质的群友
        """
        async for r in self._run(stats.xnnall, event):
            yield r

    # ---- 管理员数据清除：互C / 百合 / 喝奈 各自独立 ----
    @filter.command("ccbclear")
    async def ccbclear(self, event: AstrMessageEvent):
        """
        管理员指令：清除某人的互C记录
        dj_mode=d 时（打胶/生命因子属互C体系）自交数据一并清除
        用法：ccbclear [@目标或QQ号]
        """
        async for r in self._run(admin.ccbclear, event):
            yield r

    @filter.command("bhclear")
    async def bhclear(self, event: AstrMessageEvent):
        """
        管理员指令：清除某人的百合记录
        dj_mode=B 时（扣B/13水属百合体系）自交数据一并清除
        用法：bhclear [@目标或QQ号]
        """
        async for r in self._run(admin.bhclear, event):
            yield r

    @filter.command("hnclear")
    async def hnclear(self, event: AstrMessageEvent):
        """
        管理员指令：清除某人的喝奈记录（含ta在他人记录中的被喝史/初乳痕迹）
        用法：hnclear [@目标或QQ号]
        """
        async for r in self._run(admin.hnclear, event):
            yield r

    @filter.command("ccbnodo")
    async def ccbnodo(self, event: AstrMessageEvent):
        """
        管理员指令：切换目标防被 CCB 状态
        用法：ccbnodo [@目标或QQ号]
        """
        async for r in self._run(admin.ccbnodo, event):
            yield r

    @filter.command("timeclear")
    async def timeclear(self, event: AstrMessageEvent):
        """
        管理员指令：强制结束指定用户的神罚/昏厥冷却
        用法：timeclear [@目标或QQ号]，不带目标则默认清除自己
        """
        async for r in self._run(admin.timeclear, event):
            yield r

    @filter.command("dj")
    async def dj(self, event: AstrMessageEvent):
        """
        打胶：随机B水并记录（不影响被C记录与处女状态），可能随机昏厥
        禁C名单中的用户也可使用本命令
        """
        async for r in self._run(actions.dj, event):
            yield r

    @filter.command("djtop")
    async def djtop(self, event: AstrMessageEvent):
        """今日自交榜（按配置模式）"""
        async for r in self._run(stats.djtop, event):
            yield r

    @filter.command("djtopall")
    async def djtopall(self, event: AstrMessageEvent):
        """
        自交排行榜：按自交次数排行（数据与文案按配置模式：扣B=13水，打胶=生命因子）
        """
        async for r in self._run(stats.djtopall, event):
            yield r

    @filter.command("djmax")
    async def djmax(self, event: AstrMessageEvent):
        """今日单次最高自交榜（按配置模式）"""
        async for r in self._run(stats.djmax, event):
            yield r

    @filter.command("djmaxall")
    async def djmaxall(self, event: AstrMessageEvent):
        """
        自交排行榜：按单次最高排行（数据与文案按配置模式：扣B=13水，打胶=生命因子）
        """
        async for r in self._run(stats.djmaxall, event):
            yield r

    @filter.command("bh")
    async def bh(self, event: AstrMessageEvent):
        """
        百合：和群友互扣，被扣的人喷出B水并记录到独立数据
        用法：bh [@目标或QQ号]
        """
        async for r in self._run(actions.bh, event):
            yield r

    @filter.command("bhtop")
    async def bhtop(self, event: AstrMessageEvent):
        """今日百合被扣榜"""
        async for r in self._run(stats.bhtop, event):
            yield r

    @filter.command("bhtopall")
    async def bhtopall(self, event: AstrMessageEvent):
        """
        百合排行榜：按被扣次数排行
        """
        async for r in self._run(stats.bhtopall, event):
            yield r

    @filter.command("hnn")
    async def hnn(self, event: AstrMessageEvent):
        """
        喝奈奈：从目标汲取奶喝（泌乳），记录喂养次数与泌乳量
        用法：hnn [@目标或QQ号]
        """
        async for r in self._run(actions.hnn, event):
            yield r

    @filter.command("hntop")
    async def hntop(self, event: AstrMessageEvent):
        """今日泌乳榜"""
        async for r in self._run(stats.hntop, event):
            yield r

    @filter.command("hntopall")
    async def hntopall(self, event: AstrMessageEvent):
        """
        泌乳排行榜：按喂养次数排行
        """
        async for r in self._run(stats.hntopall, event):
            yield r

    @filter.command("hninfo")
    async def hninfo(self, event: AstrMessageEvent):
        """查询某人今日泌乳：初乳被谁喝了、单次最大、累计
        用法：hninfo [@目标]
        """
        async for r in self._run(stats.hninfo, event):
            yield r

    @filter.command("hninfoall")
    async def hninfoall(self, event: AstrMessageEvent):
        """
        查询泌乳信息：初乳被谁喝了、被喝史、单次最大泌乳量、累计泌乳量
        用法：hninfo [@目标]
        """
        async for r in self._run(stats.hninfoall, event):
            yield r
