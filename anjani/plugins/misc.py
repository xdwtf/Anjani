"""miscellaneous bot commands"""
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

from json import JSONDecodeError
from typing import Any, ClassVar, Optional

from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiopath import AsyncPath

from anjani import command, filters, listener, plugin
from pyrogram.types import Message
from pyrogram.enums.parse_mode import ParseMode

import re, json, random, requests, os, io, filetype, httpx
from bs4 import BeautifulSoup

platforms_regex = re.compile(r'('
    r'https?://open\.spotify\.com/(?:album|track|playlist)/[a-zA-Z0-9]+(?:/.*)?|'
    r'https?://itunes\.apple\.com/(?:[a-z]{2}/)?(?:album/[^/?#]+|artist/[^/?#]+/[^/?#]+|playlist/[^/?#]+)|'
    r'https?://music\.apple\.com/(?:[a-z]{2}/)?(?:album/[^/?#]+|artist/[^/?#]+/[^/?#]+|playlist/[^/?#]+)?|'
    r'https?://music\.youtube\.com/(?:(?:watch\?v=[a-zA-Z0-9_-]+&list=[a-zA-Z0-9_-]+)|(?:watch\?v=[a-zA-Z0-9_-]+))|'
    r'https?://www\.youtube\.com/(?:(?:watch\?v=[a-zA-Z0-9_-]+&list=[a-zA-Z0-9_-]+)|(?:watch\?v=[a-zA-Z0-9_-]+))|'
    r'https?://www\.google\.com/search\?.*&(?:source=lnms&tbm=isch&q=)?spotify\+[^&]*(?:&[^&]*)*|'
    r'https?://play\.google\.com/store/music/album/[^/?#]+/[^/?#]+|'
    r'https?://www\.pandora\.com/artist/[^/?#]+/[^/?#]+|'
    r'https?://www\.deezer\.com/(?:album|track|playlist)/[0-9]+|'
    r'https?://listen\.tidal\.com/(?:album|track|playlist)/[0-9]+|'
    r'https?://www\.amazon\.(?:com|co\.uk|de|fr|ca)/gp/product/[^/?#]+|'
    r'https?://music\.amazon\.(?:com|co\.uk|de|fr|ca)/(?:albums|artists|playlists)/[^/?#]+|'
    r'https?://soundcloud\.com/(?:[^/?#]+/)?[^/?#]+|'
    r'https?://us\.napster\.com/(?:artist|album|track)/[^/?#]+|'
    r'https?://music\.yandex\.ru/(?:album|track|playlist)/[0-9]+|'
    r'https?://spinrilla\.com/songs/[^/?#]+|'
    r'https?://audius\.co/(?:artist|track|playlist)/[^/?#]+|'
    r'https?://(?:www\.)?anghami\.com/.*|'
    r'https?://(?:www\.)?boomplay\.com/songs/[0-9]+|'
    r'https?://audiomack\.com/[^/?#]+/song/[^/?#]+'
    r')')

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
        async with self.__session.post(self.__url, data=content) as r:
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
            "-s": "http://stashbin.xyz/api/document",
            "hastebin": "https://hastebin.com/documents",
            "stashbin": "http://stashbin.xyz/api/document",
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

    @listener.priority(95)
    @listener.filters(filters.regex(r"https?://(?:www\.)instagram\.com/(?:reel)/[a-zA-Z0-9-_]{11}/") & filters.group & ~filters.outgoing)
    async def on_message(self, message: Message) -> None:
        """Listen Instagram Reel"""
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

    @listener.priority(95)
    @listener.filters(filters.regex(r"https://www\.threads\.net/t/([a-zA-Z0-9_-]+)") & ~filters.outgoing)
    async def on_message(self, message: Message) -> None:
        """Threads Media Handler"""
        chat = message.chat
        ie = message.reply_to_message or message
        text = message.text
        tp = r"https://www\.threads\.net/t/([a-zA-Z0-9_-]+)"
        post_ids = re.findall(tp, text)
        self.log.info(post_ids)
        
        try:
            # Find all post IDs matching the pattern
            if not post_ids:
                return None

            for post_id in post_ids:
                async with httpx.AsyncClient() as http_client:
                    response = await http_client.get("https://www.threads.net/")
                    if response.status_code != 200:
                        self.log.warning(f"Failed to fetch homepage: {response.status_code}")
                        return None

                    r = await http_client.get(f"https://www.threads.net/t/{post_id}/embed/")
                    soup = BeautifulSoup(r.text, "html.parser")
                    medias = []

                    if div := soup.find("div", {"class": "SingleInnerMediaContainer"}):
                        if video := div.find("video"):
                            url = video.find("source").get("src")
                            medias.append({"p": url, "w": 0, "h": 0})
                        if image := div.find("img", {"class": "img"}):
                            url = image.get("src")
                            medias.append({"p": url, "w": 0, "h": 0})

                    if not medias:
                        self.log.info(f"No media found for post ID: {post_id}")
                        return None

                    files = []
                    for media in medias:
                        response = await http_client.get(media["p"])
                        file = io.BytesIO(response.content)
                        file.name = f"{media['p'][60:80]}.{filetype.guess_extension(file)}"
                        files.append({"p": file, "w": media["w"], "h": media["h"]})

                    if not files:
                        self.log.warning(f"No files downloaded for post ID: {post_id}")
                        return None

                    for file in files:
                        filepath = f"{file['p'].name}"
                        with open(filepath, 'wb') as f:
                            f.write(file['p'].getbuffer())

                        self.log.info(f"Sending document for post ID: {post_id}, file path: {filepath}")
                        await self.bot.client.send_document(chat.id, document=filepath, caption=f"/t/{post_id}", reply_to_message_id=ie.id)

                        # Remove the downloaded file
                        os.remove(filepath)

        except Exception as e:
            self.log.exception(f"An error occurred: {str(e)}")
            return None
                
    @listener.priority(95)
    @listener.filters(filters.regex(platforms_regex) & ~filters.outgoing)
    async def on_message(self, message: Message) -> None:
        """Listen Music Links"""
        chat = message.chat
        userx = message.from_user
        ie = message.reply_to_message or message
        xd = platforms_regex.findall(message.text)

        try:
            if xd:
                urlx = f'https://api.song.link/v1-alpha.1/links?url={xd[0]}'
                response = requests.request("GET", urlx)
                data = response.json()
                entities = data.get("entitiesByUniqueId", {})
                song_entity = next(iter(entities.values()))
                artist_name = song_entity.get("artistName")
                title = song_entity.get("title")
                links_by_platform = data.get("linksByPlatform", {})
                pu = data.get("pageUrl")
                platforms = []
                urls = []
                for platform, platform_data in links_by_platform.items():
                    url = platform_data.get("url")
                    cw = platform.title()
                    platforms.append(f"[{cw}]({url})")

                um = f'**{title}** by **{artist_name}** from: **{userx.mention}**\n\n'
                link_text = " | ".join(platforms)
                li = f'\n\n[View on Odesli]({pu})'
                nt = um + link_text + li
                await self.bot.client.send_message(
                    chat.id,
                    text=nt,
                    reply_to_message_id=ie.id,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
            else:
                return None
        except Exception as e:
            return None
