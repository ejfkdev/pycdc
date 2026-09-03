nums = [1, 2, 3, 4]
sq = [x * x for x in nums]
ev = [x for x in nums if x % 2 == 0]
pairs = [(x, y) for x in nums for y in nums if x != y]
s = {x * 2 for x in nums}
d = {x: x * x for x in nums}
g = sum(x for x in nums)
nested = [[y for y in row] for row in [[1, 2], [3, 4]]]
