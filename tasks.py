from bot.views import *
from common.models import *
from common.sheet_parser import SheetParser
from config import Config


async def expired_invites():
    while True:
        expired = await Invite.query.where(datetime.now() > Invite.created_at + timedelta(days=3)).gino.all()

        for invite in expired:
            emp = await Employee.get(invite.employee_id)
            await emp.delete()
        await asyncio.sleep(8 * 3600)


async def reload_users(bot_api):
    active_users = await Employee.query.where(Employee.active == True).gino.all()
    for user in active_users:
        if user.employee_role == 'leader':
            users[user.chat_id] = LeaderMainView(user, bot_api)
        elif user.employee_role == 'subordinate':
            users[user.chat_id] = SubordinateMainView(user, bot_api)


async def run_parser():
    hour, minute = map(int, Config.PARSE_TIME.split(':'))
    while True:
        now = datetime.now()
        if now.hour != hour or now.minute < minute or now.minute > minute + 10:
            await asyncio.sleep(120)
            continue
        parser = SheetParser(Config.SHEET_SERVICE_FILE,
                             Config.SHEET_URL)
        await parser.parse()
        parser = None
        await asyncio.sleep(3600 * 23)


async def users_report(session):
    hour, minute = map(int, Config.REPORT_TIME.split(':'))
    while True:
        now = datetime.now()
        date = now.date()
        date = str(date.year) + str(date.month).zfill(2) + str(date.day).zfill(2)

        is_workday = True
        try:
            async with session.get('https://isdayoff.ru/' + date + '?cc=ru') as resp:
                if int(await resp.text()) == 1:
                    is_workday = False
        except:  # anti service-break security :)
            pass

        if now.hour != hour or now.minute < minute or now.minute > minute + 10:
            if not is_workday:
                await asyncio.sleep(3600 * 23)
            else:
                await asyncio.sleep(60)
            continue

        if is_workday:
            subordinates = await Employee.query.where(db.and_(Employee.active == True, Employee.employee_role == 'subordinate')).gino.all()

            nowdate = now.date()

            for sub in subordinates:
                try:
                    if sub.vacation_from and sub.vacation_to:
                        if sub.vacation_from <= nowdate < sub.vacation_to:
                            continue
                        elif nowdate >= sub.vacation_to:
                            await sub.update(vacation_to=None, vacation_from=None).apply()
                    await users[sub.chat_id].report_notify()
                except:
                    continue
                await asyncio.sleep(0.03)  # Limit message to 30 different users per seconds
        await asyncio.sleep(3600 * 23)

