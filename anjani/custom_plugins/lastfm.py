""" last.fm Plugin """
import json, requests, urllib.parse, re, datetime
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from io import BytesIO

from typing import Any, ClassVar, Mapping, MutableMapping, Optional

from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiopath import AsyncPath

from anjani import command, filters, listener, plugin, util
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.enums.chat_action import ChatAction

from .clast import create_album_chart

def create_custom_image(track_picture_url, upfp, track_name, artist_name):
    # Fetch the image from the URL
    response = requests.get(track_picture_url)
    music_cover = Image.open(BytesIO(response.content))

    # Open the profile picture (pfp) image and resize it as circular
    #pfp = Image.open('/app/anjani/custom_plugins/pfp.jpg')
    pfp = Image.open(upfp)
    pfp = pfp.resize((music_cover.width // 4, music_cover.width // 4))

    # Create a circular mask image with the same size as pfp
    mask = Image.new('L', pfp.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, pfp.width, pfp.height), fill=255)

    # Apply the mask to the pfp image
    pfp.putalpha(mask)

    # Blur the music cover image
    blurred_music_cover = music_cover.copy()
    blurred_music_cover = blurred_music_cover.filter(ImageFilter.GaussianBlur(radius=10))

    # Reduce the brightness of the blurred background
    enhancer = ImageEnhance.Brightness(blurred_music_cover)
    blurred_music_cover = enhancer.enhance(0.5)  # Adjust the brightness factor as needed

    # Calculate the position to center the unblurred circular music cover
    x_offset = 100
    y_offset = 100

    # Increase the size of the blurred background
    desired_background_size = (600, 600)  # Adjust the size as needed
    blurred_music_cover = blurred_music_cover.resize(desired_background_size)

    # Resize only the circular music cover (not blurred)
    desired_size = (400, 400)  # Change the size as needed
    music_cover = music_cover.resize(desired_size)

    # Create a circular mask for the original music cover
    mask = Image.new('L', music_cover.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((0, 0, music_cover.width, music_cover.height), fill=255)
    # Apply the mask to the original music cover
    music_cover.putalpha(mask)

    # Calculate the position to place the pfp on the right side and a little below the circular music cover
    adjacent_x = x_offset + music_cover.width  # Adjust the value to move it to the right
    adjacent_y = y_offset // 6  # Adjust the value to move it a bit below

    # Create a new image for the final output
    output_image = Image.new('RGBA', (blurred_music_cover.width, blurred_music_cover.height))

    # Paste the blurred music cover as the background
    output_image.paste(blurred_music_cover, (0, 0))

    # Paste the unblurred circular music cover in the center
    output_image.paste(music_cover, (x_offset, y_offset), music_cover)

    # Paste the pfp on the right side and a little below the circular music cover
    output_image.paste(pfp, (adjacent_x, adjacent_y), pfp)

    # Truncate track name and artist name if they are too long
    max_track_name_length = 20
    max_artist_name_length = 20
    track_name = (track_name[:max_track_name_length] + '...') if len(track_name) > max_track_name_length else track_name
    artist_name = (artist_name[:max_artist_name_length] + '...') if len(artist_name) > max_artist_name_length else artist_name

    # Add your own text right below the center unblurred image
    text = f"{track_name} by {artist_name}"
    # Set the custom font size
    font_size = 20  # Adjuste as needed

    # Load the default font with the custom size
    font = ImageFont.truetype("/app/anjani/custom_plugins/NotoSansMongolian-Regular.ttf", font_size)

    draw = ImageDraw.Draw(output_image)

    # Calculate the position for the text
    text_bbox = draw.textbbox((x_offset, y_offset + music_cover.height), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]

    # Calculate the horizontal center
    text_x = (output_image.width - text_width) // 2

    # Split the text into lines
    lines = text.split('\n')

    # Calculate vertical position right below the circular cover
    line_height = text_bbox[3] - text_bbox[1]
    text_y = y_offset + music_cover.height + 15

    # Function to determine text color based on background brightness
    def get_text_color(bg_color):
        # Calculate perceived luminance (brightness)
        luminance = (0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]) / 255
        # Choose black or white text based on luminance
        return (0, 0, 0) if luminance > 0.5 else (255, 255, 255)

    # Get the background color at the text position
    bg_color = output_image.getpixel((text_x, text_y))  # Replace with the actual position

    # Get the appropriate text color based on the background
    text_color = get_text_color(bg_color)

    # Draw each line of text with the determined text color
    draw.text((text_x, text_y), text, font=font, fill=text_color)

    # Save the final image
    #output_image.save('xy.png')
    output_stream = BytesIO()

    # Save the final image to the binary stream
    output_image.save(output_stream, format="PNG")

    # Set the name attribute for in-memory upload
    output_stream.name = "custom_image.png"

    # Reset the stream position to the beginning
    output_stream.seek(0)

    return output_stream

def generate_lastfm_album_chart(api_key, username, size, time_period):
    base_url = f'http://ws.audioscrobbler.com/2.0/'
    method = 'user.gettopalbums'

    # Translate size into limit parameters (assuming size like 3x3 means 9 albums)
    size_map = {
        '2x2': 4, '3x3': 9, '4x4': 16, '5x5': 25, '6x6': 36,
        '7x7': 49, '8x8': 64, '9x9': 81, '10x10': 100
    }
    limit = size_map.get(size)  # Default to 3x3 size

    # Translate time_period into Last.fm period
    period_map = {'w': '7day', 'm': '1month', 'q': '3month', 'h': '6month', 'y': '12month', 'a': 'overall'}
    period = period_map.get(time_period)  # Default to weekly

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

def generate_lastfm_album_chart_collage(chart_data, uname, size, time_period):
    result = chart_data
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
        footer_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
        footer_position = ((width - footer_bbox[2]) // 2, height + (footer_height // 2))
        draw.text(footer_position, footer_text, fill='black', font=footer_font)

        #new_img.save('lastfm_album_chart.png')  # Save the generated image
        output_stream = BytesIO()
        new_img.save(output_stream, format="PNG")
        output_stream.name = "album_chart.png"
        output_stream.seek(0)
        return output_stream
    else:
        self.log.error("Failed to fetch Last.fm chart data.")
        return None

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
        if 'image' in data['user'] and data['user']['image']:
            user_image = data['user']['image'][-1]['#text']
            await ctx.respond(message, photo=user_image, parse_mode=ParseMode.MARKDOWN)
        else:
            await ctx.respond(message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    
    @command.filters(filters.private | filters.group, aliases=["s"])
    async def cmd_status(self, ctx: command.Context) -> None:
        """Show the user's Last.fm status"""
        lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)

        if not lastfm_username:
            await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
            return

        lastfm_api_key = self.bot.config.LASTFM_API_KEY

        url_recent_tracks = f"https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={lastfm_username}&api_key={lastfm_api_key}&format=json&limit=1"
        response_recent_tracks = requests.get(url_recent_tracks)
        data_recent_tracks = json.loads(response_recent_tracks.text)

        if "error" in data_recent_tracks:
            await ctx.respond("An error occurred while retrieving Last.fm data. Please try again later.")
            return

        track = data_recent_tracks["recenttracks"]["track"][0]
        artist = track["artist"]["#text"]
        title = track["name"]
        total_listens = int(data_recent_tracks["recenttracks"]["@attr"]["total"])
        is_playing = "@attr" in track and track["@attr"]["nowplaying"] == "true"

        # Fetching track info including the image and tags
        url_track_info = f"https://ws.audioscrobbler.com/2.0/?method=track.getInfo&api_key={lastfm_api_key}&artist={urllib.parse.quote(artist)}&track={urllib.parse.quote(title)}&format=json"
        response_track_info = requests.get(url_track_info)
        data_track_info = json.loads(response_track_info.text)

        # Extracting the track's image URL if available
        track_info = data_track_info.get("track", {})
        album_images = track_info.get("album", {}).get("image", [])
        if album_images:
            # Selecting the largest available image size
            track_image_url = next((img["#text"] for img in reversed(album_images)), None)
        else:
            track_image_url = None  # No image available

        tags = data_track_info["track"].get("toptags", {}).get("tag", [])
        formatted_tags = ", ".join(f"#{tag['name'].replace(' ', '_')}" for tag in tags) if tags else "No tags available"

        # Constructing the message with the track's image, tags, summary, and other information
        if is_playing:
            message = f"[{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) is currently listening to:\n\n🎵 Title: [{title}](https://open.spotify.com/search/{urllib.parse.quote(title)}%20{urllib.parse.quote(artist)})\n🎙 Artist: {artist}"
        else:
            message = f"[{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) recently listened to:\n\n🎵 Title: [{title}](https://open.spotify.com/search/{urllib.parse.quote(title)}%20{urllib.parse.quote(artist)})\n🎙 Artist: {artist}"

        play_count, user_loved = await self.track_playcount(lastfm_username, artist, title)

        if user_loved:
            message += f"\n💖 Loved"

        if play_count > 0:
            message += f"\n🎧 Play Count: {play_count}"

        if formatted_tags != "No tags available":
            message += f"\n🔖 Tags: {formatted_tags}"
        message += f"\n\n📈 Total Listens: {total_listens}"

        # Adding the track image URL to the message if available
        if track_image_url:
            user = await self.bot.client.get_users(ctx.msg.from_user.id)
            if user.photo:
                file = await self.bot.client.download_media(user.photo.big_file_id)
                upfp = file
            else:
                upfp = '/app/anjani/custom_plugins/pfp.jpg'
            # Generate a custom image using create_custom_image
            custom_image = create_custom_image(track_picture_url=track_image_url, upfp=upfp, track_name=title, artist_name=artist)
            await ctx.respond(message, photo=custom_image, parse_mode=ParseMode.MARKDOWN)
        else:
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

        lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)

        if not lastfm_username:
            await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
            return

        lastfm_api_key = self.bot.config.LASTFM_API_KEY

        # Period mapping
        period_map = {'w': '7day', 'm': '1month', 'q': '3month', 'h': '6month', 'y': '12month', 'a': 'overall'}
        time_range_arg = ctx.args[1].lower() if len(ctx.args) > 1 else 'overall'

        # Validate if the provided period exists in the mapping or is one of the specified valid time ranges
        lastfm_period = period_map.get(time_range_arg, None)  # Check if the provided period is valid
        if lastfm_period not in valid_time_ranges:
            available_periods = ", ".join(["w (weekly)", "m (monthly)", "q (quarterly)", "h (half-yearly)", "y (yearly)", "a (overall)"])
            await ctx.respond(f"Invalid period provided. Available periods: {available_periods}")
            return

        if top_option == 'tracks':
            url = f"https://ws.audioscrobbler.com/2.0/?method=user.gettoptracks&user={lastfm_username}&period={lastfm_period}&api_key={lastfm_api_key}&format=json&limit=5"
        elif top_option == 'artists':
            url = f"https://ws.audioscrobbler.com/2.0/?method=user.gettopartists&user={lastfm_username}&period={lastfm_period}&api_key={lastfm_api_key}&format=json&limit=5"
        else:  # top_option == 'albums'
            url = f"https://ws.audioscrobbler.com/2.0/?method=user.gettopalbums&user={lastfm_username}&period={lastfm_period}&api_key={lastfm_api_key}&format=json&limit=5"

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
            message = f"Top Tracks for [{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) | {lastfm_period.capitalize()}\n\n{item_info}"
        elif top_option == 'artists':
            item_info = "\n\n".join([f"[{item['name']}]({item['url']}) • {item['playcount']}" for item in top_items])
            message = f"Top Artists for [{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) | {lastfm_period.capitalize()}\n\n{item_info}"
        else:  # top_option == 'albums'
            item_info = "\n\n".join([f"[{item['name']}]({item['url']}) - {item['artist']['name']} • {item['playcount']}" for item in top_items])
            message = f"Top Albums for [{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) | {lastfm_period.capitalize()}\n\n{item_info}"

        await ctx.respond(message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

    @command.filters(filters.private | filters.group)
    async def cmd_collage_album(self, ctx: command.Context) -> None:
        """Show a collage of the user's top albums."""
        chat = ctx.chat.id
        ie = ctx.msg.reply_to_message or ctx.msg
        async with ctx.action(ChatAction.TYPING):
            lastfm_username = await self.get_lastfm_username(ctx.msg.from_user.id)
            lastfm_api_key = self.bot.config.LASTFM_API_KEY

            if not lastfm_username:
                await ctx.respond("Last.fm username not found. Please set your Last.fm username using /setusername in PM")
                return

            if len(ctx.args) != 2:
                available_periods = ", ".join(["w (weekly)", "m (monthly)", "q (quarterly)", "h (half-yearly)", "y (yearly)", "a (overall)"])
                available_sizes = ", ".join(["2x2", "3x3", "4x4", "5x5", "6x6", "7x7", "8x8", "9x9", "10x10"])
                await ctx.respond(f"Please provide both period and size grid in the format: `/collage_album <period> <size>`\n\nAvailable periods: {available_periods}\nAvailable sizes: {available_sizes}")
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

            uname = ctx.msg.from_user.first_name
            generated_image = await create_album_chart(lastfm_api_key, lastfm_username, lastfm_period.lower(), size.lower())
            if generated_image:
                caption = f"[{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) {lastfm_period.lower()} Albums" 
                await self.bot.client.send_document(chat, document=generated_image, caption=caption, reply_to_message_id=ie.id, parse_mode=ParseMode.MARKDOWN)
            else:
                await ctx.respond("Failed to generate the collage.")
