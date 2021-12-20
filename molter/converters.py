import re
import typing

import dis_snek

from . import errors

T_co = typing.TypeVar("T_co", covariant=True)


@typing.runtime_checkable
class Converter(typing.Protocol[T_co]):
    async def convert(self, ctx: dis_snek.MessageContext, argument: str) -> T_co:
        raise NotImplementedError("Derived classes need to implement this.")


_ID_REGEX = re.compile(r"([0-9]{15,20})$")


class IDConverter(Converter[T_co]):
    @staticmethod
    def _get_id_match(argument):
        return _ID_REGEX.match(argument)


class SnowflakeConverter(IDConverter[dis_snek.SnowflakeObject]):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.SnowflakeObject:
        match = self._get_id_match(argument) or re.match(
            r"<(?:@(?:!|&)?|#)([0-9]{15,20})>$", argument
        )

        if match is None:
            raise errors.BadArgument(argument)

        return dis_snek.SnowflakeObject(int(match.group(1)))  # type: ignore


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
                pass
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
                pass
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


class ChannelConverter(IDConverter[T_co]):
    def _check(self, result: dis_snek.BaseChannel):
        return True

    async def convert(
        self,
        ctx: dis_snek.MessageContext,
        argument: str,
    ) -> T_co:
        match = self._get_id_match(argument) or re.match(
            r"<#([0-9]{15,20})>$", argument
        )
        result = None

        if match:
            try:
                result = await ctx.bot.get_channel(int(match.group(1)))
            except dis_snek.HTTPException:
                pass
        elif ctx.guild:
            result = next((c for c in ctx.guild.channels if c.name == argument), None)

        if not result:
            raise errors.BadArgument(f'Channel "{argument}" not found.')

        if self._check(result):
            return result  # type: ignore

        raise errors.BadArgument(f'Channel "{argument}" not found.')


class BaseChannelConverter(ChannelConverter[dis_snek.BaseChannel]):
    pass


class TextChannelConverter(ChannelConverter[dis_snek.TYPE_MESSAGEABLE_CHANNEL]):
    def _check(self, result: dis_snek.BaseChannel):
        return (
            isinstance(result.type, dis_snek.enums.ChannelTypes)
            and not result.type.voice
        ) or result.type not in {2, 13}


class GuildChannelConverter(ChannelConverter[dis_snek.GuildChannel]):
    def _check(self, result: dis_snek.BaseChannel):
        return isinstance(result, dis_snek.GuildChannel)


class GuildTextConverter(ChannelConverter[dis_snek.GuildText]):
    def _check(self, result: dis_snek.BaseChannel):
        return isinstance(result, dis_snek.GuildText)


class VoiceChannelConverter(ChannelConverter[dis_snek.VoiceChannel]):
    def _check(self, result: dis_snek.BaseChannel):
        return isinstance(result, dis_snek.VoiceChannel)


class ThreadChannelConverter(ChannelConverter[dis_snek.ThreadChannel]):
    def _check(self, result: dis_snek.BaseChannel):
        return isinstance(result, dis_snek.ThreadChannel)


class RoleConverter(IDConverter[dis_snek.Role]):
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
                pass
        else:
            result = next(
                (r for r in ctx.guild.roles if r.name == argument),
                None,
            )

        if not result:
            raise errors.BadArgument(f'Role "{argument}" not found.')

        return result


class GuildConverter(IDConverter[dis_snek.Guild]):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.Guild:
        match = self._get_id_match(argument)
        result = None

        if match:
            try:
                result = await ctx.bot.get_guild(int(match.group(1)))
            except dis_snek.HTTPException:
                pass
        else:
            result = next(
                (g for g in ctx.bot.guilds if g.name == argument),
                None,
            )

        if not result:
            raise errors.BadArgument(f'Guild "{argument}" not found.')

        return result


class EmojiConverter(IDConverter[dis_snek.Emoji]):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.Emoji:

        match = self._get_id_match(argument) or re.match(
            r"<a?:[a-zA-Z0-9\_]{1,32}:([0-9]{15,20})>$", argument
        )

        if match:
            emoji_animated = bool(match.group(1))
            emoji_name = match.group(2)
            emoji_id = int(match.group(3))

            return dis_snek.Emoji(id=emoji_id, name=emoji_name, animated=emoji_animated)  # type: ignore

        raise errors.BadArgument(f'Couldn\'t convert "{argument}" to Emoji.')


class CustomEmojiConverter(IDConverter[dis_snek.CustomEmoji]):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.CustomEmoji:
        if not ctx.guild:
            raise errors.BadArgument("This command cannot be used in private messages.")

        match = self._get_id_match(argument) or re.match(
            r"<a?:[a-zA-Z0-9\_]{1,32}:([0-9]{15,20})>$", argument
        )
        result = None

        if match:
            try:
                result = await ctx.guild.get_custom_emoji(int(match.group(1)))
            except dis_snek.HTTPException:
                pass
        else:
            emojis = await ctx.guild.get_all_custom_emojis()
            result = next((e for e in emojis if e.name == argument))

        if not result:
            raise errors.BadArgument(f'Emoji "{argument}" not found.')

        return result


SNEK_OBJECT_TO_CONVERTER: dict[type, Converter] = {
    dis_snek.SnowflakeObject: SnowflakeConverter,
    dis_snek.Member: MemberConverter,
    dis_snek.User: UserConverter,
    dis_snek.BaseChannel: BaseChannelConverter,
    dis_snek.GuildChannel: GuildChannelConverter,
    dis_snek.GuildText: GuildTextConverter,
    dis_snek.VoiceChannel: VoiceChannelConverter,
    dis_snek.ThreadChannel: ThreadChannelConverter,
    dis_snek.Role: RoleConverter,
    dis_snek.Guild: GuildConverter,
    dis_snek.Emoji: EmojiConverter,
    dis_snek.CustomEmoji: CustomEmojiConverter,
}
