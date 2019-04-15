import asyncio
import calendar
from asyncio import CancelledError

import phonenumbers
import random

from time import time
from datetime import datetime, timedelta
from common.models import *
from config import Config
from tg import *
from tg.bot import ApiException
from search import search_active_projects
from app import app

users = {}
tasks = []


def _add_task(task):
    tasks.append(task)


def _delete_task(task):
    try:
        i = tasks.index(task)
        tasks.pop(i)
    except ValueError:
        pass


class CalendarView(DialogView):
    MONTH_NAMES = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль',
                   'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

    def __init__(self, bot_api: BotAPI, year: int = None, month: int = None):
        self.year: int = year
        self.month: int = month
        self.day: int = None
        super(CalendarView, self).__init__(bot_api)

    @classmethod
    def __create_callback_data(cls, action, day):
        return ':'.join([action, str(day)])

    @classmethod
    def __separate_callback_data(cls, data):
        return data.split(':')

    async def start_view(self, update: Update):
        callback_query = update.callback_query
        chat_id = callback_query.from_user.id
        self.state = STATUS_START
        self.completed = False

        now = datetime.now()
        if self.year is None:
            self.year = now.year
        if self.month is None:
            self.month = now.month

        data_ignore = self.__create_callback_data('calendar_ignore', 0)
        data_back = self.__create_callback_data('calendar_back', 0)
        data_next = self.__create_callback_data('calendar_next', 0)
        data_prev = self.__create_callback_data('calendar_prev', 0)

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(self.MONTH_NAMES[self.month - 1] + ' ' + str(self.year),
                                          callback_data=data_ignore))
        row = []
        for day in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Cб', 'Вс']:
            row.append(InlineKeyboardButton(day, callback_data=data_ignore))
        keyboard.row(*row)

        cal = calendar.monthcalendar(self.year, self.month)
        for week in cal:
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(' ', callback_data=data_ignore))
                else:
                    row.append(InlineKeyboardButton(str(day),
                                                    callback_data=self.__create_callback_data('calendar_day', day)))
            keyboard.row(*row)

        row = [InlineKeyboardButton('⬅', callback_data=data_prev),
               InlineKeyboardButton('↩️ Назад', callback_data=data_back),
               InlineKeyboardButton('➡', callback_data=data_next)]
        keyboard.row(*row)

        await self._bot.edit_message_reply_markup(chat_id,
                                                  callback_query.message.message_id,
                                                  reply_markup=keyboard)

    def _result_to_dict(self):
        return {'date': datetime(year=self.year, month=self.month, day=self.day)}

    @DialogView.callback_handler(state=STATUS_START)
    async def calendar_actions(self, update: Update):
        callback_query = update.callback_query
        action, day = self.__separate_callback_data(callback_query.data)
        day = int(day)

        current = datetime(self.year, self.month, 1)
        if action == 'calendar_ignore':
            await self._bot.answer_callback_query(callback_query.id)
        elif action == 'calendar_day':
            await self._bot.answer_callback_query(callback_query.id)
            self.completed = True
            self.day = day
        elif action == 'calendar_prev':
            pre = current - timedelta(days=1)
            self.year, self.month = pre.year, pre.month
            await self._bot.answer_callback_query(callback_query.id)
            await self.start_view(update)
        elif action == 'calendar_next':
            next = current + timedelta(days=31)
            self.year, self.month = next.year, next.month
            await self._bot.answer_callback_query(callback_query.id)
            await self.start_view(update)
        elif action == 'calendar_back':
            self.state = STATUS_BACK
            await self._bot.answer_callback_query(callback_query.id)


class PhoneRequestView(DialogView):
    share_number_text = '📱 Предоставить номер'

    def __init__(self, bot_api: BotAPI):
        self.phone = None
        super(PhoneRequestView, self).__init__(bot_api)

    def _result_to_dict(self):
        return {'phone': self.phone}

    async def start_view(self, update: Update):
        user_id = update.message.from_user.id
        callback_query = update.callback_query

        self.completed = False
        self.state = STATUS_START
        markup = api_types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(KeyboardButton(self.share_number_text, request_contact=True))

        if callback_query:
            await self._bot.delete_message(user_id, callback_query.message.from_user.id)
        await self._bot.send_message(user_id,
                                     'Вам необходимо предоставить *свой* номер телефон',
                                     reply_markup=markup,
                                     parse_mode='Markdown')

    @DialogView.message_handler(state=STATUS_START)
    async def phone_got(self, update: Update):
        message = update.message
        if message.contact:
            if message.contact.user_id != message.from_user.id:
                await self._bot.send_message(message.from_user.id,
                                             'Вы предоставили *не свой* номер телефона!',
                                             reply_to_message_id=message.message_id,
                                             parse_mode='Markdown')
            else:
                self.phone = message.contact.phone_number
                self.completed = True


