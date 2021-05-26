#pylint: disable=too-many-public-methods
"""
EBML Container types: Container and File.
"""

from operator import attrgetter
from io import IOBase
from os import SEEK_SET, SEEK_CUR, SEEK_END
from datetime import datetime

from . import Inconsistent, DecodeError
from .header import Header
from .tags import MATROSKA_TAGS
from .sortedlist import SortedList

__all__ = ['Container', 'File']

import logging
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

class Container(SortedList):
    """A SortedList of Element instances.

    Subclassed by File and ElementMaster.  Reads its children from a
    seekable binary stream, and writes its children back out.

    Also responsible for adding, deleting, and rearranging its children.  Note
    that these editing methods make no consistency checks.  Call
    make_consistent() to put everything in order before trying to write.

    Attributes:
     + pos_data_absolute: The position in the EBML stream where the first child
       starts.  This is actually a property since ElementMaster reimplements
       it as a property.
     + beg_first_child: The relative position of the beginning of the first
       child element, or zero if no children.
     + end_last_child: The relative position of the end of the last child
       element, or zero if no children.
    """

    def __init__(self, pos_data_absolute):
        super().__init__(key=attrgetter('pos_relative'))
        self._pos_data_absolute = pos_data_absolute

    @property
    def pos_data_absolute(self):
        "Return pos_data_absolute property."
        return self._pos_data_absolute
    @pos_data_absolute.setter
    def pos_data_absolute(self, val):
        "Set pos_data_absolute property."
        self._pos_data_absolute = val
    @property
    def beg_first_child(self):
        "Return the relative position of the beginning of the first child."
        return self[0].pos_relative if len(self) else 0
    @property
    def end_last_child(self):
        "Return the relative position of the end of the last child."
        if len(self):
            # There may be several children starting at the same position.
            i = self.index_ge(self[-1].pos_relative)
            return max([child.pos_end_relative for child in self[i:]])
        else:
            return 0

    def intrinsic_equal(self, other):
        "Check if all child elements are intrinsic_equal()."
        if len(self) != len(other):
            return False
        for i in range(len(self)):
            if not self[i].intrinsic_equal(other[i]):
                return False
        return True

    # Reimplement default equality testing (overwriting SortedList) so instances
    # are hashable.
    def __hash__(self):
        return id(self)
    def __eq__(self, other):
        return self is other
    def __ne__(self, other):
        return self is not other

    def children_named(self, name):
        "Return an iterator over all children with a given name."
        return (child for child in self if child.name == name)

    def child_named(self, name):
        "Return the first child with the given name, or None."
        try:
            return next(self.children_named(name))
        except StopIteration:
            return None

    def children_with_id(self, ebml_id):
        "Return an iterator over all children with a given ebml_id."
        return (child for child in self if child.ebml_id == ebml_id)

    def children_in_region(self, start, size=None, *, novoids=False):
        """Return a SortedList of children between start and start + size.

        More precisely, return all children whose pos_relative attribute is >=
        start and < start + size.  If size is None, return all children after
        start.

        If novoids is True, ignore Void children.
        """
        try:
            i = self.index_ge(start)
        except ValueError: # No children after start
            return SortedList(key=attrgetter('pos_relative'))
        if size is not None:
            try:
                j = self.index_ge(start + size)
            except ValueError:
                j = len(self)
        else:
            j = len(self)
        children = SortedList(self[i:j], attrgetter('pos_relative'))
        if novoids:
            for i in reversed(range(len(children))):
                if children[i].name == 'Void':
                    del children[i]
        return children

    # Printing

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, self.pos_data_absolute)

    def __str__(self):
        return "{}: {} child{}".format(self.__class__.__name__, len(self),
                                       "ren" if len(self) != 1 else "")

    def print_children(self, level=1, indent=0):
        """List child elements.

        Args:
         + level: List descendents up to this relative level (1=direct children
           only, None=all).
        """
        ret = (" " * indent) + str(self) + "\n"
        if level is None or level > 0:
            next_level = None if level is None else level - 1
            for child in self:
                if isinstance(child, Container):
                    ret += child.print_children(next_level, indent+4)
                else:
                    ret += (" " * (indent+4)) + str(child) + "\n"
        return ret

    @classmethod
    def _space_line(cls, start_pos, start_rel, end_rel):
        "Format the sizes line for print_space()."
        return "{:<11d}--{:<11d} | {:<11d}--{:<11d} | {:11d} bytes: " \
            .format(start_pos + start_rel, start_pos + end_rel,
                    start_rel, end_rel, end_rel - start_rel)

    def print_space(self, level_up=1, level_down=0, start_pos=0):
        """List descendents and how much space they take.

        Args:
         + level_up: List descendents up to this relative level (1=direct
           children only, None=all).
         + level_down: Current level of recursion.
         + start_pos: Use this value instead of self.pos_absolute for showing
           absolute positions.
        """
        ret = ""
        ind_str = "{}> ".format(level_down+1)
        cur_pos = 0
        for i in range(len(self)):
            child = self[i]
            start = child.pos_relative
            size = child.total_size
            end = start + size

            if start > cur_pos:
                ret += ind_str + self._space_line(start_pos, cur_pos, start)
                ret += "***NO CHILD***\n"
            elif start < cur_pos:
                ret += ind_str + self._space_line(start_pos, start, cur_pos)
                ret += "***OVERLAP***\n"

            ret += ind_str + self._space_line(start_pos, start, start + size)
            ret += "[{:2d}] {}\n".format(i, child.name)
            cur_pos = end

            if (level_up is None or level_up > 1) \
               and isinstance(child, Container):
                next_level = None if level_up is None else level_up - 1
                ret += "\n"
                ret += child.print_space(next_level, level_down+1,
                                         start_pos + start)
                if i != len(self):
                    ret += "\n"

        return ret

    # Managing blank space

    def find_gap(self, size, start=0, region_size=None, shrink=False,
                 one_byte_ok=False):
        """Find a blank space of a specified size.

        Search for gaps in self of at least 'size' bytes between 'start' and
        'start+region_size'.  Return the smallest such.  If 'shrink' is True,
        try shrinking children as well.

        This method ignores Voids.  It has undefined results if the non-Void
        elements overlap.

        Args:
         + size: Search for a gap of this size.
         + start: Search after this relative position.
         + region_size: Search for gaps that fit between start and start +
           region_size.  If region_size is None, treat it as the end of the last
           child.
         + shrink: Use the minimum size of elements when searching.  This does
           not actually resize any elements.
         + one_byte_ok: If True, find gaps of size+1 bytes; otherwise ignore
           them.
        Returns:
           A triple (start, gap_size, prev) where start is the start position of
           the gap, gap_size >= size is its size, and prev is the previous
           element, if any.  The space after the last child is considered a gap
           only if region_size is specified.  If no gap was found, return None.
        """
        #pylint: disable=too-many-branches,too-many-locals,too-many-arguments
        def test_gap_size(gap_size):
            "Check if gap size is OK given one_byte_ok."
            return size <= gap_size - 2 or size == gap_size or \
                (size == gap_size - 1 and one_byte_ok)
        region_end = None if region_size is None else start + region_size
        children = self.children_in_region(
            self.beg_first_child, region_end, novoids=True)
        while len(children) and children[0].pos_end_relative <= start:
            del children[0]
        if not len(children):
            if region_size is None:
                #return (start, MAX_DATA_SIZE - start, None)
                return None
            elif test_gap_size(region_size):
                return (start, region_size, None)
            return None
        gaps = []
        # Gap at the beginning
        if children[0].pos_relative > start and \
           test_gap_size(children[0].pos_relative - start):
            gaps.append((start, children[0].pos_relative - start, None))
        # Gaps in the middle
        def calc_prev_end(prev_child):
            "Calculate the effective end of prev_child."
            if shrink:
                return prev_child.pos_relative + prev_child.min_total_size()
            return prev_child.pos_end_relative
        prev_child = children[0]
        for child in children[1:]:
            prev_end = calc_prev_end(prev_child)
            gap_size = child.pos_relative - prev_end
            if test_gap_size(gap_size):
                gaps.append((prev_end, gap_size, prev_child))
            prev_child = child
        # Gap at the end
        prev_end = calc_prev_end(prev_child)
        if region_size is None:
            #gaps.append((prev_end, MAX_DATA_SIZE - prev_end, prev_child))
            pass
        elif test_gap_size(start + region_size - prev_end):
            gaps.append((prev_end, start + region_size - prev_end, prev_child))
        if not gaps:
            return None
        smallest = gaps[0]
        for gap in gaps:
            if gap[1] < smallest[1]:
                smallest = gap
        return smallest

    # Arranging children

    def add_child(self, child, pos=None):
        """Add a child to self at pos.

        This sets child.parent and child.pos_relative.  If pos is None, add
        after all current children.
        """
        child.parent = self
        if pos is not None:
            child.pos_relative = pos
        else:
            child.pos_relative = self.end_last_child
        self.insert(child)

    def place_child(self, child, start=0, region_size=None, *,
                    shrink_child=True, shrink_previous=True, grow_child=True):
        """Place an Element in a blank space and add as a child.

        This method searches for a blank space large enough for 'child'.  If it
        finds one, it places it there.  If not, it tries again after shrinking
        'child'; if it still has no success, it tries shrinking elements located
        before blank spaces too.  If there is a large enough space, it chooses
        the smallest such.  If not, it places 'child' after the last element
        without shrinking anything (subject to the region_size argument).

        This algorithm ignores Void elements entirely.  It has undefined results
        if there are any overlaps among the (non-Void) children.  The current
        total_size of 'child' is used; if 'child' is an ElementMaster in an
        inconsistent state, this may not be what you want.

        Args:
         + child: The Element to place.
         + start: Place after this relative position.
         + region_size: If specified, the end of child will not extend beyond
           start + region_size.
         + shrink_child: If True, allow shrinking child.
         + shrink_previous: If True, allow shrinking the element before.
         + grow_child: If True, allow growing child by one byte in case child
           occupies n bytes and there is a blank space of n+1 bytes available.
           Otherwise the algorithm will not place child in such a space, as
           there would be no room for a one-byte Void element between it and the
           next child.
        Raises:
           Inconsistent, if region_size is specified and the child does not fit.
        """
        #pylint: disable=too-many-branches,too-many-locals
        from . import element
        one_byte_ok = grow_child and \
                      child.valid_total_size(child.total_size + 1)
        def resize_and_rearrange(elt, size):
            "Run resize_total() and rearrange_if_necessary()."
            elt.resize_total(size)
            if isinstance(elt, element.ElementMaster):
                elt.rearrange_if_necessary(
                    prefer_grow=False, allow_shrink=False)

        gap = self.find_gap(child.total_size, start=start,
                            region_size=region_size, shrink=False,
                            one_byte_ok=one_byte_ok)
        if gap is not None:
            self.add_child(child, gap[0])
            if gap[1] == child.total_size + 1:
                resize_and_rearrange(child, gap[1])
            return
        # If we get here then child cannot fit without shrinking it or
        # appending it.
        min_size = child.min_total_size()
        if min_size >= child.total_size:
            shrink_child = False # for the next part of the algorithm
        if shrink_child:
            # Note min_size + 1 <= child.total_size.  one_byte_ok_min will
            # essentially always be true since the header can be stretched.
            one_byte_ok_min = child.valid_total_size(min_size + 1)
            gap = self.find_gap(min_size, start=start,
                                region_size=region_size, shrink=False,
                                one_byte_ok=one_byte_ok_min)
            if gap is not None:
                self.add_child(child, gap[0])
                if gap[1] == min_size + 1:
                    resize_and_rearrange(child, gap[1])
                else:
                    resize_and_rearrange(child, min_size)
                return
        # If we get here then child cannot fit without appending even after
        # shrinking it.
        if shrink_previous:
            if shrink_child:
                goal_size = min_size
                one_byte_ok = one_byte_ok_min
            else:
                goal_size = child.total_size
            gap = self.find_gap(goal_size, start=start,
                                region_size=region_size, shrink=True,
                                one_byte_ok=one_byte_ok)
            if gap is not None:
                gap_start, gap_size, prev_child = gap[0], gap[1], gap[2]
                gap_end = gap_start + gap_size
                prev_new_size = prev_child.valid_total_size_le(
                    gap_end - prev_child.pos_relative - goal_size)
                if gap_end - prev_child.pos_relative - prev_new_size \
                   == goal_size - 1:
                    # Very rarely happens since prev_child can shrink data and
                    # grow header by one byte.
                    if one_byte_ok:
                        goal_size += 1
                    else:
                        prev_new_size = prev_child.valid_total_size_le(
                            gap_end - prev_child.pos_relative - goal_size - 2)
                resize_and_rearrange(prev_child, prev_new_size)
                self.add_child(child, prev_child.pos_end_relative)
                if goal_size != child.total_size:
                    resize_and_rearrange(child, goal_size)
                return
        # If we get here then we're forced to append child at the end.
        if region_size is not None:
            # We already know it won't fit
            raise Inconsistent("Cannot fit child {!r}".format(child))
        # Put it after the last non-Void
        prev_end = 0
        for prev_child in reversed(self):
            if prev_child.name != 'Void':
                prev_end = prev_child.pos_end_relative
                break
        self.add_child(child, prev_end)

    def remove_child(self, child):
        """Remove a child.

        This sets child.parent to None.

        Args:
         + child: Either an index or an Element with self as its parent.
        """
        if isinstance(child, int):
            child = self[child]
        self.remove(child)
        child.parent = None

    def remove_children_named(self, name):
        "Remove children named 'name'."
        for child in list(self.children_named(name)):
            self.remove_child(child)

    def move_child(self, child, new_pos):
        """Move a child to a new relative position.

        This makes no attempt to check whether the child would overlap with
        another element in its new position.

        Args:
         + child: Either an index or an Element with self as its parent.
         + new_pos: The new relative position.
        """
        from . import element
        if isinstance(child, element.Element):
            self.remove(child)
        else:
            index = child
            child = self[index]
            del self[index]
        child.pos_relative = new_pos
        self.insert(child)

    def check_consecutivity(self, child_consistency=False):
        """Like check_consistency(), but maybe skip allowedness checks.

        If child_consistency is False, run check_consecutivity() instead of
        check_consistency() on Master children.
        """
        from . import element
        if len(self) == 0:
            return

        prev_child = None
        for child in self:
            if prev_child:
                difference = child.pos_relative - prev_child.pos_end_relative
                if difference < 0:
                    raise Inconsistent("Overlapping children {!r} and {!r}"
                                       .format(prev_child, child))
                elif difference > 0:
                    raise Inconsistent(
                        "Empty space between children {!r} and {!r}"
                        .format(prev_child, child))
            else:
                if child.pos_relative != 0:
                    raise Inconsistent(
                        "Blank space at beginning before child {!r}"
                        .format(child))
            prev_child = child

            if isinstance(child, element.ElementMaster) and \
               not child_consistency:
                child.check_consecutivity()
            else:
                child.check_consistency()

    def check_consistency(self):
        """Check whether this container is in a consistent state.

        The state is consistent provided that:

         1. The first element starts at relative position zero.
         2. Element i+1 starts immediately after element i ends.
         3. Only allowed children are present.
         4. Required children are present.
         5. Unique children are unique.
         6. Every child container is consistent.
         7. The values of non-Container children are valid.

        Raises:
         + Inconsistent, if the state is not consistent.
        """
        self.check_consecutivity(True)
        # The File subclass checks allowedness, uniqueness, and existence of
        # level-zero elements.  The Master subclass checks this for its
        # children.

    # Support routine for rearrange()
    def _fill_gaps(self):
        """Replace gaps with Voids.

        First delete all Voids, then fill all gaps with Voids.  This ignores
        overlaps.  It will raise EbmlException if there are any gaps of size 1.
        """
        from . import element
        children = list(self)
        cur_pos = 0
        for child in children:
            if child.name == 'Void':
                self.remove_child(child)
                continue
            if child.pos_relative > cur_pos:
                element.ElementVoid.of_size(
                    child.pos_relative - cur_pos, self, cur_pos)
            cur_pos = child.pos_end_relative

    def rearrange(self, goal_size=None):
        """Move and resize children to eliminate overlaps and gaps.

        This method moves and resizes its children in order to eliminate
        overlaps and to try to fit all children into 'goal_size' bytes.  It
        tries to do as little resizing and moving as possible, preferring
        resizing to moving.  The algorithm goes as follows:

         1. First it steps forward through the child list, shrinking children
            and moving them forward when necessary to eliminate overlaps.
         2. Then it steps backward through the list, shrinking children again
            and moving them back to fit into the requested size.
         3. Finally it calls rearrange() on each child Master element.

        Void elements are treated as empty space; they are created and deleted
        as necessary.  Any gaps are eventually filled with Voids.  Any space
        after the last element is not considered a gap.  The end result may not
        fit into 'goal_size' bytes, but it will come as close as possible.

        Args:
         + goal_size: Attempt to fit children into goal_size bytes.  If
           possible, the last child will not end at goal_size - 1.  If None, do
           not run step 2 of the algorithm.
        """
        #pylint: disable=too-many-branches,too-many-statements,too-many-locals
        from . import element
        children = self.children_in_region(self.beg_first_child, novoids=True)
        if len(children) == 0:
            self._fill_gaps()
            return # Nothing to rearrange
        # Precalculate minimum sizes
        min_sizes_dict = {child : child.min_total_size() for child in children}
        min_sizes = [min_sizes_dict[child] for child in children]

        # Eliminate internal overlaps in children so that we know their actual
        # starting sizes and end positions.
        for child in children:
            if isinstance(child, element.ElementMaster):
                child.rearrange_if_necessary(prefer_grow=True,
                                             allow_shrink=True)

        # Step 1: eliminate overlaps
        prev_child = None
        cur_pos = 0
        for child in list(children):
            child_start = child.pos_relative
            if child_start < cur_pos and prev_child is None:
                # First element started at a negative pos
                child.pos_relative = 0
            elif child_start < cur_pos:
                prev_child_start = prev_child.pos_relative
                # Shrink previous child or move this one forward
                available = max([0, child_start - prev_child_start])
                shrunk_size \
                    = prev_child.valid_total_size_le(available)
                if shrunk_size is None:
                    # Just move past prev_child.  Moving a little is as
                    # expensive as moving a lot, so no reason to shrink
                    # prev_child too.
                    child.pos_relative = cur_pos
                elif prev_child_start + shrunk_size == child_start or \
                     prev_child_start + shrunk_size <= child_start - 2:
                    prev_child.resize_total(shrunk_size)
                else: # prev_child_start + shrunk_size == child_start - 1
                    # Very unlikely
                    shrunk_size = prev_child.valid_total_size_le(available - 2)
                    if shrunk_size is None:
                        child.pos_relative = cur_pos
                    else:
                        prev_child.resize_total(shrunk_size)
            elif child_start == cur_pos + 1:
                # Can't fill the gap with a Void of size 1.  As usual do not
                # bother trying to grow prev_child by one byte.
                child.pos_relative = cur_pos
            cur_pos = child.pos_end_relative
            prev_child = child
        children.re_sort()
        min_sizes = [min_sizes_dict[child] for child in children]

        # Step 2: fit goal size
        if goal_size is not None:
            # First decide how many children to shrink and move.
            start_index = 0
            for i in reversed(range(len(children))):
                pos_end = children[i].pos_relative + sum(min_sizes[i:])
                if pos_end <= goal_size and pos_end != goal_size - 1:
                    start_index = i
                    break
            # Do we need to move children[0]?
            pos_end = children[0].pos_relative + sum(min_sizes)
            if start_index == 0 and \
               (pos_end > goal_size or pos_end == goal_size - 1):
                children[0].pos_relative = 0
            # Do we need to shrink the first child?  (Handles the case when
            # everything already fits.)
            pos_end = children[start_index].pos_end_relative \
                      + sum(min_sizes[start_index+1:])
            if pos_end > goal_size or pos_end == goal_size - 1:
                children[start_index].resize_total(min_sizes[start_index])
            cur_pos = children[start_index].pos_end_relative
            for i in range(start_index+1, len(children)):
                child = children[i]
                child.pos_relative = cur_pos
                child.resize_total(min_sizes[i])
                cur_pos = child.pos_end_relative
            children.re_sort()

        # Step 3: rearrange recursively
        for child in children:
            if isinstance(child, element.ElementMaster):
                # Rearrange with goal size equal to the Element's data size.  If
                # we shrunk an element, this is the Element's new size.
                child.rearrange_if_necessary(prefer_grow=False,
                                             allow_shrink=False)

        self.re_sort()
        self._fill_gaps()

    def make_consecutive(self):
        """Rearrange children to make them consecutive.

        This shrinks all children to their smallest size.
       """
        self.rearrange(0)

    def get_overlapping(self, fixed=()):
        """Remove and return overlapping elements.

        More specifically, for each pair of elements that overlap, this method
        will remove one of them.  If the name of one of the two elements is
        contained in the argument 'fixed', remove the other one.  Otherwise
        remove the smaller of the two.  Elements separated by one byte count as
        overlapping.

        Returns:
           The set of elements that were removed.
        Raises:
         + Inconsistent, if neither of two overlapping elements could be
           removed.
        """
        deleted = set()
        # Make a set of pairs of overlapping elements
        pairs = set()
        for child in self:
            if child.pos_relative < 0:
                if child.name in fixed:
                    raise Inconsistent("Cannot delete fixed element {!r} "
                                       "at negative position".format(child))
                deleted.add(child)
                continue
            for overlap in \
                self.children_in_region(child.pos_relative, child.total_size+2):
                if child != overlap and \
                   overlap.pos_relative != child.pos_end_relative:
                    pairs.add(frozenset({child, overlap}))
        # Delete one from each pair
        for pair in pairs:
            if pair & deleted:
                continue
            elt1, elt2 = list(pair)
            if elt1.name in fixed and elt2.name in fixed:
                raise Inconsistent("Cannot delete either of two "
                                   "overlapping fixed elements {!r}, {!r}"
                                   .format(elt1, elt2))
            elif elt1.name in fixed:
                deleted.add(elt2)
            elif elt2.name in fixed:
                deleted.add(elt1)
            else:
                smaller = elt1 if elt1.total_size < elt2.total_size else elt2
                deleted.add(smaller)
        # From this point on we won't raise an exception
        for elt in deleted:
            self.remove_child(elt)
        return frozenset(deleted)

    # Read and write

    def read(self, stream, start, length, *, summary=False, seekfirst=True):
        """Read elements from a seekable binary stream.

        Args:
         + stream: A seekable binary stream.
         + start: The position in the stream to begin reading, relative to
           self.pos_data_absolute.
         + length: Stop after reading this many bytes.  Actually stop after
           reading the last child element starting before this many bytes have
           been read.
         + summary: Passed to self.read_element().
         + seekfirst: If True first seek to self.pos_data_absolute + start.
           Otherwise the stream must already be at that position.

        There should be a valid element beginning at relative position 'start'.
        The current position in the stream after this function returns is
        immediately after the last child's data.
        """
        if seekfirst:
            stream.seek(self.pos_data_absolute + start, SEEK_SET)
        cur_pos = start
        end = cur_pos + length
        while cur_pos < end:
            child = self.read_element(stream, cur_pos, summary=summary,
                                      seekfirst=False)
            cur_pos += child.total_size

    def force_dirty(self):
        "Recursively set all children to dirty."
        for child in self:
            child.dirty = 'recurse'

    def write(self, stream, seekfirst=True):
        """Write child elements.

        Check first if the Container is in a consistent state.  Advance the
        stream to the end of the last child element and do nothing if there are
        no child elements.

        Args:
         + stream: A writable binary stream.
         + seekfirst: If true seek to self.pos_data_absolute first.
        Raises:
         + EbmlException, if the write fails.
         + Inconsistent, if the Container is not in a consistent state.
        """
        self.check_consistency()
        self._write(stream, seekfirst)

    def _write(self, stream, seekfirst=True):
        "Like write(), but doesn't check consistency."
        if seekfirst:
            stream.seek(self.pos_data_absolute, SEEK_SET)
        for child in self:
            if child.dirty:
                child.write(stream, False)
                child.dirty = False
            else:
                stream.seek(child.total_size, SEEK_CUR)

    def read_element(self, stream, start, *, summary=False, seekfirst=True):
        """Read a single element from a seekable binary stream.

        Args:
         + stream: A seekable binary stream.
         + start: The position in the stream to begin reading, relative to
           self.pos_data_absolute.
         + summary: If True, call child.read_summary() instead of
           child.read_data().
         + seekfirst: If True first seek to self.pos_data_absolute + start.
           Otherwise the stream must already be at that position.
        Returns:
           The child element that was just read.

        If there is already a child at position 'start', just return that child,
        unless it is only partially loaded and 'summary' is False.  When
        creating a new child (i.e. when there is no child at position 'start'),
        call child.set_dirty(False).

        There should be a valid element beginning at relative position 'start'.
        The current position in the stream after this function returns is
        immediately after the child element's data.

        If the current instance has a method named "parse_ELT" and the current
        child element's name is "ELT", run that method with the child element
        and the stream as arguments.  If the child at that position has been
        partially loaded, the hook is not run.
        """
        if seekfirst:
            stream.seek(self.pos_data_absolute + start, SEEK_SET)
        try:
            child = self.find(start)
        except ValueError:
            pass
        else:
            # Do we need to read the child at all?
            from .element import STATE_LOADED, STATE_SUMMARY
            if child.read_state == STATE_LOADED \
               or (child.read_state == STATE_SUMMARY and summary):
                stream.seek(child.total_size, SEEK_CUR)
                return child
            # The element is partially loaded.
            Header(stream) # Skip over header
            if summary:
                child.read_summary(stream, seekfirst=False)
            else:
                child.read_data(stream, seekfirst=False)
            return child

        # New child
        header = Header(stream)
        tag = MATROSKA_TAGS[header.ebml_id]
        child = tag(header)
        self.add_child(child, start)
        if summary:
            child.read_summary(stream, seekfirst=False)
        else:
            child.read_data(stream, seekfirst=False)
        child.dirty = False

        try:
            getattr(self, 'parse_' + child.name)(child, stream)
        except AttributeError:
            pass

        return child

    @classmethod
    def peek_element(cls, stream):
        """Return the Tag for the EBML ID of the next element in stream.

        Does not advance the stream.  Returns None if at the end of the stream
        or no element was found.
        """
        try:
            header = Header(stream)
        except(DecodeError, EOFError):
            return None
        stream.seek(-header.numbytes, SEEK_CUR)
        return MATROSKA_TAGS[header.ebml_id]

    def reparse(self):
        """Call parse_ELT hooks for current children."""
        for child in self:
            try:
                getattr(self, 'parse_' + child.name)(child, None)
            except AttributeError:
                pass


