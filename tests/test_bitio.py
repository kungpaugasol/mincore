import random

import pytest

from mincore.bitio import BitReader, BitWriter


def test_roundtrip_random():
    random.seed(0)
    for trial in range(200):
        writes = []
        for _ in range(50):
            n = random.randrange(1, 17)          # widths 1..16
            v = random.randrange(1 << n)
            writes.append((v, n))

        w = BitWriter()
        for v, n in writes:
            w.write_bits(v, n)

        r = BitReader(w.bytes())
        for v, n in writes:
            got = r.read_bits(n)
            assert got == v, f"trial {trial}: expected {v} ({n} bits), got {got}"


def test_byte_align():
    w = BitWriter()
    w.write_bits(0b101, 3)
    w.write_bytes(b"\xff\x00")

    r = BitReader(w.bytes())
    assert r.read_bits(3) == 0b101
    assert r.read_bytes(2) == b"\xff\x00"


def test_single_bits():
    pattern = [1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 1]
    w = BitWriter()
    for b in pattern:
        w.write_bit(b)

    r = BitReader(w.bytes())
    for expected in pattern:
        assert r.read_bit() == expected


def test_zero_width_write_is_noop():
    w = BitWriter()
    w.write_bits(0, 0)
    w.write_bits(7, 3)
    r = BitReader(w.bytes())
    assert r.read_bits(3) == 7


def test_reader_exhaustion_raises():
    w = BitWriter()
    w.write_bits(0b1010, 4)
    r = BitReader(w.bytes())         # buffer is 1 byte = 8 bits total
    assert r.read_bits(4) == 0b1010  # consume 4 bits
    r.read_bits(4)                   # consume the 4 padding bits → buffer fully drained
    with pytest.raises(EOFError):
        r.read_bits(1)               # now there's nothing left


def test_read_bytes_skips_partial_bits():
    w = BitWriter()
    w.write_bits(0b1, 1)      # 1 bit, gets padded to a byte on flush
    w.write_bytes(b"\xab\xcd")

    r = BitReader(w.bytes())
    assert r.read_bit() == 1
    # leftover 7 padding bits are discarded by read_bytes
    assert r.read_bytes(2) == b"\xab\xcd"
