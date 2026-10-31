import os

flag = bool(os.environ.get("NEVER"))
mode = int(os.environ.get("MODE", "0"))


class Single:
    if flag:
        def method(self):
            return "then"


class Either:
    if flag:
        def method(self):
            return "then"
    else:
        def method(self):
            return "else"


class Chained:
    if mode == 1:
        def method(self):
            return "one"
    elif mode == 2:
        def method(self):
            return "two"
    else:
        def method(self):
            return "many"


print(Single.method(None), Either.method(None), Chained.method(None))
