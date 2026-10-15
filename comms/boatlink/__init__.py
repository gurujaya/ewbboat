"""boatlink: the one piece of code that talks over the radio.

Both the boat Pi and the ground station import this. Nothing else in the repo
opens a UDP socket or builds a JSON message by hand.

    from boatlink import Link
    link = Link(name="boat", listen=("0.0.0.0", 5001), peer=("192.168.4.1", 5000))
    link.on("cmd", handle_cmd)
    link.on_link_lost(lambda: ...)
    link.start()
    link.send("tlm", {...})

Every message type is defined in docs/MESSAGES.md.
"""

from .link import Link
from .messages import encode, decode, TYPES

__all__ = ["Link", "encode", "decode", "TYPES"]
