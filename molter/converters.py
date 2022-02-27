import re
import typing

import dis_snek

from . import errors

T = typing.TypeVar("T")
T_co = typing.TypeVar("T_co", covariant=True)


@typing.runtime_checkable
class Converter(typing.Protocol[T_co]):
    async def convert(self, ctx: dis_snek.MessageContext, argument: str) -> T_co:
        raise NotImplementedError("Derived classes need to implement this.")


class LiteralConverter(Converter):
    values: typing.Dict

    def __init__(self, args: typing.Any):
        self.values = {arg: type(arg) for arg in args}

    async def convert(self, ctx: dis_snek.MessageContext, argument: str):
        for arg, converter in self.values.items():
            try:
                if arg == converter(argument):
                    return argument
            except Exception:
                continue

        literals_list = [str(a) for a in self.values.keys()]
        literals_str = ", ".join(literals_list[:-1]) + f", or {literals_list[-1]}"
        raise errors.BadArgument(
            f'Could not convert "{argument}" into one of {literals_str}.'
        )


_ID_REGEX = re.compile(r"([0-9]{15,})$")


class IDConverter(Converter[T_co]):
    @staticmethod
    def _get_id_match(argument):
        return _ID_REGEX.match(argument)


class SnowflakeConverter(IDConverter[dis_snek.SnowflakeObject]):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.SnowflakeObject:
        match = self._get_id_match(argument) or re.match(
            r"<(?:@(?:!|&)?|#)([0-9]{15,})>$", argument
        )

        if match is None:
            raise errors.BadArgument(argument)

        return dis_snek.SnowflakeObject(int(match.group(1)))  # type: ignore


class MemberConverter(IDConverter[dis_snek.Member]):
    def _get_member_from_list(self, members: list[dis_snek.Member], argument: str):
        result = None
        if len(argument) > 5 and argument[-5] == "#":
            result = next((m for m in members if m.user.tag == argument), None)

        if not result:
            result = next(
                (
                    m
                    for m in members
                    if m.display_name == argument or m.user.username == argument
                ),
                None,
            )

        return result

    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.Member:
        if not ctx.guild:
            raise errors.BadArgument("This command cannot be used in private messages.")

        match = self._get_id_match(argument) or re.match(
            r"<@!?([0-9]{15,})>$", argument
        )
        result = None

        if match:
            result = await ctx.guild.fetch_member(int(match.group(1)))
        elif ctx.guild.chunked:
            result = self._get_member_from_list(ctx.guild.members, argument)
        else:
            query = argument
            if len(argument) > 5 and argument[-5] == "#":
                query, _, _ = argument.rpartition("#")

            members = await ctx.guild.search_members(query, limit=100)
            result = self._get_member_from_list(members, argument)

        if not result:
            raise errors.BadArgument(f'Member "{argument}" not found.')

        return result


class UserConverter(IDConverter[dis_snek.User]):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.User:
        match = self._get_id_match(argument) or re.match(
            r"<@!?([0-9]{15,})>$", argument
        )
        result = None

        if match:
            result = await ctx.bot.fetch_user(int(match.group(1)))
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
        match = self._get_id_match(argument) or re.match(r"<#([0-9]{15,})>$", argument)
        result = None

        if match:
            result = await ctx.bot.fetch_channel(int(match.group(1)))
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


class GuildVoiceConverter(ChannelConverter[dis_snek.GuildVoice]):
    def _check(self, result: dis_snek.BaseChannel):
        return isinstance(result, dis_snek.GuildVoice)


class ThreadChannelConverter(ChannelConverter[dis_snek.ThreadChannel]):
    def _check(self, result: dis_snek.BaseChannel):
        return isinstance(result, dis_snek.ThreadChannel)


class RoleConverter(IDConverter[dis_snek.Role]):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.Role:
        if not ctx.guild:
            raise errors.BadArgument("This command cannot be used in private messages.")

        match = self._get_id_match(argument) or re.match(r"<@&([0-9]{15,})>$", argument)
        result = None

        if match:
            result = await ctx.guild.fetch_role(int(match.group(1)))
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
            result = await ctx.bot.fetch_guild(int(match.group(1)))
        else:
            result = next(
                (g for g in ctx.bot.guilds if g.name == argument),
                None,
            )

        if not result:
            raise errors.BadArgument(f'Guild "{argument}" not found.')

        return result


