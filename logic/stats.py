# -- coding: utf-8 --
# 本文件由 zt_split.py 从 main.py 机械生成；与旧 main.py 中同名方法体逐字一致（self→inst）。
import time
import random

from astrbot.api import logger
import astrbot.api.message_components as Comp

from .storage import (
    a1, a2, a3, a4, a5, a8, a9, a10, d_num, d_vol, d_max, bh_num, bh_vol,
    hn_num, hn_vol, hn_max, hn_first,
)
from .state import get_avatar, makeit, StateKeeper
from .text import time_long, volume



async def ccbtop(inst, event):
    """今日被ccb次数排行"""
    group_id = str(event.get_group_id())
    agg = inst._daily_agg("ccb", group_id)
    if not agg:
        yield event.plain_result("今日暂无ccb记录。" + inst._all_tip("ccbtop"))
        return
    top5 = sorted(agg.items(), key=lambda x: x[1]["num"], reverse=True)[:5]
    msg = "今日被ccb排行榜 TOP5：\n"
    for i, (uid, d) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        msg += f"{i}. {nick} - 被超：{d['num']}次，今日被注入{d['vol']:.2f}ml\n"
    msg += inst._all_tip("ccbtop")
    yield event.plain_result(msg)


async def ccbtopall(inst, event):
    """
    按次数排行
    """
    group_id = str(event.get_group_id())
    group_data = inst.store.ccb_group_records(group_id)
    if not group_data:
        yield event.plain_result("当前群暂无ccb记录。")
        return

    top5 = sorted(group_data, key=lambda x: int(x.get(a2, 0) or 0), reverse=True)[:5]
    msg = "被ccb排行榜 TOP5：\n"
    for i, r in enumerate(top5, 1):
        uid = r[a1]
        nick = await inst._get_nickname(event, uid)
        msg += f"{i}. {nick} - 被超：{int(r.get(a2, 0) or 0)}次，累计被注入{float(r.get(a3, 0) or 0):.2f}ml\n"
    yield event.plain_result(msg)


async def ccbvol(inst, event):
    """今日被注入量排行"""
    group_id = str(event.get_group_id())
    agg = inst._daily_agg("ccb", group_id)
    if not agg:
        yield event.plain_result("今日暂无ccb记录。" + inst._all_tip("ccbvol"))
        return
    top5 = sorted(agg.items(), key=lambda x: x[1]["vol"], reverse=True)[:5]
    msg = "今日被注入量排行榜 TOP5：\n"
    for i, (uid, d) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        msg += f"{i}. {nick} - 今日共被注入：{d['vol']:.2f}ml\n"
    msg += inst._all_tip("ccbvol")
    yield event.plain_result(msg)


async def ccbvolall(inst, event):
    """
    按注入量排行
    """
    group_id = str(event.get_group_id())
    group_data = inst.store.ccb_group_records(group_id)
    if not group_data:
        yield event.plain_result("当前群暂无ccb记录。")
        return

    top5 = sorted(group_data, key=lambda x: float(x.get(a3, 0)), reverse=True)[:5]
    msg = "被注入量排行榜 TOP5：\n"
    for i, r in enumerate(top5, 1):
        uid = r[a1]
        nick = await inst._get_nickname(event, uid)
        msg += f"{i}. {nick} - 共被注入：{float(r[a3]):.2f}ml\n"
    yield event.plain_result(msg)


