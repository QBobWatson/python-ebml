#pylint: disable=too-many-locals,no-self-use
#pylint: disable=too-many-public-methods,too-many-statements
"""
Element container tests.
"""

from .test import EbmlTest, UNK_ID

__all__ = ['ContainerTest']

class ContainerTest(EbmlTest):
    "Container tests."

    def make_test_container(self):
        """Return a container with elements from 5--10, 16--25, 33--40.

        The middle element is shrinkable to size 5.
        """
        from ebml.element import ElementMaster, ElementUnsupported, ElementVoid
        from ebml.atomic import ElementString
        elt = ElementMaster.new(UNK_ID)
        ElementVoid.of_size(5, elt, 0)
        ElementUnsupported.of_size(UNK_ID, 5, elt, 5)
        ElementVoid.of_size(6, elt, 10)
        ElementString.new_with_value(UNK_ID, '', elt, 16).resize_total(9)
        ElementVoid.of_size(8, elt, 25)
        ElementUnsupported.of_size(UNK_ID, 7, elt, 33)
        ElementVoid.of_size(8, elt, 40)
        elt.resize(48)
        return elt

    def check_child_pos(self, elt, *positions):
        "Check elements have the specified start and end positions."
        children = iter(elt)
        prev_child = None
        for start in positions:
            try:
                child = next(children)
            except StopIteration:
                child = None
            if prev_child is not None:
                self.assertEqual(prev_child.pos_end_relative, start)
            if child is not None:
                self.assertEqual(child.pos_relative, start)
            prev_child = child
        self.assertEqual(len(positions), len(elt) + 1)

    def test_1_containers(self):
        "Test Container methods."
        from ebml import Inconsistent
        from ebml.element import ElementVoid, ElementMaster, ElementUnsupported
        from ebml.atomic import ElementString, ElementUnicode
        from ebml.tags import MATROSKA_TAGS

        ebmlf = self.read_file_data()
        seg = ebmlf[1]
        elt = self.track_entry_elt(ebmlf)

        # Test end_last_child
        self.assertEqual(elt.end_last_child, elt.size)
        # Two elements starting at the same final position
        void = ElementVoid.of_size(20, elt, elt[-1].pos_relative)
        self.assertEqual(elt.end_last_child, void.pos_end_relative)
        elt.remove_child(void)

        # Test children_named, children_with_id
        self.assertEqual(list(seg.children_named('SeekHead')),
                         [seg[0], seg[2], seg[10], seg[12]])
        ebml_id = MATROSKA_TAGS['Void'].ebml_id
        self.assertEqual(list(seg.children_with_id(ebml_id)),
                         [seg[1], seg[7]])

        # Test children_in_region
        children = seg.children_in_region(seg[-1].pos_relative + 1)
        self.assertEqual(list(children), [])
        children = seg.children_in_region(seg[-2].pos_relative)
        self.assertEqual(list(children), seg[-2:])
        children = seg.children_in_region(seg[-2].pos_relative-1)
        self.assertEqual(list(children), seg[-2:])
        children = seg.children_in_region(seg[1].pos_relative,
                                          seg[1].total_size)
        self.assertEqual(list(children), seg[1:2])
        children = seg.children_in_region(seg[1].pos_relative,
                                          seg[1].total_size+1)
        self.assertEqual(list(children), seg[1:3])
        children = seg.children_in_region(seg[-2].pos_relative, 1000)
        self.assertEqual(list(children), seg[-2:])
        children = seg.children_in_region(0, seg[3].pos_relative, novoids=True)
        self.assertEqual(list(children), [seg[0], seg[2]])

        # Test adding and moving children
        void = ElementVoid.of_size(20)
        old_end = seg.end_last_child
        seg.add_child(void)
        self.assertIs(void.parent, seg)
        self.assertEqual(void.pos_relative, old_end)
        seg.remove_child(void)
        seg.add_child(void, 3)
        self.assertEqual(void.pos_relative, 3)
        seg.remove_child(void)
        elt = seg[3]
        seg.move_child(elt, 3)
        self.assertEqual(elt.pos_relative, 3)
        self.assertIs(seg[1], elt)
        seg.move_child(1, 24)
        self.assertEqual(elt.pos_relative, 24)
        self.assertIs(seg[2], elt)

        # Test find_gap()
        elt = ElementMaster.new(UNK_ID)
        # No children
        #self.assertEqual(elt.find_gap(100), (0, MAX_DATA_SIZE, None))
        self.assertEqual(elt.find_gap(100), None)
        self.assertEqual(elt.find_gap(100, region_size=150), (0, 150, None))
        self.assertEqual(elt.find_gap(100, region_size=50), None)
        ElementUnsupported.of_size(UNK_ID, 20, elt, 5)
        elt1 = ElementString.new_with_value(UNK_ID, 'abcde', elt, 31)
        elt1.resize_total(20)
        # gaps: 0--5, 25--31, 51--
        self.assertEqual(elt.find_gap(100, start=51, region_size=150),
                         (51, 150, None))
        # Gap at beginning
        self.assertEqual(elt.find_gap(5), (0, 5, None))
        self.assertEqual(elt.find_gap(5, start=25), None)
        self.assertEqual(elt.find_gap(5, start=25, region_size=35),
                         (51, 9, elt[1]))
        self.assertEqual(elt.find_gap(5, start=25, one_byte_ok=True),
                         (25, 6, None))
        # Gap in the middle
        self.assertEqual(elt.find_gap(6), (25, 6, elt[0]))
        self.assertEqual(elt.find_gap(5), (0, 5, None))
        # Gap at the end
        self.assertEqual(elt.find_gap(4, region_size=55), (51, 4, elt[1]))
        self.assertEqual(elt.find_gap(7), None)
        self.assertEqual(elt.find_gap(7, region_size=60), (51, 9, elt[1]))
        # No solution
        self.assertEqual(elt.find_gap(7, region_size=57), None)
        self.assertEqual(elt.find_gap(7, region_size=59), None)
        self.assertEqual(elt.find_gap(7, region_size=58),
                         (51, 7, elt[1]))
        # Several gaps: 0--5, 25--31, 51--55, 75--
        ElementUnsupported.of_size(UNK_ID, 20, elt, 55)
        self.assertEqual(elt.find_gap(3), (0, 5, None))
        self.assertEqual(elt.find_gap(3, one_byte_ok=True), (51, 4, elt[1]))
        self.assertEqual(elt.find_gap(4), (51, 4, elt[1]))
        self.assertEqual(elt.find_gap(5), (0, 5, None))
        self.assertEqual(elt.find_gap(5, start=10, one_byte_ok=True),
                         (25, 6, elt[0]))
        self.assertEqual(elt.find_gap(6), (25, 6, elt[0]))
        self.assertEqual(elt.find_gap(7), None)
        self.assertEqual(elt.find_gap(7, region_size=100), (75, 25, elt[2]))
        # Shrinking child: gaps 0--5, 25--31, 41--55, 75--
        self.assertEqual(elt.find_gap(4, shrink=True, one_byte_ok=True),
                         (0, 5, None))
        self.assertEqual(elt.find_gap(6, shrink=True), (25, 6, elt[0]))
        self.assertEqual(elt.find_gap(7, shrink=True), (41, 14, elt[1]))
        self.assertEqual(elt.find_gap(14, shrink=True), (41, 14, elt[1]))
        self.assertEqual(elt.find_gap(15, region_size=100, shrink=True),
                         (75, 25, elt[2]))

        # Test place_child()
        # No shrink necessary
        elt = self.make_test_container()
        child = ElementVoid.of_size(3)
        elt.place_child(child, shrink_child=False, shrink_previous=False,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (0, 3))
        elt = self.make_test_container()
        child = ElementVoid.of_size(4)
        elt.place_child(child, shrink_child=False, shrink_previous=False,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (10, 4))
        elt = self.make_test_container()
        child = ElementVoid.of_size(4)
        elt.place_child(child, shrink_child=False, shrink_previous=False,
                        grow_child=True)
        self.assertEqual((child.pos_relative, child.total_size), (0, 5))
        elt = self.make_test_container()
        child = ElementVoid.of_size(7)
        with self.assertRaises(Inconsistent):
            elt.place_child(child, region_size=40, shrink_child=False,
                            shrink_previous=False, grow_child=False)
        elt.place_child(child, shrink_child=False, shrink_previous=False,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (40, 7))
        elt = self.make_test_container()
        child = ElementVoid.of_size(7)
        elt.place_child(child, shrink_child=False, shrink_previous=False,
                        grow_child=True)
        self.assertEqual((child.pos_relative, child.total_size), (25, 8))
        # Shrink child
        elt = self.make_test_container()
        child = ElementVoid.of_size(10)
        elt.place_child(child, shrink_child=True, shrink_previous=False,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (0, 2))
        elt = self.make_test_container()
        child = ElementString.new_with_value(UNK_ID, 'a') # min size == 6
        child.resize_total(10)
        elt.place_child(child, shrink_child=True, shrink_previous=False,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (10, 6))
        elt = self.make_test_container()
        child = ElementString.new_with_value(UNK_ID, 'ab') # min size == 7
        child.resize_total(10)
        elt.place_child(child, shrink_child=True, shrink_previous=False,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (25, 8))
        elt = self.make_test_container()
        child = ElementString.new_with_value(UNK_ID, 'abcd') # min size == 9
        child.resize_total(10)
        with self.assertRaises(Inconsistent):
            elt.place_child(child, region_size=40, shrink_child=True,
                            shrink_previous=False, grow_child=False)
        elt.place_child(child, shrink_child=True, shrink_previous=False,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (40, 10))
        # Shrink previous
        elt = self.make_test_container()
        child = ElementString.new_with_value(UNK_ID, 'abcd') # min size == 9
        elt.place_child(child, shrink_child=False, shrink_previous=True,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (24, 9))
        self.assertEqual(elt.find(16).total_size, 8)
        elt = self.make_test_container()
        child = ElementString.new_with_value(UNK_ID, 'abcd') # min size == 9
        child.resize_total(10)
        elt.place_child(child, shrink_child=False, shrink_previous=True,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (23, 10))
        self.assertEqual(elt.find(16).total_size, 7)
        elt = self.make_test_container()
        child = ElementString.new_with_value(UNK_ID, 'abcd') # min size == 9
        child.resize_total(10)
        elt.place_child(child, shrink_child=True, shrink_previous=True,
                        grow_child=False)
        self.assertEqual((child.pos_relative, child.total_size), (24, 9))
        self.assertEqual(elt.find(16).total_size, 8)
        elt = self.make_test_container()
        elt.remove_child(elt.find(16))
        ElementMaster.new(UNK_ID, elt, 16, size=2) # total size == 7
        # gap from 23 -- 33, shrinks to 22--33
        child = ElementString.new_with_value(UNK_ID, 'abcd')
        child.resize_total(11)
        with self.assertRaises(Inconsistent):
            # Won't find the gap with grow_child=False
            elt.place_child(child, region_size=40, shrink_child=False,
                            shrink_previous=True, grow_child=False)
        elt.place_child(child, shrink_child=False, shrink_previous=True,
                        grow_child=True)
        self.assertEqual((child.pos_relative, child.total_size), (22, 11))
        self.assertEqual(elt.find(16).total_size, 6)

        # Test get_overlapping()
        elt = self.make_test_container()
        self.assertEqual(elt.get_overlapping(), frozenset())
        # Negative position
        child = ElementUnicode.new_with_value('MuxingApp', 'abcd', elt, -1)
        self.assertEqual(elt.get_overlapping(), frozenset({child}))
        elt.add_child(child, -1)
        self.assertRaises(Inconsistent, elt.get_overlapping, ('MuxingApp', ))
        # Two fixed
        elt.add_child(child, 100)
        ElementUnicode.new_with_value('MuxingApp', 'efgh', elt, 105)
        self.assertRaises(Inconsistent, elt.get_overlapping, ('MuxingApp', ))
        # One fixed
        elt = self.make_test_container()
        result = frozenset({elt[0], elt[1], elt[2]})
        child = ElementUnicode.new_with_value('MuxingApp', 'abcd', elt, 2)
        child.resize_total(10)
        self.assertEqual(elt.get_overlapping(('MuxingApp',)), result)
        # None fixed
        elt = self.make_test_container()
        result = frozenset({elt[0], elt[1], elt[2]})
        child = ElementUnicode.new_with_value('MuxingApp', 'abcd', elt, 2)
        child.resize_total(10) # this one is largest
        self.assertEqual(elt.get_overlapping(), result)
        elt = self.make_test_container()
        child = ElementVoid.of_size(2, elt, 4) # this one is smallest
        self.assertEqual(elt.get_overlapping(), frozenset({child}))
        # One-byte gap
        elt = self.make_test_container()
        result = frozenset({elt[0]})
        elt[0].resize_total(4)
        self.assertEqual(elt.get_overlapping(), result)

    def test_2_rearrange(self):
        "Test Container.rearrange() and its relatives."
        from ebml.element import ElementMaster, ElementVoid, ElementUnsupported

        # -- Test rearrange_resize()
        # Already arranged
        elt = self.make_test_container()
        elt.resize(40)
        elt.rearrange_resize()
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 33, 40)
        self.assertEqual(elt.size, 40)
        # Shrink
        elt = self.make_test_container()
        elt.resize(50)
        elt.rearrange_resize()
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 33, 40)
        self.assertEqual(elt.size, 40)
        # Grow
        elt = self.make_test_container()
        elt.resize(30)
        elt.rearrange_resize()
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 33, 40)
        self.assertEqual(elt.size, 40)
        # Grow because we're lazy
        elt = self.make_test_container()
        elt.resize(40)
        ElementUnsupported.of_size(UNK_ID, 15, elt, 24)
        elt.rearrange_resize()
        self.check_child_pos(elt, 0, 5, 10, 16, 24, 39, 46)
        self.assertEqual(elt.size, 46)
        # Grow because we're forced to
        elt = self.make_test_container()
        elt.resize(40)
        ElementUnsupported.of_size(UNK_ID, 35, elt, 0)
        elt.rearrange_resize(prefer_grow=False)
        self.check_child_pos(elt, 0, 35, 40, 45, 52)
        self.assertEqual(elt.size, 52)
        elt = self.make_test_container()
        elt.resize(16)
        elt.rearrange_resize(prefer_grow=False)
        self.check_child_pos(elt, 0, 5, 10, 17)
        self.assertEqual(elt.size, 17)
        # Add a Void at the end
        elt = self.make_test_container()
        elt.resize(50)
        elt.rearrange_resize(allow_shrink=False)
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 33, 40, 50)
        self.assertEqual(elt.size, 50)
        elt = self.make_test_container()
        elt.resize(41)
        elt.rearrange_resize(allow_shrink=False)
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 33, 40, 42)
        self.assertEqual(elt.size, 42)
        elt = self.make_test_container()
        elt.resize(20)
        elt.rearrange_resize(prefer_grow=False, allow_shrink=False)
        self.check_child_pos(elt, 0, 5, 10, 17, 20)
        self.assertEqual(elt.size, 20)
        elt = self.make_test_container()
        elt.resize(18)
        elt.rearrange_resize(prefer_grow=False, allow_shrink=False)
        self.check_child_pos(elt, 0, 5, 10, 17, 19)
        self.assertEqual(elt.size, 19)

        # -- Test rearrange() --
        # No children
        elt = ElementMaster.new(UNK_ID)
        ElementVoid.of_size(5, elt, 0)
        elt.rearrange()
        self.assertEqual(len(elt), 0)

        # Eliminate overlaps (part 1 of the algorithm)
        # Push everything forward
        elt = self.make_test_container()
        ElementUnsupported.of_size(UNK_ID, 35, elt, 0)
        elt.rearrange()
        self.check_child_pos(elt, 0, 35, 40, 49, 56)
        # Push first and second forward less
        elt = self.make_test_container()
        ElementUnsupported.of_size(UNK_ID, 24, elt, 0)
        elt.rearrange()
        self.check_child_pos(elt, 0, 24, 29, 38, 45)
        # Push first and second forward and shrink second
        elt = self.make_test_container()
        ElementUnsupported.of_size(UNK_ID, 23, elt, 0)
        elt.rearrange()
        self.check_child_pos(elt, 0, 23, 28, 33, 40)
        # Push first and second forward and shrink second less
        elt = self.make_test_container()
        ElementUnsupported.of_size(UNK_ID, 22, elt, 0)
        elt.rearrange()
        self.check_child_pos(elt, 0, 22, 27, 33, 40)
        # No need to shrink second
        elt = self.make_test_container()
        ElementUnsupported.of_size(UNK_ID, 19, elt, 0)
        elt.rearrange()
        self.check_child_pos(elt, 0, 19, 24, 33, 40)
        # Push first and second forward with 1-byte gap
        elt = self.make_test_container()
        ElementUnsupported.of_size(UNK_ID, 18, elt, 0)
        elt.rearrange()
        self.check_child_pos(elt, 0, 18, 23, 32, 39)
        # Push first and second forward with 4-byte gap
        elt = self.make_test_container()
        ElementUnsupported.of_size(UNK_ID, 15, elt, 0)
        elt.rearrange()
        self.check_child_pos(elt, 0, 15, 20, 29, 33, 40)
        # One-byte gap at beginning
        elt = self.make_test_container()
        ElementUnsupported.of_size(0x012233, 4, elt, 1)
        elt.rearrange()
        self.check_child_pos(elt, 0, 4, 9, 16, 25, 33, 40)

        # Fit in goal size (part 2 of the algorithm)
        # Everything already fits
        elt = self.make_test_container()
        elt.rearrange(40)
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 33, 40)
        # One-byte gap
        elt = self.make_test_container()
        elt.rearrange(41)
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 32)
        # Move last
        elt = self.make_test_container()
        elt.rearrange(39)
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 32)
        elt = self.make_test_container()
        elt.rearrange(34)
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 32)
        elt = self.make_test_container()
        elt.rearrange(32)
        self.check_child_pos(elt, 0, 5, 10, 16, 25, 32)
        # Move last with 1-byte gap (shrinks second)
        elt = self.make_test_container()
        elt.rearrange(33)
        self.check_child_pos(elt, 0, 5, 10, 16, 21, 28)
        # Move last and shrink second
        elt = self.make_test_container()
        elt.rearrange(31)
        self.check_child_pos(elt, 0, 5, 10, 16, 21, 28)
        elt = self.make_test_container()
        elt.rearrange(30)
        self.check_child_pos(elt, 0, 5, 10, 16, 21, 28)
        elt = self.make_test_container()
        elt.rearrange(28)
        self.check_child_pos(elt, 0, 5, 10, 16, 21, 28)
        # Move two last
        elt = self.make_test_container()
        elt.rearrange(29)
        self.check_child_pos(elt, 0, 5, 10, 15, 22)
        elt = self.make_test_container()
        elt.rearrange(27)
        self.check_child_pos(elt, 0, 5, 10, 15, 22)
        elt = self.make_test_container()
        elt.rearrange(24)
        self.check_child_pos(elt, 0, 5, 10, 15, 22)
        elt = self.make_test_container()
        elt.rearrange(22)
        self.check_child_pos(elt, 0, 5, 10, 15, 22)
        # Maximal shrink
        elt = self.make_test_container()
        elt.rearrange(23)
        self.check_child_pos(elt, 0, 5, 10, 17)
        elt = self.make_test_container()
        elt.rearrange(21)
        self.check_child_pos(elt, 0, 5, 10, 17)
        elt = self.make_test_container()
        elt.rearrange(17)
        self.check_child_pos(elt, 0, 5, 10, 17)
        # Nothing to do about the trailing 1-byte gap
        elt = self.make_test_container()
        elt.rearrange(18)
        self.check_child_pos(elt, 0, 5, 10, 17)
        # Doesn't fit
        elt = self.make_test_container()
        elt.rearrange(16)
        self.check_child_pos(elt, 0, 5, 10, 17)

        # Recursively rearrange (part 3 of the algorithm)
        elt = self.make_test_container()
        elt2 = self.make_test_container()
        elt.add_child(elt2, 7)
        elt.rearrange()
        self.check_child_pos(elt, 0, 5, 10, 63, 72, 79)
        self.check_child_pos(elt2, 0, 5, 10, 16, 25, 33, 40, 48)
        self.assertEqual(elt2.size, 48)
        elt = self.make_test_container()
        elt2 = self.make_test_container()
        elt.add_child(elt2, 7)
        elt.rearrange(0)
        self.check_child_pos(elt, 0, 5, 27, 32, 39)
        self.check_child_pos(elt2, 0, 5, 10, 17)
        self.assertEqual(elt2.size, 17)

        # Test expand_header() and element at negative position
        elt = self.make_test_container()
        size = elt.total_size
        elt.remove_child(0)
        elt.remove_child(-1)
        ElementUnsupported.of_size(UNK_ID, 5, elt, 0)
        elt.expand_header(4)
        self.assertEqual(elt.total_size, size)
        self.check_child_pos(elt, -3, 2, 7, 13, 22, 30, 37)
        elt.rearrange()
        self.check_child_pos(elt, 0, 5, 10, 13, 22, 30, 37)
