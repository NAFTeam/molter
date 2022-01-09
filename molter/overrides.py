import inspect
import logging
import typing

import dis_snek

from .command import MolterCommand

log = logging.getLogger(dis_snek.const.logger_name)


class MolterScale(dis_snek.Scale):
    """
    A custom subclass of `dis_snek.Scale` that allows you to use aliases with Molter commands in scales.
    Unlike `MolterSnake`, this only has to be be used for Scales with Molter commands.
    Do not use this with `MolterSnake` - use one or the other.
    One must be careful about overriding the `__new__` function in the class, as doing
    so improperly will break alias support.
    """

    def __new__(cls, bot: dis_snek.Snake, *args, **kwargs):
        # most of this code is from the original scale object
        new_cls = object.__new__(cls)
        new_cls.bot = bot
        new_cls.__name = cls.__name__
        new_cls.scale_checks = []
        new_cls.scale_prerun = []
        new_cls.scale_postrun = []
        new_cls.auto_defer = dis_snek.MISSING

        new_cls.description = kwargs.get("Description", None)
        if not new_cls.description:
            new_cls.description = inspect.cleandoc(cls.__doc__) if cls.__doc__ else None

        # load commands from class
        new_cls._commands = []
        new_cls._listeners = []

        for name, val in inspect.getmembers(
            new_cls,
            predicate=lambda x: isinstance(
                x, (dis_snek.BaseCommand, dis_snek.Listener, dis_snek.Task)
            ),
        ):
            if isinstance(val, dis_snek.BaseCommand):
                val.scale = new_cls
                val = dis_snek.utils.wrap_partial(val, new_cls)

                new_cls._commands.append(val)

                if isinstance(val, dis_snek.ComponentCommand):
                    bot.add_component_callback(val)
                elif isinstance(val, dis_snek.InteractionCommand):
                    bot.add_interaction(val)
                elif isinstance(val, MolterCommand):
                    # this is the only part we actually care about
                    # we basically check if this is a molter cmd, and if so
                    # make it so it adds the commands and its aliases
                    # to the commands dict
                    bot.add_message_command(val)

                    for alias in val.aliases:
                        if alias not in bot.commands:
                            bot.commands[alias] = val
                            return
                        raise ValueError(
                            "Duplicate Command! Multiple commands share the name/alias"
                            f" `{alias}`"
                        )
                else:
                    bot.add_message_command(val)
            elif isinstance(val, dis_snek.Listener):
                val = dis_snek.utils.wrap_partial(val, new_cls)
                bot.add_listener(val)
                new_cls.listeners.append(val)
            elif isinstance(val, dis_snek.Task):
                dis_snek.utils.wrap_partial(val, new_cls)

        log.debug(
            f"{len(new_cls._commands)} commands and {len(new_cls.listeners)} listeners"
            f" have been loaded from `{new_cls.name}`"
        )

        new_cls.extension_name = inspect.getmodule(new_cls).__name__
        new_cls.bot.scales[new_cls.name] = new_cls
        return new_cls


class MolterSnake(dis_snek.Snake):
    """
    A custom subclass of `dis_snek.Snake` that allows you to use aliases with Molter commands.
    Unlike `MolterScale`, this only has to be specified during initalization once.
    Do not use this with `MolterScale` - use one or the other.
    One must be careful about overriding the `add_message_command` function in the class, as doing
    so improperly will break alias support.
    """

    def add_message_command(
        self, command: typing.Union[dis_snek.MessageCommand, MolterCommand]
    ):
        super().add_message_command(
            command
        )  # both times, we want to add the command for "cmd.name"

        if isinstance(command, MolterCommand):
            for alias in command.aliases:
                if alias not in self.commands:
                    self.commands[alias] = command
                    return
                raise ValueError(
                    "Duplicate Command! Multiple commands share the name/alias"
                    f" `{alias}`"
                )
