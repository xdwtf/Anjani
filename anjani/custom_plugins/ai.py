""" AI Plugin """
import json, requests, urllib.parse, re, datetime

from typing import Any, ClassVar, Mapping, MutableMapping, Optional

from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiopath import AsyncPath

from anjani import command, filters, listener, plugin, util
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from pyrogram.enums.parse_mode import ParseMode

def ask(model, inputs):
    input = { "messages": inputs }
    response = requests.post(f"{API_BASE_URL}{model}", headers=headers, json=input)
    print(response.json())
    return response.json()

class aiPlugin(plugin.Plugin):
    name = "AI"
    helpable: ClassVar[bool] = False #True

    db: util.db.AsyncCollection

    async def on_load(self) -> None:
        self.db = self.bot.db.get_collection("AI")

    async def get_data(self, key: str, value: Any) -> Optional[MutableMapping[str, Any]]:
        return await self.db.find_one({key: value})
    
    async def set_data(self, user_id: int, account_id: str, api_token: str) -> None:
        await self.db.update_one({"user_id": user_id}, {"$set": {"account_id": account_id, "api_token": api_token}}, upsert=True)
    
    async def get_info(self, user_id: int) -> Optional[str]:
        data = await self.get_data("user_id", user_id)
        print(data)
        if data and "api_token" in data:
            print(data["account_id"])
            print(data["api_token"])
            return data["account_id"], data["api_token"]
        return None

    @command.filters(filters.private)
    async def cmd_setai(self, ctx: command.Context) -> None:
        """Set the user's AI info"""
        if len(ctx.args) < 2:
            await ctx.respond("Please provide two values as command-line arguments.")
            return

        account_id = ctx.args[0]
        api_token = ctx.args[1]
        await self.set_data(ctx.msg.from_user.id, account_id, api_token)
        await ctx.respond(f"AI info has been set as: {account_id} {api_token}")
    
    @command.filters(filters.private | filters.group)
    async def cmd_ai(self, ctx: command.Context) -> None:
        """WORKER AI API CALL"""
        print(ctx.input)
        if not ctx.input:
            return "Give me a message to send."
        if len(ctx.input) > 768:
            await ctx.respond("Please note that there is a 768 character limit for the replied message.")
            print("this return")
            return
        print(await self.get_info(ctx.msg.from_user.id))
        account_id, api_token = await self.get_info(ctx.msg.from_user.id)
        if not account_id:
            await ctx.respond("AI info not found. Please set your AI infousing /setai in PM")
            return
        API_BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/"
        headers = {"Authorization": "Bearer {api_token}"}
        inputs = [
            { "role": "system", "content": "You are a friendly assistant" },
            { "role": "user", "content": ctx.input}
        ];
        print(inputs)
        output = ask("@cf/meta/llama-2-7b-chat-int8", inputs)
        if 'result' in output and 'response' in output['result']:
            aimessage = output['result']['response']
            await ctx.respond(aimessage, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        else:
            await ctx.respond("Failed to retrieve AI response.")
