"""miscellaneous bot commands"""
# Copyright (C) 2020 - 2024  UserbotIndo Team, <https://github.com/userbotindo.git>
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

from json import JSONDecodeError
from typing import Any, ClassVar, Optional

from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiopath import AsyncPath
import aiohttp

from anjani import command, filters, listener, plugin
from pyrogram.types import Message
from pyrogram.enums.parse_mode import ParseMode

import re, json, random, requests, os, io, filetype, httpx
from bs4 import BeautifulSoup

custom_patterns = {
    "youtube": r"^(https?:\/\/)?((www\.)?youtube\.com|music\.youtube\.com|youtu\.?be)\/.+",
    "spotify": r"^(https?:\/\/)?(www\.)?(open\.spotify\.com)\/.+",
    "soundcloud": r"^(https?:\/\/)?((www\.)?soundcloud\.com)\/.+",
    "deezer": r"^(https?:\/\/)?((www\.)?deezer\.com)\/.+",
    "apple": r"^(https?:\/\/)?((www\.)?music\.apple\.com)\/.+",
    "tidal": r"^(https?:\/\/)?((www\.)?tidal\.com)\/.+",
    "amazon": r"^(https?:\/\/)?((www\.)?music\.amazon\.com)\/.+",
    "audioMack": r"^(https?:\/\/)?((www\.)?audiomack\.com)\/.+",
    "qobuz": r"^(https?:\/\/)?((www\.)?qobuz\.com)\/.+",
    "napster": r"^(https?:\/\/)?((www\.)?us\.napster\.com)\/.+",
    "pandora": r"^(https?:\/\/)?((www\.)?pandora\.com)\/.+",
    "itunes": r"^(https?:\/\/)?((www\.)?itunes\.apple\.com)\/.+",
    "lineMusic": r"^(https?:\/\/)?((www\.)?music\.line\.me)\/.+",
    "amazonMusic": r"^(https?:\/\/)?((www\.)?music\.amazon\.co\.jp)\/.+",
    "itunesStore": r"^(https?:\/\/)?((www\.)?itunes\.apple\.com)\/.+",
    "youtubeMusic": r"^(https?:\/\/)?((www\.)?music\.youtube\.com)\/.+",
    "googlePlayMusic": r"^(https?:\/\/)?((www\.)?play\.google\.com)\/.+",
    "bandcamp": r"^(https?:\/\/)?((www\.)?bandcamp\.com)\/.+",
    "discogs": r"^(https?:\/\/)?((www\.)?discogs\.com)\/.+",
    "ticketmaster": r"^(https?:\/\/)?((www\.)?ticketmaster\.com)\/.+",
    "musicbrainz": r"^(https?:\/\/)?((www\.)?musicbrainz\.org)\/.+",
}

class Paste:
    def __init__(self, session: ClientSession, name: str, url: str):
        self.__session = session
        self.__name = name
        self.__url = url

        self.url_map = {
            "-h": "https://hastebin.com/",
            "-s": "https://stashbin.xyz/",
            "hastebin": "https://hastebin.com/",
            "stashbin": "https://stashbin.xyz/",
            "spacebin": "https://spaceb.in/",
        }

    async def __aenter__(self) -> "Paste":
        return self

    async def __aexit__(self, _: Any, __: Any, ___: Any) -> None:
        ...

    async def go(self, content: Any) -> str:
        async with self.__session.post(self.__url, json=content) as r:
            content_data = await r.json()
            url = self.url_map[self.__name]
            if self.__name == "stashbin":
                slug = content_data["data"]["key"]
            elif self.__name == "hastebin":
                slug = content_data["key"]
            else:
                slug = content_data["payload"]["id"]
            return url + slug