class PartialEmojiConverter(IDConverter[dis_snek.PartialEmoji]):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.PartialEmoji:

        if match := self._get_id_match(argument) or re.match(
            r"<a?:[a-zA-Z0-9\_]{1,32}:([0-9]{15,})>$", argument
        ):
            emoji_animated = bool(match.group(1))
            emoji_name = match.group(2)
            emoji_id = int(match.group(3))

            return dis_snek.PartialEmoji(id=emoji_id, name=emoji_name, animated=emoji_animated)  # type: ignore

        raise errors.BadArgument(
            f'Couldn\'t convert "{argument}" to {dis_snek.PartialEmoji.__name__}.'
        )


class CustomEmojiConverter(IDConverter[dis_snek.CustomEmoji]):
    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.CustomEmoji:
        if not ctx.guild:
            raise errors.BadArgument("This command cannot be used in private messages.")

        match = self._get_id_match(argument) or re.match(
            r"<a?:[a-zA-Z0-9\_]{1,32}:([0-9]{15,})>$", argument
        )
        result = None

        if match:
            result = await ctx.guild.fetch_custom_emoji(int(match.group(1)))
        else:
            if ctx.bot.cache.enable_emoji_cache:
                emojis = ctx.bot.cache.emoji_cache.values()
                result = next((e for e in emojis if e.name == argument))

            if not result:
                emojis = await ctx.guild.fetch_all_custom_emojis()
                result = next((e for e in emojis if e.name == argument))

        if not result:
            raise errors.BadArgument(f'Emoji "{argument}" not found.')

        return result


class MessageConverter(Converter[dis_snek.Message]):
    # either just the id or <chan_id>-<mes_id>, a format you can get by shift clicking "copy id"
    _ID_REGEX = re.compile(
        r"(?:(?P<channel_id>[0-9]{15,})-)?(?P<message_id>[0-9]{15,})"
    )
    # of course, having a way to get it from a link is nice
    _MESSAGE_LINK_REGEX = re.compile(
        r"https?://[\S]*?discord(?:app)?\.com/channels/(?P<guild_id>[0-9]{15,}|@me)/"
        r"(?P<channel_id>[0-9]{15,})/(?P<message_id>[0-9]{15,})\/?$"
    )

    async def convert(
        self, ctx: dis_snek.MessageContext, argument: str
    ) -> dis_snek.Message:
        match = self._ID_REGEX.match(argument) or self._MESSAGE_LINK_REGEX.match(
            argument
        )
        if not match:
            raise errors.BadArgument(f'Message "{argument}" not found.')

        data = match.groupdict()

        message_id = data["message_id"]
        channel_id = (
            ctx.channel.id if not data.get("channel_id") else int(data["channel_id"])
        )

        # this guild checking is technically unnecessary, but we do it just in case
        # it means a user cant just provide an invalid guild id and still get a message
        guild_id = ctx.guild_id if not data.get("guild_id") else data["guild_id"]
        guild_id = None if guild_id == "@me" else int(guild_id)

        if guild_id:
            base = await ctx.bot.fetch_guild(guild_id)
            if not base:  #  if not a guild
                raise errors.BadArgument(f'Guild "{guild_id}" not found.')
        else:
            base = ctx.bot

        channel = await base.fetch_channel(channel_id)
        if not channel:
            raise errors.BadArgument(f'Channel "{channel_id}" not found.')

        try:
            message = await channel.fetch_message(message_id)
            if not message:
                raise errors.BadArgument(f'Message "{argument}" not found.')
        except AttributeError:  # if the channel doesnt have the ability to fetch messages
            raise errors.BadArgument(
                f"Channel {channel.mention} is not a text channel."
            )
        except dis_snek.errors.Forbidden:
            raise errors.BadArgument(f"Cannot read messages for {channel.mention}.")

        return message


class Greedy(typing.List[T]):
    # this class doesn't actually do a whole lot
    # it's more or less simply a note to the parameter
    # getter
    pass


SNEK_OBJECT_TO_CONVERTER: dict[type, type[Converter]] = {
    dis_snek.SnowflakeObject: SnowflakeConverter,
    dis_snek.Member: MemberConverter,
    dis_snek.User: UserConverter,
    dis_snek.BaseChannel: BaseChannelConverter,
    dis_snek.GuildChannel: GuildChannelConverter,
    dis_snek.GuildText: GuildTextConverter,
    dis_snek.GuildVoice: GuildVoiceConverter,
    dis_snek.ThreadChannel: ThreadChannelConverter,
    dis_snek.Role: RoleConverter,
    dis_snek.Guild: GuildConverter,
    dis_snek.PartialEmoji: PartialEmojiConverter,
    dis_snek.CustomEmoji: CustomEmojiConverter,
    dis_snek.Message: MessageConverter,
}
