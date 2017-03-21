#pylint: disable=too-many-public-methods,too-many-ancestors
"""
Atomic elements.
"""

from os import SEEK_SET
from struct import pack, unpack
from datetime import datetime, timedelta

from . import DecodeError, Inconsistent, MAX_DATA_SIZE
from .utility import hex_bytes, numbytes_var_int, encode_var_int, decode_var_int
from .element import Element, STATE_LOADED
from .tags import MATROSKA_TAGS
from .sortedlist import SortedList

__all__ = ['ElementAtomic', 'ElementRaw', 'ElementUnsigned', 'ElementSigned',
           'ElementBoolean', 'ElementEnum', 'ElementBitField', 'ElementFloat',
           'ElementString', 'ElementUnicode', 'ElementDate', 'ElementID']

class ElementAtomic(Element):
    """Base class for all elements that directly interpret their data.

    The data for these elements is always read and parsed immediately when
    reading from a stream.  The raw data is passed through decode() and then
    stored in self.value.  When writing, self.value is passed through encode()
    to recover the raw data.  Subclasses should reimplement these methods.

    The value property is settable.  When it is set, it passes the new value
    through the set_value() method, which subclasses can use to translate the
    value and update other class attributes.  This method also resizes the
    element if necessary.  The new size is calculated using the encoded_size()
    method.

    New atomic elements can be created with new_with_value().

    Attributes:
     + value: The decoded value of this element.  This is a read-write property.
     + default_val: The value to use for an uninitialized element.  This must be
       a valid value for the value property, and must be accepted by encode().
     + allowed_len: A list of integers, or None.  If not None, the size of any
       raw data to be read or written must be contained in allowed_len.  The
       first element in this list is the preferred size of an element created
       with new_with_value().

    The following consistency assumptions are made and enforced:
     + self.size is compatible with self.allowed_len, as described below.
     + self.value is a valid encodable value.
     + It is possible to encode self.value in self.size bytes (exception: when
       initializing from a stream, between __init__() and read_data()).
     + It is possible to encode self.default_val in the preferred size.
    """
    # Override these in subclasses
    default_val = None
    allowed_len = None

    # Private attribute:
    #  + _orig_val: The value read from the stream.

    def __init__(self, header, name='Unknown'):
        super().__init__(header, name)
        if self.allowed_len is not None and self.size not in self.allowed_len:
            raise DecodeError("{}: data has length {}, should be in {!r}" \
                              .format(self.__class__.__name__,
                                      self.size, self.allowed_len))
        self._value = self.default_val
        self._orig_val = None

    @classmethod
    def new_with_value(cls, name_or_id, value=None, parent=None,
                       pos_relative=None):
        """Create a new atomic element with a specified value.

        Args:
         + name_or_id, parent, pos_relative: As in Element.new.
         + value: Value to use.  If not specified, use default_val.  Must be a
           valid value otherwise.
        Returns:
           The new instance of ElementAtomic.  The new element's data size will
           be the maximum of its preferred size and self.data_size_min, if its
           value can be encoded in that many bytes, and whatever encoded_size()
           returns otherwise.
        """
        #pylint: disable=too-many-arguments
        data_size_min = MATROSKA_TAGS[name_or_id].data_size_min # default is 0
        if cls.allowed_len:
            allowed_len = SortedList(cls.allowed_len)
            try:
                start_size = allowed_len.find_ge(data_size_min)
            except ValueError:
                start_size = allowed_len[-1]
            start_size = max([start_size, cls.allowed_len[0]])
        else:
            start_size = data_size_min
        elt = cls.new(name_or_id, parent, pos_relative, start_size)
        if value is None:
            value = cls.default_val
        elt.value = value # Resizes if necessary
        return elt

    def intrinsic_equal(self, other):
        return Element.intrinsic_equal(self, other) and \
            self.value == other.value

    @property
    def value(self):
        "Getter for the value property."
        return self._value
    @value.setter
    def value(self, val):
        """Setter for the value property.

        Runs self.set_hook(), a hook for subclasses.  Resizes the element if
        the new value cannot be encoded in self.size bytes.  Raises
        ValueError if val is not a valid value.
        """
        newval = self.set_hook(val)
        newsize = self.encoded_size(newval, self.size)
        self._value = newval
        if self.size != newsize:
            self.resize(newsize)

    def valid_data_size_le(self, goal):
        if self.allowed_len is None:
            size = self.encoded_size(self.value, goal)
        else:
            allowed_len = SortedList(self.allowed_len)
            try:
                preferred = allowed_len.find_le(goal)
            except ValueError:
                return None # No allowed size <= goal
            size = self.encoded_size(self.value, preferred)
        # Can't return < self.min_data_size()
        size = max([size, self.min_data_size()])
        if size <= goal:
            return size
        return None

    def resize(self, new_size):
        """Resize the element with consistency checking.

        Since self.value is required to be encodable in self.size bytes, we
        can't allow resizing to other values.
        """
        if self.allowed_len is not None and new_size not in self.allowed_len:
            raise ValueError("Cannot set size of {} to {} bytes"
                             .format(self.__class__.__name__, new_size))
        if new_size != self.encoded_size(self.value, new_size):
            raise ValueError("Cannot encode value of {} in {} bytes"
                             .format(self, new_size))
        super().resize(new_size)

    def is_dirty(self):
        if super().is_dirty():
            return True
        return self._orig_val != self.value_signature(self.value)

    def set_dirty(self, val):
        super().set_dirty(val)
        if not val:
            self._orig_val = self.value_signature(self.value)

    def read_data(self, stream, seekfirst=True):
        if seekfirst:
            stream.seek(self.pos_data_absolute, SEEK_SET)
        data = stream.read(self.size)
        if len(data) != self.size:
            raise EOFError("Unexpectedly reached end of stream.")
        if self.allowed_len is None or self.size in self.allowed_len:
            self.value = self.decode(data)
        else:
            assert False
        self.read_state = STATE_LOADED

    def write(self, stream, seekfirst=True):
        """Write this element to a binary stream.

        If this element element is not dirty, this method should reproduce the
        byte stream used to read it.

        Raises:
         + ValueError: if the object's data cannot be encoded in self.size
           bytes.
        """
        if seekfirst:
            stream.seek(self.pos_absolute, SEEK_SET)
        stream.write(self.header.encode())
        stream.write(self.encode(self.value, self.size))

    # Virtual

    def set_hook(self, val):
        """Hook for setting the value property.

        Return the new value.  Must be a valid value.  Raise ValueError if
        val is not a valid value.  Subclasses should probably call
        super().set_hook().
        """
        #pylint: disable=no-self-use
        return val

    def encoded_size(self, val, preferred):
        """Calculate the size of the encoded value.

        Args:
         + val: The value to encode.  Is a valid value.
         + preferred: The preferred size.  Is a valid size.
        Returns:
           The encoded size.  If the value can be encoded in preferred bytes,
           returns preferred.  The return value must be compatible with
           self.allowed_len.
        """
        raise NotImplementedError

    def decode(self, data):
        """Decode the value from a bytes object.

        The length of the data parameter is compatible with self.allowed_len.
        Return the decoded value.  This must be a valid value.  Does not set
        self.value.
        """
        raise NotImplementedError

    def encode(self, val, size):
        """Encode a value in size bytes.

        Args:
         + val: The value to encode.  Is a valid value.
         + size: The size to encode the value in.  It is guaranteed that val can
           be encoded in size bytes accordiing to encoded_size().
        Returns:
         + The encoded value, a bytes object of size bytes.
        """
        #pylint: disable=no-self-use
        raise NotImplementedError

    # Suggested to reimplement in subclasses

    def min_data_size(self):
        if self.allowed_len is None:
            min_size = self.encoded_size(self.value, self.data_size_min)
        else:
            sizes = SortedList(self.allowed_len)
            try:
                min_size = self.encoded_size(self.value,
                                             sizes.find_ge(self.data_size_min))
            except ValueError: # self.data_size_min is too big (???)
                min_size = self.encoded_size(self.value, max(self.allowed_len))
        return min([self.size, min_size])

    def max_data_size(self):
        if self.allowed_len is None:
            # Reimplement if this is the wrong thing
            return self.encoded_size(self.value, 0)
        return self.encoded_size(self.value, max(self.allowed_len))

    def value_signature(self, val):
        """Return an object used to test equality of two values.

        This is used to test whether the value of the object has changed since
        it was read, without storing a (potentially large) value twice.  This is
        not used in self.intrinsic_equal().

        Args:
         + val: A valid value for this object.
        Returns:
           Any object 'signature' subject to the following requirements:
            - 'signature' is not None.
            - Two values 'signature1' and 'signature2' compare equal if and only
              if the original values were equal (or were extremely likely to
              have been equal).
        """
        #pylint: disable=no-self-use
        return val

    def __str__(self):
        return "{}: {!r}".format(super().__str__(), self.value)


