"""Exercise _logger.py against a filesystem that fills up."""
import sys, types, importlib, importlib.util

sys.path.insert(0, "stub")

FULL = {"on": False}
FILES = {}

class FakeFile:
    def __init__(self, name): self.name = name
    def write(self, s):
        if FULL["on"]:
            raise OSError(28, "ENOSPC")
        FILES[self.name] = FILES.get(self.name, "") + s
    def flush(self):
        if FULL["on"]:
            raise OSError(28, "ENOSPC")
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False

def fake_open(name, mode="r"):
    if FULL["on"] and ("w" in mode or "a" in mode):
        raise OSError(28, "ENOSPC")
    FILES.setdefault(name, "")
    return FakeFile(name)

fake_os = types.ModuleType("os")
fake_os.listdir = lambda p=".": list(FILES)
fake_os.stat = lambda n: (0,0,0,0,0,0, len(FILES.get(n, "")))
sys.modules["os"] = fake_os
import builtins; builtins.open = fake_open

def load():
    for m in list(sys.modules):
        if m == "_logger": del sys.modules[m]
    spec = importlib.util.spec_from_file_location("_logger", "../pico_firmware/_logger.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.Logger

print("=== 1. normal operation")
L = load()
assert L.write("out", "hello") is True
assert "hello" in FILES["out.txt"], FILES["out.txt"]
print("   writes ok, fs_full =", L.fs_full)

print("=== 2. disk fills mid-run")
FULL["on"] = True
r = L.write("out", "during full")
assert r is False, "write should report failure"
assert L.fs_full is True
assert L.dropped == 1, L.dropped
print("   degraded, dropped =", L.dropped, "- no exception raised")

print("=== 3. import with the disk already full  <-- the bug that killed main.py")
FILES.clear()
try:
    L2 = load()
    print("   IMPORT SUCCEEDED (previously raised OSError 28)")
except OSError as e:
    raise SystemExit(f"   FAIL: import still raises {e}")
assert L2.fs_full is True
assert L2.write("out", "x") is False
print("   fs_full =", L2.fs_full, " write returns False, still no exception")

print("=== 4. recovery after clearing space")
FULL["on"] = False
assert L2.reopen() is True
assert L2.write("out", "after cleanup") is True
print("   reopen() works, writing again")

print("=== 5. per-file cap")
FILES.clear(); L3 = load()
L3.MAX_KB = 1
for i in range(200):
    L3.write("out", "x" * 40)
sz = len(FILES["out.txt"])
assert sz <= 1024 + 200, sz
assert L3.dropped > 0
print(f"   capped at {sz} bytes, dropped {L3.dropped}")

print("\nALL PASS")