class VacationView(DialogView):
    def __init__(self, bot_api: BotAPI):
        self.begin_cal = CalendarView(bot_api)
        self.end_cal = CalendarView(bot_api)
        self.begin_date = None
        self.end_date = None
        super(VacationView, self).__init__(bot_api)

    def _result_to_dict(self):
        return {'begin': self.begin_date, 'end': self.end_date}

    async def start_view(self, update: Update):
        callback_query = update.callback_query
        chat_id = update.message.from_user.id if update.message else callback_query.from_user.id

        self.completed = False
        self.state = STATUS_START
        beg_str = end_str = ''
        if self.begin_date:
            beg_str = '\nВаша дата начала отпуска: {}'.format(self.begin_date.strftime('%d/%m/%Y'))
        if self.end_date:
            end_str = '\nВаша дата конца отпуска: {}'.format(self.end_date.strftime('%d/%m/%Y'))
        text = 'Выберите даты вашего отпуска{}{}'.format(beg_str, end_str)
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('☰ Начало', callback_data='select_begin'),
                   InlineKeyboardButton('☰ Конец', callback_data='select_end'))
        markup.add(InlineKeyboardButton('🆗 Подтвердить', callback_data='confirm_dates'))
        markup.add(InlineKeyboardButton('↩️ Назад', callback_data='back'))
        if callback_query:
            await self._bot.edit_message_text(text,
                                              chat_id,
                                              reply_markup=markup,
                                              message_id=callback_query.message.message_id)
        else:
            await self._bot.send_message(chat_id, text,
                                         reply_markup=markup)

    @DialogView.callback_handler(state=STATUS_START)
    async def start_handler(self, update: Update):
        callback_query = update.callback_query

        message_id = callback_query.message.message_id
        if callback_query.data == 'select_begin':
            await self._bot.edit_message_text('Выберите дату начала отпуска:',
                                              callback_query.from_user.id,
                                              message_id=message_id)
            await self.begin_cal.start_view(update)
            await self._bot.answer_callback_query(callback_query.id)
            self.state = 'select_begin'
        elif callback_query.data == 'select_end':
            await self._bot.edit_message_text('Выберите дату конца отпуска:',
                                              callback_query.from_user.id,
                                              message_id=message_id)
            await self.end_cal.start_view(update)
            await self._bot.answer_callback_query(callback_query.id)
            self.state = 'select_end'
        elif callback_query.data == 'confirm_dates':
            if not self.begin_date or not self.end_date:
                await self._bot.answer_callback_query(callback_query.id, 'Заполните обе даты')
            elif self.begin_date >= self.end_date:
                await self._bot.answer_callback_query(callback_query.id, 'Дата начала не может быть позже даты конца')
            elif self.begin_date < datetime.now() - timedelta(days=1) or \
                    self.end_date < datetime.now() - timedelta(days=1):
                await self._bot.answer_callback_query(callback_query.id, 'Дата не может быть раньше сегодняшнего дня')
            else:
                self.completed = True
        elif callback_query.data == 'back':
            self.completed = True
            self.state = STATUS_BACK

    @DialogView.callback_handler(state='select_begin')
    async def select_begin_handler(self, update: Update):
        await self.begin_cal.process(update)
        res = self.begin_cal.get_result()
        if res:
            self.begin_date = res['date']

        if res or self.begin_cal.state == STATUS_BACK:
            await self.start_view(update)

    @DialogView.callback_handler(state='select_end')
    async def select_end_handler(self, update: Update):
        await self.end_cal.process(update)
        res = self.end_cal.get_result()
        if res:
            self.end_date = res['date']

        if res or self.end_cal.state == STATUS_BACK:
            await self.start_view(update)


class AuthenticationView(DialogView):
    __fio_steps = ['employee_family', 'employee_name']
    __fio_data = ['family', 'name']
    __fio_text = ['', 'Отлично! Теперь введите ваше имя:']

    def __init__(self, bot_api: BotAPI):
        self._employee: Employee = None
        self._invite: Invite = None
        self._leader: Employee = None
        self._data = {}
        self._phone_view = None
        super(AuthenticationView, self).__init__(bot_api)

    def _result_to_dict(self):
        return {'employee': self._employee}

    async def start_view(self, update: Update):
        user_id = update.message.from_user.id

        await self._bot.send_message(user_id,
                                     'Для авторизации в боте Вам необходимо ввести\n'
                                     '*пригласительный код* сотрудника, либо руководителя:',
                                     parse_mode='Markdown')

    @DialogView.message_handler(STATUS_START)
    async def get_code_handler(self, update: Update):
        user_id = update.message.from_user.id
        invite_code = update.message.text

        self._invite = await Invite.get(invite_code)
        if self._invite is None:
            await self._bot.send_message(user_id,
                                         'Введеный код некорректен, либо не существует!\n'
                                         'Введите корректный *код приглашения*:',
                                         parse_mode='Markdown')
        else:
            self._employee: Employee = await Employee.query.where(Employee.employee_id == self._invite.employee_id).gino.first()
            if self._employee.employee_role == 'leader':
                await self._bot.send_message(user_id,
                                             'Вы были авторизованы как руководитель:\n'
                                             'ФИО: _{}_\n'.format(str(self._employee)),
                                             parse_mode='Markdown')

                self._phone_view: PhoneRequestView = PhoneRequestView(self._bot)
                await self._phone_view.start_view(update)
                self.state = 'leader_phone'
            elif self._employee.employee_role == 'subordinate':
                self._leader: Employee = await Employee.query.where(Employee.employee_id == self._employee.leader_id).gino.first()
                await self._bot.send_message(user_id,
                                             'Ваш руководитель:\n_{}_\n'
                                             'Для продолжения введите свою фамилию:'.format(str(self._leader)),
                                             parse_mode='Markdown')
                self.state = 'employee_family'

    @DialogView.message_handler('employee_name')
    @DialogView.message_handler('employee_family')
    async def employee_fio_handler(self, update: Update):
        user_id = update.message.from_user.id
        text = update.message.text
        step_index = self.__fio_steps.index(self.state)

        self._data[self.__fio_data[step_index]] = text.strip()

        # If not end FIO
        if self.state != 'employee_name':
            await  self._bot.send_message(user_id,
                                          self.__fio_text[step_index + 1])
            self.state = self.__fio_steps[step_index + 1]
        else:
            exist = await Employee.query.where(db.and_(Employee.first_name == self._data['name'],
                                                       db.and_(Employee.last_name == self._data['family'],
                                                               Employee.active == True))).gino.first()
            if exist:
                await self._bot.send_message(user_id,
                                             'Активный сотрудник с таким ФИО уже есть в системе!')
                await asyncio.sleep(0.5)
                await self._bot.send_message(user_id,
                                             'Введите свою фамилию:')
                self.state = 'employee_family'
                return
            self._phone_view: PhoneRequestView = PhoneRequestView(self._bot)
            await self._phone_view.start_view(update)
            self.state = 'employee_phone'

    @DialogView.message_handler('leader_phone')
    async def leader_phone_handler(self, update: Update):
        user_id = update.message.from_user.id

        if await self._phone_view.process(update):
            self._data['phone'] = self._phone_view.get_result()['phone']

            await self._employee.update(phone_number=int(self._data['phone']),
                                        active=True,
                                        chat_id=user_id).apply()
            try:
                await self._invite.delete()
            except:
                pass
            self.completed = True

    @DialogView.message_handler('employee_phone')
    async def employee_phone_handler(self, update: Update):
        user_id = update.message.from_user.id

        if await self._phone_view.process(update):
            self._data['phone'] = self._phone_view.get_result()['phone']

            leader_id = self._employee.leader_id
            exist = await Employee.query.where(db.and_(Employee.first_name == self._data['name'],
                                                       Employee.last_name == self._data['family'])).gino.first()
            if exist:
                await self._employee.delete()
                self._employee = exist

            await self._employee.update(first_name=self._data['name'],
                                        last_name=self._data['family'],
                                        phone_number=int(self._data['phone']),
                                        employee_role='subordinate',
                                        active=True,
                                        chat_id=user_id,
                                        leader_id=leader_id).apply()
            try:
                await self._invite.delete()
            except:
                pass
            self.completed = True

            formatted_phone = phonenumbers.parse('+' + str(self._employee.phone_number))
            formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)
            await self._bot.send_message(self._leader.chat_id,
                                         'Был зарегистрирован новый сотрудник:\n'
                                         '{},\nНомер тел.: {}\nПригл.код: {}'.format(str(self._employee),
                                                                                     formatted_phone,
                                                                                     self._invite.invite_code),
                                         )


