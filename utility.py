"""
Utility functions.
"""

from io import BytesIO

from . import DecodeError

__all__ = ['hex_bytes', 'numbytes_var_int', 'max_var_int_in',
           'encode_var_int', 'decode_var_int', 'read_var_int', 'fmt_time']

def hex_bytes(bytestring):
    """Return a string representation of a byte string.

    Args:
     + bytestring: A bytes object.
    Returns:
       A string of the form 1A:2B:3D:4E
    """
    return ":".join("{:02X}".format(c) for c in bytestring)

def numbytes_var_int(number):
    """Determine the minimum encoded size of an integer.

    Args:
     + number: An integer.
    Returns:
       The minimum number of bytes needed to encode 'number' as in
       encode_var_int(), or None if it can't be done.
    """
    #pylint: disable=too-many-return-statements
    # This function has to be FAST
    number += 1
    number >>= 7
    if number == 0:
        return 1
    number >>= 7
    if number == 0:
        return 2
    number >>= 7
    if number == 0:
        return 3
    number >>= 7
    if number == 0:
        return 4
    number >>= 7
    if number == 0:
        return 5
    number >>= 7
    if number == 0:
        return 6
    number >>= 7
    if number == 0:
        return 7
    number >>= 7
    if number == 0:
        return 8
    # for size in range(1, 9):
    #     number >>= 7
    #     if number == 0:
    #         return size
    # for size in range(1, 9):
    #     if number <= (1 << (size*7)) - 2:
    #         return size
    return None

def max_var_int_in(size):
    "Return the largest integer encodable in size bytes."
    return (1<<(size*7))-2

def encode_var_int(number, numbytes=range(1, 9)):
    """Encode 'number' as an EBML variable-size integer.

    This will not encode the special value, i.e. the bitstring 0b0..01..1.  The
    numbytes parameter must be an integer or an iterable of integers.

    Args:
     + number: An integer to encode.
     + numbytes: An iterable of increasing integers.  The number will be encoded
       in the smallest number of bytes in 'numbytes'.
    Returns:
       The encoded integer.
    Raises:
     + ValueError, if the largest value in 'numbytes' is not sufficient to
       encode 'number'.
    """
    if isinstance(numbytes, int):
        numbytes = [numbytes]
    size = 0
    for size in numbytes:
        bits = size*7
        if number <= (1 << bits) - 2:
            return ((1 << bits) + number).to_bytes(size, byteorder='big')
    raise ValueError("Can't store {} in {} bytes".format(number, size))

def decode_var_int(bytestring, max_bytes=8):
    """Decode an EBML-encoded integer from a bytes object.

    See read_var_int().
    """
    data = BytesIO(bytestring)
    return read_var_int(data, max_bytes)

def read_var_int(stream, max_bytes=8):
    """Read EBML-encoded integer from a stream.

    Read an EBML-encoded variable-style integer with length descriptor from a
    binary stream.  Both the EBML ID and the size parts of an EBML header are
    encoded this way.

    Args:
     + stream: The binary stream to read.  The encoded integer will be read from
       the current position in the stream, and the stream will be advanced by
       the (as yet to be determined) length of the encoded integer to read.
     + max_bytes: The largest number of bytes to read.
    Returns:
       A tuple (val, raw), where 'val' is the integer value and 'raw' is the
       byte string that was read.  Set 'val' to None if we read the special
       value, i.e. the bitstring 0b0..01..1.
    Raises:
     + EOFError, for an unexpected end of stream.
     + DecodeError, if the encoded integer at point is unrecognized or is larger
       than max_bytes.
    """
    first_byte = stream.read(1)
    if len(first_byte) != 1:
        raise EOFError("End of stream reached.")
    first_char = first_byte[0]
    for size in range(max_bytes):
        i = 7-size
        if first_char & (1<<i):  # size+1 bytes
            first_char ^= (1<<i)
            rest = stream.read(size)
            if len(rest) != size:
                raise EOFError("End of stream reached.")
            val = (first_char << (size*8)) \
                  + int.from_bytes(rest, byteorder='big')
            # Detect all 1's (binary).  This is a special value.
            if val == ((1 << 7*(size+1)) - 1):
                return (None, first_byte + rest)
            return (val, first_byte + rest)
    raise DecodeError("Invalid value more than {} bytes".format(max_bytes))

def fmt_time(nsecs, precision=9, sep='.'):
    "Format a time in nanoseconds to precision decimal places."
    secs = int(nsecs/1000000000)
    mins = int(secs/60)
    hours = int(mins/60)
    frac = str(nsecs/1000000000 - secs)[2:precision+2]
    frac = frac + '0' * (precision - len(frac))
    return "{:02d}:{:02d}:{:02d}".format(hours, mins % 60, secs % 60) \
        + sep + frac
