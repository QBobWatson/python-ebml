#pylint: disable=too-many-public-methods,too-many-ancestors
"""
Basic Element types: Element, Unsupported, Placeholder, Void, Master,
MasterDefer.
"""

from os import SEEK_SET, SEEK_CUR

from . import Inconsistent, EbmlException, MAX_DATA_SIZE
from .utility import hex_bytes
from .header import Header
from .container import Container
from .tags import MATROSKA_TAGS

__all__ = ['Element', 'ElementUnsupported', 'ElementPlaceholder', 'ElementVoid',
           'ElementMaster', 'ElementMasterDefer', 'STATE_UNLOADED',
           'STATE_SUMMARY', 'STATE_LOADED']

STATE_UNLOADED, STATE_SUMMARY, STATE_LOADED = range(3)

class Element:
    """Abstract base class for EBML elements.

    Attributes describing properties intrinsic to the element:
     + header: The element's Header object.
     + ebml_id: Convenience accessor for self.header.ebml_id.
     + size: Convenience accessor for self.header.size.
     + header_size: Convenience accessor for self.header.numbytes.
     + total_size: Equals self.header_size + self.size.
     + name: The (string) name of this EBML element, if known.
     + tag: The associated Tag instance.

    Attributes governing element resizing:
     + header_size_min: resize_total() will not shrink the number of bytes used
       to encode header.size beyond this amount.  Usually set in the Tag;
       default is 0.
     + data_size_min: resize() will not shrink this Element's data beyond this
       amount.  Usually set in the Tag; default is 0.  This need not be a valid
       data size.

    Attributes describing the element's position in the EBML tree:
     + parent: The Container instance containing this element, or None if it
       has not yet been added to a container.  Accessing pos_absolute and
       pos_data_absolute will throw an error if the parent is not set.
     + level: This is self.parent.level + 1 unless self.parent is not an
       Element, in which case it is 0.

    Attributes describing the element's position in a stream:
     + pos_relative: Relative position of the element (the first byte of its
       header) from the beginning of its parent's data.  Should only be set by
       the parent.
     + pos_data_relative: Equals self.pos_relative + self.header_size.
     + pos_end_relative: Equals self.pos_relative + self.total_size.
     + pos_absolute: Absolute position of the element (the first byte of its
       header) in the stream.  Equals self.pos_relative +
       self.parent.pos_data_absolute.
     + pos_data_absolute: Equals self.pos_absolute + self.header_size.
     + pos_end_absolute: Equals self.pos_absolute + self.total_size.

    Attributes describing the element's state:
     + read_state: One of the following values:
       - STATE_UNLOADED: The element has been initialized but no data has been
         read.
       - STATE_SUMMARY: The element's read_summary() method has been called, but
         read_data() has not.
       - STATE_LOADED: The element's read_data() method has been called, so the
         element is fully loaded.
     + dirty: True if the Element's position in the stream has changed, if it
       has been resized, if its data has been changed, or if it has been created
       programatically and not read from a stream.  This attribute can be set to
       False after writing to a stream.

    A generic element knows where its data is stored in the stream but does not
    know how to interpret it.  Subclasses should reimplement the read_data(),
    read_summary(), and write() methods, at least.
    """
    #pylint: disable=too-many-instance-attributes

    # Private attributes:
    #  + _orig_pos: The absolute position of the beginning of the element when
    #    read from a stream.  None if not read from a stream.
    #  + _orig_total_size: The original value of self.total_size when read from
    #    a stream.  None if not read from a stream.
    #  + _orig_header_size: The original value of self.header_size
    #  + _forced_dirty: If True, the dirty property always evaluates to True.

    # Constructors

    def __init__(self, header, name='Unknown'):
        self.header = header
        self.tag = MATROSKA_TAGS[header.ebml_id]
        self.parent = None
        self.pos_relative = 0
        self.name = name
        self.read_state = STATE_UNLOADED

        self.header_size_min = self.tag.header_size_min
        self.data_size_min = self.tag.data_size_min

        self._orig_pos = None
        self._orig_total_size = None
        self._orig_header_size = header.numbytes
        self._forced_dirty = False

    @classmethod
    def new(cls, name_or_id, parent=None, pos_relative=None, size=0):
        """Create an empty Element.

        This creates an element programatically, as opposed to an element meant
        to be read from a stream.  This class method is not meant to be called
        directly, but from programmatic constructors for non-virtual Element
        classes.

        Args:
         + name_or_id: If a string, it must be a tag name defined in
           MATROSKA_TAGS; the EBML ID will be set from that.  If an integer, use
           that as the EBML ID.
         + parent: The child's parent.  If not None, calls
           parent.add_child(child).
         + pos_relative: The child's pos_relative.
         + size: Initial size of the data part of the element.  This should be a
           valid size for whatever the default value of the element's data is.
        """
        tag = MATROSKA_TAGS[name_or_id]
        ebml_id = tag.ebml_id
        header = Header(ebml_id=ebml_id, size=size)
        header_size = min([max([header.numbytes_size_min, tag.header_size_min]),
                           header.numbytes_size_max])
        header.numbytes = header.numbytes_id + header_size
        ret = cls(header, name=tag.name)
        if parent is not None:
            parent.add_child(ret, pos_relative)
        elif pos_relative is not None:
            ret.pos_relative = pos_relative
        return ret

    # Properties

    @property
    def ebml_id(self):
        "Return this element's EBML ID."
        return self.header.ebml_id
    @property
    def size(self):
        "Return the size of this element's data."
        return self.header.size
    @property
    def header_size(self):
        "Return the size of the EBML header."
        return self.header.numbytes
    @property
    def total_size(self):
        "Return the total size of this element in the stream."
        return self.header_size + self.size
    @property
    def level(self):
        "Calculate the element level in the EBML tree."
        if isinstance(self.parent, Element):
            return self.parent.level + 1
        return 0
    @property
    def pos_data_relative(self):
        "Return the position of this element's data relative to its parent."
        return self.pos_relative + self.header_size
    @property
    def pos_end_relative(self):
        "Return the position of this element's end relative to its parent."
        return self.pos_relative + self.total_size
    @property
    def pos_absolute(self):
        "Return the absolute position of this element in the stream."
        return self.pos_relative + self.parent.pos_data_absolute
    @property
    def pos_data_absolute(self):
        "Return the absolute position of this element's data in the stream."
        return self.pos_absolute + self.header_size
    @property
    def pos_end_absolute(self):
        "Return the absolute position of this element's end in the stream."
        return self.pos_absolute + self.total_size
    @property
    def dirty(self):
        "Shortcut for self.is_dirty()."
        return self.is_dirty()
    @dirty.setter
    def dirty(self, val):
        "Shortcut for self.set_dirty()."
        self.set_dirty(val)

    def intrinsic_equal(self, other):
        """Test for intrinsic equality.

        Generic Element instances are intrinsically equal if their intrinsic
        data are equal.  This means their types are equal, their headers are
        equal (so they have the same ebml_id and size), and their names are
        equal.  They may have different parents and be located at different
        positions in the stream.

        To test if two Element instances represent the same chunk of binary data
        in a stream, test whether their 'pos_absolute' attributes are equal.

        We do not reimplement __eq__() and __ne__() because we'd like Element
        instances to be hashable, and for things like list (e.g. Container)
        testing we want to use 'is' and not intrinsic equality.
        """
        if self.__class__ != other.__class__:
            return False
        if (self.header, self.name) != (other.header, other.name):
            return False
        return True

    def __bool__(self):
        #pylint: disable=no-self-use
        return True

    def __repr__(self):
        return '<{0} [{1}] {s.name!r} size={s.header_size}+{s.size} ' \
            '@{s.pos_relative}>' \
                .format(self.__class__.__name__,
                        hex_bytes(self.header.encoded_id), s=self)

    def __str__(self):
        if self.name == 'Unknown':
            name = "[{}]".format(hex_bytes(self.header.encoded_id))
        else:
            name = self.name
        return "{0} {1} ({s.header_size}+{s.size} @{s.pos_relative})" \
                .format(self.__class__.__name__, name, s=self)

    def summary(self, indent=0):
        "Return a pretty string summarizing this element."
        return (" " * indent) + str(self)

    def summ(self):
        "Short for print(self.summary())."
        print(self.summary())

    # Reimplement maybe

    def check_consistency(self):
        """Check if the element's value is allowed.

        This method raises Inconsistent if its value is not consistent with the
        Matroska specification as stored in self.tag.  For example, the value
        could be an integer outside the allowable range.  This functionality
        must be implemented in subclasses.

        This method also raises Inconsistent if self.parent is None.
        """
        if self.parent is None:
            raise Inconsistent("No parent element for {!r}".format(self))

    # Size calculating

    def min_data_size(self):
        """Return the minimum size to encode this element's data.

        Must return a valid size to encode the Element's current data.  Should
        return a value <= self.size.  Should not return a value less than
        self.data_size_min if possible subject to the above conditions.
        """
        raise NotImplementedError

    def max_data_size(self):
        "Return the maximum size to encode this element's data."
        raise NotImplementedError

    def valid_data_size_le(self, goal):
        """Return a valid data size.

        Args:
         + goal: Goal data size.
        Returns:
           The largest valid data size <= goal, or None if none such exists.
           The Element must be resizable to this value.  Must not be less than
           self.min_data_size().
        """
        raise NotImplementedError

    def valid_data_size(self, size):
        "Short for valid_data_size_le(size) == size."
        return self.valid_data_size_le(size) == size

    def min_header_size(self, data_size=None):
        """Return the minimum header size for a given data size.

        This takes into account self.header_size_min, but it will not return
        larger than self.header_size when data_size <= self.size.

        Args:
         + data_size: If specified, use this instead of self.size for the size
           attribute of the header.
        """
        if data_size is None:
            data_size = self.size
        tmp_header = self.header.copy()
        tmp_header.size = data_size
        # This allows the header to grow to a value < specified min header size,
        # but not to shrink to one.
        strict_min = max([tmp_header.numbytes_min,
                          tmp_header.numbytes_id + self.header_size_min])
        return min([tmp_header.numbytes, strict_min])

    def min_total_size(self):
        """Return the minimum total size to encode this element."""
        data_size = self.min_data_size()
        return self.min_header_size(data_size) + data_size

    def max_total_size(self):
        """Return the maximum total size to encode this element."""
        data_size = self.max_data_size()
        tmp_header = Header(ebml_id=self.ebml_id, size=data_size)
        return tmp_header.numbytes_max + data_size

    def valid_total_size_le(self, goal, solution=None):
        """Return a valid total size.

        Args:
         + goal: Goal total size.
         + solution: If not None, this must be a list.  If a valid total size is
           found, the header size and data size are appended to this list, in
           that order.
        Returns:
           The largest valid total size <= goal, or None if none such exists.

        When searching for solutions, this method resizes the data before
        resizing the header.  If the header must be resized, the algorithm opts
        for the smaller possible header size.
        """
        if solution is None:
            solution = []

        # Check the minimum size first
        min_data_size = self.min_data_size()
        min_header_size = self.min_header_size(min_data_size)
        min_total_size = min_header_size + min_data_size
        max_header_size = self.header.numbytes_max
        if min_total_size > goal:
            return None
        elif self.header_size + min_data_size >= goal:
            # Must shrink the header and the data
            solution.extend([goal - min_data_size, min_data_size])
            return goal

        # See if we can do it without changing the header size
        goal_data_size = goal - self.header_size # > min_data_size
        if goal_data_size <= MAX_DATA_SIZE:
            if self.min_header_size(goal_data_size) <= self.header_size:
                data_size = self.valid_data_size_le(goal_data_size)
                assert data_size is not None
                if data_size == goal_data_size:
                    solution.extend([self.header_size, data_size])
                    return goal

        # We have to resize the header.  At this point there's no preference for
        # resizing the header versus the data, so check potential header sizes
        # one by one, smallest first.
        candidate = []
        for size in range(min_header_size, max_header_size+1):
            goal_data_size = goal - size
            if goal_data_size > MAX_DATA_SIZE:
                continue
            if self.min_header_size(goal_data_size) > size:
                continue
            data_size = self.valid_data_size_le(goal_data_size)
            if data_size == goal_data_size:
                solution.extend([size, data_size])
                return goal
            elif not candidate or sum(candidate) < size + data_size:
                candidate = [size, data_size]
        if candidate:
            solution.extend(candidate)
            return sum(candidate)
        return None

    def valid_total_size_le_1(self, goal, solution=None):
        "Like valid_total_size(), but treat goal-1 as invalid."
        solution2 = []
        size = self.valid_total_size_le(goal, solution2)
        if size == goal - 1:
            return self.valid_total_size_le(goal - 2, solution)
        if solution is not None:
            solution.extend(solution2)
        return size

    def valid_total_size(self, size):
        "Short for valid_total_size_le(size) == size."
        return self.valid_total_size_le(size) == size

    # Resizing

    def resize(self, new_size):
        """Set self.header.size to a new value.

        Be aware that calling this function can grow (but not shrink) the
        header.  The Element implementation of this method does not check that
        new_size is a valid size.

        Args:
         + new_size: The new size of the data part of the element.
        """
        self.header.size = new_size

    def resize_total(self, new_size):
        """Resize the Element to a new total size.

        This method calculates the new header and data size using
        self.valid_total_size_le().  This may resize the header and/or the data
        depending on the Element type.

        Args:
         + new_size: The new total size of the element.  Must be a valid total
           size as reported by self.valid_total_size().
        Raises:
           ValueError, if new_size was not a valid size.
        """
        solution = []
        size = self.valid_total_size_le(new_size, solution)
        if size != new_size:
            raise ValueError(
                "Tried to resize Element {!r} to invalid size {}" \
                .format(self, new_size))

        self.resize(solution[1])
        self.header.numbytes = solution[0]

    def is_dirty(self):
        """Return true if the element has been modified in some way.

        This means its position in the stream has changed, it has been resized,
        its data has changed, or it has been created programatically.  The
        base implementation only knows if the element has been moved or resized;
        subclasses should reimplement this to check if the data has been
        changed.
        """
        return (self.pos_absolute != self._orig_pos) or \
            (self.total_size != self._orig_total_size) or \
            (self.header_size != self._orig_header_size) or \
            self._forced_dirty

    def set_dirty(self, val):
        """Set the dirty state.

        If bool(val) is True, this sets self._forced_dirty to True.  If val is
        False, this sets self._forced_dirty to False and sets self._orig_pos,
        self._orig_total_size, and self._orig_header_size to the current
        absolute position, total size of the element, and header size,
        respectively.  Subclasses should reimplement this to reset the stored
        original value as well.

        Note that self.is_dirty() may return True even after calling
        self.set_dirty(False), for instance in a Master element if one of the
        children is dirty.
        """
        if val:
            self._forced_dirty = True
        else:
            self._orig_pos = self.pos_absolute
            self._orig_total_size = self.total_size
            self._orig_header_size = self.header_size
            self._forced_dirty = False

    # Read and write

    def read_data(self, stream, seekfirst=True):
        """Read this element's data from a binary stream.

        After this method is run, the stream's position must be immediately
        after the current element, i.e. its absolute position will be
        self.pos_absolute + self.total_size.  Sets self.read_state to
        STATE_LOADED.

        This is an abstract method that must be reimplemented.

        Args:
         + stream: A binary stream.
         + seekfirst: If True, first seek the stream to self.pos_data_absolute.
           Otherwise the stream position must already be equal to
           self.pos_data_absolute.
        """
        raise NotImplementedError

    def read_summary(self, stream, seekfirst=True):
        """Read some of the data of the element.

        This method behaves like read_data().  Subclasses may reimplement this
        to only partially load the element.  In that case, the subclass should
        set self.read_state to STATE_SUMMARY.  The default implementation is to
        dispatch to self.read_data().
        """
        self.read_data(stream, seekfirst)

    def write(self, stream, seekfirst=True):
        """Write this element to a binary stream.

        After this method is run, the stream's position is guaranteed to be
        immediately after the current element, i.e. its absolute position will
        be self.pos_absolute + self.total_size.

        This is an abstract method that must be reimplemented.

        Args:
         + stream: A binary stream.
         + seekfirst: If True, first seek the stream to self.pos_absolute.
           Otherwise the stream position must already be equal to
           self.pos_absolute.
        """
        raise NotImplementedError

    # The next two methods are mainly for debugging
    def read_raw(self, stream):
        """Return the raw byte stream corresponding to this element."""
        stream.seek(self.pos_absolute, SEEK_SET)
        return stream.read(self.total_size)

    def read_data_raw(self, stream):
        """Return the raw byte stream corresponding to this element's data."""
        stream.seek(self.pos_data_absolute, SEEK_SET)
        return stream.read(self.size)


