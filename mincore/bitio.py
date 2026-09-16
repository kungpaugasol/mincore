"""
bitio.py — the only place raw bit twiddling lives.

Contract:
  - BitWriter buffers partial bytes. flush() pads the trailing byte with
    zero bits on the right.
  - BitWriter.write_bytes() auto-flushes before appending, so byte writes
    always land on byte boundaries.
  - BitReader.read_bits(n) may leave the reader mid-byte; partial bits sit
    in an internal accumulator.
  - BitReader.read_bytes(n) discards any partial bits, snapping to the next
    byte boundary. Symmetric with BitWriter.write_bytes()'s auto-flush.
  - BitReader raises EOFError only when the underlying byte buffer is
    exhausted — not when the padding bits within the last byte are consumed.
    Decoders must use an explicit count (for example: row_count from the container
    header) to know when to stop; padding bits are not distinguishable from
    real bits at this layer.
"""


class BitWriter:
    def __init__(self):
        self._buf = bytearray()
        self._acc = 0        # accumulator (int)
        self._nbits = 0      # bits currently in accumulator

    def write_bits(self, value: int, n: int) -> None:
        # value's low n bits are written, MSB-first within the field
        assert 0 <= value < (1 << n) or n == 0
        self._acc = (self._acc << n) | (value & ((1 << n) - 1))
        self._nbits += n
        while self._nbits >= 8:
            self._nbits -= 8
            self._buf.append((self._acc >> self._nbits) & 0xFF)
        self._acc &= (1 << self._nbits) - 1

    def write_bit(self, b: int) -> None:
        self.write_bits(b & 1, 1)

    def write_bytes(self, data: bytes) -> None:
        if self._nbits:
            self.flush()   # byte-align first
        self._buf.extend(data)

    def flush(self) -> None:
        if self._nbits:
            self._buf.append((self._acc << (8 - self._nbits)) & 0xFF)
            self._acc = 0
            self._nbits = 0

    def bytes(self) -> bytes:
        self.flush()
        return bytes(self._buf)


class BitReader:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0        # byte position
        self._acc = 0
        self._nbits = 0

    def read_bits(self, n: int) -> int:
        while self._nbits < n:
            if self._pos >= len(self._data):
                raise EOFError("bit stream exhausted")
            self._acc = (self._acc << 8) | self._data[self._pos]
            self._pos += 1
            self._nbits += 8
        self._nbits -= n
        v = (self._acc >> self._nbits) & ((1 << n) - 1)
        self._acc &= (1 << self._nbits) - 1
        return v

    def read_bit(self) -> int:
        return self.read_bits(1)

    def read_bytes(self, n: int) -> bytes:
        # Discard any partial bits — matches BitWriter.write_bytes()'s auto-flush,
        # which pads the partial byte. These bits are padding, safe to drop.
        self._nbits = 0
        self._acc = 0
        out = self._data[self._pos:self._pos + n]
        self._pos += n
        return out
