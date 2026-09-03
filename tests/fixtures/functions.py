def simple(a, b=2, *args, **kwargs):
    return a + b

def kwonly(a, *, b=3):
    return a * b

def annotated(a: int, b: str = "x") -> bool:
    return True

lam = lambda x, y=1: x + y
f = lam(3)

def outer(n):
    def inner(m):
        return n + m
    return inner(1)

def gen():
    yield 1
    yield 2

def uses_global():
    global f
    f = 1

@staticmethod
def not_really():
    pass

class Decorated:
    @property
    def prop(self):
        return 1
