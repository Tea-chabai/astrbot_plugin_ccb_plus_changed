# -- coding: utf-8 --
"""
数据层：JSON 文件路径、读写、统计更新、迁移。
所有插件数据统一存放在 data/plugin_data/astrbot_plugin_ccb_plus_changed/
"""
import json
import os
import sqlite3
import time
from pathlib import Path
from astrbot.api import logger

# ---- 字段键名（数据结构定义） ----
a1 = "id"          # qq号
a2 = "num"         # 被C次数
a3 = "vol"         # 被注入量
a4 = "ccb_by"      # 被谁C了
a5 = "max"         # 单次最大注入量
a8 = "B_vol"       # 13水累计（扣B）
a9 = "B_max"       # 13水单次最高（扣B）
a10 = "B_num"      # 扣B次数
d_num = "d_num"    # 打胶次数（生命因子）
d_vol = "d_vol"    # 打胶累计（生命因子）
d_max = "d_max"    # 打胶单次最高（生命因子）
bh_num = "bh_num"  # 被扣次数（百合）
bh_vol = "bh_vol"  # 被扣喷出B水累计（百合）
hn_num = "hn_num"    # 喂养次数（喝奈/泌乳）
hn_vol = "hn_vol"    # 泌乳累计（喝奈）
hn_max = "hn_max"    # 单次最大泌乳量
hn_by = "hn_by"      # 被谁喝了：{喝者ID: 次数}
hn_first = "hn_first"  # 初乳喝者ID（第一个喝的人）


def get_data_dir() -> str:
    """插件数据目录：data/plugin_data/astrbot_plugin_ccb_plus_changed（获取失败回退 data/）"""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path
        path = Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_ccb_plus_changed"
    except Exception:
        path = Path("data")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return str(path)


def data_file(name: str) -> str:
    """数据文件完整路径"""
    return os.path.join(get_data_dir(), name)


def read_json(path: str):
    """读取 JSON 文件，失败返回空 dict"""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.error(f"读取数据错误: {e}")
    return {}


def write_json(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"写入数据错误: {e}")


class DailyStore:
    """
    每日统计（sqlite）。每次行为写一条记录；每次操作前自动清理非今日数据，
    等效于每日零点重置。长期累计数据仍由 JSON 文件（DataStore）保存。
    行为类型 action: 'ccb' 互C | 'dj_b' 扣B | 'dj_d' 打胶 | 'bh' 百合 | 'hn' 喝奈
    """

    def __init__(self):
        self.db_path = data_file("daily.db")
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        try:
            with self._conn() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    vol REAL DEFAULT 0)""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_gad ON daily(group_id, action, date)")
        except Exception as e:
            logger.error(f"初始化每日数据库失败: {e}")

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _purge(self, conn):
        """懒清理：删除非今日记录，实现每日重置"""
        try:
            conn.execute("DELETE FROM daily WHERE date != ?", (self._today(),))
        except Exception as e:
            logger.warning(f"清理每日数据失败: {e}")

    def log(self, action: str, group_id: str, user_id: str, actor: str, vol: float):
        """写入一条当日行为记录（user_id 为被统计者）"""
        try:
            with self._conn() as conn:
                self._purge(conn)
                conn.execute(
                    "INSERT INTO daily(date, group_id, action, user_id, actor, vol) VALUES(?,?,?,?,?,?)",
                    (self._today(), group_id, action, user_id, actor, round(float(vol), 2)),
                )
        except Exception as e:
            logger.error(f"写入每日数据失败: {e}")

    def rows(self, action: str, group_id: str) -> list:
        """当日某行为的原始记录 [(user_id, actor, vol)]（按写入顺序）"""
        try:
            with self._conn() as conn:
                self._purge(conn)
                return conn.execute(
                    "SELECT user_id, actor, vol FROM daily WHERE date = ? AND group_id = ? AND action = ? ORDER BY id",
                    (self._today(), group_id, action),
                ).fetchall()
        except Exception as e:
            logger.error(f"读取每日数据失败: {e}")
            return []

    def actor_count(self, action: str, group_id: str, actor_id: str) -> int:
        """当日某人作为执行者（发起方）的次数"""
        try:
            with self._conn() as conn:
                self._purge(conn)
                row = conn.execute(
                    "SELECT COUNT(*) FROM daily WHERE date = ? AND group_id = ? AND action = ? AND actor = ?",
                    (self._today(), group_id, action, actor_id),
                ).fetchone()
                return int(row[0]) if row else 0
        except Exception as e:
            logger.error(f"读取每日数据失败: {e}")
            return 0

    def remove_user(self, action: str, group_id: str, user_id: str, also_actor: bool = False) -> int:
        """删除当日某行为中该用户作为被统计者的记录，返回删除条数。
        also_actor=True 时连同其作为执行者（发起方）的记录一并删除（ccb 双向清理）"""
        try:
            with self._conn() as conn:
                self._purge(conn)
                if also_actor:
                    cur = conn.execute(
                        "DELETE FROM daily WHERE date = ? AND group_id = ? AND action = ? "
                        "AND (user_id = ? OR actor = ?)",
                        (self._today(), group_id, action, user_id, user_id),
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM daily WHERE date = ? AND group_id = ? AND action = ? AND user_id = ?",
                        (self._today(), group_id, action, user_id),
                    )
                return int(cur.rowcount or 0)
        except Exception as e:
            logger.error(f"删除每日数据失败: {e}")
            return 0


