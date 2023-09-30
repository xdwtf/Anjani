""" AI Plugin """
import json, requests, urllib.parse, re, datetime

from typing import Any, ClassVar, Mapping, MutableMapping, Optional

from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiopath import AsyncPath

from anjani import command, filters, listener, plugin, util
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from pyrogram.enums.parse_mode import ParseMode

class aiPlugin(plugin.Plugin):
    name = "AI"
    helpable: ClassVar[bool] = false #True

    db: util.db.AsyncCollection

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection("AI")

    async def get_data(self, key: str, value: Any) -> Optional[MutableMapping[str, Any]]:
        return await self.db.find_one({key: value})
    
    async def set_data(self, user_id: int, username: str) -> None:
        await self.db.update_one({"user_id": user_id}, {"$set": {"account_id": account_id, "api_token": api_token}}, upsert=True)
    
    async def get_info(self, user_id: int) -> Optional[str]:
        data = await self.get_data("user_id", user_id)
        if data and "account_id" in data and "api_token" in data:
            return data["account_id"], data["api_token"]
        return None

    @command.filters(filters.private)
    async def cmd_setAI(self, ctx: command.Context) -> None:
        """Set the user's AI info"""
        print(ctx.args)
        if len(ctx.args) < 1:
            await ctx.respond("Please provide two values as command-line arguments.")
            return

        account_id = ctx.args[0]
        api_token = ctx.args[1]
        await self.set_data(ctx.msg.from_user.id, account_id, api_token)
        await ctx.respond(f"AI info has been set as: {account_id} {api_token}")