class SubordinateListView(DialogView):
    pagination_count = 8

    def __init__(self, leader, bot_api: BotAPI):
        self._leader: Employee = leader
        self._page = 0
        self._first = True
        self._employee = None
        super(SubordinateListView, self).__init__(bot_api)

    async def start_view(self, update: Update):
        user_id = self._leader.chat_id

        markup = InlineKeyboardMarkup()

        query = db.select([db.func.count(Employee.employee_id)]).where(db.and_(Employee.leader_id == self._leader.employee_id, Employee.active == True))
        count = await query.gino.scalar()

        if count == 0:
            markup.add(InlineKeyboardButton('↩️ Назад', callback_data='subordinate_back'))

            await self._bot.send_message(user_id,
                                         'У вас нет прикрепленных сотрудников',
                                         reply_markup=markup)
            return

        subordinates = await Employee.query.where(db.and_(Employee.leader_id == self._leader.employee_id, Employee.active == True)). \
            offset(self._page * self.pagination_count).limit(self.pagination_count).gino.all()

        for subordinate in subordinates:
            mark = ''
            if subordinate.vacation_from and subordinate.vacation_to:
                mark = '🌴 '
            markup.add(InlineKeyboardButton(mark + str(subordinate), callback_data='subordinate_emp_{}'.format(subordinate.employee_id)))

        bottom = []
        if self._page != 0:
            bottom.append(InlineKeyboardButton('⬅', callback_data='subordinate_prev'))
        else:
            bottom.append(InlineKeyboardButton(' ', callback_data='subordinate_ignore'))

        bottom.append(InlineKeyboardButton('↩️ Назад', callback_data='subordinate_back'))

        if count > self._page * self.pagination_count + self.pagination_count:
            bottom.append(InlineKeyboardButton('➡', callback_data='subordinate_next'))
        else:
            bottom.append(InlineKeyboardButton(' ', callback_data='subordinate_ignore'))

        markup.row(*bottom)

        if self._first:
            await self._bot.send_message(user_id,
                                         'Выберите сотрудника',
                                         reply_markup=markup)
            self._first = False
        else:
            await self._bot.edit_message_text('Выберите сотрудника',
                                              user_id,
                                              update.callback_query.message.message_id,
                                              reply_markup=markup)

    @DialogView.callback_handler(STATUS_START)
    async def start_callback_handler(self, update: Update):
        user_id = self._leader.chat_id

        callback: CallbackQuery = update.callback_query
        data = callback.data

        await self._bot.answer_callback_query(callback.id)

        if data == 'subordinate_back':
            await self._bot.delete_message(user_id, update.callback_query.message.message_id)
            self.completed = True
        elif data == 'subordinate_next':
            self._page += 1
            await self.start_view(update)
        elif data == 'subordinate_prev':
            self._page -= 1
            await  self.start_view(update)
        elif data.startswith('subordinate_emp'):
            self._employee = await Employee.query.where(Employee.employee_id == int(data.split('_')[2])).gino.first()

            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton('❌ Удалить', callback_data='employee_delete'))
            if self._employee.vacation_to and self._employee.vacation_from:
                markup.add(InlineKeyboardButton('🌴 Отменить отдых', callback_data='employee_no_vacation'))
            markup.add(InlineKeyboardButton('↩️ Назад', callback_data='employee_back'))

            formatted_phone = phonenumbers.parse('+' + str(self._employee.phone_number))
            formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)

            vacation_str = ''
            if self._employee.vacation_from and self._employee.vacation_to:
                vacation_str = '\nОтдых (больничный): {} - {}'.format(self._employee.vacation_from.strftime('%d/%m/%Y'),
                                                                      self._employee.vacation_to.strftime('%d/%m/%Y'))
            message = await self._bot.edit_message_text('ФИО: _{}_\nНомер тел.: _{}_{}'.format(str(self._employee), formatted_phone, vacation_str),
                                                        user_id,
                                                        callback.message.message_id,
                                                        parse_mode='Markdown',
                                                        reply_markup=markup)
            self.state = 'employee_menu'

    @DialogView.callback_handler('employee_menu')
    async def employee_callback_handler(self, update: Update):
        user_id = self._leader.chat_id

        callback = update.callback_query
        data = callback.data

        await self._bot.answer_callback_query(callback.id)

        if data == 'employee_back':
            self._employee = None
            self.state = STATUS_START
            await self.start_view(update)
        elif data == 'employee_delete':
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton('❌ Да', callback_data='employee_confirm_delete'), InlineKeyboardButton('💚 Нет', callback_data='employee_back'))

            await self._bot.edit_message_text('⚠ Вы уверены, что хотите удалить сотрудника? ⚠️',
                                              user_id,
                                              callback.message.message_id,
                                              reply_markup=markup)
        elif data == 'employee_confirm_delete':
            await self._bot.send_message(self._employee.chat_id,
                                         'Вы были удалены вашим руководителем.\nДля дальнейшей работы введите новый код приглашения:',
                                         reply_markup=ReplyKeyboardRemove())
            try:
                await users[self._employee.chat_id].was_deleted()
            except KeyError:
                pass

            await self._employee.update(active=False, chat_id=None, leader_id=None).apply()
            self._employee = None
            self.state = STATUS_START
            await self.start_view(update)
        elif data == 'employee_no_vacation':
            await self._employee.update(vacation_from=None, vacation_to=None).apply()
            await self._bot.send_message(self._employee.chat_id,
                                         'Руководителем был аннулирован ваш отпуск(больничный).\n')
            self._employee = None
            self.state = STATUS_START
            await self.start_view(update)


