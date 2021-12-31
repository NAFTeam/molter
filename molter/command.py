import functools
import inspect
import typing
from types import NoneType
from types import UnionType

import attr
import dis_snek
from dis_snek.utils.input_utils import _quotes

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
    greedy: bool = attr.ib(default=False)
    union: bool = attr.ib(default=False)
    variable: bool = attr.ib(default=False)
    consume_rest: bool = attr.ib(default=False)

    @property
    def optional(self) -> bool:
        return self.default != dis_snek.const.MISSING


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

    def back(self, count: int = 1):
        self.index -= count

    def reset(self):
        self.index = 0

    @property
    def finished(self):
        return self.index >= self.length


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
    elif typing.get_origin(anno) is typing.Literal:
        literals = typing.get_args(anno)
        return converters.LiteralConverter(literals).convert
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
                ValueError(
                    f"{_get_name(anno)} for {name} has more than 2 arguments, which is"
                    " unsupported."
                )
    elif anno == bool:
        return lambda ctx, arg: _convert_to_bool(arg)
    elif anno == inspect._empty:
        return lambda ctx, arg: str(arg)
    else:
        return lambda ctx, arg: anno(arg)


def _greedy_parse(greedy: converters.Greedy, param: inspect.Parameter):
    if param.kind in {param.KEYWORD_ONLY, param.VAR_POSITIONAL}:
        raise ValueError("Greedy[...] cannot be a variable or keyword-only argument.")

    arg = typing.get_args(greedy)[0]
    if arg in {NoneType, str}:
        raise ValueError(f"Greedy[{_get_name(arg)}] is invalid.")

    if (
        typing.get_origin(arg)
        in {
            typing.Union,
            UnionType,
        }
        and NoneType in typing.get_args(arg)
    ):
        raise ValueError(f"Greedy[{repr(arg)}] is invalid.")

    return arg


def _get_params(func: typing.Callable):
    cmd_params: list[CommandParameter] = []

    # we need to ignore parameters like self and ctx, so this is the easiest way
    # forgive me, but this is the only reliable way i can find out if the function...
    if "." in func.__qualname__:  # is part of a class
        callback = functools.partial(func, None, None)
    else:
        callback = functools.partial(func, None)

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

        if typing.get_origin(anno) == converters.Greedy:
            anno = _greedy_parse(anno, param)
            cmd_param.greedy = True

        if typing.get_origin(anno) in {typing.Union, UnionType}:
            cmd_param.union = True
            for arg in typing.get_args(anno):
                if arg != NoneType:
                    converter = _get_converter(arg, name)
                    cmd_param.converters.append(converter)
                elif not cmd_param.optional:  # d.py-like behavior
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
                if cmd_param.optional:
                    # there's a lot of parser ambiguities here, so i'd rather not
                    raise ValueError(
                        "Variable arguments cannot have default values or be Optional."
                    )

                cmd_param.variable = True
                cmd_params.append(cmd_param)
                break

        cmd_params.append(cmd_param)

    return cmd_params


def _arg_fix(arg: str):
    if arg[0] in _quotes.keys():
        return arg[1:-1]
    return arg


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
            if not param.union and not param.optional:
                if isinstance(e, errors.BadArgument):
                    raise
                raise errors.BadArgument(str(e))

    used_default = False
    if converted == dis_snek.const.MISSING:
        if param.optional:
            converted = param.default
            used_default = True
        else:
            union_types = typing.get_args(param.type)
            union_names = tuple(_get_name(t) for t in union_types)
            union_types_str = ", ".join(union_names[:-1]) + f", or {union_names[-1]}"
            raise errors.BadArgument(
                f'Could not convert "{arg}" into {union_types_str}.'
            )

    return converted, used_default


