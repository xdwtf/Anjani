""" spotify Plugin """
import json, requests, urllib.parse, re, datetime
from typing import Any, ClassVar, Mapping, MutableMapping, Optional
from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiopath import AsyncPath
from anjani import command, filters, listener, plugin, util
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.enums.chat_action import ChatAction

import time
import spotipy
import datetime
from spotipy.oauth2 import SpotifyOAuth

import io
from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance

def create_custom_image(track_picture_url, upfp, track_name, artist_name, current_time, total_duration):
    # Fetch the image from the URL
    response = requests.get(track_picture_url)
    music_cover = Image.open(BytesIO(response.content))

    # Open the profile picture (pfp) image and resize it as circular
    #pfp = Image.open('/app/anjani/custom_plugins/pfp.jpg')
    pfp = Image.open(upfp)
    pfp = pfp.resize((music_cover.width // 9, music_cover.width // 9))

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
    text = f"{track_name} by {artist_name}\n{current_time} | {total_duration}"
    # Set the custom font size
    font_size = 20  # Adjust the font size as needed

    # Load the default font with the custom size
    font = ImageFont.truetype("/app/anjani/custom_plugins/NotoSans-Medium.ttf", font_size)

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
    for line in lines:
        text_bbox = draw.textbbox((x_offset, text_y), line, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = (output_image.width - text_width) // 2
        draw.text((text_x, text_y), line, font=font, fill=text_color)
        text_y += line_height

    # Save the final image
    #output_image.save('xy.png')
    output_stream = io.BytesIO()

    # Save the final image to the binary stream
    output_image.save(output_stream, format="PNG")

    # Set the name attribute for in-memory upload
    output_stream.name = "custom_image.png"

    # Reset the stream position to the beginning
    output_stream.seek(0)

    return output_stream


def get_current_playback_info(sp):
    current_playback = sp.current_playback()

    if current_playback:
        # Extract track URL
        track_name = current_playback['item']['name']
        artist_name = current_playback['item']['artists'][0]['name']
        track_picture_url = current_playback['item']['album']['images'][0]['url']
        track_url = current_playback['item']['external_urls']['spotify']

        # Calculate time remaining in the song
        duration_ms = current_playback['item']['duration_ms']
        progress_ms = current_playback['progress_ms']

        # Convert time to minutes and seconds
        time_remaining_ms = duration_ms - progress_ms
        time_remaining_seconds = time_remaining_ms // 1000
        time_remaining_minutes = time_remaining_seconds // 60
        time_remaining_seconds %= 60

        # Calculate total song duration
        total_seconds = duration_ms // 1000
        total_minutes = total_seconds // 60
        total_seconds %= 60

        current_minutes = total_minutes - time_remaining_minutes
        current_seconds = total_seconds - time_remaining_seconds

        # If the current_seconds becomes negative, adjust it
        if current_seconds < 0:
            current_seconds += 60
            current_minutes -= 1

        # Return the track URL, time remaining, and total duration
        return {
            "track_name": track_name,
            "artist_name": artist_name,
            "track_picture_url": track_picture_url,
            "track_url": track_url,
            "current_time": f"{current_minutes}:{current_seconds:02}",
            "total_duration": f"{total_minutes}:{total_seconds:02}"
        }
    else:
        return "No music is currently playing."

class spotifyPlugin(plugin.Plugin):
    name = "SPOTIFY"
    helpable: ClassVar[bool] = False

    db: util.db.AsyncCollection
    auth_manager: SpotifyOAuth

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection("SPOTIFY")

        # Initialize auth_manager using self
        self.auth_manager = SpotifyOAuth(
            client_id=self.bot.config.CLIENT_ID,
            client_secret=self.bot.config.CLIENT_SECRET,
            redirect_uri='https://eyamika.vercel.app/callback',
            scope='user-library-read,user-top-read,user-read-recently-played,user-read-playback-state,user-read-currently-playing,user-read-private',
            cache_handler=None, 
            requests_timeout=60
        )

    async def get_data(self, key: str, value: Any) -> Optional[MutableMapping[str, Any]]:
        return await self.db.find_one({key: value})
    
    async def set_data(self, user_id: int, refresh_token: str, access_token: str, expires_at: str) -> None:
        await self.db.update_one({"user_id": user_id}, {"$set": {"refresh_token": refresh_token, "access_token": access_token, "expires_at": expires_at}}, upsert=True)

    async def get_info(self, user_id: int) -> Optional[str]:
      data = await self.get_data("user_id", user_id)
      if data:
        return data['refresh_token'], data['access_token'], data['expires_at']
      return None
      
    @command.filters(filters.private)
    async def cmd_authsp(self, ctx: command.Context) -> None:
        """Set the user's SPOTIFY info"""
        auth_url = self.auth_manager.get_authorize_url(state=ctx.msg.from_user.id)
        await ctx.respond(f"[AUTHORIZE]({auth_url})", parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

    @command.filters(filters.private | filters.group)
    async def cmd_cp(self, ctx: command.Context) -> None:
        """Show the user's SPOTIFY NOW"""
        async with ctx.action(ChatAction.TYPING):
            account_info = await self.get_info(ctx.msg.from_user.id)

            if account_info is None:
                await ctx.respond("SPOTIFY info not found.")
                return
            refresh_token, access_token, expires_at = account_info

            if expires_at < time.time():
                token_info = self.auth_manager.refresh_access_token(refresh_token)
                access_token = token_info['access_token']
                expires_at = time.time() + 3600
                await self.set_data(ctx.msg.from_user.id, refresh_token, access_token, expires_at)

            sp = spotipy.Spotify(access_token)
            playback_info = get_current_playback_info(sp)

            if playback_info != "No music is currently playing.":
                user = await self.bot.client.get_users(ctx.msg.from_user.id)
                if user.photo:
                    file = await self.bot.client.download_media(user.photo.big_file_id)
                    upfp = file
                else:
                    upfp = '/app/anjani/custom_plugins/pfp.jpg'
                # Generate a custom image using create_custom_image
                custom_image = create_custom_image(
                    track_picture_url=playback_info['track_picture_url'],
                    upfp=upfp,
                    track_name=playback_info['track_name'],
                    artist_name=playback_info['artist_name'],
                    current_time=playback_info['current_time'],
                    total_duration=playback_info['total_duration']
                )

                sptxt = f"[{ctx.msg.from_user.first_name}](tg://user?id={ctx.msg.from_user.id}) is currently listening to:\n\nTrack: {playback_info['track_name']}\nArtist: {playback_info['artist_name']}\nTime Current: {playback_info['current_time']}\nTotal Duration: {playback_info['total_duration']}\n\n[Track URL]({playback_info['track_url']})"

                await ctx.respond(sptxt, photo=custom_image)

            else:
                await ctx.respond("No music is currently playing.")
    
    @command.filters(filters.private | filters.group)
    async def cmd_toptracks(self, ctx: command.Context) -> None:
        """Show the user's top 5 tracks based on time range (s: short, m: medium, l: long)."""
        time_range_map = {
            's': 'short_term',
            'm': 'medium_term',
            'l': 'long_term'
        }

        time_range_arg = ctx.args[0].lower() if len(ctx.args) > 0 else 'medium_term'

        if time_range_arg not in time_range_map:
            await ctx.respond("Invalid time range. Please use 's' for short, 'm' for medium, or 'l' for long.")
            return

        time_range = time_range_map[time_range_arg]

        account_info = await self.get_info(ctx.msg.from_user.id)

        if account_info is None:
            await ctx.respond("SPOTIFY info not found.")
            return
        refresh_token, access_token, expires_at = account_info

        if expires_at < time.time():
            token_info = self.auth_manager.refresh_access_token(refresh_token)
            access_token = token_info['access_token']
            expires_at = time.time() + 3600
            await self.set_data(ctx.msg.from_user.id, refresh_token, access_token, expires_at)

        sp = spotipy.Spotify(access_token)
        top_tracks = sp.current_user_top_tracks(limit=5, offset=0, time_range=time_range)

        if top_tracks:
            top_tracks_info = "\n".join([f"{i + 1}. [{track['name']} by {', '.join(artist['name'] for artist in track['artists'])}]({track['external_urls']['spotify']})" for i, track in enumerate(top_tracks['items'])])
            await ctx.respond(f"Here are your top 5 tracks on Spotify ({time_range}):\n\n{top_tracks_info}", parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        else:
            await ctx.respond("No top tracks found.")
