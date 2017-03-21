#pylint: disable=too-many-locals,no-self-use
#pylint: disable=too-many-public-methods,too-many-statements
"""
General element tests.
"""

from io import BytesIO

from .test import EbmlTest, UNK_ID

__all__ = ['ElementTest']

class ElementTest(EbmlTest):
    "General element tests."

    def check_valid_total_size_le(self, elt, goal, header, data):
        #pylint: disable=too-many-arguments
        "Test case for valid_total_size_le()."
        solution = []
        size = elt.valid_total_size_le(goal, solution)
        self.assertEqual(size, solution[0] + solution[1])
        self.assertEqual(solution, [header, data])
        tmp_header = elt.header.copy()
        tmp_header.size = data
        self.assertTrue(tmp_header.numbytes_min <= header and
                        tmp_header.numbytes_max >= header)
        self.assertTrue(elt.valid_data_size(data))

    def reset_track_entry(self, ebmlf):
        "Re-read the track entry element only."
        elt = self.track_entry_elt(ebmlf)
        start = elt.pos_relative
        parent = elt.parent
        parent.remove_child(elt)
        return parent.read_element(ebmlf.stream, start)

    def test_1_resizing(self):
        "Test element minimum & maximum size, and resizing."
        from ebml import MAX_DATA_SIZE
        from ebml.element import ElementUnsupported, ElementVoid, ElementMaster
        from ebml.tags import Tag, MATROSKA_TAGS
        from ebml.atomic import ElementRaw, ElementUnsigned, ElementBoolean, \
            ElementFloat, ElementString, ElementDate, ElementID

        # ElementUnsupported: Rigid data size
        elt = ElementUnsupported.new(UNK_ID, size=1234)
        self.assertEqual(elt.size, 1234)
        self.assertEqual(elt.header_size, 6)
        self.assertEqual(elt.min_data_size(), 1234)
        self.assertEqual(elt.max_data_size(), 1234)
        self.assertEqual(elt.min_total_size(), 1234 + 4 + 2)
        self.assertEqual(elt.max_total_size(), 1234 + 4 + 8)
        self.assertEqual(elt.valid_data_size_le(1235), 1234)
        self.assertEqual(elt.valid_data_size_le(1233), None)
        self.assertRaises(ValueError, elt.resize, 1233)
        self.assertRaises(ValueError, elt.resize, 1235)
        self.assertEqual(elt.valid_total_size_le(1234 + 4 + 1), None)
        for i in range(2, 9):
            self.check_valid_total_size_le(elt, 1234 + 4 + i, 4 + i, 1234)
        self.assertEqual(elt.valid_total_size_le(1234 + 4 + 9),
                         1234 + 4 + 8)
        elt.resize_total(1234 + 4 + 8) # Grow header
        self.assertEqual(elt.total_size, 1234 + 4 + 8)
        self.assertEqual(elt.header_size, 12)
        self.assertEqual(elt.size, 1234)
        elt.resize_total(1234 + 4 + 2) # Shrink header
        self.assertEqual(elt.total_size, 1234 + 4 + 2)
        self.assertEqual(elt.header_size, 6)
        self.assertEqual(elt.size, 1234)
        self.assertRaises(ValueError, elt.resize_total, 1234 + 4 + 1)
        self.assertRaises(ValueError, elt.resize_total, 1234 + 4 + 9)

        # ElementVoid: Flexible data size
        elt = ElementVoid.of_size(2)
        self.assertEqual(elt.min_data_size(), 0)
        self.assertEqual(elt.max_data_size(), MAX_DATA_SIZE)
        self.assertEqual(elt.min_total_size(), 2)
        self.assertEqual(elt.max_total_size(), MAX_DATA_SIZE + 9)
        self.assertEqual(elt.valid_data_size_le(1000), 1000)
        elt.resize(MAX_DATA_SIZE)
        self.assertEqual(elt.size, MAX_DATA_SIZE)
        self.assertEqual(elt.header_size, 9)
        self.check_valid_total_size_le(elt, 10, 9, 1)
        for i in reversed(range(2, 10)):
            self.check_valid_total_size_le(elt, i, i, 0)
        self.assertEqual(elt.valid_total_size_le(1), None)
        # Shrink
        elt.resize(10)
        self.assertEqual(elt.size, 10)
        self.assertEqual(elt.header_size, 9)
        elt.resize_total(15) # Shrink data first
        self.assertEqual(elt.size, 6)
        self.assertEqual(elt.header_size, 9)
        elt.resize_total(5) # Then shrink header
        self.assertEqual(elt.size, 0)
        self.assertEqual(elt.header_size, 5)
        # Grow
        elt.resize_total(100)
        self.assertEqual(elt.size, 95) # Grow data
        self.assertEqual(elt.header_size, 5)
        # Min data size with data_size_min
        elt.resize(5)
        elt.data_size_min = 100
        self.assertEqual(elt.min_data_size(), 5)
        self.assertEqual(elt.valid_data_size_le(20), 20)
        self.assertEqual(elt.valid_data_size_le(4), None)
        elt.resize(200)
        self.assertEqual(elt.min_data_size(), 100)
        self.assertEqual(elt.valid_data_size_le(100), 100)
        self.assertEqual(elt.valid_data_size_le(99), None)

        # Check boundary cases in resize_total()
        elt = ElementVoid.of_size(2)
        for i in range(1, 9):
            size = (1<<(i*7)) - 2 + 1 + i
            elt.resize_total(size)
            self.assertEqual(elt.total_size, size)
            self.assertEqual(elt.header_size, 1+i)
            if i != 8:
                size += 1
                elt.resize_total(size)
                self.assertEqual(elt.total_size, size)
                self.assertEqual(elt.header_size, 2+i)

        # Container data size
        elt = self.track_entry_elt(self.read_file_data())
        # Already encoded in minimal size
        self.assertEqual(elt.min_data_size(), elt.size)
        self.assertEqual(elt.min_total_size(), elt.total_size)
        self.assertEqual(elt.max_data_size(), MAX_DATA_SIZE)
        self.assertEqual(elt.max_total_size(), MAX_DATA_SIZE + 9)
        self.assertEqual(elt.valid_data_size_le(elt.size), elt.size)
        self.assertEqual(elt.valid_data_size_le(elt.size-1), None)
        self.assertEqual(elt.valid_data_size_le(elt.size-1), None)
        self.assertEqual(elt.valid_data_size_le(elt.size+2), elt.size+2)
        # No room for a size-1 Void
        self.assertEqual(elt.valid_data_size_le(elt.size+1), elt.size)
        # Compactable child (orig data size == 1)
        elt[-1].resize(8)
        elt.resize(elt.end_last_child)
        self.assertEqual(elt.min_data_size(), elt.size-7)
        self.assertEqual(elt.min_total_size(), elt.total_size-7)
        # Replace element with Void
        elt6 = elt[6]
        pos = elt[6].pos_relative
        size = elt[6].total_size
        elt.remove_child(6)
        ElementVoid.of_size(size, elt, pos)
        elt.check_consistency()
        self.assertEqual(elt.min_data_size(), elt.size - size - 7)
        self.assertEqual(elt.min_total_size(), elt.total_size - size - 7)
        # More testing
        elt = elt6[0][0] # ContentCompression, one child
        # elt[0]: ContentCompAlgo, size (2+1)+1
        elt[0].resize(8)
        elt.resize(11)
        self.assertEqual(elt.valid_data_size_le(12), 12)
        self.assertEqual(elt.valid_data_size_le(10), 10)
        # No room for a size-1 Void
        self.assertEqual(elt.valid_data_size_le(5), 4)
        self.assertEqual(elt.valid_data_size_le(3), None)
        # With data_size_min
        elt.data_size_min = 5
        self.assertEqual(elt.min_data_size(), 6)
        self.assertEqual(elt.valid_data_size_le(5), None)
        self.assertEqual(elt.valid_data_size_le(6), 6)
        self.assertEqual(elt.valid_data_size_le(7), 7) # (!)
        self.assertEqual(elt.valid_data_size_le(8), 8)
        elt.data_size_min = 4
        self.assertEqual(elt.min_data_size(), 4)
        self.assertEqual(elt.valid_data_size_le(4), 4)
        self.assertEqual(elt.valid_data_size_le(5), 4)
        self.assertEqual(elt.valid_data_size_le(6), 6)
        elt.data_size_min = 3
        self.assertEqual(elt.min_data_size(), 4)
        self.assertEqual(elt.valid_data_size_le(4), 4)
        elt.data_size_min = 7
        self.assertEqual(elt.min_data_size(), 7)
        self.assertEqual(elt.valid_data_size_le(6), None)
        self.assertEqual(elt.valid_data_size_le(7), 7)
        self.assertEqual(elt.valid_data_size_le(8), 8)
        self.assertEqual(elt.valid_data_size_le(9), 9)

        # Atomics
        # Raw
        elt = ElementRaw.new_with_value(UNK_ID, b'abcd')
        self.assertEqual(elt.min_data_size(), 4)
        self.assertEqual(elt.max_data_size(), 4)
        self.assertEqual(elt.valid_data_size_le(4), 4)
        self.assertEqual(elt.valid_data_size_le(3), None)
        elt.data_size_min = 5
        self.assertEqual(elt.min_data_size(), 4)
        # Unsigned
        elt = ElementUnsigned.new_with_value(UNK_ID, 1000)
        self.assertEqual(elt.size, 4)
        self.assertEqual(elt.header_size, 5)
        self.assertEqual(elt.min_data_size(), 2)
        self.assertEqual(elt.max_data_size(), 8)
        self.assertEqual(elt.valid_data_size_le(1), None)
        self.assertEqual(elt.valid_data_size_le(3), 3)
        self.assertEqual(elt.valid_data_size_le(5), 5)
        self.assertEqual(elt.valid_data_size_le(9), 8)
        elt.resize_total(11) # Grow data
        self.assertEqual(elt.size, 6)
        self.assertEqual(elt.header_size, 5)
        elt.resize_total(15) # Grow header
        self.assertEqual(elt.size, 8)
        self.assertEqual(elt.header_size, 7)
        self.assertRaises(ValueError, elt.resize_total, 12 + 8 + 1)
        elt.resize_total(11) # Shrink data
        self.assertEqual(elt.size, 4)
        self.assertEqual(elt.header_size, 7)
        elt.resize_total(7) # Shrink header
        self.assertEqual(elt.size, 2)
        self.assertEqual(elt.header_size, 5)
        self.assertRaises(ValueError, elt.resize_total, 6)
        elt = ElementUnsigned.new_with_value(UNK_ID, 1000)
        elt.resize(2)
        elt.data_size_min = 4
        self.assertEqual(elt.min_data_size(), 2)
        self.assertEqual(elt.valid_data_size_le(4), 4)
        elt.resize(3)
        self.assertEqual(elt.min_data_size(), 3)
        self.assertEqual(elt.valid_data_size_le(4), 4)
        elt.resize(4)
        self.assertEqual(elt.min_data_size(), 4)
        self.assertEqual(elt.valid_data_size_le(4), 4)
        self.assertEqual(elt.valid_data_size_le(3), None)
        elt.resize(5)
        self.assertEqual(elt.min_data_size(), 4)
        elt.value = 0x0101010101
        self.assertEqual(elt.min_data_size(), 5)
        elt.data_size_min = 8
        self.assertEqual(elt.min_data_size(), 5)
        elt.resize(8)
        self.assertEqual(elt.min_data_size(), 8)
        elt.data_size_min = 9 # invalid
        self.assertEqual(elt.min_data_size(), 8)
        self.assertEqual(elt.valid_data_size_le(9), 8)
        # Boolean
        elt = ElementBoolean.new_with_value(UNK_ID, True)
        self.assertEqual(elt.min_data_size(), 1)
        self.assertEqual(elt.max_data_size(), 8)
        # Signed, Enum, BitField: same
        # Float
        elt = ElementFloat.new_with_value(UNK_ID, 0.0)
        self.assertEqual(elt.min_data_size(), 4)
        self.assertEqual(elt.max_data_size(), 8)
        self.assertEqual(elt.valid_data_size_le(3), None)
        self.assertEqual(elt.valid_data_size_le(5), 4)
        self.assertEqual(elt.valid_data_size_le(7), 4)
        self.assertEqual(elt.valid_data_size_le(8), 8)
        self.assertEqual(elt.valid_data_size_le(9), 8)
        elt.resize(8)
        self.assertEqual(elt.min_data_size(), 8)
        self.assertEqual(elt.max_data_size(), 8)
        # String
        elt = ElementString.new_with_value(UNK_ID, 'abcdefgh')
        self.assertEqual(elt.min_data_size(), 8)
        self.assertEqual(elt.max_data_size(), MAX_DATA_SIZE)
        self.assertEqual(elt.valid_data_size_le(9), 9)
        elt.resize_total(100)
        self.assertEqual(elt.value, 'abcdefgh')
        self.assertEqual(elt.total_size, 100)
        self.assertEqual(elt.header_size, 5)
        # Date
        elt = ElementDate.new_with_value(UNK_ID)
        self.assertEqual(elt.min_data_size(), 8)
        self.assertEqual(elt.max_data_size(), 8)
        self.assertEqual(elt.valid_data_size_le(7), None)
        self.assertEqual(elt.valid_data_size_le(9), 8)
        # ID
        elt = ElementID.new_with_value(UNK_ID, 0x012233)
        self.assertEqual(elt.min_data_size(), 3)
        self.assertEqual(elt.max_data_size(), 3)
        self.assertEqual(elt.valid_data_size_le(7), 3)

        # Test min_header_size()
        elt = ElementVoid.of_size(0x010101)
        elt.header_size_min = 5
        self.assertEqual(elt.min_header_size(), 4)
        self.assertEqual(elt.min_header_size(0x01010101), 5)
        self.assertEqual(elt.min_header_size(0x0101010101), 6)
        self.assertEqual(elt.min_header_size(0x010101010101), 7)
        # Grow header
        elt.resize(0x0101010101)
        elt.resize(1)
        # Refuse to shrink header
        self.assertEqual(elt.min_header_size(), 6)

        # Put valid_total_size_le() through its paces
        elt = ElementUnsigned.new_with_value(UNK_ID, 1000)
        # Resize data
        for i in range(2, 9):
            self.check_valid_total_size_le(elt, 5 + i, 5, i)
        # Grow header
        for i in range(2, 9):
            self.check_valid_total_size_le(elt, 4 + i + 8, 4 + i, 8)
        self.check_valid_total_size_le(elt, 21, 4 + 8, 8)
        # Shrinkable header
        # Resize data
        elt.header.numbytes = 10
        for i in range(2, 9):
            self.check_valid_total_size_le(elt, 10+i, 10, i)
        self.check_valid_total_size_le(elt, 19, 11, 8)
        self.check_valid_total_size_le(elt, 20, 12, 8)
        self.check_valid_total_size_le(elt, 21, 12, 8)
        # Resize header because data is at minimum size
        for i in range(5, 11):
            self.check_valid_total_size_le(elt, i + 2, i, 2)
        # Prefer resizing data
        self.check_valid_total_size_le(elt, 11 + 2, 10, 3)
        self.check_valid_total_size_le(elt, 12 + 2, 10, 4)
        self.check_valid_total_size_le(elt, 13 + 2, 10, 5)
        # Funny allowed sizes
        elt = ElementFloat.new_with_value(UNK_ID, 1.0)
        # Resize header because 7 isn't a valid data size
        self.check_valid_total_size_le(elt, 12, 8, 4)
        # Prefer resizing data
        self.check_valid_total_size_le(elt, 13, 5, 8)
        # Prefer smaller header size: 10 + 4 also works
        self.check_valid_total_size_le(elt, 14, 6, 8)

        # Test minimum header and data size on element creation
        tag = Tag(UNK_ID, 'TestTag', 'ElementMaster', None, False,
                  False, True, 1, 1, header_size_min=4, data_size_min=501)
        MATROSKA_TAGS.insert(tag)
        elt = ElementMaster.new('TestTag')
        self.assertEqual(elt.header_size, 8)
        self.assertEqual(elt.size, 501)
        elt = ElementMaster.new('TestTag', size=0x0122334455)
        self.assertEqual(elt.header_size, 9)
        tag.header_size_min = 9
        elt = ElementMaster.new('TestTag', size=0x0122334455)
        self.assertEqual(elt.header_size, 12)

        tag = Tag(UNK_ID, 'TestTag', 'ElementUnsigned', None, False,
                  False, True, 1, 1, header_size_min=4, data_size_min=5)
        MATROSKA_TAGS.insert(tag)
        elt = ElementUnsigned.new_with_value('TestTag', 1234)
        self.assertEqual(elt.header_size, 8)
        self.assertEqual(elt.size, 5)
        tag.data_size_min = 3
        elt = ElementUnsigned.new_with_value('TestTag', 1234)
        self.assertEqual(elt.size, 4)
        tag.data_size_min = 9
        elt = ElementUnsigned.new_with_value('TestTag', 1234)
        self.assertEqual(elt.size, 8)

        tag = Tag(UNK_ID, 'TestTag', 'ElementFloat', None, False,
                  False, True, 1, 1, header_size_min=4, data_size_min=5)
        MATROSKA_TAGS.insert(tag)
        elt = ElementFloat.new_with_value('TestTag', 1234.0)
        self.assertEqual(elt.size, 8)
        tag.data_size_min = 3
        elt = ElementFloat.new_with_value('TestTag', 1234.0)
        self.assertEqual(elt.size, 4)

        tag = Tag(UNK_ID, 'TestTag', 'ElementString', None, False,
                  False, True, 1, 1, header_size_min=5, data_size_min=50)
        MATROSKA_TAGS.insert(tag)
        elt = ElementString.new_with_value('TestTag', 'test string')
        self.assertEqual(elt.size, 50)

        MATROSKA_TAGS.remove(UNK_ID)

    def test_2_dirty(self):
        "Test whether the dirty property works."
        from ebml.element import Element
        from ebml.atomic import ElementRaw

        ebmlf = self.read_file_data()
        elts = self.track_entry_elt(ebmlf)
        self.assertFalse(elts.dirty)
        for elt in elts:
            self.assertFalse(elt.dirty)
        # All the ways to make an element dirty:
        elts[0].value = 5 # Changed value
        self.assertTrue(elts[0].dirty)
        self.assertTrue(elts.dirty) # Child is dirty
        elt = elts[1]
        elts.move_child(elt, 71) # Moved
        self.assertTrue(elt.dirty)
        elts[2].resize(2) # Size changed
        self.assertTrue(elts[2].dirty)
        elts[3].dirty = True # Forced dirty
        self.assertTrue(elts[3].dirty)
        elt = ebmlf[1][1] # Void
        old_size = elt.total_size
        elt.header.numbytes = 3
        elt.resize(old_size - 3)
        self.assertTrue(elt.dirty) # Header changed size
        ebmlf = self.read_file_data()
        ebmlf[1].dirty = 'recurse' # Recursively forced dirty
        elts = self.track_entry_elt(ebmlf)
        self.assertTrue(elts.dirty)
        for elt in elts:
            self.assertTrue(elt.dirty)
        # Created programatically
        elt = ElementRaw.new_with_value(UNK_ID, parent=elts)
        self.assertTrue(elt.dirty)

        # Test that only dirty elements are written.
        ebmlf = self.read_file_data()
        elts = self.track_entry_elt(ebmlf)
        stream2 = BytesIO(b'\x00' * len(self.file_data))
        ebmlf.write(stream2) # Should do nothing
        self.assertEqual(sum(stream2.getvalue()), 0)
        elt = elts[0]
        elt.dirty = True
        ebmlf.write(stream2, seekfirst=True)
        self.assertEqual(elt.read_raw(ebmlf.stream), elt.read_raw(stream2))
        # Only the parents' headers should've been written
        data = stream2.getvalue()
        parent = elt
        ancestors = []
        while isinstance(parent, Element):
            ancestors.append(parent)
            parent = parent.parent
        ancestors.reverse()
        for i in range(1, len(ancestors)):
            self.assertEqual(sum(data[ancestors[i-1].pos_data_absolute:
                                      ancestors[i].pos_absolute]), 0)
        self.assertEqual(sum(data[elt.pos_end_absolute:]), 0)
        self.assertFalse(elt.dirty)

    def test_3_consistency(self):
        "Test consistency checks."
        from ebml import Inconsistent
        from ebml.element import ElementVoid, ElementPlaceholder
        from ebml.atomic import ElementUnsigned

        ebmlf = self.read_file_data()
        ebmlf.check_consistency()
        # overlap
        elts = self.track_entry_elt(ebmlf)
        elts[0].resize(2)
        self.assertRaisesRegex(Inconsistent, 'Overlapping children',
                               ebmlf.check_consistency)
        # blank at beginning
        elts = self.reset_track_entry(ebmlf)
        elts.remove_child(0)
        self.assertRaisesRegex(Inconsistent, "Blank space at beginning",
                               elts.check_consistency)
        # blank in middle
        elts = self.reset_track_entry(ebmlf)
        elts.remove_child(4)
        self.assertRaisesRegex(Inconsistent, "Empty space between children",
                               elts.check_consistency)
        # blank at end
        elts = self.reset_track_entry(ebmlf)
        elts.remove_child(-1)
        self.assertRaisesRegex(Inconsistent, "ends before parent",
                               elts.check_consistency)
        # overflow at end
        elts = self.reset_track_entry(ebmlf)
        elts[-1].resize(2)
        self.assertRaisesRegex(Inconsistent, "ends after parent",
                               elts.check_consistency)
        # empty but size > 0
        elts = self.reset_track_entry(ebmlf)
        while len(elts):
            elts.remove_child(0)
        self.assertRaisesRegex(Inconsistent,
                               "Empty Master Element",
                               elts.check_consistency)
        # Impermissible level-0
        self.reset_track_entry(ebmlf)
        # ebmlf = self.read_file_data()
        ebmlf.add_child(ElementUnsigned.new_with_value('EBMLVersion'))
        self.assertRaisesRegex(Inconsistent, "Impermissible level-0 child",
                               ebmlf.check_consistency)
        ebmlf.remove_child(-1)
        # Missing required level-0
        ebmlf.remove_child(1)
        self.assertRaisesRegex(Inconsistent, "Mandatory level-0 element",
                               ebmlf.check_consistency)
        # Version too low
        ebmlf = self.read_file_data()
        ebmlf[0].doc_type_version = 5
        self.assertRaisesRegex(Inconsistent, "with EBML header Element",
                               ebmlf.check_consistency)
        # Missing parent
        elt = ElementUnsigned.new_with_value('EBMLVersion')
        self.assertRaisesRegex(Inconsistent, "No parent element",
                               elt.check_consistency)
        # Impermissible child
        elts = self.reset_track_entry(ebmlf)
        elts.remove_child(0)
        ElementUnsigned.new_with_value('Position', 1, elts, 0)
        elts[0].resize(1)
        self.assertRaisesRegex(Inconsistent, "Impermissible child",
                               elts.check_consistency)
        # Missing required child
        elts = self.reset_track_entry(ebmlf)
        size = elts[0].total_size
        elts.remove_child(0)
        ElementVoid.of_size(size, elts, 0)
        self.assertRaisesRegex(Inconsistent, "Mandatory child",
                               elts.check_consistency)
        # Multiple instances of unique child
        elts = self.reset_track_entry(ebmlf)
        elts.add_child(ElementUnsigned.new_with_value('TrackUID', 1))
        elts.resize(elts.size + elts[-1].total_size)
        self.assertRaisesRegex(Inconsistent, "Multiple instances of unique",
                               elts.check_consistency)
        # Zero raw value
        ebmlf = self.read_file_data()
        seg = ebmlf[1]
        info = seg[3]
        uid = info[6]
        uid.value = b'\x00' * len(uid.value)
        self.assertRaisesRegex(Inconsistent, "Zero Raw value",
                               ebmlf.check_consistency)
        # Unsigned too small
        elts = self.reset_track_entry(ebmlf)
        elts[0].value = 0
        self.assertRaisesRegex(Inconsistent, "< min value",
                               elts.check_consistency)
        # Unsigned too large
        elts = self.reset_track_entry(ebmlf)
        elts[2].value = 255
        self.assertRaisesRegex(Inconsistent, "> max value",
                               elts.check_consistency)
        # Float too small
        audio = ebmlf[1][4][1][-1]
        audio[0].value = 0.0 # SamplingFrequency
        self.assertRaisesRegex(Inconsistent, "<= min value",
                               audio.check_consistency)
        # Placeholder moved
        elt = ElementPlaceholder.of_size('LibInternal', 10, ebmlf,
                                         seg.pos_end_relative)
        elt.check_consistency()
        ebmlf.move_child(elt, seg.pos_end_relative + 10)
        self.assertRaisesRegex(Inconsistent, "Dirty ElementPlaceholder",
                               elt.check_consistency)
