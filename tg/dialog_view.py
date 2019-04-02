from . import BotAPI
from .api_types import *
from typing import *

STATUS_START = 'start'
STATUS_BACK = 'back'


class RegisterHandlersMeta(type):
    def __new__(mcs, name, bases, dct):
        attrs = [attr for attr in dct if not attr.startswith('__')]
        dct['_callback_handlers'] = {}
        dct['_message_handlers'] = {}

        for attr in attrs:
            if hasattr(dct[attr], '_callback_handler'):
                states = getattr(dct[attr], '_callback_handler')
                for state in states:
                    dct['_callback_handlers'][state] = dct[attr]
            if hasattr(dct[attr], '_message_handler'):
                states = getattr(dct[attr], '_message_handler')
                for state in states:
                    dct['_message_handlers'][state] = dct[attr]

        return type.__new__(mcs, name, bases, dct)

    @staticmethod
    def callback_handler(state: str):
        """
        Decorator to register callback handler for need state
        :param state: state to call handler
        :return: got function without changes
        """

        def decorator(handler: Callable[[DialogView, Update], Awaitable[bool]]):
            if not hasattr(handler, '_callback_handler'):
                setattr(handler, '_callback_handler', [])

            getattr(handler, '_callback_handler').append(state)
            return handler

        return decorator

    @staticmethod
    def message_handler(state: str):
        """
        Decorator to register message handler for need state
        :param state: state to call handler
        :return: got function without changes
        """

        def decorator(handler: Callable[[Any, str], Awaitable[bool]]):
            if not hasattr(handler, '_message_handler'):
                setattr(handler, '_message_handler', [])

            getattr(handler, '_message_handler').append(state)
            return handler

        return decorator


class DialogView(metaclass=RegisterHandlersMeta):
    callback_handler = RegisterHandlersMeta.callback_handler
    message_handler = RegisterHandlersMeta.message_handler

    def __init__(self, bot_api: BotAPI):
        self._bot = bot_api
        self.state = STATUS_START
        self.completed = False

    async def start_view(self, update: Update):
        """
        Handler when view just created
        :param update: Telegram update
        :return:
        """
        raise NotImplemented

    def _result_to_dict(self) -> Dict[str, Any]:
        """
        Convert dialog view result to dict
        :return: dict with dialog view result
        """
        raise NotImplemented

    def get_result(self) -> Union[Dict[str, Any], None]:
        """
        Return process view result if exist
        :return dict with data or None if not completed
        """
        if not self.completed:
            return None
        return self._result_to_dict()

    async def process(self, update: Update):
        """
        Dispatch update process to handler handler corresponding to the state and type of update
        :param update: Update to handle
        :return: dialog view is completed or not
        """
        handlers, data = None, None

        if update.callback_query is not None:
            handlers = self._callback_handlers
        elif update.message is not None:
            handlers = self._message_handlers

        try:
            handler = handlers[self.state]
        except KeyError:
            pass
        else:
            await handler(self, update)
        return self.completed
