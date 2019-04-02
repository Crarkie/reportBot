import random
import base58
import calendar
import phonenumbers

from tg import *
from common.models import *
from datetime import datetime, timedelta
from time import time


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
               InlineKeyboardButton('⟲Назад', callback_data=data_back),
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
    share_number_text = '📱Предоставить номер'

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
        return {}

    async def start_view(self, update: Update):
        callback_query = update.callback_query
        chat_id = callback_query.from_user.id

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
        await self._bot.edit_message_text(text,
                                          chat_id,
                                          reply_markup=markup,
                                          message_id=callback_query.message.message_id)

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


class StartView(DialogView):
    async def start_view(self, update: Update):
        chat_id = update.message.from_user.id

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton('Продолжить', callback_data='continue'))

        await self._bot.send_message(chat_id, 'Нажмите кнопку, чтобы продолжить',
                                     reply_markup=markup)
        self.state = STATUS_START

    @DialogView.callback_handler(state=STATUS_START)
    async def start_handler(self, update: Update):
        callback_query = update.callback_query

        if callback_query.data == 'continue':
            await self._bot.answer_callback_query(callback_query.id)
            self.completed = True


class AuthenticationView(DialogView):
    __fio_steps = ['employee_family', 'employee_name', 'employee_middle']
    __fio_data = ['family', 'name', 'middle']
    __fio_text = ['', 'Отлично! Теперь введите ваше имя:', 'Отчество:']

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
                formatted_phone = phonenumbers.parse('+' + str(self._employee.phone_number))
                formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)
                await self._bot.send_message(user_id,
                                             'Вы были авторизованы как руководитель:\n'
                                             'ФИО: _{} {} {}_\nНомер тел.: _{}_'.format(self._employee.last_name,
                                                                                        self._employee.first_name,
                                                                                        self._employee.middle_name,
                                                                                        formatted_phone),
                                             parse_mode='Markdown')
                self.completed = True
                await self._employee.update(active=True, chat_id=user_id).apply()
                await self._invite.delete()
            elif self._employee.employee_role == 'subordinate':
                self._leader: Employee = await Employee.query.where(Employee.employee_id == self._employee.leader_id).gino.first()
                await self._bot.send_message(user_id,
                                             'Ваш руководитель:\n_{} {} {}_\n'
                                             'Для продолжения введите свою фамилию:'.format(self._leader.last_name,
                                                                                            self._leader.first_name,
                                                                                            self._leader.middle_name),
                                             parse_mode='Markdown')
                self.state = 'employee_family'

    @DialogView.message_handler('employee_middle')
    @DialogView.message_handler('employee_name')
    @DialogView.message_handler('employee_family')
    async def employee_fio_handler(self, update: Update):
        user_id = update.message.from_user.id
        text = update.message.text
        step_index = self.__fio_steps.index(self.state)

        self._data[self.__fio_data[step_index]] = text

        # If not end FIO
        if self.state != 'employee_middle':
            await  self._bot.send_message(user_id,
                                          self.__fio_text[step_index + 1])
            self.state = self.__fio_steps[step_index + 1]
        else:
            self._phone_view: PhoneRequestView = PhoneRequestView(self._bot)
            await self._phone_view.start_view(update)
            self.state = 'employee_phone'

    @DialogView.message_handler('employee_phone')
    async def employee_phone_handler(self, update: Update):
        user_id = update.message.from_user.id

        if await self._phone_view.process(update):
            self._data['phone'] = self._phone_view.get_result()['phone']

            await self._employee.update(first_name=self._data['name'],
                                        last_name=self._data['family'],
                                        middle_name=self._data['middle'],
                                        phone_number=int(self._data['phone']),
                                        active=True,
                                        chat_id=user_id).apply()
            await self._invite.delete()
            self.completed = True

            formatted_phone = phonenumbers.parse('+' + str(self._employee.phone_number))
            formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)
            await self._bot.send_message(self._leader.chat_id,
                                         'Был зарегистрирован новый сотрудник:\n'
                                         '{} {} {},\nНомер тел.: {}\nПригл.код: {}'.format(self._employee.last_name,
                                                                                           self._employee.first_name,
                                                                                           self._employee.middle_name,
                                                                                           formatted_phone,
                                                                                           self._invite.invite_code),
                                         )