async def ccbinfo(inst, event):
    """查询某人今日统计：被超/发起/注入/MAX/13水/百合/喝奈
    用法：ccbinfo [@目标]
    """
    group_id = str(event.get_group_id())
    target_user_id = inst._get_target_user_id(event)

    # 今日 ccb（被C侧）
    c = inst._daily_agg("ccb", group_id).get(target_user_id, {})
    num = c.get("num", 0)
    vol = c.get("vol", 0.0)
    mx = c.get("max", 0.0)
    cb_total = inst.store.daily.actor_count("ccb", group_id, target_user_id)

    # 今日自交（按配置模式）
    action = "dj_d" if inst.state.dj_mode == "d" else "dj_b"
    d = inst._daily_agg(action, group_id).get(target_user_id, {})
    dj_num, dj_vol, dj_max = d.get("num", 0), d.get("vol", 0.0), d.get("max", 0.0)
    dj_label, dj_unit = ("打胶", "生命因子") if inst.state.dj_mode == "d" else ("13水", "ml")

    # 今日百合 / 喝奈（喝奈不计自取次数，但泌乳量算有记录）
    b = inst._daily_agg("bh", group_id).get(target_user_id, {})
    h = inst._daily_agg("hn", group_id, count_self=False).get(target_user_id, {})

    # 今日完全无任何记录时直接提示（对齐 hninfo 的空数据提示）
    if not (num or cb_total or dj_num or b.get("num", 0)
            or h.get("num", 0) or h.get("vol", 0)):
        yield event.plain_result("该用户今日暂无任何记录。" + inst._all_tip("ccbinfo"))
        return

    target_nick = await inst._get_nickname(event, target_user_id)
    # 破壁人统一遵循 ccb.json 长期记录（与 ccbinfoall 一致），不随当日数据变化
    ccb_record = next(
        (r for r in inst.store.ccb_group_records(group_id) if r.get(a1) == target_user_id),
        None,
    )
    first_id = inst._json_first_actor(ccb_record)
    first_nick = await inst._get_nickname(event, first_id) if first_id else "未知"

    msg = (
        f"【{target_nick} 】(今日)\n"
        f"• 破壁人：{first_nick}\n"
        f"• ccb：被超:{num}(发起ccb:{cb_total},被注入:{vol:.2f}ml,MAX:{mx:.2f}ml)"
    )
    if dj_num > 0:
        msg += f"\n• {dj_label}：{dj_vol:.2f}{dj_unit}（{dj_num}次，单次最高{dj_max:.2f}ml）"
    if b.get("num", 0) > 0:
        msg += "\n• 百合：{:.2f}ml（被扣{}次，单次最高{:.2f}ml）".format(
            b.get("vol", 0), b.get("num", 0), b.get("max", 0))
    if h.get("num", 0) > 0 or h.get("vol", 0) > 0:
        msg += "\n• 喝奈：{:.2f}ml（喂养{}次，单次最高{:.2f}ml）".format(
            h.get("vol", 0), h.get("num", 0), h.get("max", 0))
    msg += inst._all_tip("ccbinfo")
    yield event.plain_result(msg)


async def ccbinfoall(inst, event):
    """
    查询某人ccb信息：第一次对他ccb的人，被ccb的总次数，注入总量
    用法：ccbinfo [@目标]
    """
    group_id = str(event.get_group_id())
    target_user_id = inst._get_target_user_id(event)

    # 读取群数据
    group_data = inst.store.ccb_group_records(group_id)

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

    # 找出第一次的操作者（first 标记者，无标记则取 count 最大者兜底）
    first_actor = inst._json_first_actor(record)

    # 获取昵称
    first_nick = first_actor or "未知"
    if first_actor:
        first_nick = await inst._get_nickname(event, first_actor)

    # 自交统计（按配置模式显示：扣B=13水，打胶=生命因子，数据来自独立文件）
    if inst.state.dj_mode == "d":
        rec = inst.store.get_group_data("dj.json", group_id).get(target_user_id, {})
        num_k, vol_k, max_k, label, unit = d_num, d_vol, d_max, "打胶", "生命因子"
    else:
        rec = inst.store.get_group_data("dj_b.json", group_id).get(target_user_id, {})
        num_k, vol_k, max_k, label, unit = a10, a8, a9, "13水", "ml"
    dj_num = int(rec.get(num_k, 0) or 0)
    dj_vol = float(rec.get(vol_k, 0) or 0)
    dj_max = float(rec.get(max_k, 0) or 0)

    # 百合统计（互扣，独立于 dj_mode；单次最高直接复用扣B的B_max）
    bh_rec = inst.store.get_group_data("bh.json", group_id).get(target_user_id, {})
    bh_n = int(bh_rec.get(bh_num, 0) or 0)
    bh_v = float(bh_rec.get(bh_vol, 0) or 0)
    bh_m = float(inst.store.get_group_data("dj_b.json", group_id).get(target_user_id, {}).get(a9, 0) or 0)

    # 输出结果（第一行显示昵称而非QQ号）
    target_nick = await inst._get_nickname(event, target_user_id)
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