class DataStore:
    """全部 JSON 数据的读写与统计更新"""

    def __init__(self, dj_mode: str = "B"):
        self.dj_mode = dj_mode
        self.daily = DailyStore()   # 每日统计（sqlite）

    # ---- 基础读写 ----
    def read_ccb(self) -> dict:
        return read_json(data_file("ccb.json"))

    def write_ccb(self, data):
        write_json(data_file("ccb.json"), data)

    def get_group_data(self, name: str, group_id: str) -> dict:
        """读取独立数据文件中某群的数据（{用户ID: 统计dict}）"""
        return read_json(data_file(name)).get(group_id, {})

    def get_self_stats(self, group_id: str) -> dict:
        """按配置模式读取当前群的自交统计数据（打胶= dj.json，扣B= dj_b.json）"""
        name = "dj.json" if self.dj_mode == "d" else "dj_b.json"
        return self.get_group_data(name, group_id)

    # ---- 日志 ----
    def append_log(self, group_id: str, executor_id: str, target_id: str, time: float, vol: float):
        """完整日志（可选），格式：[{group, executor, target, time, vol}]"""
        try:
            log_file = data_file("ccb_log.json")
            logs = []
            # 注意：日志是 list 而非 dict，不能使用 read_json（其限定 dict 内容）
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8") as lf:
                    try:
                        data = json.load(lf)
                        if isinstance(data, list):
                            logs = data
                    except Exception:
                        logs = []
            logs.append({
                "group": group_id,
                "executor": executor_id,
                "target": target_id,
                "time": time,
                "vol": str(round(float(vol), 2))
            })
            write_json(log_file, logs)
        except Exception as e:
            logger.error(f"append_log 失败: {e}")

    # ---- 统计更新 ----
    def record_dj_stats(self, group_id: str, user_id: str, vol: float, mode: str = None) -> tuple:
        """
        记录自交数据（打胶= dj.json，扣B= dj_b.json）。
        返回 (记录dict, 键元组(num键, vol键, max键)) 供消息构建使用。
        """
        mode = mode or self.dj_mode
        if mode == "d":
            name, num_k, vol_k, max_k = "dj.json", d_num, d_vol, d_max
        else:
            name, num_k, vol_k, max_k = "dj_b.json", a10, a8, a9
        data = read_json(data_file(name))
        rec = data.setdefault(group_id, {}).setdefault(user_id, {})
        rec[num_k] = int(rec.get(num_k, 0)) + 1
        rec[vol_k] = round(float(rec.get(vol_k, 0)) + vol, 2)
        rec[max_k] = max(float(rec.get(max_k, 0) or 0), vol)
        write_json(data_file(name), data)
        return rec, (num_k, vol_k, max_k)

    def record_bh_stats(self, group_id: str, user_id: str, vol: float) -> dict:
        """记录百合（互扣）数据到 bh.json：被扣次数+1、喷水累计。返回记录dict"""
        data = read_json(data_file("bh.json"))
        rec = data.setdefault(group_id, {}).setdefault(user_id, {})
        rec[bh_num] = int(rec.get(bh_num, 0)) + 1
        rec[bh_vol] = round(float(rec.get(bh_vol, 0)) + vol, 2)
        write_json(data_file("bh.json"), data)
        return rec

    def merge_b_max(self, group_id: str, user_id: str, vol: float):
        """百合喷水最大值并入扣B的B_max（dj_b.json），不影响扣B次数与累计"""
        data = read_json(data_file("dj_b.json"))
        rec = data.setdefault(group_id, {}).setdefault(user_id, {})
        rec[a9] = max(float(rec.get(a9, 0) or 0), vol)
        write_json(data_file("dj_b.json"), data)

    def record_hn_stats(self, group_id: str, user_id: str, vol: float, drinker: str, count: bool = True) -> tuple:
        """
        记录喝奈（泌乳）数据到 hn.json：泌乳累计、单次最大、初乳喝者。
        count=True 时另计入喂养次数与被谁喝（drinker 为本次喝奶的人，目标自己喝时=user_id）。
        count=False 表示自取（自己喝自己）：只累计泌乳量与初乳，不计入喂养次数/被喝史。
        返回 (记录dict, 是否首次喝到初乳)
        """
        data = read_json(data_file("hn.json"))
        rec = data.setdefault(group_id, {}).setdefault(user_id, {})
        is_first = not rec.get(hn_first)
        if count:
            rec[hn_num] = int(rec.get(hn_num, 0) or 0) + 1
            by = rec.setdefault(hn_by, {})
            by[drinker] = int(by.get(drinker, 0)) + 1
            rec[hn_by] = by
        rec[hn_vol] = round(float(rec.get(hn_vol, 0) or 0) + vol, 2)
        rec[hn_max] = max(float(rec.get(hn_max, 0) or 0), vol)
        if is_first:
            rec[hn_first] = drinker
        write_json(data_file("hn.json"), data)
        return rec, is_first

    # ---- 数据清除（管理员 clear 命令） ----
    def remove_ccb_user(self, group_id: str, user_id: str) -> tuple:
        """
        双向清除某人的互C数据（ccb.json）：
        删除自身记录；并把他从他人的 ccb_by（C过谁）中摘除、重算次数与标记。
        返回 (删除自身记录数, 从他人记录中摘除的总次数)
        """
        all_data = self.read_ccb()
        group_data = all_data.get(group_id, [])
        if not isinstance(group_data, list):
            group_data = []

        before_len = len(group_data)
        kept = [r for r in group_data if isinstance(r, dict) and r.get(a1) != user_id]
        removed_self = before_len - len(kept)

        removed_from_others = 0
        for record in kept:
            if not isinstance(record, dict):
                continue
            ccb_by = record.get(a4, {}) or {}
            if user_id in ccb_by:
                try:
                    removed_from_others += int(ccb_by[user_id].get("count", 0))
                except Exception:
                    pass
                del ccb_by[user_id]
                record[a4] = ccb_by
                record[a2] = sum(
                    int(info.get("count", 0)) for info in ccb_by.values() if isinstance(info, dict)
                )
                self.recalc_max(record)

        all_data[group_id] = kept
        self.write_ccb(all_data)
        return removed_self, removed_from_others

    def remove_self_user(self, group_id: str, user_id: str, mode: str = "B") -> bool:
        """清除某人的自交数据：mode="B" 清 dj_b.json（扣B/13水），否则清 dj.json（打胶/生命因子）。
        是否真的删除了数据"""
        name = "dj_b.json" if mode == "B" else "dj.json"
        data = read_json(data_file(name))
        group = data.get(group_id, {})
        if isinstance(group, dict) and user_id in group:
            del group[user_id]
            data[group_id] = group
            write_json(data_file(name), data)
            return True
        return False

    def remove_bh_user(self, group_id: str, user_id: str) -> bool:
        """清除某人的百合被扣数据（bh.json）"""
        data = read_json(data_file("bh.json"))
        group = data.get(group_id, {})
        if isinstance(group, dict) and user_id in group:
            del group[user_id]
            data[group_id] = group
            write_json(data_file("bh.json"), data)
            return True
        return False

    def remove_hn_user(self, group_id: str, user_id: str) -> tuple:
        """
        双向清除某人的喝奈数据（hn.json）：
        删除自身记录；并把他从他人的“被谁喝(hn_by)/初乳喝者(hn_first)”中摘除。
        返回 (删除自身记录数, 从他人记录中摘除的痕迹数)
        """
        data = read_json(data_file("hn.json"))
        group = data.get(group_id, {})
        traces = 0
        removed_self = 0
        if isinstance(group, dict):
            if user_id in group:
                del group[user_id]
                removed_self = 1
            for rec in group.values():
                if not isinstance(rec, dict):
                    continue
                by = rec.get(hn_by, {}) or {}
                if user_id in by:
                    del by[user_id]
                    rec[hn_by] = by
                    traces += 1
                if rec.get(hn_first) == user_id:
                    rec.pop(hn_first, None)
                    traces += 1
        if removed_self or traces:
            data[group_id] = group
            write_json(data_file("hn.json"), data)
        return removed_self, traces

    # ---- 数据维护 ----
    def recalc_max(self, record: dict):
        """ccbclear 后重新计算记录中的 max 与产生者标记"""
        if not isinstance(record, dict):
            return
        ccb_by = record.get(a4, {}) or {}
        total_num = int(record.get(a2, 0) or 0)
        total_vol = float(record.get(a3, 0) or 0)
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

    def migrate_legacy_b_data(self):
        """把旧版 ccb.json 记录中的B水字段（B_vol/B_max/B_num）迁移到独立的 dj_b.json"""
        try:
            b_data = read_json(data_file("dj_b.json"))
            if not os.path.exists(data_file("ccb.json")):
                return
            all_data = self.read_ccb()
            migrated = False
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
                self.write_ccb(all_data)
                write_json(data_file("dj_b.json"), b_data)
                logger.info("已迁移旧版B水数据到 dj_b.json")
        except Exception as e:
            logger.warning(f"迁移旧版B水数据失败: {e}")
