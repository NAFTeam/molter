import functools
import inspect
import typing
from types import NoneType
from types import UnionType

import attr
import dis_snek

from . import converters
from . import errors


@attr.s(slots=True)
class CommandParameter:
    name: str = attr.ib(default=None)
    default: typing.Optional[typing.Any] = attr.ib(default=None)
    type: type = attr.ib(default=None)
    converters: list[
        typing.Callable[[dis_snek.MessageContext, str], typing.Any]
    ] = attr.ib(factory=list)
    union: bool = attr.ib(default=False)
    variable: bool = attr.ib(default=False)
    consume_rest: bool = attr.ib(default=False)


@attr.s(slots=True)
class ArgsIterator:
    args: typing.Sequence[str] = attr.ib(converter=tuple)
    index: int = attr.ib(init=False, default=0)
    length: int = attr.ib(init=False, default=0)

    def __iter__(self):
        self.length = len(self.args)
        return self

    def __next__(self):
        if self.index >= self.length:
            raise StopIteration

        result = self.args[self.index]
        self.index += 1
        return result

    def consume_rest(self):
        result = self.args[self.index - 1 :]
        self.index = self.length
        return result

    def forward(self, count: int = 1):
        result = self.args[self.index - 1 : self.length + (count - 1)]
        self.index += count
        return result

    def back(self, count: int = 1):
        self.index -= count

    def reset(self):
        self.index = 0


def _get_name(x: typing.Any):
    try:
        return x.__name__
    except AttributeError:
        if hasattr(x, "__origin__"):
            return repr(x)
        return x.__class__.__name__


def _convert_to_bool(argument: str) -> bool:
    lowered = argument.lower()
    if lowered in ("yes", "y", "true", "t", "1", "enable", "on"):
        return True
    elif lowered in ("no", "n", "false", "f", "0", "disable", "off"):
        return False
    else:
        raise errors.BadArgument(f"{argument} is not a recognised boolean option.")


def _get_converter(
    anno: type, name: str
) -> typing.Callable[[dis_snek.MessageContext, str], typing.Any]:  # type: ignore
    if converter := converters.SNEK_OBJECT_TO_CONVERTER.get(anno, None):
        return converter().convert  # type: ignore
    elif inspect.isclass(anno) and issubclass(anno, converters.Converter):
        return anno().convert  # type: ignore
    elif hasattr(anno, "convert") and inspect.isfunction(anno.convert):  # type: ignore
        return anno.convert  # type: ignore
    elif inspect.isfunction(anno):
        num_params = len(inspect.signature(anno).parameters.values())
        match num_params:
            case 2:
                return lambda ctx, arg: anno(ctx, arg)
            case 1:
                return lambda ctx, arg: anno(arg)
            case 0:
                return lambda ctx, arg: anno()
            case _:
                errors.BadArgument(
                    f"{_get_name(anno)} for {name} has more than 2 arguments, which is"
                    " unsupported."
                )
    elif anno == bool:
        return lambda ctx, arg: _convert_to_bool(arg)
    elif anno == inspect._empty:
        return lambda ctx, arg: str(arg)
    else:
        return lambda ctx, arg: anno(arg)


def _get_params(func: typing.Callable):
    cmd_params: list[CommandParameter] = []

    callback = functools.partial(func, dis_snek.MessageContext())

    params = inspect.signature(callback).parameters
    for name, param in params.items():
        cmd_param = CommandParameter()
        cmd_param.name = name
        cmd_param.default = (
            param.default
            if param.default is not param.empty
            else dis_snek.const.MISSING
        )

        cmd_param.type = anno = param.annotation

        if typing.get_origin(anno) in {typing.Union, UnionType}:
            cmd_param.union = True
            for arg in typing.get_args(anno):
                if arg != NoneType:
                    converter = _get_converter(arg, name)
                    cmd_param.converters.append(converter)
                elif cmd_param.default == dis_snek.const.MISSING:  # d.py-like behavior
                    cmd_param.default = None
        else:
            converter = _get_converter(anno, name)
            cmd_param.converters.append(converter)

        match param.kind:
            case param.KEYWORD_ONLY:
                cmd_param.consume_rest = True
                cmd_params.append(cmd_param)
                break
            case param.VAR_POSITIONAL:
                if not cmd_param.default == dis_snek.const.MISSING:
                    # there's a lot of parser ambiguities here, so i'd rather not
                    raise ValueError(
                        "Variable arguments cannot have default values or be Optional."
                    )

                cmd_param.variable = True
                cmd_params.append(cmd_param)
                break

        cmd_params.append(cmd_param)

    return cmd_params


