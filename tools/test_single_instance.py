"""验证单实例锁：第一个进程拿到锁，第二个被拒，持有者退出后能重新拿到。

全部用子进程跑 —— 同一个进程内重复调用会一直拿不到（自己持着句柄），
那属于正常语义，不适合用来做断言。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failed = False

# 用独立的锁名：真实程序可能正在运行并占着正式锁名，
# 否则测试会误报「空闲时拿不到锁」。
LOCK_NAME = f"Local\\2.4GBatteryCheck.Test.{os.getpid()}"

HOLDER_CODE = (
    "import sys; sys.path.insert(0, r'%s');"
    "from app.core.single_instance import acquire;"
    "print(acquire(r'%s'), flush=True);"
    "import time; time.sleep(%%d)" % (ROOT, LOCK_NAME)
)


def check(label, cond, extra=""):
    global failed
    print(f"[{'OK' if cond else 'FAIL'}] {label} {extra}")
    if not cond:
        failed = True


def probe(hold_seconds=0):
    """起一个子进程问一次「能不能拿到锁」。"""
    out = subprocess.run([sys.executable, "-c", HOLDER_CODE % hold_seconds],
                         capture_output=True, text=True, timeout=30)
    return (out.stdout or "").strip()


# 1) 空闲时应能拿到
check("空闲时可取得锁", probe(0) == "True")

# 2) 有实例占着时应被拒
holder = subprocess.Popen([sys.executable, "-c", HOLDER_CODE % 8],
                          stdout=subprocess.PIPE, text=True)
first = holder.stdout.readline().strip()
check("占锁进程取得锁", first == "True", f"输出={first}")
check("第二个实例被拒", probe(0) == "False")

# 3) 持有者退出后应能重新拿到
holder.terminate()
holder.wait(timeout=10)
import time
time.sleep(0.5)
check("持有者退出后可再次取得", probe(0) == "True")

print("\n全部通过" if not failed else "\n存在失败项")
sys.exit(1 if failed else 0)
