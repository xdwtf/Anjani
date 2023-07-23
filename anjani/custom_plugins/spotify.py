""" Spotify API Plugin """
import json
import requests
import urllib.parse

from typing import Any, ClassVar, Mapping, MutableMapping, Optional

from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiopath import AsyncPath

from anjani import command, filters, listener, plugin, util
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from pyrogram.enums.parse_mode import ParseMode

class SpotifyPlugin(plugin.Plugin):
    name = "SPOTIFY"
    helpable: ClassVar[bool] = True

    db: util.db.AsyncCollection

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection("SPOTIFY")

    async def get_data(self, key: str, value: Any) -> Optional[MutableMapping[str, Any]]:
        return await self.db.find_one({key: value})
    
    async def set_spotify_username(self, user_id: int, username: str) -> None:
        await self.db.update_one({"user_id": user_id}, {"$set": {"spotify_username": username}}, upsert=True)
    
    async def get_spotify_username(self, user_id: int) -> Optional[str]:
        data = await self.get_data("user_id", user_id)
        if data and "spotify_username" in data:
            return data["spotify_username"]
        return None

    async def authenticate_spotify(self, user_id: int) -> str:
        # Replace with the URL of your authentication server
        auth_server_url = "https://your-auth-server.com/auth"

        # Send a request to your authentication server to initiate the Spotify authentication process
        response = requests.get(auth_server_url + f"/{user_id}")
        auth_data = json.loads(response.text)

        if "error" in auth_data:
            raise Exception("Failed to initiate Spotify authentication")

        return auth_data["authorize_url"]

    @command.filters(filters.private, command.start)
    async def cmd_start(self, ctx: command.Context) -> None:
        """Start command to initiate the Spotify authentication process"""
        try:
            authorize_url = await self.authenticate_spotify(ctx.msg.from_user.id)
            await ctx.respond("Click the link below to authorize your Spotify account:\n\n" + authorize_url)
        except Exception as e:
            await ctx.respond("Error: " + str(e))

    @command.filters(filters.private | filters.group, aliases=["sp"])
    async def cmd_status(self, ctx: command.Context) -> None:
        """Show the user's Spotify status"""
        spotify_username = await self.get_spotify_username(ctx.msg.from_user.id)

        if not spotify_username:
            await ctx.respond("Spotify username not found. Please authorize your Spotify account using /start in PM")
            return

        try:
            # Replace with the URL of your authentication server
            auth_server_url = "https://your-auth-server.com/xyz"
            response = requests.get(auth_server_url + f"/{ctx.msg.from_user.id}")
            data = json.loads(response.text)

            if "error" in data:
                raise Exception("Failed to fetch Spotify status")

            access_token = data["access_token"]

            # Implement logic to retrieve and display Spotify status using the access token and Spotify Web API
            # ...

            await ctx.respond("Spotify status is not implemented yet.")
        except Exception as e:
            await ctx.respond("Error: " + str(e))

    @listener.filters(filters.regex(r"/callback\?code=.+"))
    async def on_callback_received(self, ctx: listener.Context) -> None:
        """Handle the Spotify API callback to exchange the authorization code for tokens"""
        # Handle the Spotify API callback as before
        # ...

        # Save the access token and refresh token to the KV store with the user's ID as the key
        user_data = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"]
        }
        await self.db.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)

        await ctx.respond("Spotify account successfully authorized.")