class ApproveReportView(DialogView):
    report_confirm_button = '✅ Утвердить'
    report_revision_button = '↪️ На доработку'

    def __init__(self, leader, report_view, bot_api: BotAPI):
        self._employee = None
        self._leader = leader
        self._report: Report = report_view.get_result()['report']
        self._report_view = report_view
        self._callback_id = None
        self._msg = None
        super(ApproveReportView, self).__init__(bot_api)

    async def start_view(self, update: Update):
        pass

    async def report(self):
        self._employee = await Employee.get(self._report.employee_id)

        report_projects = await ReportProject.load(project=Project).where(ReportProject.report_id == self._report.report_id).gino.all()
        info = ''

        for project in report_projects:
            info += '{} - {}%\n'.format(project.project.title, int(project.hours * 12.5))
        info = info[:-1]

        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton(self.report_confirm_button, callback_data='report_confirm'),
                   InlineKeyboardButton(self.report_revision_button, callback_data='report_revision'))

        await self._bot.send_message(self._leader.chat_id,
                                     'От сотрудника *{}* пришел отчет на утверждение:\n{}'.format(str(self._employee), info),
                                     reply_markup=markup,
                                     parse_mode='Markdown')

    @DialogView.callback_handler(STATUS_START)
    async def start_callback_handler(self, update: Update):
        callback = update.callback_query
        data = callback.data

        if data == 'report_confirm':
            self.completed = True
            await self._report_view.confirm()

            await self._bot.delete_message(self._leader.chat_id,
                                           callback.message.message_id)
            await self._bot.answer_callback_query(callback.id, 'Отчет сохранен')
            await self._bot.send_message(self._employee.chat_id,
                                         'Руководитель утвердил ваш отчет')
        elif data == 'report_revision':
            await self._bot.delete_message(self._leader.chat_id,
                                           callback.message.message_id)
            message = await self._bot.send_message(self._leader.chat_id,
                                                   'Введите комментарий для сотрудника: ')
            self._msg = message['message_id']
            self._callback_id = callback.id
            self.state = 'revision_comment'

    @DialogView.message_handler('revision_comment')
    async def revision_comment_handler(self, update: Update):
        text = update.message.text

        await self._bot.delete_message(self._leader.chat_id,
                                       update.message.message_id)

        await users[self._employee.chat_id].revision_report(self._report_view, comment=text)
        await self._bot.answer_callback_query(self._callback_id, 'Отправлен на доработку')
        await self._bot.delete_message(self._leader.chat_id, self._msg)
        self.completed = True


class LeaderMainView(DialogView):
    create_invite_button = '🆕 Добавить сотрудника'
    subordinate_list_button = '👨‍💼 Сотрудники'

    def __init__(self, leader, bot_api: BotAPI):
        self._leader = leader
        self.subordinate_view = None
        self.approve_list = []
        self.markup = ReplyKeyboardMarkup(resize_keyboard=True)
        self.markup.add(KeyboardButton(self.create_invite_button))
        self.markup.add(KeyboardButton(self.subordinate_list_button))
        self._last_msg = None
        self._restore = False
        super(LeaderMainView, self).__init__(bot_api)

    async def approve_report(self, report_view):
        if self.state == 'subordinate_list':
            self._restore = True
        self.approve_list.append(ApproveReportView(self._leader, report_view, self._bot))
        if len(self.approve_list) == 1:
            await self.approve_list[0].report()

        self.state = 'approve_reports'

    async def was_deleted(self):
        user_id = self._leader.chat_id
        if not user_id:
            return
        await self._bot.send_message(user_id,
                                     'Вы были удалены из системы вышестоящим руководством\nДля дальнейшей работы введите новый код приглашения:',
                                     reply_markup=ReplyKeyboardRemove())
        users[user_id] = AuthenticationView(self._bot)

    async def start_view(self, update: Update):
        user_id = self._leader.chat_id

        message = await self._bot.send_message(user_id,
                                               'Выберите необходимый пункт меню',
                                               reply_markup=self.markup)
        self._last_msg = message['message_id']

    async def _create_invite_action(self):
        new_employee = await Employee.create(leader_id=self._leader.employee_id, employee_role='subordinate')
        while True:
            random.seed(time())
            code = ''.join(random.sample(string.ascii_letters + string.digits * 2, 10))
            if not await Invite.get(code):
                break

        invite = await Invite.create(invite_code=code, employee_id=new_employee.employee_id)
        await self._bot.send_message(self._leader.chat_id,
                                     'Пригласительный код для сотрудника\n(Автоматически истекает через 3 дня): ')
        await self._bot.send_message(self._leader.chat_id,
                                     '*{}*'.format(invite.invite_code),
                                     parse_mode='Markdown',
                                     reply_markup=self.markup)

    async def _subordinate_list_action(self, update: Update):
        self.subordinate_view = SubordinateListView(self._leader, self._bot)
        await self.subordinate_view.start_view(update)

    @DialogView.message_handler(STATUS_START)
    async def menu_handler(self, update: Update):
        text = update.message.text

        if self._last_msg:
            await self._bot.delete_message(self._leader.chat_id,
                                           self._last_msg)
            self._last_msg = None

        await self._bot.delete_message(self._leader.chat_id,
                                       update.message.message_id)

        if text == self.create_invite_button:
            await self._create_invite_action()
        elif text == self.subordinate_list_button:
            await self._subordinate_list_action(update)
            self.state = 'subordinate_list'
        else:
            await self.start_view(update)

    @DialogView.callback_handler('subordinate_list')
    async def subordinate_list_handler(self, update: Update):
        if await self.subordinate_view.process(update):
            self.state = STATUS_START
            self.subordinate_view = None
            await self.start_view(update)

    @DialogView.message_handler('approve_reports')
    @DialogView.callback_handler('approve_reports')
    async def approve_reports_handler(self, update: Update):
        if await self.approve_list[0].process(update):
            self.approve_list.pop(0)
            if len(self.approve_list) > 0:
                await self.approve_list[0].report()
            else:
                self.state = STATUS_START
                if self._restore:
                    self._restore = False
                    await self.start_view(update)


