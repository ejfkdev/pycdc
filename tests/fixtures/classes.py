class Base:
    count = 0

    def __init__(self, name):
        self.name = name
        Base.count += 1

    def method(self):
        return self.name

class Child(Base):
    """Child class."""

    def __init__(self):
        super().__init__("child")
        self.data = [1, 2]

    def method(self):
        return self.data

c = Child()
print(c.method(), Base.count)
