"""Logging configuration for ari_backup package."""
import logging
import logging.handlers
import os
import sys


class Logger(logging.Logger):
    """Subclass of the normal logger, to set up desired logging behavior.

    Specifically:
      ERROR and above go to stderr
      INFO and above go to syslog, unless debug is True then DEBUG and above
    """

    def __init__(self,
                 name: str,
                 debug: bool = False,
                 stderr_logging: bool = True):
        """Initilizes Logger.

        Args:
            name: name passed to logging.Logger.
            debug: whether to enable debug logging.
            stderr_logging: whether to log to stderr.
        """
        logging.Logger.__init__(self, name)
        self.stderr_handler = None
        self.syslog_handler = None

        # Set the name, much like logging.getLogger(name) would.
        if debug:
            log_format = ('%(name)s [%(levelname)s] %(filename)s:%(lineno)d '
                          '%(message)s')
        else:
            log_format = '%(name)s [%(levelname)s] %(message)s'
        formatter = logging.Formatter(log_format)

        # Emit to sys.stderr, ERROR and above, unless debug is True.
        if stderr_logging:
            self.stderr_handler = logging.StreamHandler(sys.stderr)
            if debug:
                self.stderr_handler.setLevel(logging.DEBUG)
            else:
                self.stderr_handler.setLevel(logging.ERROR)
            self.stderr_handler.setFormatter(formatter)
            self.addHandler(self.stderr_handler)

        # On some systems (e.g. docker containers) /dev/log might not be
        # available.
        if os.access('/dev/log', os.W_OK):
            # Emit to syslog, INFO and above, or DEBUG if debug.
            self.syslog_handler = logging.handlers.SysLogHandler('/dev/log')
            if debug:
                self.syslog_handler.setLevel(logging.DEBUG)
            else:
                self.syslog_handler.setLevel(logging.INFO)
            self.syslog_handler.setFormatter(formatter)
            self.addHandler(self.syslog_handler)

    def __del__(self):
        if self.stderr_handler:
            self.stderr_handler.close()
        if self.syslog_handler:
            self.syslog_handler.close()
