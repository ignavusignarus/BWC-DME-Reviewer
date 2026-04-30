"""BWC Clipper engine entry point.

Picks a free port on 127.0.0.1, starts the HTTP server, and prints
``BWC_CLIPPER_PORT=<port>`` to stdout so the Electron parent process can
parse it. Keeps running until killed.
"""
import logging
import socket
import sys
from http.server import HTTPServer

from engine.server import BWCRequestHandler
from engine.version import BWC_CLIPPER_VERSION


def pick_free_port() -> int:
    """Bind to port 0, get the OS-assigned port, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    logger = logging.getLogger("bwc-clipper.serve")

    # Make ffmpeg discoverable on PATH for libraries that shell out to it
    # (whisperx, ffmpeg-python, etc.). Done here so it propagates to all
    # threads / subprocesses spawned by the engine.
    from engine.ffmpeg import prepend_ffmpeg_to_path
    ffmpeg_dir = prepend_ffmpeg_to_path()
    if ffmpeg_dir:
        logger.info("ffmpeg discoverable on PATH: %s", ffmpeg_dir)
    else:
        logger.warning("ffmpeg not found — whisperx and other ffmpeg-using libs will fail")

    port = pick_free_port()
    logger.info("starting BWC Clipper engine version %s on port %d", BWC_CLIPPER_VERSION, port)

    # Print the port on a clearly-prefixed line so the parent (Electron)
    # can robustly parse it without confusing log output.
    print(f"BWC_CLIPPER_PORT={port}", flush=True)

    server = HTTPServer(("127.0.0.1", port), BWCRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
