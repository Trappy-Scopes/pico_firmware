"""Test double for hive.assembly.ScopeAssembly."""
class _Scope:
    def __init__(self): self.pumpset=None; self.kp=None
class ScopeAssembly:
    current = _Scope()