async def ccbmax(inst, event):
    """今日单次最大注入排行（含产生者）"""
    group_id = str(event.get_group_id())
    agg = inst._daily_agg("ccb", group_id)
    entries = [(uid, d) for uid, d in agg.items() if d["max"] > 0]
    if not entries:
        yield event.plain_result("今日暂无ccb记录。" + inst._all_tip("ccbmax"))
        return
    top5 = sorted(entries, key=lambda x: x[1]["max"], reverse=True)[:5]
    msg = "今日单次最大注入排行榜 TOP5：\n"
    for i, (uid, d) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        producer = d.get("max_actor")
        pnick = await inst._get_nickname(event, producer) if producer else "未知"
        msg += f"{i}. {nick} - MAX注入：{d['max']:.2f}ml（{pnick}）\n"
    msg += inst._all_tip("ccbmax")
    yield event.plain_result(msg)


async def ccbmaxall(inst, event):
    """
    按max值排行并输出产生者
    """
    group_id = str(event.get_group_id())
    group_data = inst.store.ccb_group_records(group_id)
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
        nick = await inst._get_nickname(event, uid)
        producer_nick = producer_id or "未知"
        if producer_id:
            producer_nick = await inst._get_nickname(event, producer_id)

        msg += f"{i}. {nick} - MAX注入：{max_val:.2f}ml（{producer_nick}）\n"

    yield event.plain_result(msg)


async def xnn(inst, event):
    """今日XNN榜"""
    w_num, w_vol, w_action = 1.0, 0.1, 0.5
    group_id = str(event.get_group_id())
    rows = inst.store.daily.rows("ccb", group_id)
    agg = inst._daily_agg("ccb", group_id)
    if not agg:
        yield event.plain_result("今日暂无ccb记录。" + inst._all_tip("xnn"))
        return
    actor_actions = {}
    for _, actor, _ in rows:
        actor_actions[actor] = actor_actions.get(actor, 0) + 1
    ranking = []
    for uid, d in agg.items():
        ranking.append((uid, d["num"] * w_num + d["vol"] * w_vol - actor_actions.get(uid, 0) * w_action))
    ranking.sort(key=lambda x: x[1], reverse=True)
    msg = "💎 今日小南梁 TOP5 💎\n"
    for idx, (uid, xnn_val) in enumerate(ranking[:5], 1):
        nick = await inst._get_nickname(event, uid)
        d = agg.get(uid, {})
        msg += (f"{idx}. {nick} - XNN值：{xnn_val:.2f} \n"
                f"(被ccb次数：{d.get('num', 0)}，容量：{d.get('vol', 0):.2f}ml，对他人ccb：{actor_actions.get(uid, 0)})\n")
    msg += inst._all_tip("xnn")
    yield event.plain_result(msg)


async def xnnall(inst, event):
    """
    XNN榜
    计算群中最xnn特质的群友
    """
    # 配置权重
    w_num = 1.0
    w_vol = 0.1
    w_action = 0.5

    group_id = str(event.get_group_id())
    group_data = inst.store.ccb_group_records(group_id)
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
        nick = await inst._get_nickname(event, uid)
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

# ---- 管理员数据清除：互C / 百合 / 喝奈 各自独立 ----

async def djtop(inst, event):
    """今日自交榜（按配置模式）"""
    group_id = str(event.get_group_id())
    action = "dj_d" if inst.state.dj_mode == "d" else "dj_b"
    name = "打胶" if inst.state.dj_mode == "d" else "扣B"
    agg = inst._daily_agg(action, group_id)
    if not agg:
        yield event.plain_result("今日暂无自交记录。" + inst._all_tip("djtop"))
        return
    top5 = sorted(agg.items(), key=lambda x: x[1]["num"], reverse=True)[:5]
    msg = f"今日{name}排行榜 TOP5：\n"
    for i, (uid, d) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        msg += f"{i}. {nick} - {name}：{d['num']}次，今日累计{d['vol']:.2f}ml\n"
    msg += inst._all_tip("djtop")
    yield event.plain_result(msg)


async def djtopall(inst, event):
    """
    自交排行榜：按自交次数排行（数据与文案按配置模式：扣B=13水，打胶=生命因子）
    """
    group_id = str(event.get_group_id())
    group = inst.store.get_self_stats(group_id)
    num_k, vol_k = (d_num, d_vol) if inst.state.dj_mode == "d" else (a10, a8)
    name = "打胶" if inst.state.dj_mode == "d" else "扣B"

    entries = [(uid, rec) for uid, rec in group.items() if int(rec.get(num_k, 0) or 0) > 0]
    if not entries:
        yield event.plain_result("当前群暂无自交记录。")
        return

    top5 = sorted(entries, key=lambda x: int(x[1].get(num_k, 0)), reverse=True)[:5]
    msg = f" {name}排行榜 TOP5 \n"
    for i, (uid, rec) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        msg += f"{i}. {nick} - {name}：{int(rec.get(num_k, 0))}次，累计{float(rec.get(vol_k, 0) or 0):.2f}ml\n"
    yield event.plain_result(msg)


