import io
import logging
import unittest
from unittest.mock import patch

from bot.main import configure_logging


class LoggingTests(unittest.TestCase):
    def test_normal_logs_use_stdout_and_errors_use_stderr(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("bot.main.sys.stdout", stdout),
            patch("bot.main.sys.stderr", stderr),
            patch("bot.main.logging.basicConfig") as configure,
        ):
            configure_logging()

        handlers = configure.call_args.kwargs["handlers"]
        logger = logging.Logger("test")
        for handler in handlers:
            logger.addHandler(handler)
        logger.info("polling started")
        logger.warning("retrying")
        logger.error("polling failed")

        self.assertIn("polling started", stdout.getvalue())
        self.assertIn("retrying", stdout.getvalue())
        self.assertNotIn("polling failed", stdout.getvalue())
        self.assertIn("polling failed", stderr.getvalue())
        self.assertNotIn("polling started", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
