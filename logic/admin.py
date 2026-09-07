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



async def ccbclear(inst, event):
    """
    管理员指令：清除某人的互C记录
    dj_mode=d 时（打胶/生命因子属互C体系）自交数据一并清除
    用法：ccbclear [@目标或QQ号]
    """
    if not await inst._is_admin(event):
        yield event.plain_result("无权限使用此命令")
        return
    group_id = str(event.get_group_id())
    target_user_id, err = await inst.state.resolve_target(event, str(event.message_str), group_id)
    if err:
        yield event.plain_result(err)
        return

    removed_self, removed_from_others = inst.store.remove_ccb_user(group_id, target_user_id)

    dj_cleared = False
    daily_deleted = inst.store.daily.remove_user("ccb", group_id, target_user_id, also_actor=True)
    if inst.state.dj_mode == "d":
        # 自交记录按配置归属：打胶（生命因子）随互C一起清除
        dj_cleared = inst.store.remove_self_user(group_id, target_user_id, "d")
        daily_deleted += inst.store.daily.remove_user("dj_d", group_id, target_user_id)

    nickname = await inst._get_nickname(event, target_user_id)
    msg = (
        f"已清除 {nickname} 的互C记录：\n"
        f"删除自身被C记录：{removed_self} 条\n"
        f"摘除ta在他人记录中的痕迹：{removed_from_others} 次"
    )
    if dj_cleared:
        msg += "\n打胶（生命因子）记录已一并清除"
    if daily_deleted > 0:
        msg += f"\n今日统计已同步清除：{daily_deleted} 条"
    if removed_from_others > 0:
        msg += "\n相关记录已重新校准"
    yield event.plain_result(msg)


async def bhclear(inst, event):
    """
    管理员指令：清除某人的百合记录
    dj_mode=B 时（扣B/13水属百合体系）自交数据一并清除
    用法：bhclear [@目标或QQ号]
    """
    if not await inst._is_admin(event):
        yield event.plain_result("无权限使用此命令")
        return
    group_id = str(event.get_group_id())
    target_user_id, err = await inst.state.resolve_target(event, str(event.message_str), group_id)
    if err:
        yield event.plain_result(err)
        return

    removed_bh = inst.store.remove_bh_user(group_id, target_user_id)

    dj_cleared = False
    daily_deleted = inst.store.daily.remove_user("bh", group_id, target_user_id)
    if inst.state.dj_mode == "B":
        # 自交记录按配置归属：扣B/13水（含百合并入的B_max）随百合一起清除
        dj_cleared = inst.store.remove_self_user(group_id, target_user_id, "B")
        daily_deleted += inst.store.daily.remove_user("dj_b", group_id, target_user_id)

    nickname = await inst._get_nickname(event, target_user_id)
    msg = f"已清除 {nickname} 的百合记录：\n删除自身被扣记录：{int(removed_bh)} 条"
    if dj_cleared:
        msg += "\n自扣（13水/B_max）记录已一并清除"
    if daily_deleted > 0:
        msg += f"\n今日统计已同步清除：{daily_deleted} 条"
    yield event.plain_result(msg)


async def hnclear(inst, event):
    """
    管理员指令：清除某人的喝奈记录（含ta在他人记录中的被喝史/初乳痕迹）
    用法：hnclear [@目标或QQ号]
    """
    if not await inst._is_admin(event):
        yield event.plain_result("无权限使用此命令")
        return
    group_id = str(event.get_group_id())
    target_user_id, err = await inst.state.resolve_target(event, str(event.message_str), group_id)
    if err:
        yield event.plain_result(err)
        return

    removed_self, traces = inst.store.remove_hn_user(group_id, target_user_id)
    daily_deleted = inst.store.daily.remove_user("hn", group_id, target_user_id)

    nickname = await inst._get_nickname(event, target_user_id)
    msg = (
        f"已清除 {nickname} 的喝奈记录：\n"
        f"删除自身记录：{removed_self} 条\n"
        f"摘除他人记录中的痕迹：{traces} 处"
    )
    if daily_deleted > 0:
        msg += f"\n今日统计已同步清除：{daily_deleted} 条"
    yield event.plain_result(msg)


async def ccbnodo(inst, event):
    """
    管理员指令：切换目标防被 CCB 状态
    用法：ccbnodo [@目标或QQ号]
    """
    if not await inst._is_admin(event):
        yield event.plain_result("无权限使用此命令")
        return

    group_id = str(event.get_group_id())
    # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
    target_user_id, err = await inst.state.resolve_target(event, str(event.message_str), group_id)
    if err:
        yield event.plain_result(err)
        return
    nickname = await inst._get_nickname(event, target_user_id)
    if target_user_id in inst.state.white_list:
        inst.state.white_list = [uid for uid in inst.state.white_list if uid != target_user_id]
        inst._save_white_list()
        yield event.plain_result(f"已解除 {nickname} 的保护状态")
    else:
        inst.state.white_list.append(target_user_id)
        inst._save_white_list()
        yield event.plain_result(f"已将 {nickname} 加入保护名单：ta无法被C和C别人了")


async def timeclear(inst, event):
    """
    管理员指令：强制结束指定用户的神罚/昏厥冷却
    用法：timeclear [@目标或QQ号]，不带目标则默认清除自己
    """
    if not await inst._is_admin(event):
        yield event.plain_result("无权限使用此命令")
        return

    group_id = str(event.get_group_id())
    # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
    target_user_id, err = await inst.state.resolve_target(event, str(event.message_str), group_id)
    if err:
        yield event.plain_result(err)
        return
    inst.state.ban_list.pop(target_user_id, None)
    inst.state.faint_list.pop(target_user_id, None)
    nickname = await inst._get_nickname(event, target_user_id)
    yield event.plain_result(f"已强制结束 {nickname} 的神罚/昏厥状态，ta又可以愉快的ccb了")

