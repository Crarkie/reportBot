import aiohttp
from sanic import response
from sanic.log import logger
from sanic.response import html

from tasks import *
from app import app
from api import init_api

db.init_app(app)
init_api()


@app.listener('before_server_start')
async def init(app, loop):
    app.session = aiohttp.ClientSession(loop=loop)
    app.bot: BotAPI = BotAPI(Config.BOT_TOKEN, app.session)


@app.listener('after_server_start')
async def after(app, loop):
    await app.bot.set_webhook('crarkie.site/bot/{}'.format(Config.BOT_TOKEN))
    await reload_users(app.bot)

    app.parser_task = loop.create_task(run_parser())
    app.reports_task = loop.create_task(users_report(app.session))
    app.expired_invites_task = loop.create_task(expired_invites())


@app.listener('after_server_stop')
async def finish(app, loop):
    await app.session.close()

    app.parser_task.cancel()
    app.reports_task.cancel()
    app.expired_invites_task.cancel()

    for task in tasks:
        task.cancel()


async def bot(request):
    try:
        update = Update.de_json(request.json)

        user_id = update.message.from_user.id if update.message is not None else update.callback_query.from_user.id

        if user_id not in users:
            employee = await Employee.query.where(Employee.chat_id == user_id).gino.first()
            if employee:
                if employee.employee_role == 'leader':
                    users[user_id] = LeaderMainView(employee, app.bot)
                    await users[user_id].start_view(update)
                    return
                elif employee.employee_role == 'subordinate':
                    users[user_id] = SubordinateMainView(employee, app.bot)
                    await users[user_id].start_view(update)
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
    except ApiException as e:
        logger.error(e)


@app.route('/bot/{}'.format(Config.BOT_TOKEN), methods=['POST'])
async def bot_route(request):
    await asyncio.create_task(bot(request))
    return response.json({})

app.static('/static/', './dist/static/')


@app.route('/')
@app.route('/<path:path>')
async def web_admin(request, path=''):
    with open('./dist/index.html', 'r', encoding='utf8') as index:
        return html(index.read())


if __name__ == '__main__':
    app.run('127.0.0.1', 5000)