class ElementUnsupported(Element):
    """Element we don't want to handle.

    This Element ignores its data and cannot be resized or written back to a
    stream.
    """

    @classmethod
    def new(cls, name_or_id, parent=None, pos_relative=None, size=0):
        return super(ElementUnsupported, cls).new(
            name_or_id, parent, pos_relative, size)

    @classmethod
    def of_size(cls, name_or_id, total_size, parent=None, pos_relative=None):
        """Like ElementVoid.of_size().

        Convenience method for creating placeholder Elements.
        """
        # This is a bit of a hack: we create a Void of the specified size with
        # our tag information, then use its total size calculations to resize
        # the new Unsupported element.
        void = ElementVoid.new(name_or_id)
        void.resize_total(total_size)
        elt = cls.new(name_or_id, parent, pos_relative, size=void.size)
        elt.header.numbytes = void.header_size
        return elt

    def resize(self, new_size):
        if new_size != self.size:
            raise ValueError("Tried to resize ElementUnsupported")
        super().resize(new_size)

    def min_data_size(self):
        return self.size
    def max_data_size(self):
        return self.size
    def valid_data_size_le(self, goal):
        if self.size <= goal:
            return self.size
        return None

    def read_data(self, stream, seekfirst=True):
        "Ignore the element's data."
        if seekfirst:
            stream.seek(self.pos_data_absolute, SEEK_SET)
        stream.seek(self.size, SEEK_CUR)
        self.read_state = STATE_LOADED

    def write(self, stream, seekfirst=True):
        raise EbmlException("Cannot write unsupported element to a stream.")


