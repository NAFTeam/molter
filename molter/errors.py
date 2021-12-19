import typing

import dis_snek


class BadArgument(dis_snek.CommandException):
    def __init__(self, message: typing.Optional[str] = None, *args: typing.Any) -> None:
        if message is not None:
            message = dis_snek.utils.escape_mentions(message)
            super().__init__(message, *args)
        else:
            super().__init__(*args)