class LeaderMainView(DialogView):
    create_invite_button = '➕Добавить сотрудника'

    def __init__(self, leader, bot_api: BotAPI):
        self._leader = leader
        self.markup = ReplyKeyboardMarkup(resize_keyboard=True)
        self.markup.add(KeyboardButton(self.create_invite_button))
        super(LeaderMainView, self).__init__(bot_api)

    async def start_view(self, update: Update):
        user_id = self._leader.chat_id

        await self._bot.send_message(user_id,
                                     'Выберите необходимый пункт меню',
                                     reply_markup=self.markup)

    async def _create_invite_action(self):
        new_employee = await Employee.create(leader_id=self._leader.employee_id, employee_role='subordinate')
        while True:
            random.seed(time())
            code = ''.join(random.sample(string.ascii_letters+ string.digits * 2, 10))
            if not await Invite.get(code):
                break

        invite = await Invite.create(invite_code=code, employee_id=new_employee.employee_id)
        await self._bot.send_message(self._leader.chat_id,
                                     'Пригласительный код для сотрудника\n(Автоматически истекает через 3 дня): ')
        await self._bot.send_message(self._leader.chat_id,
                                     '*{}*'.format(invite.invite_code),
                                     parse_mode='Markdown')

    @DialogView.message_handler(STATUS_START)
    async def menu_handler(self, update: Update):
        text = update.message.text

        if text == self.create_invite_button:
            await self._create_invite_action()


class SubordinateMainView(DialogView):
    leader_info_button = 'ℹ️Руководитель'
    reference_button = '🔰Справка'

    reference_text = '''
Каждый рабочий день в 19:30 Вам будет приходить оповещение
о необходимости заполнить отчет по проектам.\n
В случае отсутствия реакции, через 15 минут приходит повторное уведомление.\n
На заполнение отчета предоставляется 20 минут.\n
Если отчет не будет заполнен в течении этого времени,
либо не последует реакции в течении 15 минут после второго оповещения, 
то об этом будет доложено вашему руководителю.\n
После отправки отчета, руководитель должен подтвердить его, либо отправить на доработку.
        '''

    def __init__(self, employee, bot_api: BotAPI):
        self._employee = employee
        self.markup = ReplyKeyboardMarkup(resize_keyboard=True)
        self.markup.add(KeyboardButton(self.leader_info_button))

        super(SubordinateMainView, self).__init__(bot_api)

    async def start_view(self, update: Update):
        user_id = self._employee.chat_id

        await self._bot.send_message(user_id,
                                     self.reference_text,
                                     reply_markup=self.markup)

    async def _leader_info_action(self):
        leader = await Employee.query.where(Employee.employee_id == self._employee.leader_id).gino.first()

        formatted_phone = phonenumbers.parse('+' + str(leader.phone_number))
        formatted_phone = phonenumbers.format_number(formatted_phone, phonenumbers.PhoneNumberFormat.NATIONAL)

        await self._bot.send_message(self._employee.chat_id,
                                     "Ваш руководитель:\n{} {} {}\nТел.: {}".format(leader.last_name,
                                                                                    leader.first_name,
                                                                                    leader.middle_name,
                                                                                    formatted_phone))

    @DialogView.message_handler(STATUS_START)
    async def menu_handler(self, update: Update):
        text = update.message.text

        if text == self.leader_info_button:
            await self._leader_info_action()
        elif text == self.reference_button:
            await self._bot.send_message(self._employee.chat_id,
                                         self.reference_text)
