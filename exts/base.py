"""
Base extension for qrm
---
Copyright (C) 2019-2021 classabbyamp, 0x5c

SPDX-License-Identifier: LiLiQ-Rplus-1.1
"""


import random
import re
from typing import Union, Iterable
import pathlib

import discord
import discord.ext.commands as commands
from discord.ext.commands import Command, CommandError

import info
import common as cmn
from data import options as opt


class QrmHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            "help": "Shows help about qrm or a command",
            "aliases": ["h"],
            "category": cmn.BoltCats.INFO
            })
        self.verify_checks = True
        self.context: commands.Context

    async def filter_commands(self, commands: Iterable[Command], **kwargs) -> list[Command]:
        def sort_by_cat(cmds):
            ret = []
            bolt_cmds = {}
            for c in cmds:
                cat = c.__original_kwargs__.get("category", cmn.BoltCats.OTHER)
                if isinstance(cat, cmn.BoltCats):
                    if cat in bolt_cmds:
                        bolt_cmds[cat].append(c)
                    else:
                        bolt_cmds[cat] = [c]
                else:
                    ret.append(c)

            ret.sort(key=lambda c: c.__original_kwargs__["category"].name)

            for cat in cmn.BoltCats:
                if cat in bolt_cmds:
                    ret += sorted(bolt_cmds[cat], key=lambda c: c.name)

            return ret

        iterator = commands if self.show_hidden else filter(lambda c: not c.hidden, commands)

        if not self.verify_checks:
            return sort_by_cat(iterator)

        async def predicate(cmd):
            try:
                return await cmd.can_run(self.context)
            except CommandError:
                return False

        cmds = []
        for cmd in iterator:
            if await predicate(cmd):
                cmds.append(cmd)

        return sort_by_cat(cmds)

    async def get_bot_mapping(self):
        bot = self.context.bot
        mapping = {}

        for cmd in await self.filter_commands(bot.commands):
            cat = cmd.__original_kwargs__.get("category", cmn.BoltCats.OTHER)
            if cat in mapping:
                mapping[cat].append(cmd)
            else:
                mapping[cat] = [cmd]
        return mapping

    async def get_command_signature(self, command):
        parent = command.full_parent_name
        if command.aliases != []:
            aliases = ", ".join(command.aliases)
            fmt = command.name
            if parent:
                fmt = f"{parent} {fmt}"
            alias = fmt
            return f"{self.context.prefix}{alias} {command.signature}\n    *Aliases:* {aliases}"
        alias = command.name if not parent else f"{parent} {command.name}"
        return f"{self.context.prefix}{alias} {command.signature}"

    async def send_error_message(self, error):
        embed = cmn.embed_factory(self.context)
        embed.title = "qrm Help Error"
        embed.description = error
        embed.colour = cmn.colours.bad
        await self.context.send(embed=embed)

    async def send_bot_help(self, mapping):
        embed = cmn.embed_factory(self.context)
        embed.title = "qrm Help"
        embed.description = (f"For command-specific help and usage, use `{self.context.prefix}help [command name]`."
                             " Many commands have shorter aliases.")
        if isinstance(self.context.bot.command_prefix, list):
            embed.description += (" All of the following prefixes work with the bot: `"
                                  + "`, `".join(self.context.bot.command_prefix) + "`.")
        mapping = await mapping

        for cat, cmds in mapping.items():
            if cmds == []:
                continue
            names = sorted([cmd.name for cmd in cmds])
            if cat is not None:
                embed.add_field(name=cat.value, value=", ".join(names), inline=False)
            else:
                embed.add_field(name="Other", value=", ".join(names), inline=False)
        await self.context.send(embed=embed)

    async def send_command_help(self, command):
        if self.verify_checks:
            if not await command.can_run(self.context):
                raise commands.CheckFailure
            for p in command.parents:
                if not await p.can_run(self.context):
                    raise commands.CheckFailure
        embed = cmn.embed_factory(self.context)
        embed.title = await self.get_command_signature(command)
        embed.description = command.help
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        if self.verify_checks and not await group.can_run(self.context):
            raise commands.CheckFailure
        embed = cmn.embed_factory(self.context)
        embed.title = await self.get_command_signature(group)
        embed.description = group.help
        for cmd in await self.filter_commands(group.commands, sort=True):
            embed.add_field(name=await self.get_command_signature(cmd), value=cmd.help if cmd.help else "",
                            inline=False)
        await self.context.send(embed=embed)


class BaseCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.changelog = parse_changelog()
        commit_file = pathlib.Path("git_commit")
        dot_git = pathlib.Path(".git")
        if commit_file.is_file():
            with commit_file.open() as f:
                self.commit = f.readline().strip()[:7]
        elif dot_git.is_dir():
            head_file = pathlib.Path(dot_git, "HEAD")
            if head_file.is_file():
                with head_file.open() as hf:
                    head = hf.readline().split(": ")[1].strip()
                branch_file = pathlib.Path(dot_git, head)
                if branch_file.is_file():
                    with branch_file.open() as bf:
                        self.commit = bf.readline().strip()[:7]
        else:
            self.commit = ""
        self.donation_links = {
            "Ko-Fi": "https://ko-fi.com/miaowware",
            "LiberaPay": "https://liberapay.com/miaowware",
            "GitHub Sponsors": "https://github.com/sponsors/classabbyamp",
        }
        self.bot_invite = ""
        if self.bot.user:
            self.bot_invite = (f"https://discordapp.com/oauth2/authorize?client_id={self.bot.user.id}"
                               f"&scope=bot&permissions={opt.invite_perms}")

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.bot_invite and self.bot.user:
            self.bot_invite = (f"https://discordapp.com/oauth2/authorize?client_id={self.bot.user.id}"
                               f"&scope=bot&permissions={opt.invite_perms}")

    @commands.command(name="info", aliases=["about"], category=cmn.BoltCats.INFO)
    async def _info(self, ctx: commands.Context):
        """Shows info about qrm."""
        embed = cmn.embed_factory(ctx)
        embed.title = "About qrm"
        embed.description = info.description
        embed.add_field(name="Authors", value=", ".join(info.authors))
        embed.add_field(name="License", value=info.license)
        embed.add_field(name="Version", value=f"v{info.release} {'(`' + self.commit + '`)' if self.commit else ''}")
        embed.add_field(name="Contributing", value=info.contributing, inline=False)
        embed.add_field(name="Official Server", value=info.bot_server, inline=False)
        embed.add_field(name="Donate", value="\n".join(f"{k}: {v}" for k, v in self.donation_links.items()),
                        inline=False)
        if opt.enable_invite_cmd and (await self.bot.application_info()).bot_public:
            embed.add_field(name="Invite qrm to Your Server", value=self.bot_invite, inline=False)
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=str(self.bot.user.avatar.url))
        await ctx.send(embed=embed)

    @commands.command(name="ping", aliases=["beep"], category=cmn.BoltCats.INFO)
    async def _ping(self, ctx: commands.Context):
        """Shows the current latency to the discord endpoint."""
        embed = cmn.embed_factory(ctx)
        content = ""
        if ctx.invoked_with == "beep":
            embed.title = "**Boop!**"
        else:
            content = ctx.message.author.mention if random.random() < 0.05 else ""
            embed.title = "🏓 **Pong!**"
        embed.description = f"Current ping is {self.bot.latency*1000:.1f} ms"
        await ctx.send(content, embed=embed)

    @commands.command(name="changelog", aliases=["clog"], category=cmn.BoltCats.INFO)
    async def _changelog(self, ctx: commands.Context, version: str = "latest"):
        """Shows what has changed in a bot version. Defaults to the latest version."""
        embed = cmn.embed_factory(ctx)
        embed.title = "qrm Changelog"
        embed.description = ("For a full listing, visit [Github](https://"
                             "github.com/miaowware/qrm2/blob/master/CHANGELOG.md).")
        changelog = self.changelog
        vers = list(changelog.keys())
        vers.remove("Unreleased")

        version = version.lower()

        if version == "latest":
            version = info.release
        if version == "unreleased":
            version = "Unreleased"

        try:
            log = changelog[version]
        except KeyError:
            embed.title += ": Version Not Found"
            embed.description += "\n\n**Valid versions:** latest, "
            embed.description += ", ".join(vers)
            embed.colour = cmn.colours.bad
            await ctx.send(embed=embed)
            return

        if "date" in log:
            embed.description += f"\n\n**v{version}** ({log['date']})"
        else:
            embed.description += f"\n\n**v{version}**"
        embed = await format_changelog(log, embed)

        await ctx.send(embed=embed)

    @commands.command(name="issue", category=cmn.BoltCats.INFO)
    async def _issue(self, ctx: commands.Context):
        """Shows how to create a bug report or feature request about the bot."""
        embed = cmn.embed_factory(ctx)
        embed.title = "Found a bug? Have a feature request?"
        embed.description = """Submit an issue on the [issue tracker](https://github.com/miaowware/qrm2/issues)!

                            All issues and requests related to resources (including maps, band charts, data) \
                            should be added in \
                            [miaowware/qrm-resources](https://github.com/miaowware/qrm-resources/issues)."""
        await ctx.send(embed=embed)

    @commands.command(name="donate", aliases=["tip"], category=cmn.BoltCats.INFO)
    async def _donate(self, ctx: commands.Context):
        """Shows ways to help support development of the bot via donations."""
        embed = cmn.embed_factory(ctx)
        embed.title = "Help Support qrm's Development!"
        embed.description = ("Donations are always appreciated, and help with server and infrastructure costs."
                             "\nThank you for your support!")
        for title, url in self.donation_links.items():
            embed.add_field(name=title, value=url, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="invite", enabled=opt.enable_invite_cmd, category=cmn.BoltCats.INFO)
    async def _invite(self, ctx: commands.Context):
        """Generates a link to invite the bot to a server."""
        if not (await self.bot.application_info()).bot_public:
            raise commands.DisabledCommand
        embed = cmn.embed_factory(ctx)
        embed.title = "Invite qrm to Your Server!"
        embed.description = self.bot_invite
        await ctx.send(embed=embed)

    @commands.command(name="echo", aliases=["e"], category=cmn.BoltCats.ADMIN)
    @commands.check(cmn.check_if_owner)
    async def _echo(self, ctx: commands.Context,
                    channel: Union[cmn.GlobalChannelConverter, commands.UserConverter], *, msg: str):
        """Sends a message in a channel as qrm. Accepts channel/user IDs/mentions.
        Channel names are current-guild only.
        Does not work with the ID of the bot user."""
        if isinstance(channel, discord.ClientUser):
            raise commands.BadArgument("Can't send to the bot user!")
        await channel.send(msg)