class ElementRaw(ElementAtomic):
    "Raw byte string."
    default_val = b''

    def check_consistency(self):
        "Matroska sometimes requires that Raw UIDs have nonzero value."
        super().check_consistency()
        try:
            if self.tag.min_val > 0 and sum(self.value) == 0:
                raise Inconsistent("Zero Raw value in {!r}".format(self))
        except AttributeError:
            pass

    def set_hook(self, val):
        if not isinstance(val, bytes):
            raise ValueError("Attempt to set an invalid value {}: "
                             "must be a bytes object".format(val))
        return super().set_hook(val)

    def encoded_size(self, val, preferred):
        #pylint: disable=no-self-use
        #pylint: disable=unused-argument
        return len(val)

    def decode(self, data):
        return data

    def encode(self, val, size):
        assert len(val) == size
        return val

    def value_signature(self, val):
        """Potentially return a hash of val.

        If val is small, just return val.  Otherwise return a tuple with a
        single element consisting of a hash of val (to distinguish it from an
        ordinary bytes object).
        """
        if len(val) < 1024:
            return val
        import hashlib
        hashed = hashlib.sha512()
        hashed.update(val)
        return (hashed.digest(), )

    def __str__(self):
        if len(self.value) > 32:
            val_str = "[size {}]".format(len(self.value))
        else:
            val_str = hex_bytes(self.value)
        return "{}: {}".format(Element.__str__(self), val_str)


