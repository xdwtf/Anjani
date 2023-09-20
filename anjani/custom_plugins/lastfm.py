""" last.fm Plugin """
import json, requests, urllib.parse, re, datetime

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
        try:
            play_count = int(data["track"]["userplaycount"])
        except Exception as e:
            self.log.info(f"An error occurred play_count: {str(e)}")
            play_count = 0

        try:
            user_loved = bool(int(data["track"]["userloved"]))
        except Exception as e:
            self.log.info(f"An error occurred user_loved: {str(e)}")
            user_loved = False

        return play_count, user_loved
    
    @command.filters(filters.private)
    async def cmd_setusername(self, ctx: command.Context) -> None:
        """Set the user's Last.fm username"""
        if len(ctx.args) < 1:
            await ctx.respond("Please provide your Last.fm username.")
            return

        lastfm_username = ctx.args[0]
        await self.set_lastfm_username(ctx.msg.from_user.id, lastfm_username)
        await ctx.respond(f"Last.fm username has been set as: {lastfm_username}")

    @command.filters(filters.private | filters.group, aliases=["f"])
    async def cmd_flex(self, ctx: command.Context) -> None:
        """Show the user's Last.fm flx"""
        lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)

        if not lastfm_username:
            await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
            return

        lastfm_api_key = self.bot.config.LASTFM_API_KEY

        url = f"https://ws.audioscrobbler.com/2.0/?method=user.getinfo&user={lastfm_username}&api_key={lastfm_api_key}&format=json"
        response = requests.get(url)
        data = json.loads(response.text)

        if "error" in data:
            await ctx.respond("An error occurred while retrieving Last.fm data. Please try again later.")
            return

        name = data['user']['name']
        url = data['user']['url']
        playcount = data['user']['playcount']
        artistcount = data['user']['artist_count']
        trackcount = data['user']['track_count']
        albumcount = data['user']['album_count']
        registered_unixtime = int(data['user']['registered']['unixtime'])
        dt = datetime.datetime.fromtimestamp(registered_unixtime)
        message = f"[{name}]({ur}) LastFM:\nListens: {playcount}\nartists: {artistcount}n\tracks: {trackcount}n\albums: {albumcount}\n since:{dt}"
        await ctx.respond(message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    
    @command.filters(filters.private | filters.group, aliases=["s"])
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

        play_count, user_loved = await self.track_playcount(lastfm_username, artist, title)

        if user_loved:
            message += f"\n💖 Loved"

        if play_count > 0:
            message += f"\n🎧 Play Count: {play_count}"
        
        message += f"\n📈 Total Listens: {total_listens}"

        await ctx.respond(message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
