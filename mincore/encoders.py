"""encoders.py — pure function pairs: encode(values) -> bytes, decode(bytes, count) -> values.

Every encoder in this module follows the same contract:
  - encode takes a list of values (int, float, or str)
  - decode takes the byte payload and the count of values to produce
  - decode(encode(values), len(values)) == values, always

The container stores the encoder tag per column, so decode is dispatched by
looking up the tag in the REGISTRY at the bottom of this file. No encoder
knows about any other encoder. No encoder knows about the container format.
"""

from __future__ import annotations

import struct

from mincore.bitio import BitReader, BitWriter


# ---------------------------------------------------------------------------
# varint — LEB128 with zigzag. The fallback for any integer column.
# ---------------------------------------------------------------------------

def encode_varint(values: list[int]) -> bytes:
    out = bytearray()
    for v in values:
        # zigzag: map signed ints to unsigned so small magnitudes stay small
        z = (v << 1) ^ (v >> 63) if v < 0 else (v << 1)
        while True:
            b = z & 0x7F
            z >>= 7
            if z:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
    return bytes(out)


def decode_varint(data: bytes, count: int) -> list[int]:
    out = []
    i = 0
    for _ in range(count):
        shift = 0
        z = 0
        while True:
            b = data[i]
            i += 1
            z |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        v = (z >> 1) ^ -(z & 1)   # un-zigzag
        out.append(v)
    return out

# ---------------------------------------------------------------------------
# delta-of-delta — for evenly-spaced integer sequences (timestamps, counters).
# ---------------------------------------------------------------------------

def encode_dod(values: list[int]) -> bytes:
    """Encode a monotonic integer sequence via second differences.

    Layout (all bit-packed, MSB-first within each field):
      6 bits: bit-width of the first delta-of-delta
      N bits: the first dod value (zigzag, bit-width N)
      ... repeated for each subsequent dod
    """
    if len(values) < 2:
        return encode_varint(values)

    deltas = [values[0]]
    for i in range(1, len(values)):
        deltas.append(values[i] - values[i - 1])

    dods = [deltas[0], deltas[1]]
    for i in range(2, len(deltas)):
        dods.append(deltas[i] - deltas[i - 1])

    w = BitWriter()
    for d in dods:
        z = (d << 1) ^ (d >> 63) if d < 0 else (d << 1)
        nbits = max(1, z.bit_length())
        assert nbits <= 63, f"dod value {d} too large for 6-bit length"
        w.write_bits(nbits, 6)
        w.write_bits(z, nbits)
    return w.bytes()


def decode_dod(data: bytes, count: int) -> list[int]:
    if count < 2:
        return decode_varint(data, count)

    r = BitReader(data)
    dods = []
    for _ in range(count):
        nbits = r.read_bits(6)
        z = r.read_bits(nbits)
        d = (z >> 1) ^ -(z & 1)
        dods.append(d)

    deltas = [dods[0], dods[1]]
    for i in range(2, len(dods)):
        deltas.append(deltas[i - 1] + dods[i])

    ts = [deltas[0]]
    for i in range(1, len(deltas)):
        ts.append(ts[i - 1] + deltas[i])
    return ts

# ---------------------------------------------------------------------------
# gorilla XOR — for slowly-changing float sequences.
# Based on the Facebook Gorilla TSDB paper. Exploits the fact that
# consecutive floats in a series share exponent and high mantissa bits.
# ---------------------------------------------------------------------------

def _f2i(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _i2f(x: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", x))[0]


def encode_gorilla(values: list[float]) -> bytes:
    w = BitWriter()
    if not values:
        return w.bytes()

    prev = _f2i(values[0])
    w.write_bits(prev, 64)

    prev_leading = 64
    prev_trailing = 0

    for v in values[1:]:
        cur = _f2i(v)
        xor = cur ^ prev
        if xor == 0:
            w.write_bit(0)
        else:
            w.write_bit(1)
            leading = 64 - xor.bit_length()
            trailing = (xor & -xor).bit_length() - 1
            if leading >= prev_leading and trailing >= prev_trailing:
                # reuse previous window
                w.write_bit(0)
                meaningful = 64 - prev_leading - prev_trailing
                w.write_bits(xor >> prev_trailing, meaningful)
            else:
                w.write_bit(1)
                meaningful = 64 - leading - trailing
                w.write_bits(leading, 6)
                w.write_bits(meaningful, 6)
                w.write_bits(xor >> trailing, meaningful)
                prev_leading = leading
                prev_trailing = trailing
        prev = cur

    return w.bytes()


def decode_gorilla(data: bytes, count: int) -> list[float]:
    r = BitReader(data)
    out = []
    if count == 0:
        return out

    prev = r.read_bits(64)
    out.append(_i2f(prev))

    prev_leading = 64
    prev_trailing = 0

    for _ in range(1, count):
        if r.read_bit() == 0:
            cur = prev
        else:
            if r.read_bit() == 0:
                meaningful = 64 - prev_leading - prev_trailing
                xor = r.read_bits(meaningful) << prev_trailing
            else:
                leading = r.read_bits(6)
                meaningful = r.read_bits(6)
                trailing = 64 - leading - meaningful
                xor = r.read_bits(meaningful) << trailing
                prev_leading = leading
                prev_trailing = trailing
            cur = prev ^ xor
        out.append(_i2f(cur))
        prev = cur

    return out

# ---------------------------------------------------------------------------
# dictionary — for low-cardinality string columns (symbols, exchanges, etc.)
# ---------------------------------------------------------------------------

def encode_dict(values: list[str]) -> bytes:
    vocab: dict[str, int] = {}
    codes: list[int] = []
    for v in values:
        if v not in vocab:
            vocab[v] = len(vocab)
        codes.append(vocab[v])

    out = bytearray()
    out += struct.pack("<I", len(vocab))
    # stable order: sort by string so encode is deterministic across runs
    for s in sorted(vocab, key=vocab.get):
        b = s.encode()
        out += struct.pack("<H", len(b))
        out += b
    out += encode_varint(codes)
    return bytes(out)


def decode_dict(data: bytes, count: int) -> list[str]:
    n = struct.unpack("<I", data[:4])[0]
    pos = 4
    vocab = []
    for _ in range(n):
        l = struct.unpack("<H", data[pos:pos + 2])[0]
        pos += 2
        vocab.append(data[pos:pos + l].decode())
        pos += l
    codes = decode_varint(data[pos:], count)
    return [vocab[c] for c in codes]