async def maybe_coroutine(func: typing.Callable, *args, **kwargs):
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return func(*args, **kwargs)


async def _convert(param: CommandParameter, ctx: dis_snek.MessageContext, arg: str):
    converted = dis_snek.const.MISSING
    for converter in param.converters:
        try:
            converted = await maybe_coroutine(converter, ctx, arg)
            break
        except Exception as e:
            if not param.union and param.default == dis_snek.const.MISSING:
                if isinstance(e, errors.BadArgument):
                    raise
                raise errors.BadArgument(str(e))

    used_default = False
    if converted == dis_snek.const.MISSING:
        if param.default != dis_snek.const.MISSING:
            converted = param.default
            used_default = True
        else:
            union_types = typing.get_args(param.type)
            union_names = tuple(_get_name(t) for t in union_types)
            union_types_str = ", ".join(union_names[:-1]) + f", or {union_names[-1]}"
            raise errors.BadArgument(f"Could not convert {arg} into {union_types_str}.")

    return converted, used_default


@attr.s(
    slots=True, kw_only=True, on_setattr=[attr.setters.convert, attr.setters.validate]
)
class MolterCommand(dis_snek.MessageCommand):
    params: list[CommandParameter] = attr.ib(
        metadata=dis_snek.utils.docs("The paramters of the command."), default=None
    )

    async def call_callback(
        self, callback: typing.Callable, ctx: dis_snek.MessageContext
    ):
        if not self.params:
            # if we did this earlier, we would have to deal with self
            # and im too lazy to deal with self
            self.params = _get_params(self.callback)

        # sourcery skip: remove-empty-nested-block, remove-redundant-if, remove-unnecessary-else
        if len(self.params) == 0:
            return await callback(ctx)
        else:
            new_args: list[typing.Any] = []
            kwargs: dict[str, typing.Any] = {}
            args = ArgsIterator(ctx.args)
            param_index = 0

            for arg in args:
                while param_index < len(self.params):
                    param = self.params[param_index]

                    if param.consume_rest:
                        arg = " ".join(args.consume_rest())
                    if param.variable:
                        args_to_convert = args.consume_rest()
                        new_arg = [
                            await _convert(param, ctx, arg) for arg in args_to_convert
                        ]
                        new_arg = tuple(arg[0] for arg in new_arg)
                        new_args.append(new_arg)
                        param_index += 1
                        break

                    converted, used_default = await _convert(param, ctx, arg)
                    if not param.consume_rest:
                        new_args.append(converted)
                    else:
                        kwargs[param.name] = converted
                    param_index += 1

                    if not used_default:
                        break

            if param_index < len(self.params):
                for param in self.params[param_index:]:
                    if param.default == dis_snek.const.MISSING:
                        raise errors.BadArgument(f"Missing argument for {param.name}.")
                    else:
                        if not param.consume_rest:
                            new_args.append(param.default)
                        else:
                            kwargs[param.name] = param.default
                            break

            return await callback(ctx, *new_args, **kwargs)


def message_command(
    name: str = None,
):
    """
    A decorator to declare a coroutine as a message command.
    parameters:
        name: The name of the command, defaults to the name of the coroutine
    returns:
        Message Command Object
    """

    def wrapper(func):
        if not inspect.iscoroutinefunction(func):
            raise ValueError("Commands must be coroutines.")
        return MolterCommand(name=name or func.__name__, callback=func)

    return wrapper


msg_command = message_command
