""" last.fm Plugin """
import json, requests, urllib.parse

from typing import Any, ClassVar, Mapping, MutableMapping, Optional

from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiopath import AsyncPath

from anjani import command, filters, listener, plugin, util
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from pyrogram.enums.parse_mode import ParseMode

class LastfmPlugin(plugin.Plugin):
    name = "LASTFM"
    helpable: ClassVar[bool] = True

    db: util.db.AsyncCollection

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection("LASTFM")

    async def get_data(self, key: str, value: Any) -> Optional[MutableMapping[str, Any]]:
        return await self.db.find_one({key: value})
    
    async def set_lastfm_username(self, user_id: int, username: str) -> None:
        await self.db.update_one({"user_id": user_id}, {"$set": {"lastfm_username": username}}, upsert=True)
    
    async def get_lastfm_username(self, user_id: int) -> Optional[str]:
        data = await self.get_data("user_id", user_id)
        if data and "lastfm_username" in data:
            return data["lastfm_username"]
        return None

    async def track_playcount(self, username: str, artist: str, title: str) -> int:
        url = f"https://ws.audioscrobbler.com/2.0/?method=track.getinfo&user={username}&artist={urllib.parse.quote(artist)}&track={urllib.parse.quote(title)}&api_key={self.bot.config.LASTFM_API_KEY}&format=json"
        response = requests.get(url)
        data = json.loads(response.text)
        return int(data["track"]["userplaycount"])
    
    @command.filters(filters.private)
    async def cmd_setusername(self, ctx: command.Context) -> None:
        """Set the user's Last.fm username"""
        if len(ctx.args) < 1:
            await ctx.respond("Please provide your Last.fm username.")
            return

        lastfm_username = ctx.args[0]
        await self.set_lastfm_username(ctx.msg.from_user.id, lastfm_username)
        await ctx.respond(f"Last.fm username has been set as: {lastfm_username}")

    @command.filters((filters.private | filters.group) & filters.create(lambda cmd: cmd.text.lower() == "/status" or "status" in cmd.text.lower()))
    async def cmd_status(self, ctx: command.Context) -> None:
        """Show the user's Last.fm status"""
        lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)

        if not lastfm_username:
            await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
            return

        lastfm_api_key = self.bot.config.LASTFM_API_KEY

        url = f"https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={lastfm_username}&api_key={lastfm_api_key}&format=json&limit=1"
        response = requests.get(url)
        data = json.loads(response.text)

        if "error" in data:
            await ctx.respond("An error occurred while retrieving Last.fm data. Please try again later.")
            return

        track = data["recenttracks"]["track"][0]
        artist = track["artist"]["#text"]
        title = track["name"]
        total_listens = int(data["recenttracks"]["@attr"]["total"])
        is_playing = "@attr" in track and track["@attr"]["nowplaying"] == "true"

        if is_playing:
            message = f"[{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) is currently listening to:\n\n🎵 Title: [{title}](https://open.spotify.com/search/{urllib.parse.quote(title)}%20{urllib.parse.quote(artist)})\n🎙 Artist: {artist}"
        else:
            message = f"[{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) recently listened to:\n\n🎵 Title: [{title}](https://open.spotify.com/search/{urllib.parse.quote(title)}%20{urllib.parse.quote(artist)})\n🎙 Artist: {artist}"

        play_count = await self.track_playcount(lastfm_username, artist, title)
        message += f"\n🎧 Play Count: {play_count}"
        
        message += f"\n📈 Total Listens: {total_listens}"

        await ctx.respond(message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
