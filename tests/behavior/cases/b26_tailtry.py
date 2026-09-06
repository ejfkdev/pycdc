# -*- coding: utf-8 -*-
from __future__ import print_function
# 函数尾 try 的下沉 return None 副本族（chunk/cProfile/cgitb/aifc 形状）：
# 1) 尾位 try/except/else：隐式 return None 被 3.11+ 复制进成功路径与末
#    handler（POP_EXCEPT; RETURN），无跳转定界 else——必须还原 else 形且
#    两份副本都不渲染；
# 2) if 臂内 try/finally 收尾：每终结分支一份 RETURN_CONST 副本，不得
#    泄漏成伪 `return`；
# 3) try 体内显式 return + handler pass（旋转 while 前的尾位 try）：
#    窄化保护区把 RETURN 排在 body_end 之外，必须折回 try 体；
# 4) then 臂以「恒异常链（except: ...; raise）」收尾：终结 return 留在
#    分支级（折进 try 体会改变重编译形状，aifc 教训）。

class FakeFile:
    def __init__(self, ok):
        self.ok = ok

    def tell(self):
        if not self.ok:
            raise OSError('not seekable')
        return 42

    def read(self):
        return 'data'

class C:
    def __init__(self, f):
        self.f = f
        self.x = 0
        try:
            self.offset = f.tell()
        except (AttributeError, OSError):
            self.seekable = False
        else:
            self.seekable = True

    def close(self):
        if not self.x:
            try:
                self.f.read()
            finally:
                self.x = 1

    def skip(self):
        if self.x:
            try:
                self.x = self.x + 1
                return
            except OSError:
                pass
        while self.x < 3:
            self.x = self.x + 1
        return self.x

    def guard(self, v):
        if v:
            try:
                if v == 'raise-me':
                    raise KeyError('boom')
                self.x = self.x + 1
            except:
                print('cleanup')
                raise
        else:
            self.x = self.x + 100

c1 = C(FakeFile(True))
print(c1.seekable, c1.offset)
c2 = C(FakeFile(False))
print(c2.seekable)
c3 = C(FakeFile(True))
c3.close()
print(c3.x)
print(c3.skip())
c3.guard(True)
print(c3.x)
c3.guard(False)
print(c3.x)
try:
    c3.guard('raise-me')
except KeyError:
    print('guard-raised')
