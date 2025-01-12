""" Main Anjani plugins """

# Copyright (C) 2020 - 2023  UserbotIndo Team, <https://github.com/userbotindo.git>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import re
from hashlib import sha256
from typing import TYPE_CHECKING, Any, ClassVar, List, Optional, Any, MutableMapping

from aiopath import AsyncPath
from bson.binary import Binary
from pyrogram.enums.chat_type import ChatType
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.errors import (
    ChannelInvalid,
    ChannelPrivate,
    MessageDeleteForbidden,
    MessageNotModified,
)
from pyrogram.raw.functions.updates.get_state import GetState
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from anjani import command, filters, listener, plugin, util

if TYPE_CHECKING:
    from .rules import Rules


class Main(plugin.Plugin):
    """Bot main Commands"""

    name: ClassVar[str] = "Main"

    bot_name: str
    db: util.db.AsyncCollection

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection("SESSION")
        self.ani = self.bot.db.get_collection("ANILIST")

    async def get_data(self, key: str, value: Any) -> Optional[MutableMapping[str, Any]]:
        return await self.ani.find_one({key: value})

    async def set_data(self, user_id: int, access_token: str, expires_at: str) -> None:
        await self.ani.update_one({"user_id": user_id}, {"$set": {"access_token": access_token, "expires_at": expires_at}}, upsert=True)

    async def on_start(self, _: int) -> None:
        self.bot_name = (
            self.bot.user.first_name + self.bot.user.last_name
            if self.bot.user.last_name
            else self.bot.user.first_name
        )

        restart = await self.db.find_one({"_id": 5})
        if restart is not None:
            rs_time: Optional[int] = restart.get("time")
            rs_chat_id: Optional[int] = restart.get("status_chat_id")
            rs_message_id: Optional[int] = restart.get("status_message_id")

            # Delete data first in case message editing fails
            await self.db.delete_one({"_id": 5})

            # Bail out if we're missing necessary values
            if rs_chat_id is None or rs_message_id is None or rs_time is None:
                return

            duration = util.time.usec() - rs_time
            duration_str = util.time.format_duration_us(duration)
            __, status_msg = await asyncio.gather(
                self.bot.log_stat("downtime", value=duration),
                self.bot.client.get_messages(rs_chat_id, rs_message_id),
            )
            if isinstance(status_msg, List):
                status_msg = status_msg[0]

            self.bot.log.info(f"Bot downtime {duration_str}")
            await self.send_to_log(
                f"Bot downtime {duration_str}.", reply_to_message_id=status_msg.id
            )
            try:
                await status_msg.delete()
            except MessageDeleteForbidden:
                pass
        else:
            await self.send_to_log("Starting system...")

    async def on_stop(self) -> None:
        async with asyncio.Lock():
            file = AsyncPath("anjani/anjani.session")
            if not await file.exists():
                return

            data = await self.bot.client.invoke(GetState())
            await self.db.update_one(
                {"_id": sha256(self.bot.config.BOT_TOKEN.encode()).hexdigest()},
                {
                    "$set": {
                        "session": Binary(await file.read_bytes()),
                        "date": data.date,
                        "pts": data.pts,
                        "qts": data.qts,
                        "seq": data.seq,
                    }
                },
                upsert=True,
            )

            status_msg = await self.send_to_log("Shutdowning system...")
            self.bot.log.info("Preparing to shutdown...")
            if not status_msg:
                return

            await self.db.update_one(
                {"_id": 5},
                {
                    "$set": {
                        "status_chat_id": status_msg.chat.id,
                        "status_message_id": status_msg.id,
                        "time": util.time.usec(),
                    }
                },
                upsert=True,
            )

    async def send_to_log(self, text: str, *args: Any, **kwargs: Any) -> Optional[Message]:
        if not self.bot.config.LOG_CHANNEL:
            return
        return await self.bot.client.send_message(
            int(self.bot.config.LOG_CHANNEL), text, *args, **kwargs
        )

    async def help_builder(self, chat_id: int) -> List[List[InlineKeyboardButton]]:
        """Build the help button"""
        plugins: List[InlineKeyboardButton] = []
        for plug in list(self.bot.plugins.values()):
            if plug.helpable:
                plugins.append(
                    InlineKeyboardButton(
                        await self.text(chat_id, f"{plug.name.lower()}-button"),
                        callback_data=f"help_plugin({plug.name.lower()})",
                    )
                )
        plugins.sort(key=lambda kb: kb.text)

        pairs = [plugins[i * 3 : (i + 1) * 3] for i in range((len(plugins) + 3 - 1) // 3)]
        pairs.append([InlineKeyboardButton("✗ Close", callback_data="help_close")])

        return pairs

    @listener.filters(filters.regex(r"help_(.*)"))
    async def on_callback_query(self, query: CallbackQuery) -> None:
        """Bot helper button"""
        match = query.matches[0].group(1)
        chat = query.message.chat

        if match == "back":
            keyboard = await self.help_builder(chat.id)
            try:
                await query.edit_message_text(
                    await self.text(chat.id, "help-pm", self.bot_name),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except MessageNotModified:
                pass
        elif match == "close":
            try:
                await query.message.delete()
            except MessageDeleteForbidden:
                await query.answer("I can't delete the message")
        elif match:
            plug = re.compile(r"plugin\((\w+)\)").match(match)
            if not plug:
                raise ValueError("Unable to find plugin name")

            text_lang = await self.text(
                chat.id, f"{plug.group(1)}-help", username=self.bot.user.username
            )
            text = (
                f"Here is the help for the **{plug.group(1).capitalize()}** "
                f"plugin:\n\n{text_lang}"
            )
            try:
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    await self.text(chat.id, "back-button"),
                                    callback_data="help_back",
                                )
                            ]
                        ]
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except MessageNotModified:
                pass

    async def cmd_start(self, ctx: command.Context) -> Optional[str]:
        """Bot start command"""
        chat = ctx.chat

        if chat.type == ChatType.PRIVATE:  # only send in PM's
            if ctx.input and ctx.input == "help":
                keyboard = await self.help_builder(chat.id)
                await ctx.respond(
                    await self.text(chat.id, "help-pm", self.bot_name),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return None

            if ctx.input == "lastfm":
                mt = f"Set your Last.fm username using the following command:\n`/setusername your_lastfm_username`\n\nExample:\n`/setusername IsThisUser`\n\nAfter setting your username, revisit Mini App: t.me/eyamikabot/lastfm\n\n/status : your scrobbling Last.fm\n/flex : Flex Last.fm"
                await ctx.respond(mt, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
                return None

            if ctx.input == "music":
                mt = f"now - Display current Spotify track.\nUsage: `/now`.\n\ntoptracks - Show top 5 tracks by time range.\nUsage: `/toptracks [s|m|l]`. use 's' for short, 'm' for medium, or 'l' for long.\nExample: `/toptracks m`"
                await ctx.respond(mt, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
                return None

            if ctx.input and ctx.input.startswith("ani_"):
                unique_uuid = ctx.input[4:]
                data = await self.get_data("unique_uuid", unique_uuid)
                if data:
                    await self.set_data(ctx.msg.from_user.id, data['anilist_token'], data['expires_at'])
                    await ctx.respond("Your AniList account has been successfully linked.", parse_mode=ParseMode.MARKDOWN)
                else:
                    await ctx.respond("Error: AniList token not found. Please try again.", parse_mode=ParseMode.MARKDOWN)
                return None

            if ctx.input:
                rules_re = re.compile(r"rules_(.*)")
                if rules_re.search(ctx.input):
                    plug: "Rules" = self.bot.plugins["Rules"]  # type: ignore
                    try:
                        return await plug.start_rules(ctx)
                    except (ChannelInvalid, ChannelPrivate):
                        return await self.text(chat.id, "rules-channel-invalid")

                help_re = re.compile(r"help_(.*)").match(ctx.input)
                if help_re:
                    text_lang = await self.text(chat.id, f"{help_re.group(1)}-help")
                    text = (
                        f"Here is the help for the **{ctx.input.capitalize().replace('help_', '')}** "
                        f"plugin:\n\n{text_lang}"
                    )
                    await ctx.respond(
                        text,
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        await self.text(chat.id, "back-button"),
                                        callback_data="help_back",
                                    )
                                ]
                            ]
                        ),
                        disable_web_page_preview=True,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return

            permission = [
                "change_info",
                "post_messages",
                "edit_messages",
                "delete_messages",
                "restrict_members",
                "invite_users",
                "pin_messages",
                "promote_members",
                "manage_video_chats",
                "manage_chat",
            ]
            buttons = [
                [
                    InlineKeyboardButton(
                        text=await self.text(chat.id, "add-to-group-button"),
                        url=f"t.me/{self.bot.user.username}?startgroup=true&admin={'+'.join(permission)}",
                    ),
                    InlineKeyboardButton(
                        text=await self.text(chat.id, "start-help-button"),
                        url=f"t.me/{self.bot.user.username}?start=help",
                    ),
                ],
            ]
            if "Canonical" in self.bot.plugins:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=await self.text(chat.id, "status-page-button"),
                            url="https://status.userbotindo.com",
                        ),
                        InlineKeyboardButton(
                            text=await self.text(chat.id, "dashboard-button"),
                            url="https://userbotindo.com/dashboard",
                        ),
                    ]
                )

            await ctx.respond(
                await self.text(chat.id, "start-pm", self.bot_name),
                reply_markup=InlineKeyboardMarkup(buttons),
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN,
            )
            return None

        return await self.text(chat.id, "start-chat")

    async def cmd_help(self, ctx: command.Context) -> None:
        """Bot plugins helper"""
        chat = ctx.chat

        if chat.type != ChatType.PRIVATE:  # only send in PM's
            await ctx.respond(
                await self.text(chat.id, "help-chat"),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text=await self.text(chat.id, "help-chat-button"),
                                url=f"t.me/{self.bot.user.username}?start=help",
                            )
                        ]
                    ]
                ),
            )
            return

        keyboard = await self.help_builder(chat.id)
        await ctx.respond(
            await self.text(chat.id, "help-pm", self.bot_name),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def cmd_privacy(self, ctx: command.Context) -> None:
        """Bot privacy command"""
        privacy_text = (
        "Privacy Policy\n"
        "Effective Date: July 27, 2024\n\n"
        "Nexiuo ('we') operates the @Eyamikabot Telegram bot ('Service'). This policy outlines how we collect, use, "
        "and protect your personal data when you use our Service.\n\n"
        "Data Collection:\n"
        "We collect the following information to provide and improve the Service:\n"
        "- Telegram UserID, First Name, Last Name, Username, Profile Picture\n"
        "- Chat membership details\n"
        "- User settings and configurations\n"
        "- Last usage time\n\n"
        "Data Usage:\n"
        "We use the collected data to:\n"
        "- Provide and improve the Service\n"
        "- Notify you of changes\n"
        "- Enable interactive features\n"
        "- Analyze and enhance the Service\n"
        "- Monitor usage\n"
        "- Detect and address issues\n\n"
        "Data Protection:\n"
        "We do not sell your data. Access is restricted to authorized personnel. While we strive to protect your data, "
        "no system is completely secure. Data transfer may occur if we are acquired or cease operations.\n\n"
        "Children’s Privacy:\n"
        "Our Service is not for children under 13. We do not knowingly collect data from children under 13. Contact us if "
        "you believe we have collected such data, and we will remove it.\n\n"
        "Policy Changes:\n"
        "We may update this policy and will notify you via our support group. Check this page periodically for updates.\n\n"
        "Contact:\n"
        "For questions, contact us on Support Chat."
        )

        await ctx.respond(
            privacy_text,
        )

    async def cmd_donate(self, ctx: command.Context) -> None:
        """Bot donate command"""
        await ctx.respond(
            await self.text(ctx.chat.id, "donate"),
            disable_web_page_preview=True,
        )

    async def cmd_markdownhelp(self, ctx: command.Context) -> None:
        """Send markdown helper."""
        await ctx.respond(
            await self.text(ctx.chat.id, "markdown-helper", self.bot_name),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    @command.filters(aliases=["fillinghelp"])
    async def cmd_formathelp(self, ctx: command.Context) -> None:
        """Send markdown help."""
        await ctx.respond(
            await self.text(ctx.chat.id, "filling-format-helper", noformat=True),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
