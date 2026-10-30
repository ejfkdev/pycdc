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