class File(Container):
    """A container that can read EBML elements from a seekable binary stream.

    Attributes:
     + stream: The stream to read.
     + stream_size: The size of self.stream.
    """

    def __init__(self, f, summary=True):
        """Args:
         + f: Either a file name or a seekable binary stream.
         + summary: If True, call self.read_summary().
        """
        super().__init__(0)
        if isinstance(f, IOBase):
            self.stream = f
        else:
            self.stream = open(f, 'rb')
        self.stream.seek(0, SEEK_END)
        self.stream_size = self.stream.tell()
        self.stream.seek(0, SEEK_SET)

        if summary:
            self.read_summary()

    def __enter__(self):
        return self

    def __exit__(self, _var1, _var2, _var3):
        self.close()

    def __repr__(self):
        return "<{} stream={!r} size={}>" \
            .format(self.__class__.__name__, self.stream, self.stream_size)

    def __str__(self):
        return "{}: stream={!r}, size={}, {} child{}" \
            .format(self.__class__.__name__, self.stream,
                    self.stream_size, len(self),
                    "ren" if len(self) > 1 else "")

    def summary(self):
        "Return a pretty string with segment summary information."
        ret = str(self) + "\n"
        if len(self) == 0:
            return "No segments!\n"
        for segment in self.children_named('Segment'):
            ret += segment.summary() + "\n"
        return ret

    def close(self):
        "Close self.stream."
        if self.stream is not None:
            self.stream.close()
        self.stream = None

    def check_consistency(self):
        super().check_consistency()

        # Check allowedness
        for child in self:
            if not child.tag.is_child(None):
                raise Inconsistent("Impermissible level-0 child {!r}"
                                   .format(child))

        # Check existence and uniqueness
        for level0 in MATROSKA_TAGS.level0s():
            num_children = len(list(self.children_with_id(level0.ebml_id)))
            if level0.mandatory and not num_children:
                raise Inconsistent("Mandatory level-0 element {} missing"
                                   .format(level0.name))
            if not level0.multiple and num_children > 1: # (no such element)
                raise Inconsistent("Multiple instances of unique element {}"
                                   .format(level0.name))

        # Check we know how to write this file version
        ebml = next(self.children_named('EBML'))
        if not ebml.check_write_handled():
            raise Inconsistent("Can't write file with EBML header Element {!r}"
                               .format(ebml))

    def parse_EBML(self, ebml, _):
        "Check EBML versions."
        #pylint: disable=no-self-use,invalid-name
        if not ebml.check_read_handled():
            LOG.warning("Header element {} indicates reading the file "
                        "will probably fail".format(ebml))

    def read_summary(self):
        """Read a summary of the stream.

        This finds each level-zero element and calls read_summary() on it.
        """
        start_time = datetime.now()
        self.read(self.stream, 0, self.stream_size,
                  summary=True, seekfirst=True)
        read_time = datetime.now() - start_time
        #pylint: disable=maybe-no-member
        LOG.info("Read summary in {:.3f} seconds" \
                 .format(read_time.total_seconds()))

    def read_all(self):
        "Read all elements in non-summary mode."
        self.read(self.stream, 0, self.stream_size,
                  summary=False, seekfirst=True)

    def save_changes(self, stream):
        """Normalize all Segment children and write.

        This method will not change the relative position of any of its
        immediate children.  If there is more than one Segment and one of them
        grows to overlap another, this will raise Inconsistent.

        The parameter 'stream' must be open in read-write mode.
        """
        for seg in self.children_named('Segment'):
            # This will not shrink seg
            seg.normalize()
        # This will throw Inconsistent
        self.write(stream, seekfirst=True)
