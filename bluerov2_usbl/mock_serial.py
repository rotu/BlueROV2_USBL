import itertools
import random
import time
from io import RawIOBase
from pathlib import Path

from serial import portNotOpenError


class MockSerial(RawIOBase):
    def __init__(self, port, **kwargs):
        """
        Object which works like a serial port (as much as we can)
        """
        self.name = port
        lines = Path(port).read_bytes().splitlines()
        lines = [b.strip() for b in lines]
        lines = [b for b in lines if b]
        self.line_iterator = itertools.cycle(lines)
        self._closed = False
        time.sleep(0.1)

    def readline(self, *args, **kwargs):
        if self.closed:
            raise portNotOpenError
        time.sleep(max(0, random.uniform(-0.2, 0.2)))
        return next(self.line_iterator) + b'\r\n'

    def readable(self): return True

    def writable(self): return False

    def seekable(self): return False

    @property
    def closed(self):
        return self._closed

    def close(self, *args, **kwargs):
        self._closed = True
