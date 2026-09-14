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



async def ccb(inst, event):
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
    target_user_id, err = await inst.state.resolve_target(event, str(event.message_str), group_id)
    if err:
        yield event.plain_result(err)
        return

    faint_time = inst.state.faint_time()

    yw_prob_r1 = random.random()
    if yw_prob_r1 < inst.state.yw_prob:
        yw_prob_r = yw_prob_r1
        faint_prob_r = 1.0
    else:
        faint_prob_r = random.random()
        yw_prob_r = 1.0

    # 神罚检查（独立）
    ban_msg = inst.state.check_ban(actor_id, user_name)
    if ban_msg:
        yield event.plain_result(ban_msg)
        return
    # 昏厥检查（独立）
    faint_msg = inst.state.check_faint(actor_id, user_name)
    if faint_msg:
        yield event.plain_result(faint_msg)
        return
    faint_end_target = inst.state.faint_list.get(target_user_id, 0)

    # 滑窗限流（ccb/bh/dj 共用同一窗口计数与约束）
    rate_msg = inst.state.rate_limit(actor_id, now)
    if rate_msg:
        yield event.plain_result(rate_msg)
        return

    # 自交（0721）：固定扣B，不改变处女状态。禁C名单用户也可自交
    if target_user_id == actor_id:
        if not inst.state.selfdo:
            chain = [Comp.Plain(f"{user_name}，暂时不允许自交哦！")]
            yield event.chain_result(chain)
            return
        yield event.chain_result(inst.state.self_play(inst.store, group_id, send_id, user_name, faint_time))
        return

    # 禁C名单：名单内用户不能发起与他人的ccb（但可自交，也可/dj）
    if actor_id in inst.state.white_list:
        yield event.plain_result("神明剥夺了你求偶的权力，你无法发起ccb/百合")
        return

    # 禁C名单：名单内用户不能被他人ccb
    if target_user_id in inst.state.white_list:
        nickname = await inst._get_nickname(event, target_user_id)
        yield event.plain_result(f"{nickname}拒绝了和你ccb/百合")
        return

    # CCB 逻辑
    duration = round(random.uniform(0.1, 60), 2)
    V = round(random.uniform(0.01, 100), 2)
    user_name = event.get_sender_name()
    is_log = inst.state.is_log
    if random.random() < inst.state.crit_prob:
        V = round(V * 2, 2)

    pic = get_avatar(target_user_id)

    all_data = inst.store.read_ccb()
    raw = all_data.get(group_id, [])
    if not isinstance(raw, list):
        # 脏数据（{用户ID: 记录} 等）先归一化为列表并写回，避免整组丢失
        raw = inst.store._coerce_ccb_group(raw)
        all_data[group_id] = raw
    group_data = raw

    mode = makeit(group_data, target_user_id)
    if mode == 1:
        # 已有记录，更新
        try:
            for item in group_data:
                if item.get(a1) == target_user_id:
                    # 获取昵称
                    nickname = await inst._get_nickname(event, target_user_id)

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
                    if yw_prob_r < inst.state.yw_prob:
                        inst.state.ban_list[actor_id] = now + inst.state.ban_duration
                        m, s = divmod(int(inst.state.ban_duration), 60)

                        chain = [
                            Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                            Comp.Plain(f"这是ta的第{item[a2]}次。ta被累积注入了{item[a3]}ml的生命因子。\n"),
                            Comp.Plain(f"同时神明看你不顺眼，降下{m}分{s}秒的神罚")
                        ]
                        if inst.state.show_avatar: chain.insert(1, Comp.Image.fromURL(pic))
                        yield event.chain_result(chain)

                    # 目标正处于昏厥中（faint_end_target 为0表示从未昏厥，不满足 f_now <= 0）
                    elif f_now <= faint_end_target:
                        remain = int(faint_end_target - f_now)
                        m1, s1 = divmod(remain, 60)
                        chain = [
                            Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                            Comp.Plain(f"这是ta的第{item[a2]}次。ta被累积注入了{item[a3]}ml的生命因子。\n"),
                            Comp.Plain(f"同时{nickname}现在正处于昏厥中，ta现在什么也干不了，剩余 {m1}分{s1}秒")
                        ]
                        if inst.state.show_avatar: chain.insert(1, Comp.Image.fromURL(pic))
                        yield event.chain_result(chain)

                    # 随机昏厥
                    elif faint_prob_r < inst.state.faint_prob:
                        inst.state.faint_list[target_user_id] = f_now + faint_time
                        # 注意：faint_end_target 是命令开头读取的旧值（目标此前未昏厥时为0），
                        # 触发后必须用本次的 faint_time 计算剩余时间，否则会出现负数
                        remain = int(faint_time)
                        m1, s1 = divmod(remain, 60)
                        chain = [
                            Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                            Comp.Plain(f"这是ta的第{item[a2]}次。ta被累积注入了{item[a3]}ml的生命因子。\n"),
                            Comp.Plain(f"同时{nickname} 被 {user_name} C晕了，接下来ta将毫无还手之力，剩余 {m1}分{s1}秒")
                        ]
                        if inst.state.show_avatar: chain.insert(1, Comp.Image.fromURL(pic))
                        yield event.chain_result(chain)

                    else:
                        chain = [
                            Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                            Comp.Plain(f"这是ta的第{item[a2]}次。ta被累积注入了{item[a3]}ml的生命因子。")
                            ]
                        if inst.state.show_avatar: chain.insert(1, Comp.Image.fromURL(pic))
                        yield event.chain_result(chain)

                    # 是否保留完整日志
                    if is_log:
                        try:
                            inst.store.append_log(group_id, send_id, target_user_id, duration, V)
                        except Exception as e:
                            logger.warning(f"记录日志失败: {e}")

                    # 每日统计写入
                    inst.store.daily.log("ccb", group_id, target_user_id, send_id, V)

                    # 写回数据
                    all_data[group_id] = group_data
                    inst.store.write_ccb(all_data)
                    return
        except Exception as e:
            logger.error(f"报错: {e}")
            yield event.plain_result("对方拒绝了和你ccb")
            return

    else:
        # 新记录
        try:
            nickname = await inst._get_nickname(event, target_user_id)

            # 随机养胃
            if yw_prob_r < inst.state.yw_prob_first:
                inst.state.ban_list[actor_id] = now + inst.state.ban_duration
                m, s = divmod(int(inst.state.ban_duration), 60)
                chain = [
                Comp.Plain(f"{user_name} 和 {nickname}发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                Comp.Plain("这是ta的初体验~，你把人家的处给破了喵～要负责哦喵～\n"),
                Comp.Plain(f"同时神明看你不顺眼，降下{m}分{s}秒的神罚")
                ]
                if inst.state.show_avatar: chain.insert(1, Comp.Image.fromURL(pic))
                yield event.chain_result(chain)

            # 随机昏厥
            elif faint_prob_r < inst.state.faint_prob_first:
                inst.state.faint_list[target_user_id] = f_now + faint_time
                chain = [
                Comp.Plain(f"{user_name} 和 {nickname}发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                Comp.Plain("这是ta的初体验~，你把人家的处给破了喵～要负责哦喵～\n"),
                Comp.Plain(f"同时{nickname}被{user_name}C晕了，接下来ta将毫无还手之力")
                ]
                if inst.state.show_avatar: chain.insert(1, Comp.Image.fromURL(pic))
                yield event.chain_result(chain)

            else:
                chain = [
                    Comp.Plain(f"{user_name} 和 {nickname}发生了{duration}min长的ccb行为，{nickname}被注入了{V:.2f}ml的生命因子"),
                    Comp.Plain("这是ta的初体验~，你把人家的处给破了喵～要负责哦喵～")
                ]
                if inst.state.show_avatar: chain.insert(1, Comp.Image.fromURL(pic))
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
            # 每日统计写入
            inst.store.daily.log("ccb", group_id, target_user_id, send_id, V)
            all_data[group_id] = group_data
            inst.store.write_ccb(all_data)

            # 是否保留完整日志
            if is_log:
                try:
                    inst.store.append_log(group_id, send_id, target_user_id, duration, V)
                except Exception as e:
                    logger.warning(f"记录日志失败: {e}")
            return
        except Exception as e:
            logger.error(f"报错: {e}")
            yield event.plain_result("对方拒绝了和你ccb")
            return



async def dj(inst, event):
    """
    打胶：随机B水并记录（不影响被C记录与处女状态），可能随机昏厥
    禁C名单中的用户也可使用本命令
    """
    group_id = str(event.get_group_id())
    send_id = str(event.get_sender_id())
    user_name = event.get_sender_name()
    now = time.time()
    faint_time = inst.state.faint_time()

    # 神罚检查（独立）
    ban_msg = inst.state.check_ban(send_id, user_name)
    if ban_msg:
        yield event.plain_result(ban_msg)
        return
    # 昏厥检查（独立）
    faint_msg = inst.state.check_faint(send_id, user_name)
    if faint_msg:
        yield event.plain_result(faint_msg)
        return

    # 滑窗限流（ccb/bh/dj 共用同一窗口计数与约束）
    rate_msg = inst.state.rate_limit(send_id, now)
    if rate_msg:
        yield event.plain_result(rate_msg)
        return

    timep = round(random.uniform(1, 666), 2)
    V = round(random.uniform(0.01, 100), 2)

    # 按配置模式记录自交数据到独立文件（不改变被C记录，不改变处女状态）
    rec, (num_k, vol_k, _) = inst.store.record_dj_stats(group_id, send_id, V)

    # 每日统计写入（扣B/打胶按配置模式区分）
    inst.store.daily.log("dj_d" if inst.state.dj_mode == "d" else "dj_b", group_id, send_id, send_id, V)

    # 是否保留完整日志
    if inst.state.is_log:
        try:
            inst.store.append_log(group_id, send_id, send_id, timep, V)
        except Exception as e:
            logger.warning(f"记录日志失败: {e}")

    # 随机昏厥（概率可配置）
    if inst.state.dj_mode == "d":
        # 打胶：打出生命因子，back.py 文案特供
        a = time_long(timep)
        b = volume(V)
        head = f"{user_name}，你坚持了{timep}s哦，{a}。射出了{V:.2f}ml的生命因子，{b}！"
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
    # 自交头像按 show_self_avatar 配置显示
    if inst.state.show_self_avatar:
        chain.insert(1, Comp.Image.fromURL(get_avatar(send_id)))
    if random.random() < inst.state.dj_faint_prob:
        if inst.state.dj_mode == "d":
            # 打胶：射空 → 被降下神罚
            inst.state.ban_list[send_id] = now + inst.state.ban_duration
            tail = f"同时{user_name}射空了，被降下{int(inst.state.ban_duration // 60)}分钟的神罚"
        else:
            # 扣B：喷晕 → 昏厥，末尾显示昏厥时长
            inst.state.faint_list[send_id] = now + faint_time
            remain = int(faint_time)
            m, s = divmod(remain, 60)
            tail = f"同时{user_name} 不小心扣晕了，接下来ta什么也做不了（剩余 {m}分{s}秒）"
        chain.append(Comp.Plain(tail))
    yield event.chain_result(chain)


async def bh(inst, event):
    """
    百合：和群友互扣，被扣的人喷出B水并记录到独立数据
    用法：bh [@目标或QQ号]
    """
    group_id = str(event.get_group_id())
    send_id = str(event.get_sender_id())
    user_name = event.get_sender_name()
    now = time.time()
    # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
    target_user_id, err = await inst.state.resolve_target(event, str(event.message_str), group_id)
    if err:
        yield event.plain_result(err)
        return

    # 发起者神罚检查（独立，与 /ccb 相同）
    ban_msg = inst.state.check_ban(send_id, user_name)
    if ban_msg:
        yield event.plain_result(ban_msg)
        return
    # 发起者昏厥检查（独立）
    faint_msg = inst.state.check_faint(send_id, user_name)
    if faint_msg:
        yield event.plain_result(faint_msg)
        return

    # 滑窗限流（ccb/bh/dj 共用同一窗口计数与约束，自交也计数）
    rate_msg = inst.state.rate_limit(send_id, now)
    if rate_msg:
        yield event.plain_result(rate_msg)
        return

    # 无@自交：与 /ccb 0721 相同的自交逻辑（受 self_ccb 配置控制、白名单豁免）
    if target_user_id == send_id:
        if not inst.state.selfdo:
            chain = [Comp.Plain(f"{user_name}，暂时不允许紫薇哦！")]
            yield event.chain_result(chain)
            return
        faint_time = inst.state.faint_time()
        yield event.chain_result(inst.state.self_play(inst.store, group_id, send_id, user_name, faint_time))
        return

    # 禁C名单：不能发起百合
    if send_id in inst.state.white_list:
        yield event.plain_result("神明剥夺了你求偶的权力，你无法发起ccb/百合")
        return
    # 禁C名单：不能被百合
    if target_user_id in inst.state.white_list:
        nickname = await inst._get_nickname(event, target_user_id)
        yield event.plain_result(f"{nickname}拒绝了和你ccb/百合")
        return

    duration = round(random.uniform(0.1, 60), 2)
    V_B = round(random.uniform(0.01, 100), 2)
    if random.random() < inst.state.crit_prob:
        V_B = round(V_B * 2, 2)

    # 被扣者状态：当前是否已昏厥、昏厥时长（与全插件同一套可配置时长）
    faint_end_target = inst.state.faint_list.get(target_user_id, 0)
    is_target_fainting = now <= faint_end_target
    faint_time = inst.state.faint_time()

    # 记录被扣者的百合数据，并将最大值并入扣B的B_max
    rec = inst.store.record_bh_stats(group_id, target_user_id, V_B)
    inst.store.merge_b_max(group_id, target_user_id, V_B)
    # 每日统计写入
    inst.store.daily.log("bh", group_id, target_user_id, send_id, V_B)
    nickname = await inst._get_nickname(event, target_user_id)

    # 是否保留完整日志
    if inst.state.is_log:
        try:
            inst.store.append_log(group_id, send_id, target_user_id, duration, V_B)
        except Exception as e:
            logger.warning(f"记录日志失败: {e}")

    chain = [
        Comp.Plain(f"{user_name} 和 {nickname} 发生了{duration}min长的百合互扣，{nickname}被扣出了{V_B:.2f}ml的13水"),
        Comp.Plain(f"这是ta的第{rec[bh_num]}次被扣。ta被扣出了累计{rec[bh_vol]}ml的13水。\n"),
    ]
    if inst.state.show_avatar:
        chain.insert(1, Comp.Image.fromURL(get_avatar(target_user_id)))
    # 被扣者昏厥：已在昏厥中则提示剩余，否则按概率触发昏厥（概率/时长与ccb互C一致）
    if is_target_fainting:
        remain = int(faint_end_target - now)
        m, s = divmod(remain, 60)
        tail = f"同时{nickname}现在正处于昏厥中，ta现在什么也干不了，剩余 {m}分{s}秒"
    elif random.random() < inst.state.faint_prob:
        inst.state.faint_list[target_user_id] = now + faint_time
        remain = int(faint_time)
        m, s = divmod(remain, 60)
        tail = f"同时{nickname}被{user_name}扣晕了，接下来ta将毫无还手之力，剩余 {m}分{s}秒"
    else:
        tail = None
    if tail:
        chain.append(Comp.Plain(tail))
    yield event.chain_result(chain)


async def hnn(inst, event):
    """
    喝奈奈：从目标汲取奶喝（泌乳），记录喂养次数与泌乳量
    用法：hnn [@目标或QQ号]
    """
    group_id = str(event.get_group_id())
    send_id = str(event.get_sender_id())
    user_name = event.get_sender_name()
    now = time.time()
    # 目标解析：优先@，其次消息中的QQ号（需在本群），默认自己
    target_user_id, err = await inst.state.resolve_target(event, str(event.message_str), group_id)
    if err:
        yield event.plain_result(err)
        return

    # 神罚检查（独立）
    ban_msg = inst.state.check_ban(send_id, user_name)
    if ban_msg:
        yield event.plain_result(ban_msg)
        return
    # 昏厥检查（独立）
    faint_msg = inst.state.check_faint(send_id, user_name)
    if faint_msg:
        yield event.plain_result(faint_msg)
        return

    # 滑窗限流（与其他命令共用同一窗口计数与约束）
    rate_msg = inst.state.rate_limit(send_id, now)
    if rate_msg:
        yield event.plain_result(rate_msg)
        return

    # 无@自交：自取其乳（受 self_ccb 配置控制、白名单豁免）
    if target_user_id == send_id:
        if not inst.state.selfdo:
            chain = [Comp.Plain(f"{user_name}，暂时不允许自取其乳哦！")]
            yield event.chain_result(chain)
            return
        duration = round(random.uniform(1, 20), 2)   # 喝奈奈时长：1~20min
        V = round(random.uniform(0.01, 100), 2)
        if random.random() < inst.state.crit_prob:
            V = round(V * 2, 2)
        # count=False：自取不计入喂养次数/被喝史，但泌乳量与初乳仍记录
        rec, is_first = inst.store.record_hn_stats(group_id, send_id, V, drinker=send_id, count=False)
        # 每日统计写入（自取；聚合时该行不计次数，但计入泌乳量与当日首喝）
        inst.store.daily.log("hn", group_id, send_id, send_id, V)
        if inst.state.is_log:
            try:
                inst.store.append_log(group_id, send_id, send_id, duration, V)
            except Exception as e:
                logger.warning(f"记录日志失败: {e}")
        if is_first:
            head = f"{user_name}的{V:.2f}ml初乳被ta自己喝掉了"
        else:
            head = f"{user_name}花费{duration}min，自取其乳{V:.2f}ml"
        chain = [Comp.Plain(head)]
        # 自交头像按 show_self_avatar 配置显示
        if inst.state.show_self_avatar:
            chain.append(Comp.Image.fromURL(get_avatar(send_id)))
        yield event.chain_result(chain)
        return

    # 禁C名单：主动与被动统一受控（喝奈不在豁免范围）
    if send_id in inst.state.white_list or target_user_id in inst.state.white_list:
        target_nick = await inst._get_nickname(event, target_user_id)
        yield event.plain_result(f"{target_nick}，拒绝让你喝ta的奈奈")
        return

    duration = round(random.uniform(1, 20), 2)   # 喝奈奈时长：1~20min
    V = round(random.uniform(0.01, 100), 2)
    if random.random() < inst.state.crit_prob:
        V = round(V * 2, 2)

    # 记录泌乳数据（hn.json），返回是否首次
    rec, is_first = inst.store.record_hn_stats(group_id, target_user_id, V, drinker=send_id)
    # 每日统计写入（互喝）
    inst.store.daily.log("hn", group_id, target_user_id, send_id, V)
    target_nick = await inst._get_nickname(event, target_user_id)

    # 是否保留完整日志
    if inst.state.is_log:
        try:
            inst.store.append_log(group_id, send_id, target_user_id, duration, V)
        except Exception as e:
            logger.warning(f"记录日志失败: {e}")

    if is_first:
        head = (f"{user_name} 花费{duration}min从 {target_nick} 的身上喝到了最有营养的{V:.2f}ml初乳，"
                f"这是 {target_nick} 第一次喂养群友")
    else:
        head = (f"{user_name} 花费{duration}min从 {target_nick} 的身上喝到了{V:.2f}ml的奈奈，"
                f"这是 {target_nick} 第{int(rec.get(hn_num, 0))}次喂养群友")

    chain = [
        Comp.Plain(head),
    ]
    if inst.state.show_avatar:
        chain.append(Comp.Image.fromURL(get_avatar(target_user_id)))
    yield event.chain_result(chain)

