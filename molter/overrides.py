import logging
from typing import Optional

from dis_snek.client import Snake
from dis_snek.client.utils.input_utils import get_args
from dis_snek.client.utils.input_utils import get_first_word
from dis_snek.client.const import logger_name, MENTION_PREFIX
from dis_snek.api.events.discord import MessageCreate
from dis_snek.models.snek.scale import Scale
from dis_snek.models.snek.listener import listen
from dis_snek.models.snek.command import MessageCommand
from dis_snek.models.snek.application_commands import ComponentCommand, InteractionCommand

from molter.command import MolterCommand


log = logging.getLogger(logger_name)

__all__ = ("MolterScale", "MolterSnake")


class MolterScale(Scale):
    """
    A custom subclass of `dis_snek.Scale` that properly unloads Molter commands if aliases are used.

    Use this alongside `MolterSnake` for the best results.
    Be careful about overriding the `shed` functions, as doing so improperly will break aliases unloading.
    """

    def shed(self) -> None:
        """Called when this Scale is being removed."""
        for func in self._commands:
            if isinstance(func, ComponentCommand):
                for listener in func.listeners:
                    self.bot._component_callbacks.pop(listener)
            elif isinstance(func, InteractionCommand):
                for scope in func.scopes:
                    if self.bot.interactions.get(scope):
                        self.bot.interactions[scope].pop(func.resolved_name, [])
            elif isinstance(func, MessageCommand):
                # detect if its a molter subcommand
                # unloading a subcommand means commands that weren't supposed to
                # get unloaded that happen to have the same name would
                if not getattr(func, "parent", None):
                    self.bot.commands.pop(func.name, None)

                    if isinstance(func, MolterCommand):
                        for alias in func.aliases:
                            self.bot.commands.pop(alias, None)

        for func in self.listeners:
            self.bot.listeners[func.event].remove(func)

        self.bot.scales.pop(self.name, None)
        log.debug(f"{self.name} has been shed")


class MolterSnake(Snake):
    """
    A custom subclass of `dis_snek.Snake` that allows you to use aliases and subcommands with Molter commands.

    Be careful about overriding the `add_message_command` and `_dispatch_msg_commands` functions
    in the class, as doing so improperly will break alias and/or subcommand support.
    """

    commands: dict[str, MessageCommand | MolterCommand]
    """A dictionary of registered commands: `{name: command}`"""

    def add_message_command(self, command: MessageCommand | MolterCommand) -> None:
        """Add a message command to the client.

        Args:
            command (`dis_snek.MessageCommand | MolterCommand`): The command to add.
        """
        if not isinstance(command, MolterCommand):
            return super().add_message_command(command)

        if command.parent:
            return  # silent return to ignore subcommands - hacky, ik

        super().add_message_command(command)  # adds cmd.name

        for alias in command.aliases:
            if alias not in self.commands:
                self.commands[alias] = command
                continue
            raise ValueError(f"Duplicate Command! Multiple commands share the name/alias `{alias}`")

    def get_command(self, name: str) -> Optional[MessageCommand | MolterCommand]:
        """
        Gets a command by the name specified. Can get subcommands of commmands if needed.

        Args:
            name (`str`): The name of the command to search for. Can be its fully qualified name.

        Returns:
            `dis_snek.MessageCommand | MolterCommand`: The command object, if found.
        """
        if " " not in name:
            return self.commands.get(name)

        names = name.split()
        if not names:
            return None

        cmd = self.commands.get(names[0])
        if not cmd or not getattr(cmd, "command_dict", None):
            return cmd

        for name in names[1:]:
            try:
                cmd = cmd.command_dict[name]
            except (AttributeError, KeyError):
                return None

        return cmd

    @listen("message_create")
    async def _dispatch_msg_commands(self, event: MessageCreate) -> None:
        """
        Determine if a command is being triggered, and dispatch it.

        This special version for Molter also adds support for subcommands.
        """
        message = event.message

        if not message.content:
            return

        if not message.author.bot:
            prefixes = await self.generate_prefixes(self, message)

            if isinstance(prefixes, str) or prefixes == MENTION_PREFIX:
                # its easier to treat everything as if it may be an iterable
                # rather than building a special case for this
                prefixes = (prefixes,)

            prefix_used = None

            for prefix in prefixes:
                if prefix == MENTION_PREFIX:
                    if mention := self._mention_reg.search(message.content):
                        prefix = mention.group()
                    else:
                        continue

                if message.content.startswith(prefix):
                    prefix_used = prefix
                    break

            if prefix_used:
                context = await self.get_context(message)
                context.prefix = prefix_used

                # interestingly enough, we cannot count on ctx.invoked_name
                # being correct as its hard to account for newlines and the like
                # with the way we get subcommands here
                # we'll have to reconstruct it by getting the content_parameters
                # then removing the prefix and the parameters from the message
                # content
                content_parameters = message.content.removeprefix(prefix_used)
                command = self

                while True:
                    first_word: str = get_first_word(content_parameters)
                    if isinstance(command, MolterCommand):
                        new_command = command.command_dict.get(first_word)
                    else:
                        new_command = command.commands.get(first_word)
                    if not new_command or not new_command.enabled:
                        break

                    command = new_command
                    content_parameters = content_parameters.removeprefix(first_word).strip()
                    if not isinstance(command, MolterCommand):
                        # normal message commands can't have subcommands
                        break

                    if command.command_dict and command.hierarchical_checking:
                        await new_command._can_run(context)

                if isinstance(command, Snake):
                    command = None

                if command and command.enabled:
                    # yeah, this looks ugly
                    context.invoked_name = (
                        message.content.removeprefix(prefix_used).removesuffix(content_parameters).strip()
                    )
                    context.args = get_args(context.content_parameters)
                    try:
                        if self.pre_run_callback:
                            await self.pre_run_callback(context)
                        await self._run_message_command(command, context)
                        if self.post_run_callback:
                            await self.post_run_callback(context)
                    except Exception as e:
                        await self.on_command_error(context, e)
                    finally:
                        await self.on_command(context)