class Misc(plugin.Plugin):
    name: ClassVar[str] = "Miscs"
    helpable: ClassVar[bool] = True

    async def cmd_id(self, ctx: command.Context) -> str:
        """Display ID's"""
        msg = ctx.msg.reply_to_message or ctx.msg
        out_str = f"👥 **Chat ID :** `{(msg.forward_from_chat or msg.chat).id}`\n"
        if msg.is_topic_message:
            out_str += f"🗨️ **Topic ID :** `{msg.topics.id}`\n"
        out_str += f"💬 **Message ID :** `{msg.forward_from_message_id or msg.id}`\n"
        if msg.from_user:
            out_str += f"🙋‍♂️ **From User ID :** `{msg.from_user.id}`\n"
        file = (
            msg.audio
            or msg.animation
            or msg.document
            or msg.photo
            or msg.sticker
            or msg.voice
            or msg.video_note
            or msg.video
        ) or None
        if file:
            out_str += f"📄 **Media Type :** `{file.__class__.__name__}`\n"
            out_str += f"📄 **File ID :** `{file.file_id}`"

        return out_str

    @listener.priority(95)
    @listener.filters(~filters.outgoing)
    async def on_message(self, message: Message) -> None:
        if message.text is not None and isinstance(message.text, str):
            text = message.text
        elif message.caption is not None and isinstance(message.caption, str):
            text = message.caption
        else:
            return

        if re.match(r"https?://(?:www\.)instagram\.com/(?:reel)/[a-zA-Z0-9-_]{11}/", text):
            # Instagram Reel
            await self.handle_instagram_reel(message)
        else:
            url = await self.extract_custom_url(text)
            if url:
                await self.handle_music_links(message, url)

    async def extract_custom_url(self, text: str) -> Optional[str]:
        """Extract the first URL that matches custom patterns."""
        # Check if text contains multiple lines
        if '\n' in text:
            # Split text into lines
            lines = text.split('\n')
        else:
            # Put single-line text into a list
            lines = [text]

        # Iterate over each line
        for line in lines:
            # Iterate over each pattern
            for pattern in custom_patterns.values():
                match = re.search(pattern, line)
                if match:
                    return match.group(0)  
        return None

    async def handle_instagram_reel(self, message: Message) -> None:
        """Handle Instagram Reel"""
        chat = message.chat
        ie = message.reply_to_message or message
        Pattern = r"https?://(?:www\.)instagram\.com/(?:reel)/[a-zA-Z0-9-_]{11}/"
        xd = re.findall(Pattern, message.text)
        url = "https://instagram-downloader-download-instagram-videos-stories.p.rapidapi.com/index"
        querystring = {"url": xd[0]}
        headers = {
            "X-RapidAPI-Key": self.bot.config.RAPIDAPI_KEY,
            "X-RapidAPI-Host": "instagram-downloader-download-instagram-videos-stories.p.rapidapi.com",
        }
        response = requests.request("GET", url, headers=headers, params=querystring)
        reel= json.loads(response.text)
        self.log.info(f"Received message: {xd[0]}")
        try:
            await self.bot.client.send_video(
            chat.id,
            reel["media"],
            reply_to_message_id=ie.id,
        )
        except Exception as e:
            return None

    async def handle_music_links(self, message: Message, url: str) -> None:
        """Listen Music Links"""
        chat = message.chat
        userx = message.from_user
        ie = message.reply_to_message or message
        api_url = "https://api.songwhip.com/v3/create"
        odesli_url = f'https://api.song.link/v1-alpha.1/links?url={url}'
        platforms = set()  # Define the platforms set here

        try:
            headers = {'Content-Type': 'application/json'}
            payload = {'url': url, 'country': 'US'}
            data = None

            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        songwhip_url = data.get("data", {}).get("item", {}).get("url", None)
                        links_data = data.get("data", {}).get("item", {}).get("links", {})
                        for platform, platform_data in links_data.items():
                            for link_info in platform_data:
                                platform_url = link_info['link']
                                platforms.add((platform, platform_url))  # Add the platform and its URL to the set

            odesli_response = requests.get(odesli_url)
            if odesli_response.ok:
                odesli_data = odesli_response.json()
                odesli_page_url = odesli_data.get("pageUrl")
                entities = odesli_data.get("entitiesByUniqueId", {})
                song_entity = next(iter(entities.values()))
                artist_name = song_entity.get("artistName")
                title = song_entity.get("title")
                links_by_platform = odesli_data.get("linksByPlatform", {})
                for platform, platform_data in links_by_platform.items():
                    platform_url = platform_data.get("url")
                    platforms.add((platform, platform_url))  # Add the platform and its URL to the set

                sorted_platforms = sorted(platforms)
                platform_str = " | ".join(f"[{platform.title()}]({platform_url})" for platform, platform_url in sorted_platforms)
                message = ""
                message += f'**{title}** by **{artist_name}** from: **{userx.mention}**\n\n'
                message += platform_str
                message += f' | [Odesli]({odesli_page_url})'
                if songwhip_url is not None:
                    message += f' | [Songwhip](https://songwhip.com{songwhip_url})'
                await self.bot.client.send_message(
                    chat.id,
                    text=message,
                    reply_to_message_id=ie.id,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
            else:
                self.log.info(f"music else part")
                return None
        except Exception as e:
            self.log.error(e, exc_info=e)
            return None

    @command.filters(filters.private)
    async def cmd_paste(self, ctx: command.Context, service: Optional[str] = None) -> Optional[str]:
        if not ctx.msg.reply_to_message:
            return None

        if not service:
            service = "stashbin"

        chat = ctx.chat
        reply_msg = ctx.msg.reply_to_message

        data: Any
        if (reply_msg.document and reply_msg.document.file_size < 10000000):
            file = AsyncPath(await reply_msg.download())
            data = await file.read_text()
            await file.unlink()
        elif reply_msg.text:
            data = reply_msg.text
        else:
            return None

        uris = {
            "-h": "https://hastebin.com/documents",
            "-s": "https://stashbin.xyz/api/document",
            "hastebin": "https://hastebin.com/documents",
            "stashbin": "https://stashbin.xyz/api/document",
            "spacebin": "https://spaceb.in/api/v1/documents/",
        }
        try:
            uri = uris[service]
        except KeyError:
            return await self.get_text(chat.id, "paste-invalid", service)

        if service in {"-h", "hastebin"}:
            service = "hastebin"
            data = data.encode("utf-8")
        elif service in {"-s", "stashbin"}:
            service = "stashbin"
            data = {"content": data}
        elif service == "spacebin":
            service = "spacebin"
            data = {"content": data, "extension": "txt"}
        else:
            return await self.get_text(chat.id, "paste-invalid", service)

        await ctx.respond(await self.text(chat.id, "paste-wait", service))

        try:
            async with Paste(self.bot.http, service, uri) as paste:
                return await self.text(
                    ctx.chat.id, "paste-succes", f"[{service}]({await paste.go(data)})"
                )
        except (JSONDecodeError, ContentTypeError, ClientConnectorError, KeyError):
            self.log.error("Error while pasting", exc_info=True)
            return await self.text(ctx.chat.id, "paste-fail", service)

    @command.filters(filters.private)
    async def cmd_source(self, ctx: command.Context) -> None:
        """Send the bot source code"""
        await ctx.respond(
            "[GitHub repo](https://github.com/userbotindo/Anjani)\n"
            + "[Support](https://t.me/userbotindo)",
            disable_web_page_preview=True,
        )

    @command.filters(filters.admin_only)
    async def cmd_echo(self, ctx: command.Context) -> str:
        """Panda to Echo."""
        text = ctx.input
        chat = ctx.msg.chat
        msg = ctx.msg.reply_to_message or ctx.msg
        await self.bot.client.send_message(
            chat.id,
            text,
            reply_to_message_id=msg.id,
        )
        await ctx.msg.delete()
        return None

    @command.filters(filters.group)
    async def cmd_slap(self, ctx: command.Context) -> Optional[str]:
        """Slap member with neko slap."""
        text = ctx.input
        chat = ctx.msg.chat
        async with self.bot.http.get("https://www.nekos.life/api/v2/img/slap") as slap:
            if slap.status != 200:
                return await self.text(chat.id, "err-api-down")
            res = await slap.json()

        msg = ctx.msg.reply_to_message or ctx.msg
        await self.bot.client.send_animation(
            chat.id,
            res["url"],
            reply_to_message_id=msg.id,
            caption=text,
        )
        return None

    @command.filters(filters.group)
    async def cmd_pat(self, ctx: command.Context) -> Optional[str]:
        """Pat member with neko pat."""
        text = ctx.input
        chat = ctx.msg.chat
        async with self.bot.http.get("https://www.nekos.life/api/v2/img/pat") as pat:
            if pat.status != 200:
                return await self.text(chat.id, "err-api-down")
            res = await pat.json()

        msg = ctx.msg.reply_to_message or ctx.msg
        await self.bot.client.send_animation(
            chat.id,
            res["url"],
            reply_to_message_id=msg.id,
            caption=text,
        )
        return None

    async def cmd_ud(self, ctx: command.Context) -> Optional[str]:
        """urban dictionary"""
        tex = ctx.input.split()[-1]
        chat = ctx.msg.chat
        ud = f'http://api.urbandictionary.com/v0/define?term={tex}'
        res = requests.get(ud)
        ret = json.loads(res.text)
        try:
            word = ret["list"][0]["word"]
            definition = ret["list"][0]["definition"]
            example = ret["list"][0]["example"]
            y = f"Text: {word}\n\nMeaning: {definition}\n\nExample: {example}"
            await self.bot.client.send_message(
            chat.id,
            text=y,
            reply_to_message_id=ctx.msg.id,
        )
        except Exception as e:
            return None
