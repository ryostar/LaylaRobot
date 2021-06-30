import html
import re
from typing import Optional

import telegram
from LaylaRobot import TIGERS, WOLVES, dispatcher
from LaylaRobot.modules.disable import DisableAbleCommandHandler
from LaylaRobot.modules.helper_funcs.chat_status import (
    bot_admin,
    can_restrict,
    is_user_admin,
    user_admin,
    user_can_ban,
    user_admin_no_reply,
    can_delete,
)
from LaylaRobot.modules.helper_funcs.extraction import (
    extract_text,
    extract_user,
    extract_user_and_text,
)
from LaylaRobot.modules.helper_funcs.filters import CustomFilters
from LaylaRobot.modules.helper_funcs.misc import split_message
from LaylaRobot.modules.helper_funcs.string_handling import split_quotes
from LaylaRobot.modules.log_channel import loggable
from LaylaRobot.modules.sql import warns_sql as sql
from telegram import (
    CallbackQuery,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ParseMode,
    Update,
    User,
)
from telegram.error import BadRequest
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    DispatcherHandlerStop,
    Filters,
    MessageHandler,
    run_async,
)
from telegram.utils.helpers import mention_html
from LaylaRobot.modules.sql.approve_sql import is_approved

WARN_HANDLER_GROUP = 9
CURRENT_WARNING_FILTER_STRING = "<b>Bộ lọc cảnh báo hiện tại trong cuộc trò chuyện này:</b>\n"