class SubordinateMainView(DialogView):
    leader_info_button = 'ℹ️ Руководитель'
    submit_report_button = '📅 Сдать отчет'
    reference_button = '🔰 Справка'
    vacation_button = '🌴🌡 Отпуск'

    reference_text = '''
Каждый рабочий день в {} Вам будет приходить оповещение
о необходимости заполнить отчет по проектам.
В случае отсутствия реакции, через {} минут приходит повторное уведомление.\n
На заполнение отчета предоставляется {} минут.
Если отчет не будет заполнен в течении этого времени,
либо не последует реакции в течении {} минут после второго оповещения, то об этом будет доложено вашему руководителю.
Если сумма процентов будет выше 100, то данные по последнему отчету автоматически скорректируются.\n
После отправки отчета, руководитель должен подтвердить его, либо отправить на доработку.\n
        '''.format(Config.REPORT_TIME, Config.IDLE_REPORT_TIME,
                   Config.FILL_REPORT_TIME, Config.IDLE_REPORT_TIME)

    def __init__(self, employee, bot_api: BotAPI):
        self._employee = employee
        self.markup = ReplyKeyboardMarkup(resize_keyboard=True)
        self.markup.row(KeyboardButton(self.leader_info_button),
                        KeyboardButton(self.reference_button))
        self.markup.row(KeyboardButton(self.vacation_button),
                        KeyboardButton(self.submit_report_button))
        self.report_view = None
        self.vacation_view = None
        self._last_msg = None

        super(SubordinateMainView, self).__init__(bot_api)

    async def report_notify(self):
        self.state = 'report'
        self.report_view = ReportView(self._employee, self._bot)
        await self.report_view.prepare()
        await self.report_view.report_notify()

    async def revision_report(self, report_view, comment):
        self.state = 'report'
        self.report_view = report_view
        await self.report_view.revise_report_notify(comment)

    async def was_deleted(self):
        user_id = self._employee.chat_id
        users[user_id] = AuthenticationView(self._bot)

    async def start_view(self, update: Update):
        user_id = self._employee.chat_id

        message = await self._bot.send_message(user_id,
                                               'Выберите необходимый пункт меню:',
                                               reply_markup=self.markup)
        self._last_msg = message['message_id']

    async def _leader_info_action(self):
        leader = await Employee.query.where(Employee.employee_id == self._employee.leader_id).gino.first()

        formatted_phone = phonenumbers.parse('+' + str(leader.phone_number))
        formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)

        message = await self._bot.send_message(self._employee.chat_id,
                                               "Ваш руководитель:\n{}\nТел.: {}".format(str(leader),
                                                                                        formatted_phone),
                                               reply_markup=self.markup)
        self._last_msg = message['message_id']

    async def delete_last(self):
        if self._last_msg:
            await self._bot.delete_message(self._employee.chat_id,
                                           self._last_msg)
            self._last_msg = None

    @DialogView.message_handler(STATUS_START)
    async def menu_handler(self, update: Update):
        self._employee = await Employee.get(self._employee.employee_id)
        text = update.message.text

        await self._bot.delete_message(self._employee.chat_id,
                                       update.message.message_id)

        if text == self.leader_info_button:
            await self.delete_last()
            await self._leader_info_action()
        elif text == self.reference_button:
            await self.delete_last()
            message = await self._bot.send_message(self._employee.chat_id,
                                                   self.reference_text,
                                                   reply_markup=self.markup)
            self._last_msg = message['message_id']
        elif text == self.vacation_button:
            if self._employee.vacation_to and self._employee.vacation_from:
                now = datetime.now().date()
                days_left = '.'
                if now >= self._employee.vacation_from:
                    days_left = (self._employee.vacation_to - now).days
                    days_left = ', осталось {} дней.'.format(days_left)

                await self.delete_last()
                message = await self._bot.send_message(self._employee.chat_id,
                                                       'У вас уже назначен отпуск, либо больничный.\n'
                                                       '📅 {} - {}{}\n'
                                                       'Чтобы его отменить, обратитесь к своему руководителю.\n'
                                                       .format(self._employee.vacation_from.strftime('%d/%m/%Y'),
                                                               self._employee.vacation_to.strftime('%d/%m/%Y'),
                                                               days_left),
                                                       reply_markup=self.markup)
                self._last_msg = message['message_id']
                return
            self.state = 'choice_vacation'
            self.vacation_view = VacationView(self._bot)
            await self.vacation_view.start_view(update)
        elif text == self.submit_report_button:
            today = datetime.now().date()
            date = str(today.year) + str(today.month).zfill(2) + str(today.day).zfill(2)

            try:
                async with app.session.get('https://isdayoff.ru/' + date + '?cc=ru') as resp:
                    if int(await resp.text()) == 1:
                        await self.delete_last()
                        message = await self._bot.send_message(self._employee.chat_id,
                                                               'Вы не можете сдать отчет, так как сегодня не рабочий день.',
                                                               reply_markup=self.markup)
                        self._last_msg = message['message_id']
                        return
            except:  # anti service-break security :)
                pass

            if self._employee.vacation_to and self._employee.vacation_from:
                if self._employee.vacation_from <= datetime.now().date() < self._employee.vacation_to:
                    await self.delete_last()
                    message = await self._bot.send_message(self._employee.chat_id,
                                                           'Вы не можете сдать отчет, так как у вас назначен отпуск (больничный)\n'
                                                           'Чтобы его отменить, обратитесь к своему руководителю.',
                                                           reply_markup=self.markup)
                    self._last_msg = message['message_id']
                    return

            report = await Report.query.where(db.and_(Report.report_date == today, Report.employee_id == self._employee.employee_id)).gino.first()
            if report:
                await self.delete_last()
                message = await self._bot.send_message(self._employee.chat_id,
                                                       'Вы сегодня уже сдали отчет!',
                                                       reply_markup=self.markup)
                self._last_msg = message['message_id']
                return

            report_hour, report_minute = map(int, Config.REPORT_TIME.split(':'))
            now_hour, now_minute = datetime.now().hour, datetime.now().minute

            is_time = False
            if now_hour == report_hour:
                if now_minute > report_minute:
                    is_time = True
            elif now_hour > report_hour:
                is_time = True

            if not is_time:
                await self.delete_last()
                message = await self._bot.send_message(self._employee.chat_id,
                                                       'Сдача отчета возможна только после *{}*.'.format(Config.REPORT_TIME),
                                                       parse_mode='Markdown',
                                                       reply_markup=self.markup)
                self._last_msg = message['message_id']
            else:
                await self.report_notify()
        else:
            await self.start_view(update)

    @DialogView.callback_handler('report')
    async def report_callback_handler(self, update: Update):
        if self.report_view.completed:
            self.report_view = None
            self.state = STATUS_START
            await self.process(update)
            return

        if await self.report_view.process(update):
            leader = await Employee.query.where(Employee.employee_id == self._employee.leader_id).gino.first()

            try:
                await users[leader.chat_id].approve_report(self.report_view)
            except KeyError:
                pass

            self.report_view = None
            self.state = STATUS_START

    @DialogView.message_handler('report')
    async def report_message_handler(self, update: Update):
        if self.report_view.completed:
            self.report_view = None
            self.state = STATUS_START
            await self.process(update)
            return
        await self.report_view.process(update)

    @DialogView.callback_handler('choice_vacation')
    async def vacation_callback_handler(self, update: Update):
        if await self.vacation_view.process(update):
            await self._bot.delete_message(self._employee.chat_id,
                                           update.callback_query.message.message_id)

            if self.vacation_view.state != STATUS_BACK:
                res = self.vacation_view.get_result()

                leader = await Employee.query.where(Employee.employee_id == self._employee.leader_id).gino.first()

                await self._bot.send_message(leader.chat_id,
                                             'Сотрудник _{}_ обозначил отпуск (больничный): {} - {}'.format(str(self._employee),
                                                                                                            res['begin'].strftime('%d/%m/%Y'),
                                                                                                            res['end'].strftime('%d/%m/%Y')),
                                             parse_mode='Markdown')

                await self._employee.update(vacation_from=res['begin'], vacation_to=res['end']).apply()

            self.vacation_view = None
            self.state = STATUS_START