class ElementUnsigned(ElementAtomic):
    "Unsigned integer."
    signed = False
    default_val = 0
    allowed_len = [4, 1, 2, 3, 5, 6, 7, 8] # 4 is preferred size

    def check_consistency(self):
        super().check_consistency()
        try:
            if self.value < self.tag.min_val:
                raise Inconsistent("Value {} < min value {} in {!r}"
                                   .format(self.value, self.tag.min_val, self))
            if self.value > self.tag.max_val:
                raise Inconsistent("Value {} > max value {} in {!r}"
                                   .format(self.value, self.tag.max_val, self))
        except AttributeError:
            pass

    def set_hook(self, val):
        if not isinstance(val, int):
            raise ValueError("Attempt to set EBML integer value to "
                             "non-integer {!r}".format(val))
        if val >= (1 << 64):
            raise ValueError("Cannot encode integer {} >= 2^64".format(val))
        if val < 0 and not self.signed:
            raise ValueError("Tried to set Unsigned to the negative value {}"
                             .format(val))
        return super().set_hook(val)

    def encoded_size(self, val, preferred):
        assert preferred in self.allowed_len
        val2 = val >> 8
        size = 1
        while val2:
            val2 >>= 8
            size += 1
        return max([size, preferred])

    def decode(self, data):
        return int.from_bytes(data, byteorder='big', signed=self.signed)

    def encode(self, val, size):
        return val.to_bytes(size, byteorder='big', signed=self.signed)


class ElementSigned(ElementUnsigned):
    "Signed integer."
    signed = True


class ElementBoolean(ElementUnsigned):
    "Boolean value."
    allowed_len = [1, 2, 3, 4, 5, 6, 7, 8] # 1 is preferred size
    # Python's bool is also a subclass of int
    def intrinsic_equal(self, other):
        return Element.intrinsic_equal(self, other) and \
            bool(self.value) == bool(other.value)

    def __str__(self):
        return "{}: {} ({!r})".format(Element.__str__(self),
                                      self.value, bool(self.value))


class ElementEnum(ElementUnsigned):
    "Enumerated value."
    allowed_len = [1, 2, 3, 4, 5, 6, 7, 8] # 1 is preferred size
    def __init__(self, header, name='Unknown'):
        super().__init__(header, name)
        self.string_val = "UNKNOWN"

    def set_hook(self, val):
        """Set the value to val, which may be a string or an integer.

        Raise EbmlException if val is a string which is not a recognized enum
        value.
        """
        if isinstance(val, str):
            try:
                val = next(key for key, value in self.tag.values.items()
                           if value == val)
            except StopIteration:
                raise ValueError("Unknown enum value {!r}".format(val))
        val = super().set_hook(val) # Check it's a valid integer
        try:
            self.string_val = self.tag.values[val]
        except KeyError:
            self.string_val = "UNKNOWN"
        return val

    def __str__(self):
        return "{}: {} ({})".format(Element.__str__(self),
                                    self.value, self.string_val)


class ElementBitField(ElementUnsigned):
    "Bit field."

    def __init__(self, header, name='Unknown'):
        super().__init__(header, name)
        self.string_val = "[empty]"

    def set_hook(self, val):
        "Set self.value and self.string_val."
        val = super().set_hook(val) # Check it's a valid integer
        strings = []
        for i in range(len(self.tag.values)):
            if val & (1 << i) and self.tag.values[i]:
                strings.append(self.tag.values[i])
        if strings:
            self.string_val = ", ".join(strings)
        else:
            self.string_val = "[empty]"
        return val

    def __str__(self):
        return "{}: 0b{:b} ({})".format(Element.__str__(self),
                                        self.value, self.string_val)


