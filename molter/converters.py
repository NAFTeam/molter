import re
import typing  # importing functions/decorators directly is weird
from typing import TypeVar, Protocol, Any, Optional, List

from dis_snek.client.errors import Forbidden, HTTPException
from dis_snek.models.discord.role import Role
from dis_snek.models.discord.guild import Guild
from dis_snek.models.discord.message import Message
from dis_snek.models.discord.user import User, Member
from dis_snek.models.discord.enums import ChannelTypes
from dis_snek.models.discord.snowflake import SnowflakeObject
from dis_snek.models.discord.emoji import PartialEmoji, CustomEmoji
from dis_snek.models.discord.channel import (
    BaseChannel,
    DMChannel,
    DM,
    DMGroup,
    GuildChannel,
    GuildCategory,
    GuildStore,
    GuildNews,
    GuildText,
    ThreadChannel,
    GuildNewsThread,
    GuildPublicThread,
    GuildPrivateThread,
    GuildVoice,
    GuildStageVoice,
    TYPE_ALL_CHANNEL,
    TYPE_DM_CHANNEL,
    TYPE_GUILD_CHANNEL,
    TYPE_THREAD_CHANNEL,
    TYPE_VOICE_CHANNEL,
    TYPE_MESSAGEABLE_CHANNEL,
)
from dis_snek.models.snek.context import Context

from molter.errors import BadArgument

__all__ = (
    "Converter",
    "LiteralConverter",
    "IDConverter",
    "SnowflakeConverter",
    "MemberConverter",
    "UserConverter",
    "ChannelConverter",
    "BaseChannelConverter",
    "DMChannelConverter",
    "DMConverter",
    "DMGroupConverter",
    "GuildChannelConverter",
    "GuildNewsConverter",
    "GuildCategoryConverter",
    "GuildTextConverter",
    "ThreadChannelConverter",
    "GuildNewsThreadConverter",
    "GuildPublicThreadConverter",
    "GuildPrivateThreadConverter",
    "GuildVoiceConverter",
    "GuildStageVoiceConverter",
    "MessageableChannelConverter",
    "RoleConverter",
    "GuildConverter",
    "PartialEmojiConverter",
    "CustomEmojiConverter",
    "MessageConverter",
    "Greedy",
    "SNEK_OBJECT_TO_CONVERTER",
)

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


@typing.runtime_checkable
class Converter(Protocol[T_co]):
    async def convert(self, ctx: Context, argument: Any) -> T_co:
        raise NotImplementedError("Derived classes need to implement this.")


class LiteralConverter(Converter):
    values: dict

    def __init__(self, args: Any) -> None:
        self.values = {arg: type(arg) for arg in args}

    async def convert(self, ctx: Context, argument: str) -> Any:
        for arg, converter in self.values.items():
            try:
                if arg == converter(argument):
                    return argument
            except Exception:  # noqa
                continue

        literals_list = [str(a) for a in self.values.keys()]
        literals_str = ", ".join(literals_list[:-1]) + f", or {literals_list[-1]}"
        raise BadArgument(f'Could not convert "{argument}" into one of {literals_str}.')


_ID_REGEX = re.compile(r"([0-9]{15,})$")


class IDConverter(Converter[T_co]):
    @staticmethod
    def _get_id_match(argument: str) -> Optional[re.Match[str]]:
        return _ID_REGEX.match(argument)


class SnowflakeConverter(IDConverter[SnowflakeObject]):
    async def convert(self, ctx: Context, argument: str) -> SnowflakeObject:
        match = self._get_id_match(argument) or re.match(r"<(?:@(?:!|&)?|#)([0-9]{15,})>$", argument)

        if match is None:
            raise BadArgument(argument)

        return SnowflakeObject(int(match.group(1)))  # type: ignore


class MemberConverter(IDConverter[Member]):
    def _get_member_from_list(self, members: list[Member], argument: str) -> Optional[Member]:
        result = None
        if len(argument) > 5 and argument[-5] == "#":
            result = next((m for m in members if m.user.tag == argument), None)

        if not result:
            result = next((m for m in members if m.display_name == argument or m.user.username == argument), None)

        return result

    async def convert(self, ctx: Context, argument: str) -> Member:
        if not ctx.guild:
            raise BadArgument("This command cannot be used in private messages.")

        match = self._get_id_match(argument) or re.match(r"<@!?([0-9]{15,})>$", argument)
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
            raise BadArgument(f'Member "{argument}" not found.')

        return result


