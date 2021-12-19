import re
import typing

import dis_snek

from . import errors


class Converter:
    async def convert(self, ctx: dis_snek.MessageContext, argument: str):
        raise NotImplementedError("Derived classes need to implement this.")


_ID_REGEX = re.compile(r"([0-9]{15,20})$")


class IDConverter(Converter):
    @staticmethod
    def _get_id_match(argument):
        return _ID_REGEX.match(argument)


class SnowflakeConverter(IDConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.Snowflake_Type:
        match = self._get_id_match(argument) or re.match(
            r"<(?:@(?:!|&)?|#)([0-9]{15,20})>$", argument
        )

        if match is None:
            raise errors.BadArgument(argument)

        return int(match.group(1))


class MemberConverter(IDConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.Member:
        if not ctx.guild:
            raise errors.BadArgument("This command cannot be used in private messages.")

        match = self._get_id_match(argument) or re.match(
            r"<@!?([0-9]{15,20})>$", argument
        )
        result = None

        if match:
            try:
                result = await ctx.bot.get_member(int(match.group(1)), ctx.guild_id)
            except dis_snek.HTTPException:
                raise errors.BadArgument(f'Member "{argument}" not found.')
        elif ctx.guild.chunked:
            if len(argument) > 5 and argument[-5] == "#":
                result = next(
                    (m for m in ctx.guild.members if m.user.tag == argument), None
                )

            if not result:
                result = next(
                    (
                        m
                        for m in ctx.guild.members
                        if m.display_name == argument or m.user.username == argument
                    ),
                    None,
                )

        if not result:
            raise errors.BadArgument(f'Member "{argument}" not found.')

        return result


class UserConverter(IDConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.User:
        match = self._get_id_match(argument) or re.match(
            r"<@!?([0-9]{15,20})>$", argument
        )
        result = None

        if match:
            try:
                result = await ctx.bot.get_user(int(match.group(1)))
            except dis_snek.HTTPException:
                raise errors.BadArgument(f'User "{argument}" not found.')
        else:
            if len(argument) > 5 and argument[-5] == "#":
                result = next(
                    (u for u in ctx.bot.cache.user_cache.values() if u.tag == argument),
                    None,
                )

            if not result:
                result = next(
                    (
                        u
                        for u in ctx.bot.cache.user_cache.values()
                        if u.username == argument
                    ),
                    None,
                )

        if not result:
            raise errors.BadArgument(f'User "{argument}" not found.')

        return result


class ChannelConverter(IDConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.TYPE_ALL_CHANNEL:
        match = self._get_id_match(argument) or re.match(
            r"<#([0-9]{15,20})>$", argument
        )
        result = None

        if match:
            try:
                result = await ctx.bot.get_channel(int(match.group(1)))
            except dis_snek.HTTPException:
                raise errors.BadArgument(f'Channel "{argument}" not found.')
        elif ctx.guild:
            result = next((c for c in ctx.guild.channels if c.name == argument), None)

        if not result:
            raise errors.BadArgument(f'Channel "{argument}" not found.')

        return result


class TextChannelConverter(ChannelConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.TYPE_MESSAGEABLE_CHANNEL:
        result = await super().convert(ctx, argument)
        if (
            isinstance(result.type, dis_snek.enums.ChannelTypes)
            and not result.type.voice
        ) or result.type not in {2, 13}:
            return result  # type: ignore

        raise errors.BadArgument(f'Channel "{argument}" not found.')


class GuildChannelConverter(ChannelConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.TYPE_GUILD_CHANNEL:
        result = await super().convert(ctx, argument)
        if (
            isinstance(result.type, dis_snek.enums.ChannelTypes) and result.type.guild
        ) or result.type not in {1, 3}:
            return result  # type: ignore

        raise errors.BadArgument(f'Channel "{argument}" not found.')


class VoiceChannelConverter(ChannelConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.TYPE_VOICE_CHANNEL:
        result = await super().convert(ctx, argument)
        if (
            isinstance(result.type, dis_snek.enums.ChannelTypes) and result.type.voice
        ) or result.type in {2, 13}:
            return result  # type: ignore

        raise errors.BadArgument(f'Channel "{argument}" not found.')


class ThreadChannelConverter(ChannelConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.TYPE_THREAD_CHANNEL:
        result = await super().convert(ctx, argument)
        if (
            isinstance(result.type, dis_snek.enums.ChannelTypes)
            and result.type.value in {10, 11, 12}
        ) or result.type in {10, 11, 12}:
            return result  # type: ignore

        raise errors.BadArgument(f'Channel "{argument}" not found.')


class RoleConverter(IDConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.Role:
        if not ctx.guild:
            raise errors.BadArgument("This command cannot be used in private messages.")

        match = self._get_id_match(argument) or re.match(
            r"<@&([0-9]{15,20})>$", argument
        )
        result = None

        if match:
            try:
                result = await ctx.guild.get_role(int(match.group(1)))
            except dis_snek.HTTPException:
                raise errors.BadArgument(f'Role "{argument}" not found.')
        else:
            result = next(
                (r for r in ctx.guild.roles if r.name == argument),
                None,
            )

        if not result:
            raise errors.BadArgument(f'Role "{argument}" not found.')

        return result


class GuildConverter(IDConverter):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.Guild:
        match = self._get_id_match(argument)
        result = None

        if match:
            try:
                result = await ctx.bot.get_guild(int(match.group(1)))
            except dis_snek.HTTPException:
                raise errors.BadArgument(f'Guild "{argument}" not found.')
        else:
            result = next(
                (g for g in ctx.bot.guilds if g.name == argument),
                None,
            )

        if not result:
            raise errors.BadArgument(f'Guild "{argument}" not found.')

        return result