async def djmax(inst, event):
    """今日单次最高自交榜（按配置模式）"""
    group_id = str(event.get_group_id())
    action = "dj_d" if inst.state.dj_mode == "d" else "dj_b"
    unit = "生命因子" if inst.state.dj_mode == "d" else "13水"
    agg = inst._daily_agg(action, group_id)
    entries = [(uid, d) for uid, d in agg.items() if d["max"] > 0]
    if not entries:
        yield event.plain_result("今日暂无自交记录。" + inst._all_tip("djmax"))
        return
    top5 = sorted(entries, key=lambda x: x[1]["max"], reverse=True)[:5]
    msg = f"今日单次最高{unit} TOP5：\n"
    for i, (uid, d) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        msg += f"{i}. {nick} - 单次最高：{d['max']:.2f}ml\n"
    msg += inst._all_tip("djmax")
    yield event.plain_result(msg)


async def djmaxall(inst, event):
    """
    自交排行榜：按单次最高排行（数据与文案按配置模式：扣B=13水，打胶=生命因子）
    """
    group_id = str(event.get_group_id())
    group = inst.store.get_self_stats(group_id)
    max_k = d_max if inst.state.dj_mode == "d" else a9
    unit = "生命因子" if inst.state.dj_mode == "d" else "13水"

    entries = [(uid, rec) for uid, rec in group.items() if float(rec.get(max_k, 0) or 0) > 0]
    if not entries:
        yield event.plain_result("当前群暂无自交记录。")
        return

    top5 = sorted(entries, key=lambda x: float(x[1].get(max_k, 0) or 0), reverse=True)[:5]
    msg = f"💦 单次最高{unit} TOP5 💦\n"
    for i, (uid, rec) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        msg += f"{i}. {nick} - 单次最高：{float(rec.get(max_k, 0) or 0):.2f}ml\n"
    yield event.plain_result(msg)


async def bhtop(inst, event):
    """今日百合被扣榜"""
    group_id = str(event.get_group_id())
    agg = inst._daily_agg("bh", group_id)
    if not agg:
        yield event.plain_result("今日暂无百合记录。" + inst._all_tip("bhtop"))
        return
    top5 = sorted(agg.items(), key=lambda x: x[1]["num"], reverse=True)[:5]
    msg = "今日百合互扣排行榜 TOP5：\n"
    for i, (uid, d) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        msg += (f"{i}. {nick} - 被扣：{d['num']}次，"
                f"今日累计喷出{d['vol']:.2f}ml，"
                f"单次最高{d['max']:.2f}ml\n")
    msg += inst._all_tip("bhtop")
    yield event.plain_result(msg)


async def bhtopall(inst, event):
    """
    百合排行榜：按被扣次数排行
    """
    group_id = str(event.get_group_id())
    group = inst.store.get_group_data("bh.json", group_id)

    entries = [(uid, rec) for uid, rec in group.items() if int(rec.get(bh_num, 0) or 0) > 0]
    if not entries:
        yield event.plain_result("当前群暂无百合记录。")
        return

    top5 = sorted(entries, key=lambda x: int(x[1].get(bh_num, 0)), reverse=True)[:5]
    b_data = inst.store.get_group_data("dj_b.json", group_id)
    msg = "🌺 百合互扣排行榜 TOP5 🌺\n"
    for i, (uid, rec) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        bmax = float(b_data.get(uid, {}).get(a9, 0) or 0)
        msg += (f"{i}. {nick} - 被扣：{int(rec.get(bh_num, 0))}次，"
                f"累计喷出{float(rec.get(bh_vol, 0) or 0):.2f}ml，"
                f"单次最高{bmax:.2f}ml\n")
    yield event.plain_result(msg)


