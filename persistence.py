# -*- coding: utf-8 -*-
"""persistence.py — 原子读写、版本化备份、损坏不静默

三条硬规则：
1. 写：临时文件 + fsync + os.replace，崩溃不会留半个 JSON。
2. 备份：覆盖前把旧文件存成 .bak.N（滚动保留 N 份），而不是只留一份 .bak
   被下一次坏写覆盖掉。
3. 读：文件存在但解析失败时**不静默当空库**。抛 StoreCorrupt，
   由调用方决定是中止还是显式降级——避免"读坏了→当空库→save 覆盖真数据"。
"""

import json
import os
import shutil
import tempfile

BACKUP_KEEP = 5


class StoreCorrupt(Exception):
    """store 存在但无法解析。默认抛出，绝不静默返回空库。"""

    def __init__(self, path, reason):
        self.path = path
        self.reason = reason
        super().__init__("store 损坏：%s（%s）" % (path, reason))


def load_json(path, default=None, strict=True):
    """strict=True（默认）：损坏抛 StoreCorrupt；strict=False：显式降级返回 default。"""
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except ValueError as e:
        if strict:
            raise StoreCorrupt(path, str(e))
        return default
    except OSError as e:
        if strict:
            raise StoreCorrupt(path, str(e))
        return default


def _rotate_backups(path):
    """path.bak.1 最新，path.bak.BACKUP_KEEP 最旧。"""
    oldest = "%s.bak.%d" % (path, BACKUP_KEEP)
    if os.path.exists(oldest):
        try:
            os.remove(oldest)
        except OSError:
            pass
    for i in range(BACKUP_KEEP - 1, 0, -1):
        src = "%s.bak.%d" % (path, i)
        if os.path.exists(src):
            try:
                os.replace(src, "%s.bak.%d" % (path, i + 1))
            except OSError:
                pass
    try:
        shutil.copy2(path, path + ".bak.1")
        # 兼容旧脚本：.bak 仍指向最新一份，但不再是唯一一份
        shutil.copy2(path, path + ".bak")
    except OSError:
        pass


def save_json(path, payload, backup=True):
    if not path:
        return
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    if backup and os.path.exists(path):
        _rotate_backups(path)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def append_jsonl(path, obj):
    """append-only 原始证据库。写完 flush+fsync，保证 raw 锚不丢。"""
    if not path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def recover_latest_backup(path):
    """从最新的可解析备份恢复。返回是否成功。"""
    for name in [path + ".bak"] + ["%s.bak.%d" % (path, i) for i in range(1, BACKUP_KEEP + 1)]:
        if not os.path.exists(name):
            continue
        try:
            with open(name, encoding="utf-8") as f:
                json.load(f)
        except (OSError, ValueError):
            continue
        shutil.copy2(name, path)
        return True
    return False
