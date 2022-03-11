import functools
import inspect
import typing
from types import NoneType
from types import UnionType

import attrs
import dis_snek


@attrs.define(slots=True)
class Param:
    name: str = attrs.field(default=None)
    type: typing.Union[dis_snek.OptionTypes, type] = attrs.field(default=None)
    description: str = attrs.field(default="No Description Set")
    required: bool = attrs.field(default=True)
    autocomplete: typing.Callable = attrs.field(default=None)
    choices: list[dis_snek.SlashCommandChoice | dict] = attrs.field(factory=list)
    channel_types: typing.Optional[list[dis_snek.ChannelTypes | int]] = attrs.field(
        default=None
    )
    min_value: typing.Optional[float] = attrs.field(default=None)
    max_value: typing.Optional[float] = attrs.field(default=None)


def _get_option(t: dis_snek.OptionTypes | type):
    if isinstance(t, dis_snek.OptionTypes):
        return t

    if issubclass(t, str):
        return dis_snek.OptionTypes.STRING
    if issubclass(t, int):
        return dis_snek.OptionTypes.INTEGER
    if issubclass(t, bool):
        return dis_snek.OptionTypes.BOOLEAN
    if issubclass(t, dis_snek.BaseUser):
        return dis_snek.OptionTypes.USER
    if issubclass(t, dis_snek.BaseChannel):
        return dis_snek.OptionTypes.CHANNEL
    if issubclass(t, dis_snek.Role):
        return dis_snek.OptionTypes.ROLE
    if issubclass(t, float):
        return dis_snek.OptionTypes.NUMBER
    if issubclass(t, dis_snek.Attachment):
        return dis_snek.OptionTypes.ATTACHMENT

    if typing.get_origin(t) in {typing.Union, UnionType}:
        args = typing.get_args(t)
        if (
            len(args) in {2, 3}
            and issubclass(args[0], dis_snek.BaseUser)
            and issubclass(args[1], dis_snek.BaseChannel)
        ):
            return dis_snek.OptionTypes.MENTIONABLE

    return dis_snek.OptionTypes.STRING


def _get_params(func: typing.Callable):
    # TODO: do dirty patching with the func for defaults

    cmd_params: list[dis_snek.SlashCommandOption] = []
    autocompletes: dict[str, typing.Callable] = {}

    # we need to ignore parameters like self and ctx, so this is the easiest way
    # forgive me, but this is the only reliable way i can find out if the function...
    if "." in func.__qualname__:  # is part of a class
        callback = functools.partial(func, None, None)
    else:
        callback = functools.partial(func, None)

    params = inspect.signature(callback).parameters
    for name, param in params.items():
        param_to_opt = dis_snek.SlashCommandOption()

        if (default := param.default) is not param.empty:
            if isinstance(default, Param):
                if default.name:
                    param_to_opt.name = default.name
                if default.type:
                    param_to_opt.type = _get_option(default.type)
                if default.description:
                    param_to_opt.description = default.description
                if default.required:
                    param_to_opt.required = default.required
                if default.autocomplete:
                    param_to_opt.autocomplete = True
                if default.choices:
                    param_to_opt.choices = default.choices
                if default.channel_types:
                    param_to_opt.channel_types = default.channel_types
                if default.min_value:
                    param_to_opt.min_value = default.min_value
                if default.max_value:
                    param_to_opt.max_value = default.max_value
            else:
                param_to_opt.required = False
                # param_to_opt.default = default

        if not param_to_opt.name:
            param_to_opt.name = name

        if (
            (default := param.default) is not param.empty
            and isinstance(default, Param)
            and default.autocomplete
        ):
            autocompletes[param_to_opt.name] = default.autocomplete

        anno = param.annotation

        if typing.get_origin(anno) in {typing.Union, UnionType}:
            for arg in typing.get_args(anno):
                if arg == NoneType:
                    param_to_opt.required = False
                    break

        param_to_opt.type = _get_option(anno)
        cmd_params.append(param_to_opt)
