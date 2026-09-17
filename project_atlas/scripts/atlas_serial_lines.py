"""Bounded, nonblocking serial line assembly; no hardware side effects."""
class SerialLines:
    def __init__(self, capacity=65536):
        self.data = bytearray()
        self.capacity = capacity

    def feed(self, chunk):
        if len(self.data)+len(chunk) > self.capacity:
            self.data.clear()
            raise BufferError('sensor hub receive buffer overflow')
        self.data.extend(chunk)

    def pop(self):
        end = self.data.find(b'\n')
        if end < 0:
            return None
        line = bytes(self.data[:end])
        del self.data[:end+1]
        return line.decode(errors='replace').strip()


class CameraReplyGuard:
    """Do not adopt historical reports until the latest target is acknowledged.

    These are commanded pulse reports, NOT physical servo position feedback.
    """
    def __init__(self):
        self.pending = None

    def sent(self, target):
        self.pending = target

    def accept(self, report):
        if self.pending is not None and report != self.pending:
            return False
        self.pending = None
        return True
