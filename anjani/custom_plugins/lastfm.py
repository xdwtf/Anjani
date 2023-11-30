""" last.fm Plugin """
import json, requests, urllib.parse, re, datetime
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

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

    async def generate_lastfm_album_chart(self, username, size, time_period):
        api_key = self.bot.config.LASTFM_API_KEY
        base_url = f'http://ws.audioscrobbler.com/2.0/'
        method = 'user.gettopalbums'

        # Translate size into limit parameters (assuming size like 3x3 means 9 albums)
        size_map = {
            '2x2': 4, '3x3': 9, '4x4': 16, '5x5': 25, '6x6': 36,
            '7x7': 49, '8x8': 64, '9x9': 81, '10x10': 100
        }
        limit = size_map.get(size, 25)  # Default to 3x3 size

        # Translate time_period into Last.fm period
        period_map = {'w': '7day', 'm': '1month', 'q': '3month', 'h': '6month', 'y': '12month', 'a': 'overall'}
        period = period_map.get(time_period, '7day')  # Default to weekly

        # Make the Last.fm API request
        params = {
            'method': method,
            'user': username,
            'api_key': api_key,
            'format': 'json',
            'limit': limit,
            'period': period
        }
        response = requests.get(base_url, params=params)

        # Process the response and generate the chart
        if response.status_code == 200:
            chart_data = response.json()
            return chart_data
        else:
            return None

    async def generate_lastfm_album_chart_collage(self, uname, username, size, time_period):
        result = await self.generate_lastfm_album_chart(self, username, size, time_period)
        if result:
            albums = [(album['name'][:20] + '...' if len(album['name']) > 20 else album['name'], album['image'][-1]['#text'], album['playcount']) for album in result['topalbums']['album']]
            albums = [(name, image_url, playcount) for name, image_url, playcount in albums if image_url]
            size_map = {'2x2': (2, 2), '3x3': (3, 3), '4x4': (4, 4), '5x5': (5, 5), '6x6': (6, 6), '7x7': (7, 7), '8x8': (8, 8), '9x9': (9, 9), '10x10': (10, 10)}
            rows, columns = size_map.get(size)  # Default to 5x5 size
            # Calculate image width and height based on total items and desired padding
            padding = 20
            album_width = 200
            album_height = 200
            total_items = len(albums)
            total_rows = (total_items + columns - 1) // columns
            width = columns * (album_width + padding) + padding
            height = total_rows * (album_height + padding) + padding

            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)
            custom_font_path = "/app/anjani/custom_plugins/NotoSansMongolian-Regular.ttf"

            displayed_albums = set()  # Keep track of displayed albums to avoid duplicates

            for index, (album_name, album_image_url, playcount) in enumerate(albums):
                # No need to check again for empty URLs as we filtered those out above
                try:
                    response = requests.get(album_image_url)
                    if response.status_code == 200:
                        album_image = Image.open(BytesIO(response.content))
                        album_image.thumbnail((album_width, album_height))  # Resize album image if needed

                        row = index // columns
                        col = index % columns
                        offset_x = col * (album_width + padding) + padding
                        offset_y = row * (album_height + padding) + padding

                        img.paste(album_image, (offset_x, offset_y))
                        displayed_albums.add(album_name)

                        # Draw text for album title and playcount
                        title_font = ImageFont.truetype(custom_font_path)  # Use default font
                        draw.text((offset_x, offset_y + album_height), f"{album_name} {playcount}", fill='black', font=title_font)
                except Exception as e:
                    self.log.error(f"Error fetching image for {album_name}: {e}")

            # Create a new image with increased height to accommodate the footer
            footer_height = 40  # Adjust as needed
            new_height = height + footer_height
            new_img = Image.new('RGB', (width, new_height), color='white')
            new_img.paste(img, (0, 0))  # Paste the original image (with album art grid) onto the new image

            draw = ImageDraw.Draw(new_img)
            # Add footer
            footer_text = f"{uname} Top Albums {size}"
            footer_font = ImageFont.truetype(custom_font_path, size=16)  # Adjust font size as needed
            footer_width, footer_height = draw.textsize(footer_text, font=footer_font)
            footer_position = (width - footer_width) // 2, height + (footer_height // 2)
            draw.text(footer_position, footer_text, fill='black', font=footer_font)

            #new_img.save('lastfm_album_chart.png')  # Save the generated image
            output_stream = io.BytesIO()
            new_img.save(output_stream, format="PNG")
            output_stream.name = "album_chart.png"
            output_stream.seek(0)
            return output_stream
        else:
            self.log.error("Failed to fetch Last.fm chart data.")
            return None

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
    async def cmd_weekly(self, ctx: command.Context) -> None:
        """Show the user's top 10 tracks or albums from the weekly chart on Last.fm"""
        valid_options = ['tracks', 'albums']

        if len(ctx.args) < 1:
            await ctx.respond("Please provide either 'tracks' or 'albums' as the first argument.")
            return

        option = ctx.args[0].lower()
        if option not in valid_options:
            await ctx.respond("Invalid option. Please use either 'tracks' or 'albums'.")
            return

        lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)

        if not lastfm_username:
            await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
            return

        lastfm_api_key = self.bot.config.LASTFM_API_KEY

        # Determine whether to fetch 'track' or 'album' based on the provided option (tracks or albums)
        chart_type = 'track' if option == 'tracks' else 'album'

        # Prepare the URL for fetching the weekly chart based on the determined chart type
        url = f"https://ws.audioscrobbler.com/2.0/?method=user.getweekly{chart_type}chart&user={lastfm_username}&api_key={lastfm_api_key}&format=json"

        # Send a GET request to fetch the data
        response = requests.get(url)
        data = json.loads(response.text)

        # Check for errors in the response
        if "error" in data:
            await ctx.respond(f"An error occurred while retrieving the weekly {option}. Please try again later.")
            return

        # Extract 'from' and 'to' timestamps
        from_timestamp = int(data.get(f'weekly{chart_type}chart', {}).get('@attr', {}).get('from', 0))
        to_timestamp = int(data.get(f'weekly{chart_type}chart', {}).get('@attr', {}).get('to', 0))

        # Convert timestamps to dates
        from_date = datetime.datetime.fromtimestamp(from_timestamp).strftime('%d-%m-%Y')
        to_date = datetime.datetime.fromtimestamp(to_timestamp).strftime('%d-%m-%Y')

        # Process the retrieved data and extract top 10 information based on the determined chart type
        items = data.get(f'weekly{chart_type}chart', {}).get(chart_type, [])

        if not items:
            await ctx.respond(f"No {option} found in the weekly chart.")
            return

        # Get top 10 items or less if fewer than 10
        top_items = items[:10]
        total_play_count = sum(int(item['playcount']) for item in top_items)
        # Prepare a message with top 10 information as a numbered list
        item_info = "\n".join([f"{i+1}. [{item['name']}]({item['url']}) - {item['artist']['#text']} • {item['playcount']}" for i, item in enumerate(top_items)])
        message = f"Weekly {option.capitalize()} for [{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id})\n({from_date} to {to_date}):\n\n{item_info}\n\nTotal Play Count: {total_play_count}"
        await ctx.respond(message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

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

    @command.filters(filters.private | filters.group)
    async def cmd_collage_album(self, ctx: command.Context) -> None:
        """Show a collage of the user's top albums."""
        lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)
        
        if not lastfm_username:
            await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
            return

        if len(ctx.args) != 2:
            available_periods = ", ".join(["w (weekly)", "m (monthly)", "q (quarterly)", "h (half-yearly)", "y (yearly)", "a (overall)"])
            available_sizes = ", ".join(["2x2", "3x3", "4x4", "5x5", "6x6", "7x7", "8x8", "9x9", "10x10"])
            await ctx.respond(f"Please provide both period and size grid in the format: /Collage <period> <size>\n\nAvailable periods: {available_periods}\nAvailable sizes: {available_sizes}")
            return

        period = ctx.args[0]
        size = ctx.args[1]
        period_map = {'w': '7day', 'm': '1month', 'q': '3month', 'h': '6month', 'y': '12month', 'a': 'overall'}
        lastfm_period = period_map.get(period.lower(), None)  # Check if the provided period is valid

        if lastfm_period is None:
            available_periods = ", ".join(["w (weekly)", "m (monthly)", "q (quarterly)", "h (half-yearly)", "y (yearly)", "a (overall)"])
            await ctx.respond(f"Invalid period provided. Available periods: {available_periods}")
            return

        valid_sizes = ["2x2", "3x3", "4x4", "5x5", "6x6", "7x7", "8x8", "9x9", "10x10"]
        if size.lower() not in valid_sizes:
            await ctx.respond(f"Invalid size grid provided. Available size grids: {', '.join(valid_sizes)}")
            return

        uname=ctx.msg.from_user.first_name
        generated_image = await self.generate_lastfm_album_chart_collage(self, uname=uname, username=lastfm_username, size=size, period)

        if generated_image:
            await ctx.respond_document(document=generated_image)
        else:
            await ctx.respond("Failed to generate the collage.")
