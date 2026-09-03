import os, sys


class Greeter:
    """Greets people."""

    def __init__(self, name):
        self.name = name

    def greet(self, times=1):
        for i in range(times):
            print("Hello, %s! (%d)" % (self.name, i))
        return self.name


def fib(n):
    a, b = 0, 1
    while a < n:
        a, b = b, a + b
    return a


data = {"x": [1, 2, 3], "y": {4, 5}}
if len(data["x"]) > 2:
    g = Greeter("world")
    g.greet(2)
else:
    print(fib(10))
