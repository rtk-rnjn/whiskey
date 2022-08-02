from __future__ import annotations

import typing
from cogs.utils import inputs

if typing.TYPE_CHECKING:
    from bot import Whiskey

from constants import COLOR
from discord import TextChannel, Member, Role, Embed
from discord.ext import commands
from models import Response, ResponseData, ArrayAppend, ArrayRemove
from .utils import (
    has_not_done_setup,
    has_done_setup,
    string_input,
    truncate_string,
    aenumerate,
    Pages
)


class Responses(commands.Cog):
    def __init__(self, bot: Whiskey) -> None:
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_not_done_setup()
    async def rsetup(self, ctx: commands.Context, *channels: TextChannel) -> None:
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
    @commands.bot_has_guild_permissions(manage_messages=True, embed_links=True, add_reactions=True)
    async def rcreate(self, ctx: commands.Context) -> None:
        """create a smart auto response"""

        def check(msg):
            return msg.author == ctx.author and ctx.channel == msg.channel

        record = await Response.get(pk=ctx.guild.id)
        if not record.all and not ctx.author.guild_permissions.manage_guild:
            return await ctx.error("You need manage_server permissions to create auto-response. ")

        await ctx.send("Enter the auto-response keywords. Separate them with a comma`(,)`.")
        keywords = await string_input(ctx, check)

        keywords = keywords.strip().split(",")
        keywords = [k.strip() for k in keywords if len(k) < 100]

        cmds = [cmd.qualified_name for cmd in self.bot.walk_commands()]

        for keyword in keywords:
            if bool(await record.data.filter(keywords__icontains=keyword)):
                return await ctx.send(f"There is already a keyword with name `{keyword}`")

            if keyword in cmds:
                return await ctx.send(f"`{keyword}` is a reserved keyword.")

        await ctx.send("What should be the response for those keywords?")
        response = await string_input(ctx, check, timeout=300)
        response = truncate_string(response, 3080)

        res = await ResponseData.create(keywords=keywords, content=response, author_id=ctx.author.id)
        await record.data.add(res)
        return await ctx.send(
            "Response was created successfully." f"\n\nIt can take upto a minute to show that response."
        )

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def rperm(self, ctx: commands.Context) -> None:
        """allow/deny everyone to create responses"""
        record = await Response.get(pk=ctx.guild.id)
        await Response.filter(pk=ctx.guild.id).update(allow_all=not record.allow_all)
        return (
            await ctx.send(
                "From now on, people need manage_server permissions to create auto responses"
            )
            if record.allow_all
            else await ctx.send("Now anyone can create auto-responses")
        )

    @commands.command()
    @has_done_setup()
    async def rlist(self, ctx: commands.Context) -> None:
        """list of all response this server has"""
        main_record = await Response.get(pk=ctx.guild.id)

        _list = []
        async for idx, record in aenumerate(main_record.data.all().order_by("id")):
            keywords = ", ".join(record.keywords)
            _list.append(f"`{idx:02}` {truncate_string(keywords, 50)} (ID: {record.id})\n")

        paginator = Pages(ctx, title=f"Total Response: {len(_list)}", entries=_list, per_page=10, show_entry_count=True)
        await paginator.paginate()

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def rdelete(self, ctx: commands.Context, response_id: int)-> None:
        """delete a smart response"""
        main_record = await Response.get(pk=ctx.guild.id)
        res = await main_record.data.filter(pk=response_id).first()
        if not res:
            return await ctx.send("response id is invalid")

        await ResponseData.filter(pk=res.id).delete()
        await ctx.send("done")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def rstats(self, ctx: commands.Context, response_id: int)-> None:
        """stats of a response"""
        main_record = await Response.get(pk=ctx.guild.id)
        res = await main_record.data.filter(pk=response_id).first()
        if not res:
            return await ctx.send("response id is invalid")

        embed = Embed(
            color=COLOR,
            description=f"This response was written by {res.author} <t:{int(res.created_at.timestamp())}:R> \nIt has been used {res.uses} times",
        )
        embed.add_field(name="keywords", value="\n".join(res.keywords))
        embed.set_footer(text=f"👍: {res.upvote}   👎: {res.downvote}")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def rchannel(self, ctx: commands.Context, *, channel: TextChannel) -> None:
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
    async def rignore(self, ctx: commands.Context, member_or_role: typing.Union[Member, Role])-> None:
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
    async def rconfig(self, ctx: commands.Context) -> None:
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

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @has_done_setup()
    async def redit(self, ctx: commands.Context, response_id: int, option: str = None) -> None:
        """edit a response content or keywords"""
        main_record = await Response.get(pk=ctx.guild.id)
        res = await main_record.data.filter(pk=response_id).first()
        if not res:
            return await ctx.send("response id is invalid")

        if not option or option.lower() not in ("keyword", "content"):
            return await ctx.send("pls enter a valid option. It can be `keyword` or `content`")

        def check(msg):
            return msg.author == ctx.author and ctx.channel == msg.channel

        if option.lower() == "keyword":
            await ctx.send(
                f"please enter the new keywords to append or remove from id:{response_id}, separate them with comman(,)"
            )

            keywords = await string_input(ctx, check=check)

            keywords = keywords.strip().split(",")
            keywords = [k.strip() for k in keywords if len(k) < 100]

            cmds = [cmd.qualified_name for cmd in self.bot.walk_commands()]

            valid_keywords = set()

            for keyword in keywords:
                if (
                    not bool(
                        await main_record.data.filter(keywords__icontains=keyword)
                    )
                    and keyword not in cmds
                ):
                    if keyword in res.keywords[:]:
                        res.remove(keyword)
                    else:
                        valid_keywords.add(keyword)

            valid_keywords.update(set(res.keywords))
            query = "UPDATE response_data SET keywords = $1 WHERE id = $2"
            await self.bot.db.execute(query, valid_keywords, res.id)
            await ctx.send("keywords updated.")
            return

        await ctx.send("please enter the new content for the smart response.")

        content = await string_input(ctx, check=check, timeout=300)
        content = truncate_string(content, 3080)
        await self.bot.db.execute("UPDATE response_data SET content = $1 WHERE id = $2", content, res.id)
        await ctx.send("content updated.")


async def setup(bot):
    await bot.add_cog(Responses(bot))