async def _greedy_convert(
    param: CommandParameter, ctx: dis_snek.MessageContext, args: ArgsIterator
):
    args.back()
    broke_off = False
    greedy_args = []

    for arg in args:
        try:
            greedy_arg, used_default = await _convert(param, ctx, arg)

            if used_default:
                raise errors.BadArgument()  # does it matter?

            greedy_args.append(greedy_arg)
        except errors.BadArgument:
            broke_off = True
            break

    if not greedy_args:
        if param.default:
            greedy_args = param.default  # im sorry, typehinters
        else:
            raise errors.BadArgument(
                f"Failed to find any arguments for {repr(param.type)}."
            )

    return greedy_args, broke_off


@attr.s(
    slots=True, kw_only=True, on_setattr=[attr.setters.convert, attr.setters.validate]
)
class MolterCommand(dis_snek.MessageCommand):
    params: list[CommandParameter] = attr.ib(
        metadata=dis_snek.utils.docs("The paramters of the command.")
    )
    help: typing.Optional[str] = attr.ib(
        default=None,
        metadata=dis_snek.utils.docs("The long help text for the command."),
    )
    brief: typing.Optional[str] = attr.ib(
        default=None,
        metadata=dis_snek.utils.docs("The short help text for the command."),
    )
    hidden: bool = attr.ib(
        metadata=dis_snek.utils.docs(
            "If `True`, the default help command does not show this in the help output."
        )
    )  # means nothing rn
    ignore_extra: bool = attr.ib(
        metadata=dis_snek.utils.docs(
            "If `True`, ignores extraneous strings passed to a command if all its"
            " requirements are met (e.g. ?foo a b c when only expecting a and b)."
            " Otherwise, an error is raised. Defaults to True."
        )
    )

    async def call_callback(
        self, callback: typing.Callable, ctx: dis_snek.MessageContext
    ):

        # sourcery skip: remove-empty-nested-block, remove-redundant-if, remove-unnecessary-else
        if len(self.params) == 0:
            return await callback(ctx)
        else:
            new_args: list[typing.Any] = []
            kwargs: dict[str, typing.Any] = {}
            args = ArgsIterator(tuple(_arg_fix(a) for a in ctx.args))
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

                    if param.greedy:
                        greedy_args, broke_off = await _greedy_convert(param, ctx, args)

                        new_args.append(greedy_args)
                        param_index += 1
                        if broke_off:
                            args.back()

                        if param.default:
                            continue
                        else:
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
                    if not param.optional:
                        raise errors.BadArgument(f"Missing argument for {param.name}.")
                    else:
                        if not param.consume_rest:
                            new_args.append(param.default)
                        else:
                            kwargs[param.name] = param.default
                            break
            elif not self.ignore_extra and not args.finished:
                raise errors.BadArgument(f"Too many arguments passed to {self.name}")

            return await callback(ctx, *new_args, **kwargs)


def message_command(
    *,
    name: str = None,
    help: str = None,
    brief: str = None,
    enabled: bool = True,
    hidden: bool = False,
    ignore_extra: bool = True,
):
    """
    A decorator to declare a coroutine as a Molter message command.
    parameters:
        name: The name of the command, defaults to the name of the coroutine
    returns:
        Molter Message Command Object
    """

    def wrapper(func):
        if not inspect.iscoroutinefunction(func):
            raise ValueError("Commands must be coroutines.")

        if help is not None:
            cmd_help = inspect.cleandoc(help)
        else:
            cmd_help = inspect.getdoc(func)
            if isinstance(help, bytes):
                cmd_help = help.decode("utf-8")

        if brief is not None:
            cmd_brief = brief
        elif cmd_help is not None:
            cmd_brief = cmd_help.splitlines()[0]

        return MolterCommand(
            name=name or func.__name__,
            callback=func,
            help=cmd_help,
            brief=cmd_brief,  # type: ignore
            enabled=enabled,
            hidden=hidden,
            ignore_extra=ignore_extra,
            params=_get_params(func),
        )

    return wrapper


msg_command = message_command
