import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:0224@127.0.0.1:5432/jobagent')
    print('연결 성공!')
    await conn.close()

asyncio.run(test())