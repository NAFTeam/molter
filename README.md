[![PyPI](https://img.shields.io/pypi/v/molter)](https://pypi.org/project/molter/)
[![Downloads](https://static.pepy.tech/personalized-badge/molter?period=total&units=abbreviation&left_color=grey&right_color=green&left_text=pip%20installs)](https://pepy.tech/project/molter)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# Molter - WIP
Shedding a new skin on [Dis-Snek's](https://github.com/Discord-Snake-Pit/Dis-Snek) commands.

Currently, its goals are to make message commands more similar (not exactly the same!) to [discord.py's](https://github.com/Rapptz/discord.py) message commands.

# Installing
```sh
pip install molter
```

# Example
Load this as a normal scale in `dis_snek`:
```python
import dis_snek
import molter
from typing import Optional


class CommandTest(dis_snek.Scale):

    @molter.msg_command()
    async def test(
        self,
        ctx: dis_snek.MessageContext,
        a_num: int,
        a_user: Optional[dis_snek.Member],
        a_bool: bool,
    ):
        await ctx.message.reply(f"{a_num} {a_user} {a_bool}")


def setup(bot):
    CommandTest(bot)
```

## Note

* This project is a work in progress - it *is* unstable. Basic testing *has* been done, but more is still required.
* This hasn't been merged with `Dis-Snek` yet *because* it's unstable. Don't worry, I plan to merge these changes with `Dis-Snek` once this is ready!
* `discord.py`'s `FlagConverter` and potentially other features are not in this. If they will be added is to be seen.
* `molter` is *not* meant to be 1:1 with `discord.py`'s command parser even if it may seem like it. There are some differences, usually done for clarity's sake.