class UserConverter(IDConverter[User]):
    async def convert(self, ctx: Context, argument: str) -> User:
        match = self._get_id_match(argument) or re.match(r"<@!?([0-9]{15,})>$", argument)
        result = None

        if match:
            result = await ctx.bot.fetch_user(int(match.group(1)))
        else:
            if len(argument) > 5 and argument[-5] == "#":
                result = next((u for u in ctx.bot.cache.user_cache.values() if u.tag == argument), None)

            if not result:
                result = next((u for u in ctx.bot.cache.user_cache.values() if u.username == argument), None)

        if not result:
            raise BadArgument(f'User "{argument}" not found.')

        return result


class ChannelConverter(IDConverter[T_co]):
    def _check(self, result: BaseChannel) -> bool:
        return True

    async def convert(self, ctx: Context, argument: str) -> T_co:
        match = self._get_id_match(argument) or re.match(r"<#([0-9]{15,})>$", argument)
        result = None

        if match:
            result = await ctx.bot.fetch_channel(int(match.group(1)))
        elif ctx.guild:
            result = next((c for c in ctx.guild.channels if c.name == argument), None)
        else:
            result = next((c for c in ctx.bot.cache.channel_cache.values() if c.name == argument), None)

        if not result:
            raise BadArgument(f'Channel "{argument}" not found.')

        if self._check(result):
            return result  # type: ignore

        raise BadArgument(f'Channel "{argument}" not found.')


class BaseChannelConverter(ChannelConverter[BaseChannel]):
    pass


class DMChannelConverter(ChannelConverter[DMChannel]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, DMChannel)


class DMConverter(ChannelConverter[DM]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, DM)


class DMGroupConverter(ChannelConverter[DMGroup]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, DMGroup)


class GuildChannelConverter(ChannelConverter[GuildChannel]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildChannel)


class GuildNewsConverter(ChannelConverter[GuildNews]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildNews)


class GuildStoreConverter(ChannelConverter[GuildStore]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildStore)


class GuildCategoryConverter(ChannelConverter[GuildCategory]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildCategory)


class GuildTextConverter(ChannelConverter[GuildText]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildText)


class ThreadChannelConverter(ChannelConverter[ThreadChannel]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, ThreadChannel)


class GuildNewsThreadConverter(ChannelConverter[GuildNewsThread]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildNewsThread)


class GuildPublicThreadConverter(ChannelConverter[GuildPublicThread]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildPublicThread)


class GuildPrivateThreadConverter(ChannelConverter[GuildPrivateThread]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildPrivateThread)


class GuildVoiceConverter(ChannelConverter[GuildVoice]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildVoice)


class GuildStageVoiceConverter(ChannelConverter[GuildStageVoice]):
    def _check(self, result: BaseChannel) -> bool:
        return isinstance(result, GuildStageVoice)


class MessageableChannelConverter(ChannelConverter[TYPE_MESSAGEABLE_CHANNEL]):
    def _check(self, result: BaseChannel) -> bool:
        return (isinstance(result.type, ChannelTypes) and not result.type.voice) or result.type not in {
            2,
            13,
        }


class RoleConverter(IDConverter[Role]):
    async def convert(self, ctx: Context, argument: str) -> Role:
        if not ctx.guild:
            raise BadArgument("This command cannot be used in private messages.")

        match = self._get_id_match(argument) or re.match(r"<@&([0-9]{15,})>$", argument)
        result = None

        if match:
            result = await ctx.guild.fetch_role(int(match.group(1)))
        else:
            result = next((r for r in ctx.guild.roles if r.name == argument), None)

        if not result:
            raise BadArgument(f'Role "{argument}" not found.')

        return result


class GuildConverter(IDConverter[Guild]):
    async def convert(self, ctx: Context, argument: str) -> Guild:
        match = self._get_id_match(argument)
        result = None

        if match:
            result = await ctx.bot.fetch_guild(int(match.group(1)))
        else:
            result = next((g for g in ctx.bot.guilds if g.name == argument), None)

        if not result:
            raise BadArgument(f'Guild "{argument}" not found.')

        return result