class ElementPlaceholder(ElementUnsupported):
    """Element that represents unread data.

    This mostly behaves like an Unsupported element, but it becomes Inconsistent
    when moved, and write() seeks the stream without even writing the Header.
    """
    @classmethod
    def of_size(cls, name_or_id, total_size, parent, pos_relative):
        #pylint: disable=signature-differs
        ret = super(ElementPlaceholder, cls).of_size(name_or_id, total_size,
                                                     parent, pos_relative)
        ret.read_state = STATE_LOADED
        ret.dirty = False
        return ret

    def write(self, stream, seekfirst=True):
        if seekfirst:
            stream.seek(self.pos_absolute, SEEK_SET)
        stream.seek(self.total_size, SEEK_CUR)

    def check_consistency(self):
        if self.dirty:
            raise Inconsistent("Dirty ElementPlaceholder {!r}".format(self))
        super().check_consistency()

class ElementVoid(Element):
    """Void element.

    This class ignores its data and seeks past its data in a writable stream.
    This means that the data part of anything written by this element is
    undefined.
    """

    @classmethod
    def of_size(cls, total_size, parent=None, pos_relative=None, name='Void'):
        """Create a Void element with a specified size.

        Args:
         + parent, pos_relative, name: As in the Element constructor.
         + total_size: Total size (data plus header) of the Void element.  This
           must be an integer between 2 and 2^56+7, inclusive.
        Returns:
           An ElementVoid instance of total size = total_size.
        Raises:
         + EbmlException, if size < 2.
        """
        if total_size < 2:
            raise EbmlException("Can't create Void of size < 2")
        ret = cls.new(name, parent, pos_relative)
        ret.resize_total(total_size)
        return ret

    def min_data_size(self):
        return min([self.size, self.data_size_min])
    def valid_data_size_le(self, goal):
        ret = max([goal, self.min_data_size()])
        if ret > goal:
            return None
        return ret
    def max_data_size(self):
        return MAX_DATA_SIZE

    def read_data(self, stream, seekfirst=True):
        "Ignore the element's data."
        if seekfirst:
            stream.seek(self.pos_data_absolute, SEEK_SET)
        stream.seek(self.size, SEEK_CUR)
        self.read_state = STATE_LOADED

    def write(self, stream, seekfirst=True):
        "Seek past data and write at most one byte."
        if seekfirst:
            stream.seek(self.pos_absolute, SEEK_SET)
        stream.write(self.header.encode())
        if self.size > 0:
            stream.seek(self.size-1, SEEK_CUR)
            stream.write(b'\x00') # Extend the stream if necessary


