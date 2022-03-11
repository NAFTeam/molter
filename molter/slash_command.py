from __future__ import annotations

import collections
import functools
import inspect
import typing
from types import NoneType
from types import UnionType

import attrs
import dis_snek

T_co = typing.TypeVar("T_co", covariant=True)


@typing.runtime_checkable
class Converter(typing.Protocol[T_co]):
    async def convert(self, ctx: dis_snek.Context, argument: str) -> T_co:
        raise NotImplementedError("Derived classes need to implement this.")


def _converter_converter(value: typing.Any):
    if value is dis_snek.const.Missing:
        return value

    if inspect.isclass(value) and issubclass(value, Converter):
        return value()  # type: ignore
    elif hasattr(value, "convert") and inspect.isfunction(value.convert):  # type: ignore
        return value
    else:
        raise ValueError(f"{repr(value)} is not a valid converter.")


@attrs.define(slots=True, on_setattr=[attrs.setters.convert, attrs.setters.validate])
class Param:
    name: str = attrs.field(default=dis_snek.const.Missing)
    type: "dis_snek.OptionTypes | int | type" = attrs.field(default=dis_snek.const.Missing)
    converter: typing.Any = attrs.field(
        default=dis_snek.const.Missing, converter=_converter_converter
    )
    default: typing.Any = attrs.field(default=inspect._empty)
    description: str = attrs.field(default=dis_snek.const.Missing)
    required: bool = attrs.field(default=dis_snek.const.Missing)
    autocomplete: typing.Callable = attrs.field(default=dis_snek.const.Missing)
    choices: list[dis_snek.SlashCommandChoice | dict] = attrs.field(factory=list)
    channel_types: list[dis_snek.ChannelTypes | int] = attrs.field(
        factory=list
    )
    min_value: dis_snek.Absent[float] = attrs.field(default=dis_snek.const.Missing)
    max_value: dis_snek.Absent[float] = attrs.field(default=dis_snek.const.Missing)


def _get_option(t: dis_snek.OptionTypes | type):
    if isinstance(t, dis_snek.OptionTypes):
        return t

    if isinstance(t, str):
        return dis_snek.OptionTypes.STRING
    if isinstance(t, int):
        return dis_snek.OptionTypes.INTEGER
    if isinstance(t, bool):
        return dis_snek.OptionTypes.BOOLEAN
    if isinstance(t, dis_snek.BaseUser):
        return dis_snek.OptionTypes.USER
    if isinstance(t, dis_snek.BaseChannel):
        return dis_snek.OptionTypes.CHANNEL
    if isinstance(t, dis_snek.Role):
        return dis_snek.OptionTypes.ROLE
    if isinstance(t, float):
        return dis_snek.OptionTypes.NUMBER
    if isinstance(t, dis_snek.Attachment):
        return dis_snek.OptionTypes.ATTACHMENT

    if typing.get_origin(t) in {typing.Union, UnionType}:
        args = typing.get_args(t)
        if (
            len(args) in {2, 3}
            and isinstance(args[0], (dis_snek.BaseUser, dis_snek.BaseChannel))
            and isinstance(args[1], (dis_snek.BaseUser, dis_snek.BaseChannel))
        ):
            return dis_snek.OptionTypes.MENTIONABLE

    return dis_snek.OptionTypes.STRING


@attrs.define(slots=True, on_setattr=[attrs.setters.convert, attrs.setters.validate])
class ExpandedOptions(dis_snek.SlashCommandOption):
    name: str = attrs.field(default=None)
    type: dis_snek.OptionTypes | int = attrs.field(default=None)
    converter: typing.Any = attrs.field(default=dis_snek.const.Missing)
    default: typing.Any = attrs.field(default=inspect._empty)
    autocomplete_function: typing.Callable = attrs.field(default=None)


def _get_params(func: typing.Callable):
    # TODO: do dirty patching with the func for defaults

    cmd_params: list[ExpandedOptions] = []
    func_params: list[inspect.Parameter] = []

    # we need to ignore parameters like self and ctx, so this is the easiest way
    # forgive me, but this is the only reliable way i can find out if the function...
    if "." in func.__qualname__:  # is part of a class
        callback = functools.partial(func, None, None)
    else:
        callback = functools.partial(func, None)

    signature = inspect.signature(callback)
    params = signature.parameters
    for name, param in params.items():
        param_to_opt = ExpandedOptions()

        default = param.default

        if (default := param.default) is not param.empty:
            if isinstance(default, Param):
                if default.name is not dis_snek.const.Missing:
                    param_to_opt.name = default.name
                if default.type is not dis_snek.const.Missing:
                    param_to_opt.type = _get_option(default.type)
                if default.converter is not dis_snek.const.Missing:
                    param_to_opt.converter = default.converter
                if default.default is not inspect._empty:
                    param_to_opt.required = False
                    param_to_opt.default = default.default
                if default.description is not dis_snek.const.Missing:
                    param_to_opt.description = default.description
                if default.required is not dis_snek.const.Missing:
                    param_to_opt.required = default.required
                if default.autocomplete is not dis_snek.const.Missing:
                    param_to_opt.autocomplete = True
                    param_to_opt.autocomplete_function = default.autocomplete
                if default.choices:
                    param_to_opt.choices = default.choices
                if default.channel_types:
                    param_to_opt.channel_types = default.channel_types
                if default.min_value is not dis_snek.const.Missing:
                    param_to_opt.min_value = default.min_value
                if default.max_value is not dis_snek.const.Missing:
                    param_to_opt.max_value = default.max_value
            else:
                param_to_opt.required = False

                try:
                    param_to_opt.converter = _converter_converter(default)
                except ValueError:
                    param_to_opt.default = default

        if not param_to_opt.name:
            param_to_opt.name = name

        anno = param.annotation

        if typing.get_origin(anno) in {typing.Union, UnionType}:
            for arg in typing.get_args(anno):
                if arg == NoneType:
                    param_to_opt.required = False
                    break

        param_to_opt.type = _get_option(anno)

        if param_to_opt.converter is not dis_snek.const.Missing:
            func_params.append(param.replace(annotation=param_to_opt.converter, default=param_to_opt.default))
        else:
            func_params.append(param.replace(default=param_to_opt.default))
        cmd_params.append(param_to_opt)

    if cmd_params != sorted(
        cmd_params,
        key=lambda x: x.required,
        reverse=True,
    ):
        # this makes the next part easier if we check it now - it makes using
        # our default hack later a mess
        raise ValueError("Required options must go before optional options.")

    # deques make it easy to store data backwards
    new_defaults = collections.deque()
    new_annos: dict[str, type] = {}

    for param in reversed(func_params):  # defaults are stored in backwards order
        new_defaults.appendleft(param.default)

        if param.annotation is not dis_snek.const.MISSING:
            new_annos[param.name] = param.annotation

    # yeah, this is a hack, but its what it is lol
    func.__defaults__ = tuple(new_defaults)
    func.__annotations__.update(new_annos)

class TestConverter(Converter):
    async def convert(self, ctx: dis_snek.Context, argument: str):
        raise NotImplementedError("Derived classes need to implement this.")

async def test(
    ctx: dis_snek.Context, option_1: float = Param(default=None, converter=TestConverter), option_2: str = Param(default="None")
):
    pass


_get_params(test)
