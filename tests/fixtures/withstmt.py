class Ctx:
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False

with Ctx() as c:
    print(c)

with open("f.txt") as f1, open("g.txt") as f2:
    pass

with Ctx():
    print("no as")
