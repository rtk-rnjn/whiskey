from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from bot import Whiskey

from constants import COLOR
from discord import TextChannel, Member, Role, Embed
from discord.ext import commands
from models import Response, ResponseData, ArrayAppend, ArrayRemove
from .utils import has_not_done_setup, has_done_setup, string_input, truncate_string


class Responses(commands.Cog):
    def __init__(self, bot: Whiskey):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_not_done_setup()
    async def rsetup(self, ctx, *channels: TextChannel):
        """setup auto response"""
        if not channels:
            return await ctx.send(
                f"You forgot the channels argument, do it like `{ctx.prefix}rsetup #channel1 #channel2 ...`"
            )

        for channel in channels:
            self.bot.support_channels.add(channel.id)

        query = "INSERT INTO response_info (guild_id,valid_channel_ids,ignored_ids ,allow_all) VALUES ($1, $2, $3,$4)"
        await self.bot.db.execute(query, ctx.guild.id, [channel.id for channel in channels], [], True)
        await ctx.send(f"Auto-response setup successful.\n\nUse `{ctx.prefix}rcreate` to create responses.")

    @commands.command()
    @has_done_setup()
    async def rcreate(self, ctx):
        """create a smart auto response"""

        def check(msg):
            return msg.author == ctx.author and ctx.channel == msg.channel

        record = await Response.get(pk=ctx.guild.id)
        if not record.all and not ctx.author.guild_permissions.manage_guild:
            return await ctx.error("You need manage_server permissions to create auto-response. ")

        await ctx.send("Enter the auto-response keywords. Separate them with a comma`(,)`.")
        keywords = await string_input(ctx, check)

        keywords = keywords.strip().split(",")
        keywords = [k.strip() for k in keywords if not len(k) >= 50]

        await ctx.send("What should be the response for those keywords?")
        response = await string_input(ctx, check)
        response = truncate_string(response, 2000)

        res = await ResponseData.create(keywords=keywords, content=response, author_id=ctx.author.id)
        await record.data.add(res)
        return await ctx.send(
            "Response was created successfully." f"\n\nIt can take upto a minute to show that response."
        )

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def rperm(self, ctx):
        """allow/deny everyone to create responses"""
        record = await Response.get(pk=ctx.guild.id)
        await Response.filter(pk=ctx.guild.id).update(allow_all=not record.allow_all)
        if not record.allow_all:
            return await ctx.send("Now anyone can create auto-responses")

        return await ctx.send("From now on, people need manage_server permissions to create auto responses")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def rlist(self, ctx):
        await ctx.send("in development")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def rdelete(self, ctx):
        pass

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def rchannel(self, ctx, *, channel: TextChannel):
        """add or remove a channel to valid support channels"""

        record = await Response.get(pk=ctx.guild.id)
        func = (ArrayAppend, ArrayRemove)[channel.id in record.valid_channel_ids]
        await Response.filter(pk=ctx.guild.id).update(valid_channel_ids=func("valid_channel_ids", channel.id))
        if channel.id in record.valid_channel_ids:
            self.bot.support_channels.discard(channel.id)
            return await ctx.send(f"{channel.mention} is no longer a response channel.")

        self.bot.support_channels.add(channel.id)
        return await ctx.send(f"{channel.mention} added to response channel.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def rignore(self, ctx, member_or_role: typing.Union[Member, Role]):
        """ignore a member or role in support channel"""
        id = member_or_role.id

        record = await Response.get(pk=ctx.guild.id)
        func = (ArrayAppend, ArrayRemove)[id in record.ignored_ids]
        await Response.filter(pk=ctx.guild.id).update(ignored_ids=func("ignored_ids", id))
        if id in record.ignored_ids:
            return await ctx.send(f"{member_or_role.mention} is no longer ignored")

        return await ctx.send(f"{member_or_role.mention} will be ignored")

    @commands.command()
    @has_done_setup()
    @commands.bot_has_permissions(embed_links=True)
    async def rconfig(self, ctx):
        """Get current server's smart response config"""

        record = await Response.get(pk=ctx.guild.id)

        _list = []
        for idx in record.ignored_ids:
            val = self.bot.get_user(idx) or ctx.guild.get_role(idx)
            _list.append(getattr(val, "mention", "unknown"))

        embed = Embed(color=COLOR, title="Smart-Response config")
        if record.valid_channel_ids:
            embed.add_field(name="Channels", value=", ".join(record.valid_channels))

        embed.add_field(name="Allow everyone to create", value=record.allow_all)
        if _list:
            embed.add_field(name="Ignored", value=", ".join(_list), inline=False)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Responses(bot))