async def hntop(inst, event):
    """今日泌乳榜"""
    group_id = str(event.get_group_id())
    agg = inst._daily_agg("hn", group_id, count_self=False)
    # 只对今日有喂养行为的人排行（自取不计次数，因此不上榜）
    entries = [(uid, d) for uid, d in agg.items() if d["num"] > 0]
    if not entries:
        yield event.plain_result("今日暂无喝奈记录。" + inst._all_tip("hntop"))
        return
    top5 = sorted(entries, key=lambda x: x[1]["num"], reverse=True)[:5]
    msg = "今日泌乳排行榜 TOP5：\n"
    for i, (uid, d) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        msg += f"{i}. {nick} 今日喂养了群友{d['num']}次，今日被喝{d['vol']:.2f}ml\n"
    msg += inst._all_tip("hntop")
    yield event.plain_result(msg)


async def hntopall(inst, event):
    """
    泌乳排行榜：按喂养次数排行
    """
    group_id = str(event.get_group_id())
    group = inst.store.get_group_data("hn.json", group_id)

    entries = [(uid, rec) for uid, rec in group.items() if int(rec.get(hn_num, 0) or 0) > 0]
    if not entries:
        yield event.plain_result("当前群暂无喝奈记录。")
        return

    top5 = sorted(entries, key=lambda x: int(x[1].get(hn_num, 0)), reverse=True)[:5]
    msg = "🍼 泌乳排行榜 TOP5 🍼\n"
    for i, (uid, rec) in enumerate(top5, 1):
        nick = await inst._get_nickname(event, uid)
        msg += (f"{i}. {nick} 总共喂养了群友{int(rec.get(hn_num, 0))}次，"
                f"累计泌乳{float(rec.get(hn_vol, 0) or 0):.2f}ml\n")
    yield event.plain_result(msg)


async def hninfo(inst, event):
    """查询某人今日泌乳：初乳被谁喝了、单次最大、累计
    用法：hninfo [@目标]
    """
    group_id = str(event.get_group_id())
    target_user_id = inst._get_target_user_id(event)
    target_nick = await inst._get_nickname(event, target_user_id)
    d = inst._daily_agg("hn", group_id, count_self=False).get(target_user_id, {})
    num = d.get("num", 0)
    # 今日只有自取时 num=0，但泌乳量仍可展示；完全无记录才提示
    if not d:
        yield event.plain_result("该用户今日暂无喝奈记录。" + inst._all_tip("hninfo"))
        return
    # 初乳不可替代：统一读 hn.json 的永久记录（与 hninfoall 一致），而非当天的第一个喝者
    hn_rec = inst.store.get_group_data("hn.json", group_id).get(target_user_id, {})
    first_id = hn_rec.get(hn_first)
    first_nick = await inst._get_nickname(event, first_id) if first_id else "未知"
    msg = (
        f"【{target_nick} 】(今日)\n"
        f"• 初乳被喝：{first_nick}\n"
        f"• 今日喂养：{num}次\n"
        f"• 今日泌乳：{d.get('vol', 0):.2f}ml\n"
        f"• 今日单次最大：{d.get('max', 0):.2f}ml"
    )
    msg += inst._all_tip("hninfo")
    yield event.plain_result(msg)


async def hninfoall(inst, event):
    """
    查询泌乳信息：初乳被谁喝了、被喝史、单次最大泌乳量、累计泌乳量
    用法：hninfo [@目标]
    """
    group_id = str(event.get_group_id())
    target_user_id = inst._get_target_user_id(event)

    rec = inst.store.get_group_data("hn.json", group_id).get(target_user_id, {})
    # 自取不计次数：只自取过的用户 hn_num=0，但仍要展示初乳/泌乳信息
    if int(rec.get(hn_num, 0) or 0) <= 0 and not rec.get(hn_first):
        yield event.plain_result("该用户暂无喝奈记录。")
        return

    # 初乳喝者（第一个喝到的人）
    first_id = rec.get(hn_first)
    first_nick = "未知"
    if first_id:
        first_nick = await inst._get_nickname(event, first_id)
    target_nick = await inst._get_nickname(event, target_user_id)

    msg = (
        f"【{target_nick} 】\n"
        f"• 初乳被喝：{first_nick}\n"
        f"• 喂养：{int(rec.get(hn_num, 0))}次\n"
        f"• 累计泌乳：{float(rec.get(hn_vol, 0) or 0):.2f}ml\n"
        f"• 单次最大泌乳：{float(rec.get(hn_max, 0) or 0):.2f}ml"
    )
    yield event.plain_result(msg)
