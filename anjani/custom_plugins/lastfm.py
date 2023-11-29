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
        message = f"[{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id})\n\nListens: {playcount}\nArtists: {artistcount}\nTracks: {trackcount}\nAlbums: {albumcount}\n\nSince: {dt}"
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

    @command.filters(filters.private | filters.group)
    async def cmd_albums(self, ctx: command.Context) -> None:
        """Show the user's top 10 albums from the weekly album chart on Last.fm"""
        lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)

        if not lastfm_username:
            await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
            return

        lastfm_api_key = self.bot.config.LASTFM_API_KEY

        # Prepare the URL for fetching the weekly album chart
        url = f"https://ws.audioscrobbler.com/2.0/?method=user.getweeklyalbumchart&user={lastfm_username}&api_key={lastfm_api_key}&format=json"

        # Send a GET request to fetch the data
        response = requests.get(url)
        data = json.loads(response.text)

        # Check for errors in the response
        if "error" in data:
            await ctx.respond("An error occurred while retrieving the weekly album chart. Please try again later.")
            return

        # Extract 'from' and 'to' timestamps
        from_timestamp = int(data.get('weeklyalbumchart', {}).get('@attr', {}).get('from', 0))
        to_timestamp = int(data.get('weeklyalbumchart', {}).get('@attr', {}).get('to', 0))
        # Convert timestamps to dates
        from_date = datetime.datetime.fromtimestamp(from_timestamp).strftime('%d-%m-%Y')
        to_date = datetime.datetime.fromtimestamp(to_timestamp).strftime('%d-%m-%Y')
        # Process the retrieved data and extract top 10 album information
        albums = data.get('weeklyalbumchart', {}).get('album', [])

        if not albums:
            await ctx.respond("No albums found in the weekly chart.")
            return

        # Get top 10 albums or less if albums are fewer than 10
        top_albums = albums[:10]
        total_play_count = sum(int(albums['playcount']) for albums in top_albums)
        # Prepare a message with top 10 album information as a numbered list
        album_info = "\n".join([f"{i+1}. [{album['name']}]({album['url']}) - {album['artist']['#text']} • {album['playcount']}" for i, album in enumerate(top_albums)])
        lb = f"Weekly Album for [{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id})\n({from_date} to {to_date}):\n\n{album_info}\n\nTotal Play Count: {total_play_count}"
        await ctx.respond(lb, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        
    @command.filters(filters.private | filters.group)
    async def cmd_tracks(self, ctx: command.Context) -> None:
        """Show the user's top 10 tracks from the weekly track chart on Last.fm"""
        lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)

        if not lastfm_username:
            await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
            return

        lastfm_api_key = self.bot.config.LASTFM_API_KEY

        # Prepare the URL for fetching the weekly track chart
        url = f"https://ws.audioscrobbler.com/2.0/?method=user.getweeklytrackchart&user={lastfm_username}&api_key={lastfm_api_key}&format=json"

        # Send a GET request to fetch the data
        response = requests.get(url)
        data = json.loads(response.text)

        # Check for errors in the response
        if "error" in data:
            await ctx.respond("An error occurred while retrieving the weekly track chart. Please try again later.")
            return

        # Extract 'from' and 'to' timestamps
        from_timestamp = int(data.get('weeklytrackchart', {}).get('@attr', {}).get('from', 0))
        to_timestamp = int(data.get('weeklytrackchart', {}).get('@attr', {}).get('to', 0))

        # Convert timestamps to dates
        from_date = datetime.datetime.fromtimestamp(from_timestamp).strftime('%d-%m-%Y')
        to_date = datetime.datetime.fromtimestamp(to_timestamp).strftime('%d-%m-%Y')

        # Process the retrieved data and extract top 10 track information
        tracks = data.get('weeklytrackchart', {}).get('track', [])

        if not tracks:
            await ctx.respond("No tracks found in the weekly chart.")
            return

        # Get top 10 tracks or less if tracks are fewer than 10
        top_tracks = tracks[:10]
        total_play_count = sum(int(track['playcount']) for track in top_tracks)

        # Prepare a message with top 10 track information as a numbered list
        track_info = "\n".join([f"{i+1}. [{track['name']}]({track['url']}) - {track['artist']['#text']} • {track['playcount']}" for i, track in enumerate(top_tracks)])

        tm = f"Weekly Track for [{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id})\n({from_date} to {to_date}):\n\n{track_info}\n\nTotal Play Count: {total_play_count}"

        await ctx.respond(tm, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

    @command.filters(filters.private | filters.group, aliases=["tt"])
    async def cmd_top(self, ctx: command.Context) -> None:
        """Show the user's top tracks, artists, or albums based on time range."""
        valid_top_options = ['tracks', 'artists', 'albums']
        valid_time_ranges = ['overall', '7day', '1month', '3month', '6month', '12month']

        if len(ctx.args) < 1:
            await ctx.respond("Please provide either 'tracks', 'artists', or 'albums' as the first argument.")
            return

        top_option = ctx.args[0].lower()
        if top_option not in valid_top_options:
            await ctx.respond("Invalid option. Please use either 'tracks', 'artists', or 'albums'.")
            return

        time_range_arg = ctx.args[1].lower() if len(ctx.args) > 1 else 'overall'
        if time_range_arg not in valid_time_ranges:
            await ctx.respond("Invalid time range. Please use one of the following: overall, 7day, 1month, 3month, 6month, 12month.")
            return

        lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)

        if not lastfm_username:
            await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
            return

        lastfm_api_key = self.bot.config.LASTFM_API_KEY

        if top_option == 'tracks':
            url = f"https://ws.audioscrobbler.com/2.0/?method=user.gettoptracks&user={lastfm_username}&period={time_range_arg}&api_key={lastfm_api_key}&format=json&limit=5"
        elif top_option == 'artists':
            url = f"https://ws.audioscrobbler.com/2.0/?method=user.gettopartists&user={lastfm_username}&period={time_range_arg}&api_key={lastfm_api_key}&format=json&limit=5"
        else:  # top_option == 'albums'
            url = f"https://ws.audioscrobbler.com/2.0/?method=user.gettopalbums&user={lastfm_username}&period={time_range_arg}&api_key={lastfm_api_key}&format=json&limit=5"

        response = requests.get(url)
        data = json.loads(response.text)

        if "error" in data:
            await ctx.respond("An error occurred while retrieving top data. Please try again later.")
            return

        top_items = data.get('toptracks', {}).get('track', []) if top_option == 'tracks' else data.get('topartists', {}).get('artist', []) if top_option == 'artists' else data.get('topalbums', {}).get('album', [])
        top_items = top_items[:10]

        if not top_items:
            await ctx.respond(f"No top {top_option} found for the specified time range '{time_range_arg}'")
            return

        item_info = ""
        if top_option == 'tracks':
            item_info = "\n\n".join([f"[{item['name']}]({item['url']}) - {item['artist']['name']} • {item['playcount']}" for item in top_items])
            message = f"Top Tracks for [{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) | {time_range_arg.capitalize()}\n\n{item_info}"
        elif top_option == 'artists':
            item_info = "\n\n".join([f"[{item['name']}]({item['url']}) • {item['playcount']}" for item in top_items])
            message = f"Top Artists for [{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) | {time_range_arg.capitalize()}\n\n{item_info}"
        else:  # top_option == 'albums'
            item_info = "\n\n".join([f"[{item['name']}]({item['url']}) - {item['artist']['name']} • {item['playcount']}" for item in top_items])
            message = f"Top Albums for [{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) | {time_range_arg.capitalize()}\n\n{item_info}"

        await ctx.respond(message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
