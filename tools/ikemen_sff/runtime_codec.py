"""Runtime sprite payload encoders used by the Saturn SFF converter."""
from __future__ import annotations


def encode_rle8(data: bytes) -> bytes:
    """Encode 8-bit pixels as bounded runs and literals.

    Each token stores length minus one in its low seven bits. A set high bit
    means the next byte repeats; otherwise the next `length` bytes are literal.
    """
    encoded = bytearray()
    size = len(data)
    cursor = 0
    while cursor < size:
        run = 1
        while (cursor + run < size and data[cursor + run] == data[cursor]
               and run < 128):
            run += 1
        if run >= 3:
            encoded.extend((0x80 | (run - 1), data[cursor]))
            cursor += run
            continue

        literal_start = cursor
        cursor += run
        while cursor < size and cursor - literal_start < 128:
            run = 1
            while (cursor + run < size and data[cursor + run] == data[cursor]
                   and run < 128):
                run += 1
            if run >= 3:
                break
            cursor += min(run, 128 - (cursor - literal_start))
        literal_count = cursor - literal_start
        encoded.append(literal_count - 1)
        encoded.extend(data[literal_start:cursor])
    return bytes(encoded)