class PartialEmojiConverter(IDConverter[PartialEmoji]):
    async def convert(self, ctx: Context, argument: str) -> PartialEmoji:

        if match := self._get_id_match(argument) or re.match(r"<a?:[a-zA-Z0-9\_]{1,32}:([0-9]{15,})>$", argument):
            emoji_animated = bool(match.group(1))
            emoji_name = match.group(2)
            emoji_id = int(match.group(3))

            return PartialEmoji(id=emoji_id, name=emoji_name, animated=emoji_animated)  # type: ignore

        raise BadArgument(f'Couldn\'t convert "{argument}" to {PartialEmoji.__name__}.')


class CustomEmojiConverter(IDConverter[CustomEmoji]):
    async def convert(self, ctx: Context, argument: str) -> CustomEmoji:
        if not ctx.guild:
            raise BadArgument("This command cannot be used in private messages.")

        match = self._get_id_match(argument) or re.match(r"<a?:[a-zA-Z0-9\_]{1,32}:([0-9]{15,})>$", argument)
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
            raise BadArgument(f'Emoji "{argument}" not found.')

        return result


class MessageConverter(Converter[Message]):
    # either just the id or <chan_id>-<mes_id>, a format you can get by shift clicking "copy id"
    _ID_REGEX = re.compile(r"(?:(?P<channel_id>[0-9]{15,})-)?(?P<message_id>[0-9]{15,})")
    # of course, having a way to get it from a link is nice
    _MESSAGE_LINK_REGEX = re.compile(
        r"https?://[\S]*?discord(?:app)?\.com/channels/(?P<guild_id>[0-9]{15,}|@me)/(?P<channel_id>[0-9]{15,})/(?P<message_id>[0-9]{15,})\/?$"
    )

    async def convert(self, ctx: Context, argument: str) -> Message:
        match = self._ID_REGEX.match(argument) or self._MESSAGE_LINK_REGEX.match(argument)
        if not match:
            raise BadArgument(f'Message "{argument}" not found.')

        data = match.groupdict()

        message_id = data["message_id"]
        channel_id = ctx.channel.id if not data.get("channel_id") else int(data["channel_id"])

        # this guild checking is technically unnecessary, but we do it just in case
        # it means a user cant just provide an invalid guild id and still get a message
        guild_id = ctx.guild_id if not data.get("guild_id") else data["guild_id"]
        guild_id = int(guild_id) if guild_id != "@me" else None

        try:
            # this takes less possible requests than getting the guild and/or channel
            mes = await ctx.bot.cache.fetch_message(channel_id, message_id)
            if mes._guild_id != guild_id:
                raise BadArgument(f'Message "{argument}" not found.')
            return mes
        except Forbidden as e:
            raise BadArgument(f"Cannot read messages for <#{channel_id}>.") from e
        except HTTPException as e:
            raise BadArgument(f'Message "{argument}" not found.') from e


class Greedy(List[T]):
    # this class doesn't actually do a whole lot
    # it's more or less simply a note to the parameter
    # getter
    pass


SNEK_OBJECT_TO_CONVERTER: dict[type, type[Converter]] = {
    SnowflakeObject: SnowflakeConverter,
    Member: MemberConverter,
    User: UserConverter,
    BaseChannel: BaseChannelConverter,
    DMChannel: DMChannelConverter,
    DM: DMConverter,
    DMGroup: DMGroupConverter,
    GuildChannel: GuildChannelConverter,
    GuildNews: GuildNewsConverter,
    GuildStore: GuildStoreConverter,
    GuildCategory: GuildCategoryConverter,
    GuildText: GuildTextConverter,
    ThreadChannel: ThreadChannelConverter,
    GuildNewsThread: GuildNewsThreadConverter,
    GuildPublicThread: GuildPublicThreadConverter,
    GuildPrivateThread: GuildPrivateThreadConverter,
    GuildVoice: GuildVoiceConverter,
    GuildStageVoice: GuildStageVoiceConverter,
    TYPE_ALL_CHANNEL: BaseChannelConverter,
    TYPE_DM_CHANNEL: DMChannelConverter,
    TYPE_GUILD_CHANNEL: GuildChannelConverter,
    TYPE_THREAD_CHANNEL: ThreadChannelConverter,
    TYPE_VOICE_CHANNEL: GuildVoiceConverter,
    TYPE_MESSAGEABLE_CHANNEL: MessageableChannelConverter,
    Role: RoleConverter,
    Guild: GuildConverter,
    PartialEmoji: PartialEmojiConverter,
    CustomEmoji: CustomEmojiConverter,
    Message: MessageConverter,
}
