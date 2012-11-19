import logging
import sys

from logging.handlers import SysLogHandler

class Logger(logging.Logger):
    """Subclass of the normal logger, to set up desired logging behavior.

    Specifically:
      ERROR and above go to stderr
      INFO and above go to syslog, unless debug is True then DEBUG and above

    """ 
    def __init__(self, name, debug=False):
        """
        args:
        name -- name passed to logging.Logger

        kwargs:
        debug -- bool to enable debug logging

        """
        logging.Logger.__init__(self, name)

        # Set the name, much like logging.getLogger(name) would
        formatter = logging.Formatter('%(name)s [%(levelname)s] %(message)s')

        # Emit to sys.stderr, ERROR and above
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.ERROR)
        stream_handler.setFormatter(formatter)
        self.addHandler(stream_handler)

        # Emit to syslog, INFO and above, or DEBUG if debug
        syslog_handler = SysLogHandler('/dev/log')
        if debug:
            syslog_handler.setLevel(logging.DEBUG)
        else:
            syslog_handler.setLevel(logging.INFO)
        syslog_handler.setFormatter(formatter)
        self.addHandler(syslog_handler)
