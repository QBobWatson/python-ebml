"""
EBML Header parsing.
"""

from . import DecodeError
from .utility import hex_bytes, encode_var_int, numbytes_var_int, read_var_int

__all__ = ['Header']

class Header:
    """Class representing the header of an EBML element.

    The header of an EBML element consists of its element ID and its size.
    This class is responsible for decoding and encoding a header.

    The encoded header is not uniquely determined by the element ID and size,
    since the size attribute may be encoded with different length descriptors.
    (If I understand correctly, however, the element ID may only be encoded with
    its canonical length descriptor, except for the reserved ID, which we don't
    handle.)  For in-place modifications it is important to keep the total size
    of an element unchanged if possible, so the encoding methods here offer
    flexibility in the encoded header size.

    Attributes:
     + ebml_id: The decoded id (read-only).
     + size: The element size.
     + numbytes: The number of bytes to use to encode the header.  This is
       read-write, but must be an integer between numbytes_min and numbytes_max.
     + numbytes_id: The size of the encoded ID part of the header.
     + numbytes_size_min: The minimum number of bytes needed to encode
       self.size.
     + numbytes_size_max: The maximum number of bytes that can be used to encode
       self.size.
     + numbytes_min: = numbytes_id + numbytes_size_min
     + numbytes_max = numbytes_id + numbytes_size_max
     + encoded_id: The canonically-encoded version of ebml_id.

    Setting self.size may increase self.numbytes but never decreases it.
    """

    def __init__(self, stream=None, ebml_id=None, size=None):
        """Args:
         + stream: A binary stream from which to read the header.  If not None,
           there must be an encoded EBML header at the current stream position.
         + ebml_id: The integer value of the decoded EBML ID.
         + size: The integer value of the decoded element size.

        If 'stream' is not None, read the header from the 'stream', advancing
        its position by the size of the header.  Otherwise initialize with
        'ebml_id' and 'size'.

        Raise ValueError if these requirements are not met.
        """
        if stream is None and (ebml_id is None or size is None):
            raise ValueError("Need stream or ebml_id "
                             "and size to initialize Header")
        self._numbytes = None
        self._size = None
        if stream:
            self.decode(stream)
        else:
            self._ebml_id = ebml_id
            # Sets self.numbytes
            self.size = size

    def __eq__(self, other):
        return self.ebml_id == other.ebml_id and self.size == other.size
    def __ne__(self, other):
        return not self == other

    def copy(self):
        "Create a copy of this Header."
        ret = Header(ebml_id=self.ebml_id, size=self.size)
        ret.numbytes = self.numbytes
        return ret

    def __repr__(self):
        return "{}(ebml_id=0x{:X}, size={})" \
            .format(self.__class__.__name__,
                    self.ebml_id, self.size)

    def __str__(self):
        return "{}(ebml_id=[{}] size={})" \
            .format(self.__class__.__name__,
                    hex_bytes(self.encoded_id), self.size)

    @property
    def ebml_id(self):
        "Get read-only property self.ebml_id."
        return self._ebml_id
    @property
    def size(self):
        "Get property self.size."
        return self._size
    @size.setter
    def size(self, val):
        "Set property self.size and recalculate self.numbytes."
        self._size = val
        if self.numbytes is None or self.numbytes < self.numbytes_min:
            self.numbytes = self.numbytes_min
    @property
    def numbytes(self):
        "Get property self.numbytes."
        return self._numbytes
    @numbytes.setter
    def numbytes(self, val):
        """Set property self.numbytes.

        The value must be between self.numbytes_min and self.numbytes_max,
        inclusive.  Raise ValueError otherwise.
        """
        if val > self.numbytes_max or val < self.numbytes_min:
            raise ValueError("Cannot encode header with {} bytes".format(val))
        self._numbytes = val
    @property
    def numbytes_min(self):
        "Get calculated property self.numbytes_min."
        return self.numbytes_id + self.numbytes_size_min
    @property
    def numbytes_max(self):
        "Get calculated property self.numbytes_max."
        return self.numbytes_id + self.numbytes_size_max
    @property
    def encoded_id(self):
        "Get the (canonically) encoded self.ebml_id."
        return encode_var_int(self.ebml_id, numbytes=range(1, 5))

    @property
    def numbytes_id(self):
        "Get the (fixed) number of bytes to encode self.ebml_id."
        return numbytes_var_int(self.ebml_id)
    @property
    def numbytes_size_min(self):
        "Get the minimum number of bytes to encode self.size."
        return numbytes_var_int(self.size)
    numbytes_size_max = 8

    def decode(self, stream):
        """Decode the header from a binary stream.

        Set self.ebml_id and self.size accordingly.  Set self.numbytes to the
        actual size of the encoded header in the stream.

        Args:
         + stream: A binary stream.  Decoding begins at the current position in
           the stream.  The current position is advanced by the size of the
           encoded header.
        Raises:
         + DecodeError, if there is not a valid header at the current position
           in 'stream'.
         + EOFError, for an unexpected end of stream.
        """
        ebml_id, raw = read_var_int(stream, 4)
        numbytes_id = len(raw)
        if ebml_id is None:
            raise DecodeError("Can't handle reserved EBML ID")
        if numbytes_id != numbytes_var_int(ebml_id):
            raise DecodeError("EBML ID not canonically encoded")
        size, raw = read_var_int(stream)
        if size is None:
            raise DecodeError("Can't handle reserved EBML size")
        self._ebml_id = ebml_id
        self._size = size
        self._numbytes = numbytes_id + len(raw)

    def encode(self):
        """Encode the header to a bytes object.

        Returns:
           The encoded header.  It will have size self.numbytes.
        """
        enc_id = self.encoded_id
        enc_size = encode_var_int(self.size, self.numbytes-len(enc_id))
        return enc_id + enc_size
