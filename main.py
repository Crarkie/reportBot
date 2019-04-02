import asyncio

import aiohttp
from sanic import response
from sanic import Sanic
from sanic.log import logger
from tg import *
from bot.views import *
from common.models import *
import logging

app = Sanic(__name__)
app.config.DB_USER = 'report_bot'
app.config.DB_DATABASE = 'report_bot_db'
app.config.DB_PASSWORD = '131MoonNight131'
db.init_app(app)

TOKEN = '803629540:AAHUCOPy8aROwVUnlhjM3Kd6z5YddaVdG-8'

users = {}


@app.listener('before_server_start')
async def init(app, loop):
    app.session = aiohttp.ClientSession(loop=loop)
    app.bot: BotAPI = BotAPI(TOKEN, app.session)


@app.listener('after_server_start')
async def after(app, loop):
    await app.bot.set_webhook('crarkie.site/bot/{}'.format(TOKEN), certificate=open('cert.pem', 'r'))


@app.listener('after_server_stop')
async def finish(app, loop):
    await app.session.close()


async def bot(request):
    update = Update.de_json(request.json)

    user_id = update.message.from_user.id if update.message is not None else update.callback_query.from_user.id

    if update.message is not None and update.message.text == '/reset':
        del (users[user_id])
    if user_id not in users:
        employee = await Employee.query.where(Employee.chat_id == user_id).gino.first()
        if employee:
            if employee.employee_role == 'leader':
                users[user_id] = LeaderMainView(employee, app.bot)
                await users[user_id].process(update)
                return
            elif employee.employee_role == 'subordinate':
                users[user_id] = SubordinateMainView(employee, app.bot)
                await users[user_id].process(update)
                return
        else:
            users[user_id] = AuthenticationView(app.bot)
            await users[user_id].start_view(update)
            return

    view: DialogView = users[user_id]
    if await view.process(update):
        if isinstance(view, AuthenticationView):
            if view.get_result()['employee'].employee_role == 'leader':
                users[user_id] = LeaderMainView(view.get_result()['employee'], app.bot)
                await users[user_id].start_view(update)
            elif view.get_result()['employee'].employee_role == 'subordinate':
                users[user_id] = SubordinateMainView(view.get_result()['employee'], app.bot)
                await users[user_id].start_view(update)


@app.route('/bot/{}'.format(TOKEN), methods=['POST'])
async def bot_route(request):
    await asyncio.create_task(bot(request))
    return response.json({})

if __name__ == '__main__':
    app.run('127.0.0.1', 5000)
