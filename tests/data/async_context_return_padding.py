async def constant_one(owner):
    async with owner:
        async with owner.query('row0') as query:
            row0 = await query.read()
        return 4


async def padded_mapping(owner):
    async with owner:
        async with owner.query('row0') as query:
            row0 = await query.read()
        return {'value': row0}
