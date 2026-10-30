# MIN_VERSION: 3.12
# Walrus syntax starts in 3.8; this tests the modern generator route.

def select(rows):
    return tuple(isinstance(row, dict) and (change := row.get("change")) is not None and change >= 0 for row in rows)


def last_binding(rows):
    change = "initial"
    results = tuple((change := row.get("change")) for row in rows)
    return results, change


for rows in ([], [None], [{}], [{"change": None}], [{"change": -1}],
             [{"change": 0}, {"change": 7}, {"change": -3}, None],
             [{"change": "invalid"}]):
    try:
        print(select(rows))
    except TypeError as error:
        print(type(error).__name__, str(error))

for rows in ([], [{}], [{"change": 1}, {"change": 7}], [{"change": None}]):
    print(last_binding(rows))


events = []


class Row(dict):
    def get(self, key):
        events.append(key)
        return dict.get(self, key)


print(select([None, Row(change=None), Row(change=0), Row(change=7)]))
print(events)
