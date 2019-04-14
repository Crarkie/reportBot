from common.models import *
import asyncio
import aiomysql

__all__ = ['search_active_projects', 'search_all_projects']


async def _execute(query, args):
    loop = asyncio.get_running_loop()
    connection = await aiomysql.connect(host='127.0.0.1', port=9306,
                                        loop=loop)

    cur = await connection.cursor()
    await cur.execute(query, args)

    ids = await cur.fetchall()
    await cur.close()
    connection.close()

    ids = [id[0] for id in ids]
    total = len(ids)

    projects = Project.query.where(Project.project_id.in_(ids))

    return total, projects


async def search_active_projects(query: str):
    return (await _execute("SELECT id FROM projects WHERE active=1 AND MATCH(%s)", (query,)))[1]


async def search_all_projects(query: str):
    return await _execute("SELECT id FROM projects WHERE MATCH(%s)", (query,))