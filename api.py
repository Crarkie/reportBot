import asyncio
import random
import string
from datetime import timedelta
from functools import wraps
from time import time
import jwt
import phonenumbers
from dateutil import relativedelta
from sanic.response import json

from app import app
from common.models import *
from config import Config
from search import search_all_projects
from bot.views import users

# Auth
from tg import ReplyKeyboardRemove
from tg.bot import ApiException


# Side-effect import is bad:(
def init_api():
    def token_required(f):
        @wraps(f)
        async def _verify(request, *args, **kwargs):
            if request.method == 'OPTIONS':
                return json({})

            auth_headers = request.headers.get('Authorization', '').split()

            invalid_msg = {
                'message': 'Invalid token. Registration and / or authentication required',
                'authenticated': False
            }
            expired_msg = {
                'message': 'Expired token. Reauthentication required.',
                'authenticated': False
            }

            if len(auth_headers) != 2:
                return json(invalid_msg, status=401)

            try:
                token = auth_headers[1]
                data = jwt.decode(token, Config.SECRET_KEY)
                if data['sub'] != Config.PANEL_LOGIN:
                    raise RuntimeError('Not a admin')
                return await f(request, *args, **kwargs)
            except jwt.ExpiredSignatureError:
                return json(expired_msg, status=401)
            except (jwt.InvalidTokenError, Exception) as e:
                print(e)
                return json(invalid_msg, status=401)

        return _verify

    @app.route('/api/login/', methods=['POST', 'OPTIONS'])
    async def login(request):
        if request.method == 'OPTIONS':
            return json({})
        data = request.json

        if data['login'] != Config.PANEL_LOGIN or data['password'] != Config.PANEL_PASSWORD:
            return json({'message': 'Invalid credentials', 'authenticated': False}, status=401)

        token = jwt.encode({
            'sub': data['login'],
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(days=180)},
            Config.SECRET_KEY)
        return json({'token': token.decode('utf8')})

    @app.route('/api/subordinate/<subordinate_id:int>/fio', methods=['POST', 'OPTIONS'])
    @token_required
    async def api_fio_subordinate(request, subordinate_id):
        sub = await Employee.get(subordinate_id)
        leader = await Employee.get(sub.leader_id)

        req = request.json
        first_name = req['first_name']
        last_name = req['last_name']

        old_fio = str(sub)

        await sub.update(first_name=first_name, last_name=last_name).apply()

        try:
            await app.bot.send_message(sub.chat_id,
                                       'Вышестоящее руководство измененило ваше ФИО на _{}_.'
                                       .format(str(sub)),
                                       parse_mode='Markdown')

            if leader:
                await app.bot.send_message(leader.chat_id,
                                           'У сотрудника _{}_ вышестоящим руководством было изменено ФИО на _{}_.'
                                           .format(old_fio, str(sub)),
                                           parse_mode='Markdown')
        except ApiException:
            pass

        return json({'message': 'ФИО изменено'})

    @app.route('/api/subordinate/<subordinate_id:int>/delete', methods=['POST', 'OPTIONS'])
    @token_required
    async def api_delete_subordinate(request, subordinate_id):
        sub = await Employee.get(subordinate_id)

        if sub.employee_role != 'subordinate':
            return json({'error': 'not_a_sub', 'message': 'Вы пытаетесь удалить не сотрудника!'})


        try:
            await app.bot.send_message(sub.chat_id,
                                       'Вы были откреплены от руководителя вышестоящим руководством.'
                                       '\nДля дальнейшей работы введите новый код приглашения:',
                                       reply_markup=ReplyKeyboardRemove())
            await users[sub.chat_id].was_deleted()
        except (KeyError, ApiException):
            pass
        await sub.update(active=False, chat_id=None, leader_id=None).apply()
        return json({'message': 'Сотрудник успешно удален'})

    @app.route('/api/leader/<leader_id:int>/delete', methods=['POST', 'OPTIONS'])
    @token_required
    async def api_delete_leader(request, leader_id):
        leader = await Employee.get(leader_id)

        force = request.json.get('force', False)

        if leader.employee_role != 'leader':
            return json({'error': 'not_a_leader', 'message': 'Вы пытаетесь удалить не руководителя!'})

        subs = await Employee.query.where(db.and_(Employee.leader_id == leader_id, Employee.active == True)).gino.all()
        if len(subs) > 0:
            if force:
                for sub in subs:
                    try:
                        await app.bot.send_message(sub.chat_id,
                                                   'Вы были откреплены от руководителя вышестоящим руководством.'
                                                   '\nДля дальнейшей работы введите новый код приглашения:',
                                                   reply_markup=ReplyKeyboardRemove())
                        await users[sub.chat_id].was_deleted()
                        await asyncio.sleep(0.02)
                    except (KeyError, ApiException):
                        pass
                    await sub.update(active=False, chat_id=None, leader_id=None).apply()
            else:
                return json({'error': 'has_subs', 'message': 'Вы не можете удалить данного руководителя, так как у него есть прикрепленные сотрудники'})
        try:
            await users[leader.chat_id].was_deleted()
        except KeyError:
            pass
        await leader.update(active=False, chat_id=None).apply()
        await Employee.delete.where(db.and_(Employee.leader_id == leader_id, Employee.chat_id == None)).gino.status()
        return json({'message': 'Руководитель успешно удален'})

    @app.route('/api/leader/add', methods=['POST', 'OPTIONS'])
    @token_required
    async def api_add_leader(request):
        request = request.json

        first_name = request['first_name'].strip()
        last_name = request['last_name'].strip()

        exist = await Employee.query.where(db.and_(Employee.first_name == first_name,
                                                   Employee.last_name == last_name)).gino.first()
        if exist:
            if exist.active:
                return json({'error': 'exist', 'message': 'Активный сотрудник или руководитель с таким ФИО уже существует!'})
            else:
                leader = exist
                await leader.update(employee_role='leader').apply()
        else:
            leader = await Employee.create(first_name=first_name, last_name=last_name,
                                           employee_role='leader')

        invite = await Invite.query.where(Invite.employee_id == leader.employee_id).gino.first()
        if invite:
            code = invite.invite_code
        else:
            while True:
                random.seed(time())
                code = ''.join(random.sample(string.ascii_letters + string.digits * 2, 10))
                if not await Invite.get(code):
                    break
            await Invite.create(invite_code=code, employee_id=leader.employee_id)

        return json({'invite_code': code})

    @app.route('/api/leaders', methods=['POST', 'OPTIONS'])
    @token_required
    async def api_leader_list(request):
        req = request.json

        total = await db.select([db.func.count(Employee.employee_id)]) \
            .where(db.and_(Employee.active == True, Employee.employee_role == 'leader')).gino.scalar()

        if req['perPage'] == total:
            req['page'] = 1

        leaders = await Employee.query.where(db.and_(Employee.active == True, Employee.employee_role == 'leader')) \
            .offset((req['page'] - 1) * req['perPage']).limit(req['perPage']).order_by(Employee.last_name).gino.all()

        res = {
            'total': total,
            'rows': []
        }
        for leader in leaders:
            formatted_phone = phonenumbers.parse('+' + str(leader.phone_number))
            formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)
            res['rows'].append({'id': leader.employee_id, 'fio': str(leader), 'phone_number': formatted_phone})

        return json(res)

    @app.route('/api/subordinates', methods=['POST', 'OPTIONS'])
    @token_required
    async def api_subordinate_list(request):
        req = request.json

        total = await db.select([db.func.count(Employee.employee_id)]) \
            .where(db.and_(Employee.active == True, Employee.employee_role == 'subordinate')).gino.scalar()

        if req['perPage'] == total:
            req['page'] = 1

        subordinates = await Employee.query.where(db.and_(Employee.active == True, Employee.employee_role == 'subordinate')) \
            .offset((req['page'] - 1) * req['perPage']).limit(req['perPage']).order_by(Employee.last_name).gino.all()

        res = {
            'total': total,
            'rows': []
        }
        for subordinate in subordinates:
            leader = await Employee.get(subordinate.leader_id)
            formatted_phone = phonenumbers.parse('+' + str(subordinate.phone_number))
            formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)
            res['rows'].append({'id': subordinate.employee_id, 'fio': str(subordinate),
                                'phone_number': formatted_phone, 'leader': str(leader), 'leader_id': leader.employee_id})

        return json(res)

    @app.route('/api/leader/<leader_id:int>/subordinates', methods=['POST', 'OPTIONS'])
    @token_required
    async def api_leader_subordinates_list(request, leader_id):
        req = request.json
        leader = await Employee.get(leader_id)

        total = await db.select([db.func.count(Employee.employee_id)]) \
            .where(db.and_(Employee.active == True, Employee.leader_id == leader_id)).gino.scalar()

        if req['perPage'] == total:
            req['page'] = 1

        subordinates = await Employee.query.where(db.and_(Employee.active == True, Employee.leader_id == leader_id)) \
            .offset((req['page'] - 1) * req['perPage']).limit(req['perPage']).order_by(Employee.last_name).gino.all()

        res = {
            'total': total,
            'rows': [],
            'leader': str(leader)
        }
        for subordinate in subordinates:
            formatted_phone = phonenumbers.parse('+' + str(subordinate.phone_number))
            formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)
            res['rows'].append({'id': subordinate.employee_id, 'fio': str(subordinate),
                                'phone_number': formatted_phone})

        return json(res)

    @app.route('/api/projects', methods=['GET', 'POST', 'OPTIONS'])
    @token_required
    async def api_projects_search(request):
        req = request.json

        query = Project.query
        if req['query'] != '':
            total, query = await search_all_projects(req['query'])
        else:
            total = await db.func.count(Project.project_id).gino.scalar()

        if req['perPage'] == total:
            req['page'] = 1

        projects = await query.offset((req['page'] - 1) * req['perPage']).limit(req['perPage']).gino.all()

        res = {
            'total': total,
            'rows': []
        }

        for proj in projects:
            leader = str(await Employee.get(proj.leader_id))
            res['rows'].append({'id': proj.project_id,
                                'title': proj.title,
                                'customer': proj.customer,
                                'code': proj.project_code,
                                'leader': leader})

        return json(res)

    @app.route('/api/subordinate/<employee_id:int>', methods=['POST', 'OPTIONS'])
    @token_required
    async def api_subordinate_projects(request, employee_id):
        employee = await Employee.get(employee_id)
        req = request.json
        year = req['year']
        month = req['month']

        total = await db.select([db.func.count(ReportStatistics.statistics_id)]) \
            .where(db.and_(ReportStatistics.employee_id == employee_id,
                           db.and_(ReportStatistics.year == year,
                                   ReportStatistics.month == month))).gino.scalar()

        if req['perPage'] == total:
            req['page'] = 1

        statistics = await ReportStatistics.load(project=Project) \
            .where(db.and_(ReportStatistics.employee_id == employee_id,
                           db.and_(ReportStatistics.year == year,
                                   ReportStatistics.month == month))) \
            .offset((req['page'] - 1) * req['perPage']).limit(req['perPage']).order_by(Project.title).gino.all()

        formatted_phone = phonenumbers.parse('+' + str(employee.phone_number))
        formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)

        res = {
            'fio': str(employee),
            'phone_number': formatted_phone,
            'total': total,
            'rows': []
        }

        for stat in statistics:
            res['rows'].append({
                'id': stat.project.project_id,
                'title': stat.project.title,
                'customer': stat.project.customer,
                'project_code': stat.project.project_code,
                'spent': round(stat.hours / 8.0),
                'worked': stat.count
            })

        return json(res)

    @app.route('/api/project/<project_id:int>', methods=['POST', 'OPTIONS'])
    @token_required
    async def api_project(request, project_id):
        project = await Project.get(project_id)
        req = request.json
        year = req['year']
        month = req['month']

        total = await db.select([db.func.count(ReportStatistics.statistics_id)]) \
            .where(db.and_(ReportStatistics.project_id == project_id,
                           db.and_(ReportStatistics.year == year,
                                   ReportStatistics.month == month))).gino.scalar()

        if req['perPage'] == total:
            req['page'] = 1

        statistics = await ReportStatistics.load(employee=Employee)\
            .where(db.and_(ReportStatistics.project_id == project_id,
                           db.and_(ReportStatistics.year == year,
                                   ReportStatistics.month == month))) \
            .offset((req['page'] - 1) * req['perPage']).limit(req['perPage']).order_by(Employee.last_name).gino.all()

        res = {
            'title': project.title,
            'customer': project.customer,
            'total': total,
            'rows': []
        }

        for stat in statistics:
            res['rows'].append({
                'id': stat.employee.employee_id,
                'fio': str(stat.employee),
                'spent': round(stat.hours / 8.0),
                'worked': stat.count
            })

        return json(res)