def parse_changelog():
    changelog = {}
    ver = ""
    heading = ""

    with open("CHANGELOG.md") as changelog_file:
        for line in changelog_file.readlines():
            if line.strip() == "":
                continue
            if re.match(r"##[^#]", line):
                ver_match = re.match(r"\[(.+)\](?: - )?(\d{4}-\d{2}-\d{2})?", line.lstrip("#").strip())
                if ver_match is not None:
                    ver = ver_match.group(1)
                    changelog[ver] = dict()
                    if ver_match.group(2):
                        changelog[ver]["date"] = ver_match.group(2)
            elif re.match(r"###[^#]", line):
                heading = line.lstrip("#").strip()
                changelog[ver][heading] = []
            elif ver != "" and heading != "":
                if line.startswith("-"):
                    changelog[ver][heading].append(line.lstrip("-").strip())
    return changelog


async def format_changelog(log: dict, embed: discord.Embed):
    for header, lines in log.items():
        formatted = ""
        if header != "date":
            for line in lines:
                formatted += f"- {line}\n"
            embed.add_field(name=f"**{header}**", value=formatted, inline=False)
    return embed


def setup(bot: commands.Bot):
    bot.add_cog(BaseCog(bot))
    bot._original_help_command = bot.help_command
    bot.help_command = QrmHelpCommand()


def teardown(bot: commands.Bot):
    bot.help_command = bot._original_help_command
