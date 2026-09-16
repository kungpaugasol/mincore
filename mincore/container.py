import struct
from dataclasses import dataclass

MAGIC = b"MINC"
VERSION = 1

# type tags
T_INT = 0
T_FLOAT = 1
T_STR = 2
T_BYTES = 3

@dataclass
class Column:
    name: str
    type_tag: int
    enc_tag: int
    payload: bytes

def _write_container_to_fileobj(columns, row_count, f):
    f.write(MAGIC)
    f.write(struct.pack("<BQI", VERSION, row_count, len(columns)))
    for c in columns:
        name = c.name.encode()
        f.write(struct.pack("<B", len(name)))
        f.write(name)
        f.write(struct.pack("<BBI", c.type_tag, c.enc_tag, len(c.payload)))
    for c in columns:
        f.write(c.payload)


def write_container(columns, row_count, out_path):
    with open(out_path, "wb") as f:
        _write_container_to_fileobj(columns, row_count, f)


def _read_container_from_fileobj(f):
    assert f.read(4) == MAGIC
    version, row_count, ncols = struct.unpack("<BQI", f.read(13))
    assert version == VERSION
    cols = []
    for _ in range(ncols):
        nlen = struct.unpack("<B", f.read(1))[0]
        name = f.read(nlen).decode()
        type_tag, enc_tag, plen = struct.unpack("<BBI", f.read(6))
        cols.append((name, type_tag, enc_tag, plen))
    out = []
    for name, type_tag, enc_tag, plen in cols:
        payload = f.read(plen)
        out.append(Column(name, type_tag, enc_tag, payload))
    return row_count, out


def read_container(path):
    with open(path, "rb") as f:
        return _read_container_from_fileobj(f)
