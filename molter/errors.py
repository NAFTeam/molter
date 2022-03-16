from typing import Optional, Any

from dis_snek.client.errors import CommandException
from dis_snek.client.utils.misc_utils import escape_mentions


__all__ = ("BadArgument",)


class BadArgument(CommandException):
    """A special exception for invalid arguments when using molter commands."""

    def __init__(self, message: Optional[str] = None, *args: Any) -> None:
        if message is not None:
            message = escape_mentions(message)
            super().__init__(message, *args)
        else:
            super().__init__(*args)
