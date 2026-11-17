"""Test double for the Experiment record."""
class _Stream:
    def __init__(self): self.rows=[]
    def add(self, **kw): self.rows.append(kw)
class Experiment:
    def __init__(self):
        self.attribs={}; self.logs={}; self.notes=[]
    @classmethod
    def Construct(cls, *a, **k): return cls()
    def new_measurementstream(self, name, measurements=None):
        setattr(self, name, _Stream()); return getattr(self, name)
    def note(self, msg): self.notes.append(msg)
    def save(self): return True
