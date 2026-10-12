"""Stalwart's junk port (stalwart-provision's NetworkListener): Stalwart
opens a listener only when it starts, so the first start after init created
it restarts Stalwart once. Used by tools/deploy and tools/demo.

    open_junk_port(compose, healthy, say)

compose(*args, capture=False): runs `docker compose ...` for the stack;
healthy(): whether Stalwart reports healthy; say(text): progress. Raises
RuntimeError when the port is still closed after the restart.
"""
import time

# Run in mail-bridge, which has MAILSTACK_JUNK_PORT from stack.env.
PROBE = ("import os, socket\n"
         "try: socket.create_connection(('stalwart', int(os.environ['MAILSTACK_JUNK_PORT'])), 5).close(); print('up')\n"
         "except OSError: print('down')")


def open_junk_port(compose, healthy, say, timeout=300):
    def probe():
        return compose("exec", "-T", "mail-bridge", "python3", "-c", PROBE, capture=True).strip()

    if probe() == "up":
        return
    say("Stalwart restarts once to open the junk port")
    compose("restart", "stalwart")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if healthy() and probe() == "up":
            say("junk port open")
            return
        time.sleep(3)
    raise RuntimeError("Stalwart's junk port did not open after a restart")
