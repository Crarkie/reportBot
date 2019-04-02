from . import *
from aiohttp import ClientSession
import ujson as json
__all__ = ['BotAPI']

API_URL = 'https://api.telegram.org/bot{self}/{method_name}'
FILE_URL = 'https://api.telegram.org/file/bot{self}/{file_id}'


class BotAPI:
    def __init__(self, token: str, session: ClientSession):
        self._self = self
        self._token = token
        self._session = session

    async def _make_request(self, method_name, params=None, files=None):
        request_url = API_URL.format(self=self._token, method_name=method_name)

        result = await self._session.post(request_url, params=params, data=files)
        return (await self._check_result(method_name, result))['result']

    @classmethod
    def _convert_markup(cls, markup):
        if isinstance(markup, JsonSerializable):
            return markup.to_json()
        return markup

    @classmethod
    def _convert_input_media(cls, media):
        if isinstance(media, InputMedia):
            return media.convert_input_media()
        return None, None

    @classmethod
    def _convert_list_json_serializable(cls, results):
        ret = ''
        for r in results:
            if isinstance(r, JsonSerializable):
                ret = ret + r.to_json() + ','
        if len(ret) > 0:
            ret = ret[:-1]
        return '[' + ret + ']'

    @classmethod
    def _convert_input_media_array(cls, array):
        media = []
        files = {}
        for input_media in array:
            if isinstance(input_media, InputMedia):
                media_dict = input_media.to_dic()
                if media_dict['media'].startswith('attach://'):
                    key = media_dict['media'].replace('attach://', '')
                    files[key] = input_media.media
                media.append(media_dict)
        return json.dumps(media), files

    @staticmethod
    async def _check_result(method_name, result):
        if result.status != 200:
            msg = 'The server returned HTTP {0} {1}. Response body:\n[{2}]' \
                .format(result.status, result.reason, await result.text())
            raise ApiException(msg, method_name, result)

        try:
            result_json = await result.json(loads=json.loads)
        except ValueError:
            msg = 'The server returned an invalid JSON response. Response body:\n[{0}]' \
                .format(await result.text())
            raise ApiException(msg, method_name, result)

        if not result_json['ok']:
            msg = 'Error code: {0} Description: {1}' \
                .format(result_json['error_code'], result_json['description'])
            raise ApiException(msg, method_name, result)
        return result_json

    async def get_me(self):
        return await self._make_request('getMe')

    async def get_file(self, file_id):
        return await self._make_request('getFile', params={'file_id': file_id})

    async def get_file_url(self, file_id):
        return FILE_URL.format(self=self._self, file_id=(await self.get_file(file_id)).file_path)

    async def download_file(self, file_path):
        url = FILE_URL.format(self=self._self, file_id=file_path)
        result = await self._session.get(url)
        if result.status != 200:
            msg = 'The server returned HTTP {0} {1}. Response body:\n[{2}]' \
                .format(result.status, result.reason, await result.text())
            raise ApiException(msg, 'Download file', result)
        return result.content

    async def send_message(self, chat_id, text,
                           disable_web_page_preview=None,
                           reply_to_message_id=None,
                           reply_markup=None,
                           parse_mode=None,
                           disable_notification=None):
        payload = {'chat_id': str(chat_id), 'text': text}
        if disable_web_page_preview:
            payload['disable_web_page_preview'] = disable_notification
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        if parse_mode:
            payload['parse_mode'] = parse_mode
        if disable_notification:
            payload['disable_notification'] = disable_notification
        return await self._make_request('sendMessage', params=payload)

    async def set_webhook(self, url=None,
                          certificate=None,
                          max_connections=None,
                          allowed_updates=None):
        payload = {
            'url': url if url else ''
        }
        files = None
        if certificate:
            files = {'certificate': certificate}
        if max_connections:
            payload['max_connections'] = max_connections
        if allowed_updates:
            payload['allowed_updates'] = json.dumps(allowed_updates)
        return await self._make_request('setWebhook', params=payload, files=files)

    async def delete_webhook(self):
        return await self._make_request('deleteWebhook')

    async def get_webhook_info(self):
        return await self._make_request('getWebhookInfo')

    async def get_updates(self, offset=None, limit=None, timeout=None, allowed_updates=None):
        payload = {}
        if offset:
            payload['offset'] = offset
        if limit:
            payload['limit'] = limit
        if timeout:
            payload['timeout'] = timeout
        if allowed_updates:
            payload['allowed_updates'] = json.dumps(allowed_updates)
        return await self._make_request('getUpdates', params=payload)

    async def get_user_profile_photos(self, user_id, offset=None, limit=None):
        payload = {'user_id': user_id}
        if offset:
            payload['offset'] = offset
        if limit:
            payload['limit'] = limit
        return await self._make_request('getUserProfilePhotos', params=payload)

    async def get_chat(self, chat_id):
        payload = {'chat_id': chat_id}
        return await self._make_request('getChat', params=payload)

    async def leave_chat(self, chat_id):
        payload = {'chat_id': chat_id}
        return await self._make_request('leaveChat', params=payload)

    async def get_chat_administrators(self, chat_id):
        payload = {'chat_id': chat_id}
        return await self._make_request('getChatAdministrators', params=payload)

    async def get_chat_members_count(self, chat_id):
        payload = {'chat_id': chat_id}
        return await self._make_request('getChatMembersCount', params=payload)

    async def set_chat_sticker_set(self, chat_id, sticker_set_name):
        payload = {'chat_id': chat_id, 'sticker_set_name': sticker_set_name}
        return await self._make_request('setChatStickerSet', params=payload)

    async def delete_chat_sticker_set(self, chat_id):
        payload = {'chat_id': chat_id}
        return await self._make_request('deleteChatStickerSet', params=payload)

    async def get_chat_member(self, chat_id, user_id):
        payload = {'chat_id': chat_id, 'user_id': user_id}
        return await self._make_request('getChatMember', params=payload)

    async def forward_message(self, chat_id, from_chat_id, message_id, disable_notification=None):
        payload = {'chat_id': chat_id, 'from_chat_id': from_chat_id, 'message_id': message_id}
        if disable_notification:
            payload['disable_notification'] = disable_notification
        return await self._make_request('forwardMessage', params=payload)

    async def send_photo(self, chat_id, photo, caption=None, reply_to_message_id=None,
                         reply_markup=None, parse_mode=None, disable_notification=None):
        payload = {'chat_id': chat_id}
        files = None
        if photo is not str:
            files = {'photo': photo}
        else:
            payload['photo'] = photo
        if caption:
            payload['caption'] = caption
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = reply_markup
        if parse_mode:
            payload['parse_mode'] = parse_mode
        if disable_notification:
            payload['disable_notification'] = disable_notification
        return await self._make_request('sendPhoto', params=payload, files=files)

    async def send_media_group(self, chat_id, media, disable_notificaton=None, reply_to_message_id=None):
        media_json, files = self._convert_input_media_array(media)
        payload = {'chat_id': chat_id, 'media': media_json}
        if disable_notificaton:
            payload['disable_notification'] = disable_notificaton
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        return await self._make_request('sendMediaGroup', params=payload, files=files)

    async def send_location(self, chat_id, latitude, longitude, live_period=None,
                            reply_to_message_id=None, reply_markup=None,
                            disable_notification=None):
        payload = {'chat_id': chat_id, 'latitude': latitude, 'longitude': longitude}
        if live_period:
            payload['live_period'] = live_period
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        if disable_notification:
            payload['disable_notification'] = disable_notification
        return await self._make_request('sendLocation', params=payload)

    async def edit_message_live_location(self, latitude, longitude, chat_id=None, message_id=None,
                                         inline_message_id=None, reply_markup=None):
        method_url = r'editMessageLiveLocation'
        payload = {'latitude': latitude, 'longitude': longitude}
        if chat_id:
            payload['chat_id'] = chat_id
        if message_id:
            payload['message_id'] = message_id
        if inline_message_id:
            payload['inline_message_id'] = inline_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        return await self._make_request(method_url, params=payload)

    async def stop_message_live_location(self, chat_id=None, message_id=None,
                                         inline_message_id=None, reply_markup=None):
        method_url = r'stopMessageLiveLocation'
        payload = {}
        if chat_id:
            payload['chat_id'] = chat_id
        if message_id:
            payload['message_id'] = message_id
        if inline_message_id:
            payload['inline_message_id'] = inline_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        return await self._make_request(method_url, params=payload)

    async def send_venue(self, chat_id, latitude, longitude, title, address, foursquare_id=None,
                         disable_notification=None, reply_to_message_id=None, reply_markup=None):
        method_url = r'sendVenue'
        payload = {'chat_id': chat_id, 'latitude': latitude, 'longitude': longitude, 'title': title, 'address': address}
        if foursquare_id:
            payload['foursquare_id'] = foursquare_id
        if disable_notification:
            payload['disable_notification'] = disable_notification
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        return await self._make_request(method_url, params=payload)

    async def send_contact(self, chat_id, phone_number, first_name, last_name=None, disable_notification=None,
                           reply_to_message_id=None, reply_markup=None):
        method_url = r'sendContact'
        payload = {'chat_id': chat_id, 'phone_number': phone_number, 'first_name': first_name}
        if last_name:
            payload['last_name'] = last_name
        if disable_notification:
            payload['disable_notification'] = disable_notification
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        return await self._make_request(method_url, params=payload)

    async def send_chat_action(self, chat_id, action):
        method_url = r'sendChatAction'
        payload = {'chat_id': chat_id, 'action': action}
        return await self._make_request(method_url, params=payload)

    async def send_video(self, chat_id, data, duration=None, caption=None, reply_to_message_id=None, reply_markup=None,
                         parse_mode=None, supports_streaming=None, disable_notification=None, timeout=None):
        method_url = r'sendVideo'
        payload = {'chat_id': chat_id}
        files = None
        if data is not str:
            files = {'video': data}
        else:
            payload['video'] = data
        if duration:
            payload['duration'] = duration
        if caption:
            payload['caption'] = caption
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        if parse_mode:
            payload['parse_mode'] = parse_mode
        if supports_streaming:
            payload['supports_streaming'] = supports_streaming
        if disable_notification:
            payload['disable_notification'] = disable_notification
        if timeout:
            payload['connect-timeout'] = timeout
        return await self._make_request(method_url, params=payload, files=files)

    async def send_voice(self, chat_id, voice, caption=None, duration=None, reply_to_message_id=None, reply_markup=None,
                         parse_mode=None, disable_notification=None, timeout=None):
        method_url = r'sendVoice'
        payload = {'chat_id': chat_id}
        files = None
        if voice is not str:
            files = {'voice': voice}
        else:
            payload['voice'] = voice
        if caption:
            payload['caption'] = caption
        if duration:
            payload['duration'] = duration
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        if parse_mode:
            payload['parse_mode'] = parse_mode
        if disable_notification:
            payload['disable_notification'] = disable_notification
        if timeout:
            payload['connect-timeout'] = timeout
        return await self._make_request(method_url, params=payload, files=files)

    async def send_video_note(self, chat_id, data, duration=None, length=None, reply_to_message_id=None,
                              reply_markup=None, disable_notification=None, timeout=None):
        method_url = r'sendVideoNote'
        payload = {'chat_id': chat_id}
        files = None
        if data is not str:
            files = {'video_note': data}
        else:
            payload['video_note'] = data
        if duration:
            payload['duration'] = duration
        if length:
            payload['length'] = length
        else:
            payload['length'] = 639  # seems like it is MAX length size
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        if disable_notification:
            payload['disable_notification'] = disable_notification
        if timeout:
            payload['connect-timeout'] = timeout
        return await self._make_request(method_url, params=payload, files=files)

    async def send_audio(self, chat_id, audio, caption=None, duration=None, performer=None, title=None,
                         reply_to_message_id=None,
                         reply_markup=None, parse_mode=None, disable_notification=None, timeout=None):
        method_url = r'sendAudio'
        payload = {'chat_id': chat_id}
        files = None
        if audio is not str:
            files = {'audio': audio}
        else:
            payload['audio'] = audio
        if caption:
            payload['caption'] = caption
        if duration:
            payload['duration'] = duration
        if performer:
            payload['performer'] = performer
        if title:
            payload['title'] = title
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        if parse_mode:
            payload['parse_mode'] = parse_mode
        if disable_notification:
            payload['disable_notification'] = disable_notification
        if timeout:
            payload['connect-timeout'] = timeout
        return await self._make_request(method_url, params=payload, files=files)

    async def send_data(self, chat_id, data, data_type, reply_to_message_id=None, reply_markup=None, parse_mode=None,
                        disable_notification=None, timeout=None, caption=None):
        method_url = self.get_method_by_type(data_type)
        payload = {'chat_id': chat_id}
        files = None
        if data is not str:
            files = {data_type: data}
        else:
            payload[data_type] = data
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        if parse_mode and data_type == 'document':
            payload['parse_mode'] = parse_mode
        if disable_notification:
            payload['disable_notification'] = disable_notification
        if timeout:
            payload['connect-timeout'] = timeout
        if caption:
            payload['caption'] = caption
        return await self._make_request(method_url, params=payload, files=files)

    @classmethod
    def get_method_by_type(cls, data_type):
        if data_type == 'document':
            return r'sendDocument'
        if data_type == 'sticker':
            return r'sendSticker'

    async def kick_chat_member(self, chat_id, user_id, until_date=None):
        method_url = 'kickChatMember'
        payload = {'chat_id': chat_id, 'user_id': user_id}
        if until_date:
            payload['until_date'] = until_date
        return await self._make_request(method_url, params=payload)

    async def unban_chat_member(self, chat_id, user_id):
        method_url = 'unbanChatMember'
        payload = {'chat_id': chat_id, 'user_id': user_id}
        return await self._make_request(method_url, params=payload)

    async def restrict_chat_member(self, chat_id, user_id, until_date=None, can_send_messages=None,
                                   can_send_media_messages=None, can_send_other_messages=None,
                                   can_add_web_page_previews=None):
        method_url = 'restrictChatMember'
        payload = {'chat_id': chat_id, 'user_id': user_id}
        if until_date:
            payload['until_date'] = until_date
        if can_send_messages:
            payload['can_send_messages'] = can_send_messages
        if can_send_media_messages:
            payload['can_send_media_messages'] = can_send_media_messages
        if can_send_other_messages:
            payload['can_send_other_messages'] = can_send_other_messages
        if can_add_web_page_previews:
            payload['can_add_web_page_previews'] = can_add_web_page_previews

        return await self._make_request(method_url, params=payload)

    async def promote_chat_member(self, chat_id, user_id, can_change_info=None, can_post_messages=None,
                                  can_edit_messages=None, can_delete_messages=None, can_invite_users=None,
                                  can_restrict_members=None, can_pin_messages=None, can_promote_members=None):
        method_url = 'promoteChatMember'
        payload = {'chat_id': chat_id, 'user_id': user_id}
        if can_change_info:
            payload['can_change_info'] = can_change_info
        if can_post_messages:
            payload['can_post_messages'] = can_post_messages
        if can_edit_messages:
            payload['can_edit_messages'] = can_edit_messages
        if can_delete_messages:
            payload['can_delete_messages'] = can_delete_messages
        if can_invite_users:
            payload['can_invite_users'] = can_invite_users
        if can_restrict_members:
            payload['can_restrict_members'] = can_restrict_members
        if can_pin_messages:
            payload['can_pin_messages'] = can_pin_messages
        if can_promote_members:
            payload['can_promote_members'] = can_promote_members
        return await self._make_request(method_url, params=payload)

    async def export_chat_invite_link(self, chat_id):
        method_url = 'exportChatInviteLink'
        payload = {'chat_id': chat_id}
        return await self._make_request(method_url, params=payload)

    async def set_chat_photo(self, chat_id, photo):
        method_url = 'setChatPhoto'
        payload = {'chat_id': chat_id}
        files = None
        if photo is not str:
            files = {'photo': photo}
        else:
            payload['photo'] = photo
        return await self._make_request(method_url, params=payload, files=files)

    async def delete_chat_photo(self, chat_id):
        method_url = 'deleteChatPhoto'
        payload = {'chat_id': chat_id}
        return await self._make_request(method_url, params=payload)

    async def set_chat_title(self, chat_id, title):
        method_url = 'setChatTitle'
        payload = {'chat_id': chat_id, 'title': title}
        return await self._make_request(method_url, params=payload)

    async def set_chat_description(self, chat_id, description):
        method_url = 'setChatDescription'
        payload = {'chat_id': chat_id, 'description': description}
        return await self._make_request(method_url, params=payload)

    async def pin_chat_message(self, chat_id, message_id, disable_notification=False):
        method_url = 'pinChatMessage'
        payload = {'chat_id': chat_id, 'message_id': message_id, 'disable_notification': disable_notification}
        return await self._make_request(method_url, params=payload)

    async def unpin_chat_message(self, chat_id):
        method_url = 'unpinChatMessage'
        payload = {'chat_id': chat_id}
        return await self._make_request(method_url, params=payload)

    async def edit_message_text(self, text, chat_id, message_id=None, inline_message_id=None, parse_mode=None,
                                disable_web_page_preview=None, reply_markup=None):
        method_url = r'editMessageText'
        payload = {'text': text}
        if chat_id:
            payload['chat_id'] = chat_id
        if message_id:
            payload['message_id'] = message_id
        if inline_message_id:
            payload['inline_message_id'] = inline_message_id
        if parse_mode:
            payload['parse_mode'] = parse_mode
        if disable_web_page_preview:
            payload['disable_web_page_preview'] = disable_web_page_preview
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        return await self._make_request(method_url, params=payload)

    async def edit_message_caption(self, caption, chat_id=None, message_id=None, inline_message_id=None,
                                   parse_mode=None, reply_markup=None):
        method_url = r'editMessageCaption'
        payload = {'caption': caption}
        if chat_id:
            payload['chat_id'] = chat_id
        if message_id:
            payload['message_id'] = message_id
        if inline_message_id:
            payload['inline_message_id'] = inline_message_id
        if parse_mode:
            payload['parse_mode'] = parse_mode
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        return await self._make_request(method_url, params=payload)

    async def edit_message_media(self, media, chat_id=None, message_id=None, inline_message_id=None, reply_markup=None):
        method_url = r'editMessageMedia'
        media_json, file = self._convert_input_media(media)
        payload = {'media': media_json}
        if chat_id:
            payload['chat_id'] = chat_id
        if message_id:
            payload['message_id'] = message_id
        if inline_message_id:
            payload['inline_message_id'] = inline_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        return await self._make_request(method_url, params=payload, files=file if file else 'get')

    async def edit_message_reply_markup(self, chat_id=None, message_id=None, inline_message_id=None, reply_markup=None):
        method_url = r'editMessageReplyMarkup'
        payload = {}
        if chat_id:
            payload['chat_id'] = chat_id
        if message_id:
            payload['message_id'] = message_id
        if inline_message_id:
            payload['inline_message_id'] = inline_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        return await self._make_request(method_url, params=payload)

    async def delete_message(self, chat_id, message_id):
        method_url = r'deleteMessage'
        payload = {'chat_id': chat_id, 'message_id': message_id}
        return await self._make_request(method_url, params=payload)

    async def send_game(self, chat_id, game_short_name, disable_notification=None, reply_to_message_id=None,
                        reply_markup=None):
        method_url = r'sendGame'
        payload = {'chat_id': chat_id, 'game_short_name': game_short_name}
        if disable_notification:
            payload['disable_notification'] = disable_notification
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        return await self._make_request(method_url, params=payload)

    async def set_game_score(self, user_id, score, force=None, disable_edit_message=None, chat_id=None, message_id=None,
                             inline_message_id=None):
        method_url = r'setGameScore'
        payload = {'user_id': user_id, 'score': score}
        if force:
            payload['force'] = force
        if chat_id:
            payload['chat_id'] = chat_id
        if message_id:
            payload['message_id'] = message_id
        if inline_message_id:
            payload['inline_message_id'] = inline_message_id
        if disable_edit_message:
            payload['disable_edit_message'] = disable_edit_message
        return await self._make_request(method_url, params=payload)

    async def get_game_high_scores(self, user_id, chat_id=None, message_id=None, inline_message_id=None):
        method_url = r'getGameHighScores'
        payload = {'user_id': user_id}
        if chat_id:
            payload['chat_id'] = chat_id
        if message_id:
            payload['message_id'] = message_id
        if inline_message_id:
            payload['inline_message_id'] = inline_message_id
        return await self._make_request(method_url, params=payload)

    async def send_invoice(self, chat_id, title, description, invoice_payload, provider_self, currency, prices,
                           start_parameter, photo_url=None, photo_size=None, photo_width=None, photo_height=None,
                           need_name=None, need_phone_number=None, need_email=None, need_shipping_address=None,
                           is_flexible=None,
                           disable_notification=None, reply_to_message_id=None, reply_markup=None, provider_data=None):
        method_url = r'sendInvoice'
        payload = {'chat_id': chat_id, 'title': title, 'description': description, 'payload': invoice_payload,
                   'provider_self': provider_self, 'start_parameter': start_parameter, 'currency': currency,
                   'prices': self._convert_list_json_serializable(prices)}
        if photo_url:
            payload['photo_url'] = photo_url
        if photo_size:
            payload['photo_size'] = photo_size
        if photo_width:
            payload['photo_width'] = photo_width
        if photo_height:
            payload['photo_height'] = photo_height
        if need_name:
            payload['need_name'] = need_name
        if need_phone_number:
            payload['need_phone_number'] = need_phone_number
        if need_email:
            payload['need_email'] = need_email
        if need_shipping_address:
            payload['need_shipping_address'] = need_shipping_address
        if is_flexible:
            payload['is_flexible'] = is_flexible
        if disable_notification:
            payload['disable_notification'] = disable_notification
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id
        if reply_markup:
            payload['reply_markup'] = self._convert_markup(reply_markup)
        if provider_data:
            payload['provider_data'] = provider_data
        return await self._make_request(method_url, params=payload)

    async def answer_shipping_query(self, shipping_query_id, ok, shipping_options=None, error_message=None):
        method_url = 'answerShippingQuery'
        payload = {'shipping_query_id': shipping_query_id, 'ok': ok}
        if shipping_options:
            payload['shipping_options'] = self._convert_list_json_serializable(shipping_options)
        if error_message:
            payload['error_message'] = error_message
        return await self._make_request(method_url, params=payload)

    async def answer_pre_checkout_query(self, pre_checkout_query_id, ok, error_message=None):
        method_url = 'answerPreCheckoutQuery'
        payload = {'pre_checkout_query_id': pre_checkout_query_id, 'ok': ok}
        if error_message:
            payload['error_message'] = error_message
        return await self._make_request(method_url, params=payload)

    async def answer_callback_query(self, callback_query_id, text=None, show_alert=None, url=None, cache_time=None):
        method_url = 'answerCallbackQuery'
        payload = {'callback_query_id': callback_query_id}
        if text:
            payload['text'] = text
        if show_alert:
            payload['show_alert'] = show_alert
        if url:
            payload['url'] = url
        if cache_time is not None:
            payload['cache_time'] = cache_time
        return await self._make_request(method_url, params=payload)

    async def answer_inline_query(self, inline_query_id, results, cache_time=None, is_personal=None, next_offset=None,
                                  switch_pm_text=None, switch_pm_parameter=None):
        method_url = 'answerInlineQuery'
        payload = {'inline_query_id': inline_query_id, 'results': self._convert_list_json_serializable(results)}
        if cache_time is not None:
            payload['cache_time'] = cache_time
        if is_personal:
            payload['is_personal'] = is_personal
        if next_offset is not None:
            payload['next_offset'] = next_offset
        if switch_pm_text:
            payload['switch_pm_text'] = switch_pm_text
        if switch_pm_parameter:
            payload['switch_pm_parameter'] = switch_pm_parameter
        return await self._make_request(method_url, params=payload)

    async def get_sticker_set(self, name):
        method_url = 'getStickerSet'
        return await self._make_request(method_url, params={'name': name})

    async def upload_sticker_file(self, user_id, png_sticker):
        method_url = 'uploadStickerFile'
        payload = {'user_id': user_id}
        files = {'png_sticker': png_sticker}
        return await self._make_request(method_url, params=payload, files=files)

    async def create_new_sticker_set(self, user_id, name, title, png_sticker, emojis, contains_masks=None,
                                     mask_position=None):
        method_url = 'createNewStickerSet'
        payload = {'user_id': user_id, 'name': name, 'title': title, 'emojis': emojis}
        files = None
        if png_sticker is not str:
            files = {'png_sticker': png_sticker}
        else:
            payload['png_sticker'] = png_sticker
        if contains_masks:
            payload['contains_masks'] = contains_masks
        if mask_position:
            payload['mask_position'] = mask_position.to_json()
        return await self._make_request(method_url, params=payload, files=files)

    async def add_sticker_to_set(self, user_id, name, png_sticker, emojis, mask_position):
        method_url = 'addStickerToSet'
        payload = {'user_id': user_id, 'name': name, 'emojis': emojis}
        files = None
        if png_sticker is not str:
            files = {'png_sticker': png_sticker}
        else:
            payload['png_sticker'] = png_sticker
        if mask_position:
            payload['mask_position'] = mask_position.to_json()
        return await self._make_request(method_url, params=payload, files=files)

    async def set_sticker_position_in_set(self, sticker, position):
        method_url = 'setStickerPositionInSet'
        payload = {'sticker': sticker, 'position': position}
        return await self._make_request(method_url, params=payload)

    async def delete_sticker_from_set(self, sticker):
        method_url = 'deleteStickerFromSet'
        payload = {'sticker': sticker}
        return await self._make_request(method_url, params=payload)


class ApiException(Exception):
    def __init__(self, msg, function_name, result):
        super(ApiException, self).__init__("A request to the Telegram API was unsuccessful. {0}".format(msg))
        self.function_name = function_name
        self.result = result
