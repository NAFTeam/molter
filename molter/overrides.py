import typing

import dis_snek

from .command import MolterCommand


class MolterSnake(dis_snek.Snake):
    """
    A custom subclass of `dis_snek.Snake` that allows you to use aliases and subcommands with Molter commands.
    This does NOT support normal message commands built in the library - the bot will error out if so.
    One must be careful about overriding the `add_message_command` and `_dispatch_msg_commands` functions
    in the class, as doing so improperly will break alias and/or subcommand support.
    """

    def add_message_command(
        self, command: typing.Union[dis_snek.MessageCommand, MolterCommand]
    ):
        if not isinstance(command, MolterCommand):
            raise ValueError("Only Molter commands can be added to `MolterSnake`!")

        if command.parent:
            return  # silent return to ignore subcommands - hacky, ik

        super().add_message_command(command)  # adds cmd.name

        for alias in command.aliases:
            if alias not in self.commands:
                self.commands[alias] = command
                continue
            raise ValueError(
                f"Duplicate Command! Multiple commands share the name/alias `{alias}`"
            )

    @dis_snek.listen("message_create")
    async def _dispatch_msg_commands(self, event: dis_snek.events.MessageCreate):
        """Determine if a command is being triggered, and dispatch it.
        This special version for Molter also adds support for subcommands."""
        message = event.message

        if not message.author.bot:
            prefix = await self.get_prefix(message)

            if prefix == dis_snek.const.MENTION_PREFIX:
                mention = self._mention_reg.search(message.content)
                if mention:
                    prefix = mention.group()
                else:
                    return

            if message.content.startswith(prefix):
                context = await self.get_context(message)
                context.invoked_name = ""
                context.prefix = prefix

                content = message.content.removeprefix(prefix)
                self.commands: dict[str, MolterCommand]
                command = self

                while True:
                    first_word: str = dis_snek.utils.get_first_word(content)
                    if isinstance(command, MolterCommand):
                        new_command = command.command_dict.get(first_word)
                    else:
                        new_command = command.commands.get(first_word)
                    if not new_command or not new_command.enabled:
                        break

                    command = new_command
                    context.invoked_name += f"{first_word} "

                    if command.command_dict and command.hierarchical_checking:
                        await new_command._can_run(context)

                    content = content.removeprefix(first_word).strip()

                if isinstance(command, dis_snek.Snake):
                    command = None

                if command and command.enabled:
                    context.invoked_name = context.invoked_name.strip()
                    context.args = dis_snek.utils.get_args(context.content_parameters)
                    try:
                        if self.pre_run_callback:
                            await self.pre_run_callback(context)
                        await command(context)
                        if self.post_run_callback:
                            await self.post_run_callback(context)
                    except Exception as e:
                        await self.on_command_error(context, e)
                    finally:
                        await self.on_command(context)