# Not async
def warn(user: User,
         chat: Chat,
         reason: str,
         message: Message,
         warner: User = None) -> str:
    if is_user_admin(chat, user.id):
        # message.reply_text("Damn admins, They are too far to be One Punched!")
        return

    if user.id in TIGERS:
        if warner:
            message.reply_text("Hổ không thể được cảnh báo.")
        else:
            message.reply_text(
                "Tiger triggered an auto warn filter!\n I can't warn tigers but they should avoid abusing this."
            )
        return

    if user.id in WOLVES:
        if warner:
            message.reply_text("Wolf disasters are warn immune.")
        else:
            message.reply_text(
                "Wolf Disaster triggered an auto warn filter!\nI can't warn wolves but they should avoid abusing this."
            )
        return

    if warner:
        warner_tag = mention_html(warner.id, warner.first_name)
    else:
        warner_tag = "Bộ lọc cảnh báo tự động."

    limit, soft_warn = sql.get_warn_setting(chat.id)
    num_warns, reasons = sql.warn_user(user.id, chat.id, reason)
    if num_warns >= limit:
        sql.reset_warns(user.id, chat.id)
        if soft_warn:  # punch
            chat.unban_member(user.id)
            reply = (
                f"<code>❕</code><b>MỘT BÉ ĐÃ BỊ SÚT</b>\n"
                f"<code> </code><b>•  Bé:</b> {mention_html(user.id, user.first_name)}\n"
                f"<code> </code><b>•  Số lần vi phạm:</b> {limit}")

        else:  # ban
            chat.kick_member(user.id)
            reply = (
                f"<code>❕</code><b>MỘT BÉ BỊ ĐUỔI</b>\n"
                f"<code> </code><b>•  Bé:</b> {mention_html(user.id, user.first_name)}\n"
                f"<code> </code><b>•  Số lần vi phạm:</b> {limit}")

        for warn_reason in reasons:
            reply += f"\n - {html.escape(warn_reason)}"

        # message.bot.send_sticker(chat.id, BAN_STICKER)  # Saitama's sticker
        keyboard = None
        log_reason = (f"<b>{html.escape(chat.title)}:</b>\n"
                      f"#WARN_BAN\n"
                      f"<b>Admin:</b> {warner_tag}\n"
                      f"<b>Bé:</b> {mention_html(user.id, user.first_name)}\n"
                      f"<b>Lý do:</b> {reason}\n"
                      f"<b>Số lần vi phạm:</b> <code>{num_warns}/{limit}</code>")

    else:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔘 Xóa cảnh cáo", callback_data="rm_warn({})".format(user.id))
        ]])

        reply = (
            f"<code>❕</code><b>CHỊ CẢNH CÁO NÈ:</b>\n"
            f"<code> </code><b>•  Bé:</b> {mention_html(user.id, user.first_name)}\n"
            f"<code> </code><b>•  Số lần vi phạm:</b> {num_warns}/{limit}")
        if reason:
            reply += f"\n<code> </code><b>•  Lý do:</b> {html.escape(reason)}"

        log_reason = (f"<b>{html.escape(chat.title)}:</b>\n"
                      f"#WARN\n"
                      f"<b>Admin:</b> {warner_tag}\n"
                      f"<b>User:</b> {mention_html(user.id, user.first_name)}\n"
                      f"<b>Reason:</b> {reason}\n"
                      f"<b>Counts:</b> <code>{num_warns}/{limit}</code>")

    try:
        message.reply_text(
            reply, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except BadRequest as excp:
        if excp.message == "Không tìm thấy tin nhắn đã reply":
            # Do not reply
            message.reply_text(
                reply,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                quote=False)
        else:
            raise
    return log_reason



@run_async
@user_admin_no_reply
# @user_can_ban
@bot_admin
@loggable
def button(update: Update, context: CallbackContext) -> str:
    query: Optional[CallbackQuery] = update.callback_query
    user: Optional[User] = update.effective_user
    match = re.match(r"rm_warn\((.+?)\)", query.data)
    if match:
        user_id = match.group(1)
        chat: Optional[Chat] = update.effective_chat
        res = sql.remove_warn(user_id, chat.id)
        if res:
            update.effective_message.edit_text(
                "Cảnh báo đã bị xóa bởi {}.".format(mention_html(user.id, user.first_name)),
                parse_mode=ParseMode.HTML,
            )
            user_member = chat.get_member(user_id)
            return (
                f"<b>{html.escape(chat.title)}:</b>\n"
                f"#UNWARN\n"
                f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
                f"<b>User:</b> {mention_html(user_member.user.id, user_member.user.first_name)}"
            )
        else:
            update.effective_message.edit_text(
                "Người dùng không có cảnh báo.", parse_mode=ParseMode.HTML
            )

    return ""


@run_async
@user_admin
@can_restrict
# @user_can_ban
@loggable
def warn_user(update: Update, context: CallbackContext) -> str:
    args = context.args
    message: Optional[Message] = update.effective_message
    chat: Optional[Chat] = update.effective_chat
    warner: Optional[User] = update.effective_user

    user_id, reason = extract_user_and_text(message, args)
    if message.text.startswith("/d") and message.reply_to_message:
        message.reply_to_message.delete()
    if user_id:
        if (
            message.reply_to_message
            and message.reply_to_message.from_user.id == user_id
        ):
            return warn(
                message.reply_to_message.from_user,
                chat,
                reason,
                message.reply_to_message,
                warner,
            )
        else:
            return warn(chat.get_member(user_id).user, chat, reason, message, warner)
    else:
        message.reply_text("Đối với tôi, điều đó có vẻ như là một ID người dùng không hợp lệ.")
    return ""


@run_async
@user_admin
# @user_can_ban
@bot_admin
@loggable
def reset_warns(update: Update, context: CallbackContext) -> str:
    args = context.args
    message: Optional[Message] = update.effective_message
    chat: Optional[Chat] = update.effective_chat
    user: Optional[User] = update.effective_user

    user_id = extract_user(message, args)

    if user_id:
        sql.reset_warns(user_id, chat.id)
        message.reply_text("Cảnh cáo đã được đặt lại!")
        warned = chat.get_member(user_id).user
        return (
            f"<b>{html.escape(chat.title)}:</b>\n"
            f"#RESETWARNS\n"
            f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
            f"<b>User:</b> {mention_html(warned.id, warned.first_name)}"
        )
    else:
        message.reply_text("Không có người dùng đã được chỉ định!")
    return ""


@run_async
def warns(update: Update, context: CallbackContext):
    args = context.args
    message: Optional[Message] = update.effective_message
    chat: Optional[Chat] = update.effective_chat
    user_id = extract_user(message, args) or update.effective_user.id
    result = sql.get_warns(user_id, chat.id)

    if result and result[0] != 0:
        num_warns, reasons = result
        limit, soft_warn = sql.get_warn_setting(chat.id)

        if reasons:
            text = (
                f"Bé này có {num_warns}/{limit} cảnh cáo, vì những lý do sau:"
            )
            for reason in reasons:
                text += f"\n • {reason}"

            msgs = split_message(text)
            for msg in msgs:
                update.effective_message.reply_text(msg)
        else:
            update.effective_message.reply_text(
                f"Bé có {num_warns}/{limit} lần bị cảnh cáo, nhưng không có lý do cho bất kỳ lý do nào trong số chúng."
            )
    else:
        update.effective_message.reply_text("Bé này ngoan, 10 điểm không vi phạm!")


# Dispatcher handler stop - do not async
@user_admin
# @user_can_ban
def add_warn_filter(update: Update, context: CallbackContext):
    chat: Optional[Chat] = update.effective_chat
    msg: Optional[Message] = update.effective_message

    args = msg.text.split(
        None, 1
    )  # use python's maxsplit to separate Cmd, keyword, and reply_text

    if len(args) < 2:
        return

    extracted = split_quotes(args[1])

    if len(extracted) >= 2:
        # set trigger -> lower, so as to avoid adding duplicate filters with different cases
        keyword = extracted[0].lower()
        content = extracted[1]

    else:
        return

    # Note: perhaps handlers can be removed somehow using sql.get_chat_filters
    for handler in dispatcher.handlers.get(WARN_HANDLER_GROUP, []):
        if handler.filters == (keyword, chat.id):
            dispatcher.remove_handler(handler, WARN_HANDLER_GROUP)

    sql.add_warn_filter(chat.id, keyword, content)

    update.effective_message.reply_text(f"Đã thêm trình xử lý cảnh báo cho '{keyword}'!")
    raise DispatcherHandlerStop


@user_admin
# @user_can_ban
def remove_warn_filter(update: Update, context: CallbackContext):
    chat: Optional[Chat] = update.effective_chat
    msg: Optional[Message] = update.effective_message

    args = msg.text.split(
        None, 1
    )  # use python's maxsplit to separate Cmd, keyword, and reply_text

    if len(args) < 2:
        return

    extracted = split_quotes(args[1])

    if len(extracted) < 1:
        return

    to_remove = extracted[0]

    chat_filters = sql.get_chat_warn_triggers(chat.id)

    if not chat_filters:
        msg.reply_text("Không có bộ lọc cảnh báo nào đang hoạt động ở đây!")
        return

    for filt in chat_filters:
        if filt == to_remove:
            sql.remove_warn_filter(chat.id, to_remove)
            msg.reply_text("Được rồi, tôi sẽ ngừng cảnh báo mọi người về điều đó.")
            raise DispatcherHandlerStop

    msg.reply_text(
        "Đó không phải là bộ lọc cảnh báo hiện tại - chạy /warnlist cho tất cả các bộ lọc cảnh báo đang hoạt động."
    )


@run_async
def list_warn_filters(update: Update, context: CallbackContext):
    chat: Optional[Chat] = update.effective_chat
    all_handlers = sql.get_chat_warn_triggers(chat.id)

    if not all_handlers:
        update.effective_message.reply_text("Không có bộ lọc cảnh báo nào đang hoạt động ở đây!")
        return

    filter_list = CURRENT_WARNING_FILTER_STRING
    for keyword in all_handlers:
        entry = f" - {html.escape(keyword)}\n"
        if len(entry) + len(filter_list) > telegram.MAX_MESSAGE_LENGTH:
            update.effective_message.reply_text(filter_list, parse_mode=ParseMode.HTML)
            filter_list = entry
        else:
            filter_list += entry

    if filter_list != CURRENT_WARNING_FILTER_STRING:
        update.effective_message.reply_text(filter_list, parse_mode=ParseMode.HTML)


@run_async
@loggable
def reply_filter(update: Update, context: CallbackContext) -> str:
    chat: Optional[Chat] = update.effective_chat
    message: Optional[Message] = update.effective_message
    user: Optional[User] = update.effective_user

    if not user:  # Ignore channel
        return

    if user.id == 777000:
        return
    if is_approved(chat.id, user.id):
        return
    chat_warn_filters = sql.get_chat_warn_triggers(chat.id)
    to_match = extract_text(message)
    if not to_match:
        return ""

    for keyword in chat_warn_filters:
        pattern = r"( |^|[^\w])" + re.escape(keyword) + r"( |$|[^\w])"
        if re.search(pattern, to_match, flags=re.IGNORECASE):
            user: Optional[User] = update.effective_user
            warn_filter = sql.get_warn_filter(chat.id, keyword)
            return warn(user, chat, warn_filter.reply, message)
    return ""


@run_async
@user_admin
# @user_can_ban
@loggable
def set_warn_limit(update: Update, context: CallbackContext) -> str:
    args = context.args
    chat: Optional[Chat] = update.effective_chat
    user: Optional[User] = update.effective_user
    msg: Optional[Message] = update.effective_message

    if args:
        if args[0].isdigit():
            if int(args[0]) < 1:
                msg.reply_text("Giới hạn cảnh báo tối thiểu là 2!")
            else:
                sql.set_warn_limit(chat.id, int(args[0]))
                msg.reply_text("Đã cập nhật giới hạn cảnh báo thành {}".format(args[0]))
                return (
                    f"<b>{html.escape(chat.title)}:</b>\n"
                    f"#SET_WARN_LIMIT\n"
                    f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
                    f"Đặt giới hạn cảnh báo thành <code>{args[0]}</code>"
                )
        else:
            msg.reply_text("Cho tôi một con số như một lập luận!")
    else:
        limit, soft_warn = sql.get_warn_setting(chat.id)

        msg.reply_text("Giới hạn cảnh báo hiện tại là {}".format(limit))
    return ""


@run_async
@user_admin
# @user_can_ban
def set_warn_strength(update: Update, context: CallbackContext):
    args = context.args
    chat: Optional[Chat] = update.effective_chat
    user: Optional[User] = update.effective_user
    msg: Optional[Message] = update.effective_message

    if args:
        if args[0].lower() in ("on", "yes"):
            sql.set_warn_strength(chat.id, False)
            msg.reply_text("Quá nhiều cảnh báo bây giờ sẽ dẫn đến một Lệnh cấm!")
            return (
                f"<b>{html.escape(chat.title)}:</b>\n"
                f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
                f"Has enabled strong warns. Users will be seriously punched.(banned)"
            )

        elif args[0].lower() in ("off", "no"):
            sql.set_warn_strength(chat.id, True)
            msg.reply_text(
                "Quá nhiều cảnh báo bây giờ sẽ dẫn đến một cú sút bình thường! Người dùng sẽ có thể tham gia lại sau đó."
            )
            return (
                f"<b>{html.escape(chat.title)}:</b>\n"
                f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
                f"Đã vô hiệu hóa những lệnh cấm. Tôi sẽ sử dụng cú đấm bình thường vào người dùng."
            )

        else:
            msg.reply_text("Thêm on/yes/no/off! đi cha")
    else:
        limit, soft_warn = sql.get_warn_setting(chat.id)
        if soft_warn:
            msg.reply_text(
                "Cảnh báo hiện được đặt thành *sút* người dùng khi họ vượt quá giới hạn.",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            msg.reply_text(
                "Cảnh báo hiện được đặt thành *cấm* người dùng khi họ vượt quá giới hạn.",
                parse_mode=ParseMode.MARKDOWN,
            )
    return ""


def __stats__():
    return (
        f"• {sql.num_warns()} cảnh báo tổng thể, qua {sql.num_warn_chats()} nhóm.\n"
        f"• {sql.num_warn_filters()} bộ lọc cảnh báo, qua {sql.num_warn_filter_chats()} nhóm."
    )


def __import_data__(chat_id, data):
    for user_id, count in data.get("warns", {}).items():
        for x in range(int(count)):
            sql.warn_user(user_id, chat_id)


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    num_warn_filters = sql.num_warn_chat_filters(chat_id)
    limit, soft_warn = sql.get_warn_setting(chat_id)
    return (
        f"Cuộc trò chuyện này có `{num_warn_filters}` cảnh báo bộ lọc. "
        f"Nó cần `{limit}` cảnh báo trước khi người dùng nhận được *{'kicked' if soft_warn else 'banned'}*."
    )


__help__ = """
 ❍ /canhcao <userhandle>*:* lấy số ID của người dùng và lý do cảnh báo.
 ❍ /warnlist*:* danh sách tất cả các bộ lọc cảnh báo hiện tại
*Admins only:*
 ❍ /canhcao <userhandle>*:* cảnh báo người dùng. Sau 3 lần cảnh báo, người dùng sẽ bị cấm vào nhóm. Cũng có thể được sử dụng như một câu trả lời.
 ❍ /dwarn <userhandle>*:* cảnh báo người dùng và xóa tin nhắn. Sau 3 lần cảnh báo, người dùng sẽ bị cấm vào nhóm. Cũng có thể được sử dụng như một câu trả lời.
 ❍ /resetwarn <userhandle>*:* reset the warns for a user. Can also be used as a reply.
 ❍ /addwarn <keyword> <reply message>*:* set a warning filter on a certain keyword. If you want your keyword to \
be a sentence, encompass it with quotes, as such: `/addwarn "very angry" This is an angry user`.
 ❍ /nowarn <keyword>*:* stop a warning filter
 ❍ /warnlimit <num>*:* set the warning limit
 ❍ /strongwarn <on/yes/off/no>*:* If set to on, exceeding the warn limit will result in a ban. Else, will just punch.
"""

__mod_name__ = "Cảnh báo"

WARN_HANDLER = CommandHandler(["canhcao", "dwarn"], warn_user, filters=Filters.group)
RESET_WARN_HANDLER = CommandHandler(
    ["resetwarn", "resetwarns"], reset_warns, filters=Filters.group
)
CALLBACK_QUERY_HANDLER = CallbackQueryHandler(button, pattern=r"rm_warn")
MYWARNS_HANDLER = DisableAbleCommandHandler("warns", warns, filters=Filters.group)
ADD_WARN_HANDLER = CommandHandler("addwarn", add_warn_filter, filters=Filters.group)
RM_WARN_HANDLER = CommandHandler(
    ["nowarn", "stopwarn"], remove_warn_filter, filters=Filters.group
)
LIST_WARN_HANDLER = DisableAbleCommandHandler(
    ["warnlist", "warnfilters"], list_warn_filters, filters=Filters.group, admin_ok=True
)
WARN_FILTER_HANDLER = MessageHandler(
    CustomFilters.has_text & Filters.group, reply_filter
)
WARN_LIMIT_HANDLER = CommandHandler("warnlimit", set_warn_limit, filters=Filters.group)
WARN_STRENGTH_HANDLER = CommandHandler(
    "strongwarn", set_warn_strength, filters=Filters.group
)

dispatcher.add_handler(WARN_HANDLER)
dispatcher.add_handler(CALLBACK_QUERY_HANDLER)
dispatcher.add_handler(RESET_WARN_HANDLER)
dispatcher.add_handler(MYWARNS_HANDLER)
dispatcher.add_handler(ADD_WARN_HANDLER)
dispatcher.add_handler(RM_WARN_HANDLER)
dispatcher.add_handler(LIST_WARN_HANDLER)
dispatcher.add_handler(WARN_LIMIT_HANDLER)
dispatcher.add_handler(WARN_STRENGTH_HANDLER)
dispatcher.add_handler(WARN_FILTER_HANDLER, WARN_HANDLER_GROUP)