class ElementMaster(Element, Container):
    """Generic Master element.

    An EBML Master element is an element type that contains other elements.
    """

    @classmethod
    def new(cls, name_or_id, parent=None, pos_relative=None, size=None):
        if size is None:
            size = MATROSKA_TAGS[name_or_id].data_size_min
        return super(ElementMaster, cls).new(
            name_or_id, parent, pos_relative, size)

    def __init__(self, header, name='Unknown'):
        Element.__init__(self, header, name)
        # It doesn't matter what Container sets its _pos_data_absolute
        # attribute to since self.pos_data_absolute uses the Element
        # property of that name.  We don't just pass self.pos_data_absolute in
        # case self.parent is None.
        Container.__init__(self, 0)

    def intrinsic_equal(self, other):
        return Element.intrinsic_equal(self, other) and \
            Container.intrinsic_equal(self, other)

    # Printing

    def print_space(self, level_up=1, level_down=0, start_pos=0):
        ret = super().print_space(level_up, level_down, start_pos)
        ind_str = "{}> ".format(level_down+1)

        last_end = self.end_last_child
        if last_end < self.size:
            ret += ind_str + self._space_line(start_pos, last_end, self.size)
            ret += "***UNUSED***\n"
        elif last_end > self.size:
            ret += ind_str + self._space_line(start_pos, self.size, last_end)
            ret += "***OVERFLOW***\n"
        return ret

    def __str__(self):
        return super().__str__() + ": {} child{}" \
                      .format(len(self), "ren" if len(self) > 1 else "")

    # Data size

    def _min_data_size(self):
        "Sum the min_total_size()s of children."
        ret = 0
        for child in self:
            if child.name != 'Void':
                ret += child.min_total_size()
        return ret

    def min_data_size(self):
        ret = self._min_data_size()
        if ret == self.data_size_min - 1: # one-byte Voids...
            ret += 2
        return max([ret, self.data_size_min])

    def max_data_size(self):
        # Can always add Voids
        return MAX_DATA_SIZE

    def valid_data_size_le(self, goal):
        # The reason for this convoluted algorithm is to avoid the following
        # situation: say self._min_data_size() == 8, self.data_size_min == 9,
        # and goal == 11.  We should return 11, not 12, which is what we would
        # get if we simply set min_size = self.min_data_size() (== 10) and
        # checked for one-byte Voids.
        min_size = real_min_size = self._min_data_size()
        if real_min_size == self.data_size_min - 1:
            min_size = real_min_size + 2
        min_size = max([min_size, self.data_size_min])
        if min_size > goal:
            return None
        if min_size == goal or min_size <= goal - 2:
            return goal
        # min_size == goal - 1
        if real_min_size < min_size:
            return goal
        return min_size # == goal - 1

    # Dirty

    def is_dirty(self):
        "Returns True if self or any child is dirty."
        if super().is_dirty():
            return True
        for child in self:
            if child.is_dirty():
                return True
        return False

    def set_dirty(self, val):
        """Set the dirty state.

        Like Element.set_dirty(), but if val == 'recurse', also set all children
        to dirty.
        """
        super().set_dirty(val)
        if val == 'recurse':
            self.force_dirty()

    # Rearranging

    def rearrange_resize(self, prefer_grow=True, allow_shrink=True):
        """Rearrange and resize the element.

        Call self.rearrange() then self.resize() to include all rearranged child
        elements.

        Args:
         + prefer_grow: If True, pass goal_size=None to rearrange(); otherwise
           pass goal_size=self.size.
         + allow_shrink: If False, when all elements fit in self.size bytes, do
           not shrink the element's data; instead add a Void between the last
           child and the end of the data.
        """
        goal_size = None if prefer_grow else self.size
        self.rearrange(goal_size)
        if self.end_last_child == self.size:
            return
        elif self.end_last_child > self.size or allow_shrink:
            self.resize(self.end_last_child)
        else: # self.end_last_child < self.size and not allow_shrink
            if self.end_last_child == self.size-1:
                self.resize(self.size+1)
            ElementVoid.of_size(self.size - self.end_last_child, self,
                                self.end_last_child)

    def rearrange_if_necessary(self, prefer_grow=True, allow_shrink=True):
        """Run rearrange_resize() if the Element is inconsecutive."""
        try:
            self.check_consecutivity()
        except Inconsistent:
            self.rearrange_resize(prefer_grow, allow_shrink)

    def make_consecutive(self):
        "Like Container.make_consecutive, but also resize() self."
        super().make_consecutive()
        self.resize(self.end_last_child)

    def expand_header(self, to_size):
        """Expand header data size to to_size bytes.

        If header.numbytes_id + to_size is greater than header.numbytes, resize
        the header and move all children back by the difference so that their
        absolute position does not change.  Also resize self by the difference.
        """
        header = self.header
        if header.numbytes_id + to_size <= header.numbytes:
            return
        diff = header.numbytes_id + to_size - header.numbytes
        header.numbytes = header.numbytes + diff
        for child in self:
            child.pos_relative -= diff
        self.re_sort()
        self.resize(self.size - diff)

    def check_consecutivity(self, child_consistency=False):
        """Like check_consistency() but skip allowedness checks."""
        Container.check_consecutivity(self, child_consistency)
        # Check end of last element
        if len(self) > 0:
            last_end = self.end_last_child
            difference = self.size - last_end
            if difference < 0:
                raise Inconsistent("Last child {!r} ends after parent {!r} ends"
                                   .format(self[-1], self))
            elif difference > 0:
                raise Inconsistent(
                    "Last child {!r} ends before parent {!r} ends"
                    .format(self[-1], self))
        else:
            if self.size > 0:
                raise Inconsistent("Empty Master Element {!r} of nonzero size"
                                   .format(self))

    def check_consistency(self):
        """Check if the Element in a consistent state

        Like Container.check_consistency(), but also check that the last child
        ends at relative position self.size and that parent is not None.  Also
        checks required and unique children.
        """
        Element.check_consistency(self)
        self.check_consecutivity(True)

        # Check allowed children
        for child in self:
            if not child.tag.is_child(self.tag):
                raise Inconsistent("Impermissible child {!r} of {!r}"
                                   .format(child, self))
        # Check required children
        for tag in self.tag.required_children:
            num_children = len(list(self.children_with_id(tag.ebml_id)))
            if not num_children:
                raise Inconsistent("Mandatory child {} missing"
                                   .format(tag.name))
        # Check unique children
        for tag in self.tag.unique_children:
            num_children = len(list(self.children_with_id(tag.ebml_id)))
            if num_children > 1:
                raise Inconsistent("Multiple instances of unique child {}"
                                   .format(tag.name))

    def read_data(self, stream, seekfirst=True):
        """Read all child elements.

        For a large file it can take a very long time to read all child
        elements.
        """
        Container.read(self, stream, 0, self.size, seekfirst=seekfirst)
        self.read_state = STATE_LOADED

    def write(self, stream, seekfirst=True):
        """Write header and child elements.

        This checks first whether the Element is in a consistent state.

        Args:
         + stream: As in Element.write().
         + seekfirst: As in Element.write().
        Raises:
         + EbmlException, if the write fails.
         + Inconsistent, if the Element is not in a consistent state.
        """
        self.check_consistency()
        if seekfirst:
            stream.seek(self.pos_absolute, SEEK_SET)
        stream.write(self.header.encode())
        Container._write(self, stream, False)


