# -*- coding: utf-8 -*-
from __future__ import print_function
# 类：继承、多继承、属性、方法种类、super、魔术方法
class Base(object):
    kind = 'base'

    def __init__(self, name):
        self.name = name
        self._init_called = 'Base'

    def speak(self):
        return '%s says hi' % self.name

    @classmethod
    def make(cls, name):
        return cls(name)

    @staticmethod
    def helper(x):
        return x * 2

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.name)


class Mixin(object):
    def speak(self):
        return 'mixin ' + Base.speak(self)


class Child(Mixin, Base):
    kind = 'child'

    def __init__(self, name, age=0):
        Base.__init__(self, name)
        self.age = age

    def speak(self):
        return Mixin.speak(self) + '!'

    @property
    def info(self):
        return (self.name, self.age, self.kind)


c = Child('bob', 3)
print(c.speak())
print(c.info)
print(c.kind, Base.kind)
print(Base.helper(21))
b = Base.make('sue')
print(b, b.speak(), b._init_called)
print(isinstance(c, Base), isinstance(c, Mixin), isinstance(b, Child))


class Counter(object):
    total = 0

    def __init__(self, start=0):
        self.value = start
        Counter.total += 1

    def __len__(self):
        return self.value

    def __getitem__(self, i):
        return self.value + i

    def __call__(self, delta):
        self.value += delta
        return self.value

    def __eq__(self, other):
        return isinstance(other, Counter) and self.value == other.value


c1 = Counter(5)
c2 = Counter(5)
print(len(c1), c1[2], c1(3), c1 == c2, c1 == Counter(1), Counter.total)


class WithPrivate(object):
    def __init__(self):
        self.__secret = 42

    def get(self):
        return self.__secret


wp = WithPrivate()
print(wp.get(), wp._WithPrivate__secret)


class Desc(object):
    def __get__(self, obj, objtype=None):
        return 'desc-get'

    def __set__(self, obj, v):
        obj.__dict__['stored'] = v


class HasDesc(object):
    d = Desc()


h = HasDesc()
print(h.d)
h.d = 7
print(h.stored)
