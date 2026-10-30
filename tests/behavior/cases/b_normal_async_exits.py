# MIN_VERSION: 3.14
import asyncio

async def normal_1(owner):
    async with owner:
        async with owner.query("row0") as query:
            row0 = await query.read()
    value = owner.build(row0, row0)
    return {"value": value, "active": owner.active}


async def normal_2(owner):
    async with owner:
        async with owner.query("row0") as query:
            row0 = await query.read()
        async with owner.query("row1") as query:
            row1 = await query.read()
    value = owner.build(row0, row1)
    return {"value": value, "active": owner.active}


async def normal_4(owner):
    async with owner:
        async with owner.query("row0") as query:
            row0 = await query.read()
        async with owner.query("row1") as query:
            row1 = await query.read()
        async with owner.query("row2") as query:
            row2 = await query.read()
        async with owner.query("row3") as query:
            row3 = await query.read()
    value = owner.build(row0, row3)
    return {"value": value, "active": owner.active}


async def constant_one(owner):
    async with owner:
        async with owner.query("row0") as query:
            row0 = await query.read()
        return 4


async def constant_two(owner):
    async with owner:
        async with owner.query("row0") as query:
            row0 = await query.read()
        async with owner.query("row1") as query:
            row1 = await query.read()
        return 4


async def carried_one(owner):
    async with owner:
        async with owner.query("row0") as query:
            row0 = await query.read()
        return row0


async def computed_two(owner):
    async with owner:
        async with owner.query("row0") as query:
            row0 = await query.read()
        async with owner.query("row1") as query:
            row1 = await query.read()
        return owner.build(row0, row0)


async def mapping_two(owner):
    async with owner:
        async with owner.query("row0") as query:
            row0 = await query.read()
        async with owner.query("row1") as query:
            row1 = await query.read()
        return {"value": row0}


async def user_await(owner):
    async with owner:
        await owner.user(None, None, None)
        return owner.build(1, 2)


async def branch_return(owner):
    async with owner:
        if owner.ready:
            return 4
        await owner.write(1, 2)
    return 2


class Owner:
    active = False

    def __init__(self):
        self.events = []
        self.ready = ready

    async def __aenter__(self):
        await asyncio.sleep(0)
        self.events.append('outer-enter')
        if fault == 'outer-enter':
            raise ValueError('owned outer enter')
        self.active = True
        return self

    async def __aexit__(self, kind, value, trace):
        await asyncio.sleep(0)
        self.events.append(('outer-exit', None if kind is None else kind.__name__))
        self.active = False
        if fault == 'outer-exit':
            raise ValueError('owned outer exit')
        return suppression == 'outer'

    def query(self, name):
        self.events.append(('query', name))
        return Query(self, name)

    def build(self, first, last):
        self.events.append(('build', self.active, first, last))
        if fault == 'build':
            raise ValueError('owned build')
        if fault == 'build-cancel':
            raise asyncio.CancelledError('owned build cancellation')
        return first + last

    async def user(self, *values):
        await asyncio.sleep(0)
        self.events.append(('user', self.active, values))
        if fault == 'read':
            raise ValueError('owned user')
        if fault == 'read-cancel':
            raise asyncio.CancelledError('owned user cancellation')

    async def write(self, first, last):
        await asyncio.sleep(0)
        await self.user(first, last)

class Query:

    def __init__(self, owner, name):
        self.owner, self.name = (owner, name)
        self.selected = name == f'row{count // 2}'

    async def __aenter__(self):
        await asyncio.sleep(0)
        self.owner.events.append(('query-enter', self.name, self.owner.active))
        if self.selected and fault == 'query-enter':
            raise ValueError('owned query enter')
        return self

    async def read(self):
        await asyncio.sleep(0)
        self.owner.events.append(('read', self.name, self.owner.active))
        if self.selected and fault == 'read':
            raise ValueError('owned read')
        if self.selected and fault == 'read-cancel':
            raise asyncio.CancelledError('owned read cancellation')
        return int(self.name[3:])

    async def __aexit__(self, kind, value, trace):
        await asyncio.sleep(0)
        self.owner.events.append(('query-exit', self.name, None if kind is None else kind.__name__, self.owner.active))
        if self.selected and fault == 'query-exit':
            raise ValueError('owned query exit')
        return suppression == 'query'

functions = [
    (normal_1, 1),
    (normal_2, 2),
    (normal_4, 4),
    (constant_one, 1),
    (constant_two, 2),
    (carried_one, 1),
    (computed_two, 2),
    (mapping_two, 2),
    (user_await, 1),
    (branch_return, 1),
]
for function, count in functions:
    for ready in (False, True):
        for fault in ("", "outer-enter", "outer-exit", "query-enter", "query-exit", "read", "read-cancel", "build", "build-cancel"):
            for suppression in ("", "outer", "query"):
                owner = Owner()
                print(function.__name__, ready, fault, suppression)
                try:
                    print("return", asyncio.run(function(owner)))
                except BaseException as error:
                    print("error", type(error).__name__, str(error))
                print(owner.events, owner.active)