class ElementFloat(ElementAtomic):
    "Floating point (float or double)."
    default_val = 0.0
    allowed_len = [4, 8]

    def check_consistency(self):
        super().check_consistency()
        try:
            if self.value <= self.tag.min_val:
                raise Inconsistent("Value {} <= min value {} in {!r}"
                                   .format(self.value, self.tag.min_val, self))
            if self.value >= self.tag.max_val:
                raise Inconsistent("Value {} >= max value {} in {!r}"
                                   .format(self.value, self.tag.max_val, self))
        except AttributeError:
            pass

    def set_hook(self, val):
        if isinstance(val, int):
            val = float(val)
        if not isinstance(val, float):
            raise ValueError("Attempt to set EBML float value to "
                             "non-float {!r}".format(val))
        return super().set_hook(val)

    def min_data_size(self):
        # Don't lose precision
        return self.size

    def encoded_size(self, val, preferred):
        assert preferred in self.allowed_len
        return max(preferred, self.size) # Don't lose precision

    def decode(self, data):
        if len(data) == 4:
            return unpack('>f', data)[0]
        elif len(data) == 8:
            return unpack('>d', data)[0]
        assert False

    def encode(self, val, size):
        if size == 4:
            return pack('>f', val)
        elif size == 8:
            return pack('>d', val)
        assert False


class ElementString(ElementAtomic):
    "ASCII string."
    codec = 'ascii'
    default_val = ''

    def set_hook(self, val):
        if not isinstance(val, str):
            raise ValueError("Attempt to set EBML string value to "
                             "non-string {!r}".format(val))
        return super().set_hook(val)

    def encoded_size(self, val, preferred):
        size = len(val.encode(self.codec, errors='replace'))
        return max([size, preferred])

    def max_data_size(self):
        # Strings can be zero-padded, hence can be arbitrarily long
        return MAX_DATA_SIZE

    def decode(self, data):
        return data.rstrip(b'\x00').decode(self.codec, errors='replace')

    def encode(self, val, size):
        ret = val.encode(self.codec, errors='replace')
        assert size >= len(ret)
        return ret + b'\x00' * (size - len(ret))


class ElementUnicode(ElementString):
    "Unicode string."
    codec = 'utf-8'


class ElementDate(ElementSigned):
    """Date value.

    Matroska dates are encoded as 8-bit signed integers representing nanoseconds
    since the Matroska epoch.
    """
    allowed_len = [8]
    epoch = datetime(2001, 1, 1)
    default_val = epoch

    def set_hook(self, val):
        if not isinstance(val, datetime):
            raise ValueError("Attempt to set EBML date value to "
                             "non-date {!r}".format(val))
        return val

    def encoded_size(self, val, preferred):
        assert preferred == 8
        return preferred

    def decode(self, data):
        intval = super().decode(data)
        return self.epoch + timedelta(microseconds=(intval/1000))

    def encode(self, val, size):
        assert size == 8
        intval = int((val - datetime(2001, 1, 1)).total_seconds() * 1e9)
        return super().encode(intval, size)

    def __str__(self):
        #pylint: disable=maybe-no-member
        return "{}: {}".format(Element.__str__(self),
                               self.value.strftime("%Y-%m-%d %H:%M:%S"))


class ElementID(ElementAtomic):
    "EBML ID."
    default_val = 0
    allowed_len = [1, 2, 3, 4]

    def __init__(self, header, name='Unknown'):
        super().__init__(header, name)
        self.raw = b''
        self.string_name = "Unknown"

    def set_hook(self, val):
        "Set self.raw, self.string_name."
        if not isinstance(val, int) or numbytes_var_int(val) > 4:
            raise ValueError("Attempt to set EBML ID value to "
                             "invalid number {!r}".format(val))
        self.raw = encode_var_int(val, numbytes=range(1, 5))
        self.string_name = MATROSKA_TAGS[val].name
        return super().set_hook(val)

    def encoded_size(self, val, preferred):
        return numbytes_var_int(val)

    def decode(self, data):
        val, _ = decode_var_int(data)
        return val

    def encode(self, val, size):
        raw = encode_var_int(val, numbytes=range(1, 5))
        assert len(raw) == size
        return raw

    def __str__(self):
        return "{}: [{}] ({})".format(Element.__str__(self),
                                      hex_bytes(self.raw), self.string_name)

