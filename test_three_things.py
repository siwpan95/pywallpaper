# -*- coding: utf-8 -*-
"""
test_three_things.py —— media_engine 阶段 A 冒烟（Context / WorldLog / dump CLI）

运行：python test_three_things.py（脚本式，与 test_engine.py 同风格）
"""
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_context():
    from core.context import Context
    ctx = Context()
    order = []
    ctx.provide("svc", 1, dispose=lambda: order.append("undone"))
    ctx.effect(lambda: order.append("effect"))
    assert ctx.get("svc") == 1
    ctx.dispose()
    assert order == ["effect", "undone"]
    print("[OK] Context 注册即回滚")


def test_worldlog():
    from core.world_log import WorldLog
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "log.json")
        log = WorldLog()
        log.append("run_start", {"run_id": "r1", "mode": "normal"})
        log.append("run_end", {"run_id": "r1", "ok": True})
        log.save_to(p)
        loaded = WorldLog.load_from(p)
        assert loaded.seq == 2
        assert loaded.entries()[0]["type"] == "run_start"
    print("[OK] WorldLog 持久化往返")


def test_dump_profile():
    import subprocess
    root = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(root, "main.pyw"), "--dump-profile"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore",
                       cwd=root, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    assert "effects:" in r.stdout and "primitives:" in r.stdout
    print("[OK] --dump-profile 自省")


if __name__ == "__main__":
    test_context()
    test_worldlog()
    test_dump_profile()
    print("\n✅ 三件事冒烟全过")