class ElementMasterDefer(ElementMaster):
    """Master element with deferred reading.

    This is exactly the same as an Master element, except that it has a
    read_summary() method that skips over its children.  Also consecutivity and
    consistency requirements are relaxed: as long as the Element is not dirty,
    its children need not be in memory.
    """
    def read_summary(self, stream, seekfirst=True):
        "Skip over child elements."
        if seekfirst:
            stream.seek(self.pos_data_absolute, SEEK_SET)
        stream.seek(self.size, SEEK_CUR)
        self.read_state = STATE_SUMMARY

    def check_consecutivity(self, child_consistency=False):
        "Summary mode elements are consecutive if they're not dirty."
        if self.read_state != STATE_SUMMARY or self.dirty:
            super().check_consecutivity(child_consistency)
        else:
            Container.check_consecutivity(self, child_consistency)

    def check_consistency(self):
        "Summary mode elements are consistent if they're not dirty."
        if self.read_state != STATE_SUMMARY or self.dirty:
            super().check_consistency()
        else:
            Element.check_consistency(self)
            self.check_consecutivity(True)

    def write(self, stream, seekfirst=True):
        if self.read_state == STATE_SUMMARY:
            self.read_state = STATE_LOADED # force strong consistency checks
        super().write(stream, seekfirst)
