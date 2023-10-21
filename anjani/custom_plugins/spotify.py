""" spotify Plugin """
import json, requests, urllib.parse, re, datetime
from typing import Any, ClassVar, Mapping, MutableMapping, Optional
from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiopath import AsyncPath
from anjani import command, filters, listener, plugin, util
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from pyrogram.enums.parse_mode import ParseMode

import time
import spotipy
import datetime
from spotipy.oauth2 import SpotifyOAuth

# Create the auth manager object with client ID, secret, redirect URI, and scopes
auth_manager = SpotifyOAuth(client_id, client_secret, redirect_uri='https://localhost:8000/callback',
                            scope='user-library-read,user-top-read,user-read-recently-played,user-read-playback-state,user-modify-playback-state,user-read-currently-playing,playlist-read-private,playlist-modify-public,playlist-modify-private,user-follow-read,user-read-email,user-read-private',
                            cache_handler=None)

def get_current_playback_info(sp):
    current_playback = sp.current_playback()

    if current_playback:
        # Extract track URL
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

        # Return the track URL, time remaining, and total duration
        return {
            "track_url": track_url,
            "time_remaining": f"{time_remaining_minutes}:{time_remaining_seconds:02}",
            "total_duration": f"{total_minutes}:{total_seconds:02}"
        }
    else:
        return "No music is currently playing."

class spotifyPlugin(plugin.Plugin):
    name = "SPOTIFY"
    helpable: ClassVar[bool] = False

    db: util.db.AsyncCollection

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection("SPOTIFY")

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
    async def cmd_regsp(self, ctx: command.Context) -> None:
        """Set the user's AI info"""
        if len(ctx.args) < 2:
            await ctx.respond("Please provide value as `/regsp refresh_token`")
            return

        refresh_token = ctx.args[0]
        token_info = auth_manager.refresh_access_token(refresh_token)
        access_token = token_info['access_token']
        expires_at = time.time() + 3600
        
        await self.set_data(ctx.msg.from_user.id, refresh_token, access_token, expires_at)
        await ctx.respond(f"SPOTIFY info has been set.")

    @command.filters(filters.private | filters.group, aliases=["np"])
    async def cmd_now(self, ctx: command.Context) -> None:
        """Show the user's SPOTIFY NOW"""
        account_info = await self.get_info(ctx.msg.from_user.id)
        if account_info is None:
            await ctx.respond("SPOTIFY info not found.")
            return
        refresh_token, access_token, expires_at = account_info
        if expires_at < time.time():
            token_info = auth_manager.refresh_access_token(refresh_token)
            access_token = token_info['access_token']
            expires_at = time.time() + 3600
            await self.set_data(ctx.msg.from_user.id, refresh_token, access_token, expires_at)
        sp = spotipy.Spotify(access_token)
        playback_info = get_current_playback_info(sp)
        if playback_info != "No music is currently playing.":
            message = f"Track URL: {playback_info['track_url']}\nTime Remaining: {playback_info['time_remaining']}\nTotal Duration: {playback_info['total_duration']}"
        else:
            message = playback_info
            await ctx.respond(message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)