class ReportView(DialogView):
    pagination_count = 8

    first_report_text = '''
_{{}}_, добрый вечер. 
Вам необходимо заполнить отчет. 
Если сумма по всем проектам будет выше 100, данные по последнему отчету автоматически скорректируются.
У вас есть {fill_time} минут на заполнение отчета.\n
Если нужного проекта нет в списке, то напишите какую-либо информацию о проекте, и найденные проекты отобразятся.{{}}
Распределено: {{}}%'''.format(fill_time=Config.FILL_REPORT_TIME)

    revise_report_text = '''
_{{}}_, добрый вечер. 
Руководитель отправил ваш сегодняшний отчет на доработку со следующим комментарием:\n*{{}}*\n
Если сумма по всем проектам будет выше 100, данные по последнему отчету автоматически скорректируются.
У вас есть {fill_time} минут на заполнение отчета.\n
Если нужного проекта нет в списке, то напишите какую-либо информацию о проекте, и найденные проекты отобразятся.
Распределено: {{}}%'''.format(fill_time=Config.FILL_REPORT_TIME)

    def __init__(self, subordinate, bot_api: BotAPI):
        self._employee = subordinate
        self._page = 0
        self._count = 0
        self._report = None
        self._first = True
        self._projects = {}
        self._total = 0
        self._list = []
        self._found = None
        self._cur_project = None
        self._project_markup = None
        self._last_msg = None
        self._idle_task = None
        self._main_text = self.first_report_text
        self._fill_task = None
        self._comment = ''
        self._percent_per_hour = 12.5

        super(ReportView, self).__init__(bot_api)

    def _result_to_dict(self):
        return {'report': self._report}

    async def confirm(self):
        now = datetime.now()
        year, month = now.year, now.month

        count = await db.select([db.func.max(ReportStatistics.count)]) \
            .where(db.and_(ReportStatistics.employee_id == self._employee.employee_id,
                           db.and_(ReportStatistics.year == year,
                                   ReportStatistics.month == month))).gino.scalar()
        if not count:
            count = 0
        for proj in self._projects:
            statistics = await ReportStatistics.query.where(db.and_(ReportStatistics.employee_id == self._employee.employee_id,
                                                                    db.and_(ReportStatistics.year == year,
                                                                            db.and_(ReportStatistics.month == month,
                                                                                    ReportStatistics.project_id == proj)))) \
                .gino.first()
            if not statistics:
                statistics = await ReportStatistics.create(employee_id=self._employee.employee_id,
                                                           project_id=proj,
                                                           year=year, month=month,
                                                           hours=0, count=0)

            await statistics.update(hours=statistics.hours + self._projects[proj] / self._percent_per_hour).apply()

        await ReportStatistics.update.values(count=count + 1).where(
            db.and_(ReportStatistics.employee_id == self._employee.employee_id,
                    db.and_(ReportStatistics.year == year,
                            ReportStatistics.month == month))
        ).gino.status()

    async def prepare(self):
        Leader = Employee.alias()
        self._employee = await Employee.load(leader=Leader.on(Employee.leader_id == Leader.employee_id)) \
            .where(Employee.employee_id == self._employee.employee_id).gino.first()

        first_list = []
        last_report = await Report.query.where(Report.employee_id == self._employee.employee_id).order_by(Report.report_id.desc()).gino.first()
        if last_report:
            first_list = await ReportProject.select('project_id') \
                .where(ReportProject.report_id == last_report.report_id) \
                .limit(self.pagination_count).gino.all()
            first_list = list(map(lambda x: x[0], first_list))

        first_projects = await Project.query.where(Project.project_id.in_(first_list)).gino.all()
        for proj in first_projects:
            self._list.append(proj)
            self._count += 1

        other_projects = await Project.query.where(db.and_(~Project.project_id.in_(first_list),
                                                           db.and_(Project.leader_id == self._employee.leader.employee_id, Project.active == True))).gino.all()

        for proj in other_projects:
            self._list.append(proj)
            self._count += 1

        try:
            date = datetime.now().date()
            date = str(date.year) + str(date.month).zfill(2) + str(date.day).zfill(2)

            async with app.session.get('https://isdayoff.ru/' + date + '?cc=ru&pre=1') as resp:
                if int(await resp.text()) == 2:
                    self._percent_per_hour = 14.28
        except:  # anti service-break security :)
            pass

    async def _projects_markup(self):
        markup = InlineKeyboardMarkup()

        begin = self._page * self.pagination_count
        end = self._page * self.pagination_count + self.pagination_count

        for proj in self._list[begin: end]:
            percentage = '' if proj.project_id not in self._projects else ' - {}%'.format(self._projects[proj.project_id])
            markup.add(InlineKeyboardButton(proj.title + percentage, callback_data='report_project_' + str(proj.project_id)))

        bottom = []
        if self._page != 0:
            bottom.append(InlineKeyboardButton('⬅', callback_data='report_prev'))
        else:
            bottom.append(InlineKeyboardButton(' ', callback_data='report_ignore'))

        bottom.append(InlineKeyboardButton('️☑️ Отправить', callback_data='report_send'))

        if self._count > end:
            bottom.append(InlineKeyboardButton('➡', callback_data='report_next'))
        else:
            bottom.append(InlineKeyboardButton(' ', callback_data='report_ignore'))

        markup.row(*bottom)

        markup.add(InlineKeyboardButton('♻️ Сбросить заполненное', callback_data='report_clear'))

        return markup

    async def __idle_report(self, minutes):
        message = None
        try:
            await asyncio.sleep(60 * minutes)
            message = await self._bot.send_message(self._employee.chat_id,
                                                   '_{}_, напоминаем вам о *необходимости сдать вовремя отчет*. '
                                                   'В случае отсутствия реакции, '
                                                   'через {} минут *о невыполнении будет доложено* вашему руководителю'.format(str(self._employee.first_name),
                                                                                                                               Config.IDLE_REPORT_TIME),
                                                   parse_mode='Markdown')
            await asyncio.sleep(60 * minutes)
            self.completed = True
            await self._bot.delete_message(self._employee.chat_id,
                                           self._last_msg)
            await self._bot.send_message(self._employee.leader.chat_id,
                                         'Сотрудником _{}_ сегодня не был сдан отчет'.format(str(self._employee)),
                                         parse_mode='Markdown')
            self._last_msg = None

            await self._bot.send_message(self._employee.chat_id,
                                         'Время, отведенное на заполнение отчета, истекло. Обратитесь к вашему руководителю.')
        except CancelledError:
            raise
        finally:
            if message:
                await self._bot.delete_message(self._employee.chat_id,
                                               message['message_id'])
            _delete_task(asyncio.current_task())

    async def __idle_revision_report(self, minutes):
        try:
            await asyncio.sleep(60 * minutes)
            self.completed = True
            await self._bot.delete_message(self._employee.chat_id,
                                           self._last_msg)
            await self._bot.send_message(self._employee.leader.chat_id,
                                         'Сотрудником _{}_ сегодня не был сдан отчет'.format(str(self._employee)),
                                         parse_mode='Markdown')
            self._last_msg = None

            await self._bot.send_message(self._employee.chat_id,
                                         'Время, отведенное на заполнение отчета, истекло. Обратитесь к вашему руководителю.')
        except CancelledError:
            raise
        finally:
            _delete_task(asyncio.current_task())

    async def revise_report_notify(self, comment):
        self._main_text = self.revise_report_text
        self._comment = comment

        Leader = Employee.alias()
        self._employee = await Employee.load(leader=Leader.on(Employee.leader_id == Leader.employee_id)) \
            .where(Employee.employee_id == self._employee.employee_id).gino.first()

        markup = await self._projects_markup()
        message = await self._bot.send_message(self._employee.chat_id,
                                               self._main_text.format(self._employee.first_name, self._comment, self._total),
                                               reply_markup=markup,
                                               parse_mode='Markdown')

        self._last_msg = message['message_id']
        self.completed = False
        await self._report.delete()

        self._fill_task = asyncio.create_task(self.__idle_revision_report(Config.FILL_REPORT_TIME))
        _add_task(self._fill_task)

    async def report_notify(self):
        Leader = Employee.alias()
        self._employee = await Employee.load(leader=Leader.on(Employee.leader_id == Leader.employee_id)) \
            .where(Employee.employee_id == self._employee.employee_id).gino.first()

        markup = await self._projects_markup()

        message = await self._bot.send_message(self._employee.chat_id,
                                               self._main_text.format(self._employee.first_name, self._comment, self._total),
                                               reply_markup=markup,
                                               parse_mode='Markdown')
        self._last_msg = message['message_id']

        self._idle_task = asyncio.create_task(self.__idle_report(Config.IDLE_REPORT_TIME))
        _add_task(self._idle_task)

    @DialogView.message_handler('search_choice')
    @DialogView.message_handler(STATUS_START)
    async def search_project_handler(self, update: Update):
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None
            self._fill_task = asyncio.create_task(self.__idle_report(Config.FILL_REPORT_TIME))
            _add_task(self._fill_task)

        query = update.message.text

        await self._bot.delete_message(self._employee.chat_id,
                                       update.message.message_id)

        self._found = await (await search_active_projects(query)).gino.all()
        if len(self._found) > self.pagination_count:
            self._found = self._found[:self.pagination_count]

        markup = InlineKeyboardMarkup()

        for proj in self._found:
            markup.add(InlineKeyboardButton(proj.title, callback_data='search_project_' + str(proj.project_id)))

        markup.add(InlineKeyboardButton('↩️ Назад', callback_data='search_back'))

        await self._bot.delete_message(self._employee.chat_id,
                                       self._last_msg)
        if len(self._found) > 0:
            text = 'По вашему запросу найдены следующие наиболее подходящие проекты:\n' \
                   'Если нужный проект не был найден, введите новый поисковый запрос.'
        else:
            text = 'По вашему запросу ничего не найдено. Введите новый поисковый запрос.'

        message = await self._bot.send_message(self._employee.chat_id,
                                               text,
                                               parse_mode='Markdown',
                                               reply_markup=markup)
        self._last_msg = message['message_id']

        self.state = 'search_choice'

    @DialogView.callback_handler('search_choice')
    async def search_choice_handler(self, update: Update):
        callback = update.callback_query
        data = callback.data

        await self._bot.answer_callback_query(callback.id)

        if data == 'search_back':
            self.state = STATUS_START

            markup = await self._projects_markup()
            message = await self._bot.edit_message_text(self._main_text.format(self._employee.first_name, self._comment, self._total),
                                                        self._employee.chat_id,
                                                        message_id=callback.message.message_id,
                                                        parse_mode='Markdown',
                                                        reply_markup=markup)

            self._last_msg = message['message_id']
        elif data.startswith('search_project_'):
            project_id = int(data.split('_')[2])
            self._cur_project: Project = await Project.get(project_id)

            inList = False
            for proj in self._list:
                if proj.project_id == project_id:
                    inList = True
                    break

            if not inList:
                self._list.insert(0, self._cur_project)
                self._count += 1
            self._page = 0

            if project_id not in self._projects:
                self._projects[project_id] = 0

            markup = InlineKeyboardMarkup()

            markup.add(InlineKeyboardButton('♻️ Сбросить', callback_data='project_clear'))
            markup.add(InlineKeyboardButton('↩️ Назад', callback_data='project_back'))

            self._project_markup = markup

            message = await self._bot.edit_message_text('№ *{}*\n{}\nЗаказчик: _{}_\nВыделено: {}%\nВведите значение:'
                                                        .format(self._cur_project.project_id,
                                                                self._cur_project.title,
                                                                self._cur_project.customer,
                                                                self._projects[project_id]),
                                                        self._employee.chat_id,
                                                        message_id=callback.message.message_id,
                                                        parse_mode='Markdown',
                                                        reply_markup=markup)
            self._last_msg = message['message_id']
            self.state = 'project_menu'

    @DialogView.callback_handler(STATUS_START)
    async def list_callback_handler(self, update: Update):
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None
            self._fill_task = asyncio.create_task(self.__idle_report(Config.FILL_REPORT_TIME))
            _add_task(self._fill_task)

        callback = update.callback_query
        data = callback.data

        if data == 'report_ignore':
            await self._bot.answer_callback_query(callback.id)
        elif data == 'report_prev':
            await self._bot.answer_callback_query(callback.id)
            self._page -= 1
            markup = await self._projects_markup()
            await self._bot.edit_message_reply_markup(self._employee.chat_id,
                                                      message_id=callback.message.message_id,
                                                      reply_markup=markup)
        elif data == 'report_clear':
            await self._bot.answer_callback_query(callback.id)

            self._total = 0
            self._projects = {}

            try:
                markup = await self._projects_markup()
                message = await self._bot.edit_message_text(self._main_text.format(self._employee.first_name, self._comment, self._total),
                                                            self._employee.chat_id,
                                                            message_id=callback.message.message_id,
                                                            parse_mode='Markdown',
                                                            reply_markup=markup)

                self._last_msg = message['message_id']
            except ApiException:
                pass
        elif data == 'report_next':
            await self._bot.answer_callback_query(callback.id)

            self._page += 1
            markup = await self._projects_markup()
            await self._bot.edit_message_reply_markup(self._employee.chat_id,
                                                      message_id=callback.message.message_id,
                                                      reply_markup=markup)
        elif data == 'report_send':
            if self._total != 100:
                await self._bot.answer_callback_query(callback.id, text='⚠️Отчет не заполнен на 100%!⚠️', show_alert=1)
            else:
                await self._bot.answer_callback_query(callback.id, text='Отправлено. Ожидайте одобрения', show_alert=1)
                await self._bot.delete_message(self._employee.chat_id,
                                               self._last_msg)
                self._report = await Report.create(employee_id=self._employee.employee_id, report_date=datetime.now().date())
                for project_id in self._projects:
                    await ReportProject.create(project_id=project_id, report_id=self._report.report_id,
                                               employee_id=self._employee.employee_id,
                                               hours=self._projects[project_id] / self._percent_per_hour)
                self.completed = True
                self._fill_task.cancel()
                self._fill_task = None
        elif data.startswith('report_project_'):
            await self._bot.answer_callback_query(callback.id)

            project_id = int(data.split('_')[2])
            self._cur_project: Project = await Project.get(project_id)
            if project_id not in self._projects:
                self._projects[project_id] = 0

            markup = InlineKeyboardMarkup()

            markup.add(InlineKeyboardButton('♻️ Сбросить', callback_data='project_clear'))
            markup.add(InlineKeyboardButton('↩️ Назад', callback_data='project_back'))

            self._project_markup = markup

            message = await self._bot.edit_message_text('№ *{}*\n{}\nЗаказчик: _{}_\nВыделено: {}%\nВведите значение:'
                                                        .format(self._cur_project.project_id,
                                                                self._cur_project.title,
                                                                self._cur_project.customer,
                                                                self._projects[project_id]),
                                                        self._employee.chat_id,
                                                        message_id=callback.message.message_id,
                                                        parse_mode='Markdown',
                                                        reply_markup=markup)
            self._last_msg = message['message_id']
            self.state = 'project_menu'

    @DialogView.message_handler('project_menu')
    async def project_message_handler(self, update: Update):
        text = update.message.text
        project_id = self._cur_project.project_id

        await self._bot.delete_message(self._employee.chat_id,
                                       self._last_msg)

        await self._bot.delete_message(self._employee.chat_id,
                                       update.message.message_id)

        try:
            value = int(text)

            if value < 0:
                return
            elif value > 100:
                value = 100
            self._total -= self._projects[project_id]

            if value + self._total > 100:
                value = 100 - self._total

            self._projects[project_id] = value
            self._total += value
        except ValueError:
            return
        finally:
            message = await self._bot.send_message(self._employee.chat_id,
                                                   '№ *{}*\n{}\nЗаказчик: _{}_\nВыделено: {}%\nВведите значение:'
                                                   .format(self._cur_project.project_id,
                                                           self._cur_project.title,
                                                           self._cur_project.customer,
                                                           self._projects[project_id]),
                                                   parse_mode='Markdown',
                                                   reply_markup=self._project_markup)
            self._last_msg = message['message_id']

    @DialogView.callback_handler('project_menu')
    async def project_callback_handler(self, update: Update):
        callback = update.callback_query
        data = callback.data

        await self._bot.answer_callback_query(callback.id)

        if data == 'project_back':
            self.state = STATUS_START
            project_id = self._cur_project.project_id
            self._cur_project = None
            self._project_markup = None

            if self._projects[project_id] == 0:
                del (self._projects[project_id])

            markup = await self._projects_markup()
            message = await self._bot.edit_message_text(self._main_text.format(self._employee.first_name, self._comment, self._total),
                                                        self._employee.chat_id,
                                                        message_id=callback.message.message_id,
                                                        parse_mode='Markdown',
                                                        reply_markup=markup)

            self._last_msg = message['message_id']
        elif data == 'project_clear':
            project_id = self._cur_project.project_id

            self._total -= self._projects[project_id]
            self._projects[project_id] = 0

            try:
                message = await self._bot.edit_message_text('№ *{}*\n{}\nЗаказчик: _{}_\nВыделено: {}%\nВведите значение:'
                                                            .format(self._cur_project.project_id,
                                                                    self._cur_project.title,
                                                                    self._cur_project.customer,
                                                                    self._projects[project_id]),
                                                            self._employee.chat_id,
                                                            message_id=callback.message.message_id,
                                                            parse_mode='Markdown',
                                                            reply_markup=self._project_markup)

                self._last_msg = message['message_id']
            except ApiException:
                pass
