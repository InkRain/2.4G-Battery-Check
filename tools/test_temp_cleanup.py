"""验证 _MEI* 残留清理策略（全部在沙箱里跑，不碰真实目录）。"""
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import temp_cleanup as tc

failed = False


def check(label, cond, extra=""):
    global failed
    print(f"[{'OK' if cond else 'FAIL'}] {label} {extra}")
    if not cond:
        failed = True


sandbox = tempfile.mkdtemp(prefix="mei_case_")
stamp = str(os.getpid())


def fake_mei(tag, with_marker=True, owner_pid=None, age_sec=0):
    d = os.path.join(sandbox, f"_MEI{tag}{stamp}")
    os.makedirs(os.path.join(d, "app", "resources"), exist_ok=True)
    if with_marker:
        open(os.path.join(d, "app", "resources", "app.ico"), "wb").write(b"\0")
    if owner_pid is not None:
        with open(os.path.join(d, "_owner.json"), "w", encoding="utf-8") as f:
            json.dump({"pid": owner_pid, "ts": 1}, f)
    if age_sec:
        old = time.time() - age_sec
        os.utime(d, (old, old))
    return d


dead_pid = 999999
live_pid = os.getpid()

# 1) 源码运行不动任何东西
sys.frozen = False
d0 = fake_mei("src", owner_pid=dead_pid)
check("源码运行时不删目录", tc.cleanup_stale_temp_dirs(sandbox) == 0 and os.path.isdir(d0))
check("源码运行时不写主人标记",
      not os.path.exists(os.path.join(d0, "_owner.json")) or
      json.load(open(os.path.join(d0, "_owner.json")))["pid"] == dead_pid)

sys.frozen = True
sys._MEIPASS = ""

# 2) 有标记 + 进程已死 → 清理
d_dead = fake_mei("dead", owner_pid=dead_pid)
n = tc.cleanup_stale_temp_dirs(sandbox)
check("标记进程已退出 → 目录被删", not os.path.exists(d_dead) and n >= 1, f"removed={n}")

# 3) 有标记 + 进程存活 → 绝不删
d_live = fake_mei("live", owner_pid=live_pid)
n = tc.cleanup_stale_temp_dirs(sandbox)
check("标记进程仍存活 → 目录保留", os.path.isdir(d_live), f"removed={n}")

# 4) 无标记但很新 → 保留（可能是老版本正在跑）
d_new = fake_mei("new", age_sec=60)
n = tc.cleanup_stale_temp_dirs(sandbox)
check("无标记的近期目录保留", os.path.isdir(d_new))

# 5) 无标记且够老 → 兜底清理
d_old = fake_mei("old", age_sec=4 * 86400)
n = tc.cleanup_stale_temp_dirs(sandbox)
check("无标记的旧目录被兜底清理", not os.path.exists(d_old))

# 6) 不是本程序的目录（无特征文件）绝不删
d_foreign = fake_mei("foreign", with_marker=False, owner_pid=dead_pid)
tc.cleanup_stale_temp_dirs(sandbox)
check("无本程序特征的目录不删", os.path.isdir(d_foreign))

# 7) 当前进程解压目录被跳过，并写入主人标记
d_cur = fake_mei("cur")
sys._MEIPASS = d_cur
tc.cleanup_stale_temp_dirs(sandbox)
check("当前目录不被删", os.path.isdir(d_cur))
owner = tc._read_owner(d_cur)
check("当前目录写入主人标记", owner is not None and owner["pid"] == os.getpid(),
      str(owner))

# 8) 模拟重启：新进程号判断旧标记已死 → 清理
json.dump({"pid": 4242, "ts": 1}, open(os.path.join(d_cur, "_owner.json"), "w"))
sys._MEIPASS = ""
n = tc.cleanup_stale_temp_dirs(sandbox)
check("重启后清理上一实例目录", not os.path.exists(d_cur), f"removed={n}")

shutil.rmtree(sandbox, ignore_errors=True)
print("\n全部通过" if not failed else "\n存在失败项")
sys.exit(1 if failed else 0)
