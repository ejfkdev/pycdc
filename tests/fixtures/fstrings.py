name = "world"
n = 42
s1 = f"hello {name}"
s2 = f"{n!r} and {n:>10}"
s3 = f"{n + 1}"
s4 = f"nested {f'{name}'}" if False else f"plain {name}"
pct = "%s=%d" % (name, n)
frm = "{}-{}".format(name, n)
