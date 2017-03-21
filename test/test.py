#pylint: disable=too-many-locals,no-self-use
#pylint: disable=too-many-public-methods,too-many-statements
"""
General unit tests.

Run 'python3 -m unittest -v' from the ebml directory.
"""

import unittest
from io import BytesIO
import os
import sys
import random

from os.path import dirname as dn, abspath as ap
sys.path.append(dn(dn(dn(ap(__file__)))))

TEST_DATA_DIR = os.path.dirname(__file__)
TEST_FILE = os.path.join(TEST_DATA_DIR, 'test.mkv')

__all__ = ['EbmlTest', 'UtilityTest', 'HeaderTest', 'TagsTest', 'ParsedTest',
           'FilesTest', 'UNK_ID', 'TEST_FILE_DATA']

import logging
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

UNK_ID = 0x01223344

with open(TEST_FILE, 'rb') as mkv_file:
    TEST_FILE_DATA = mkv_file.read()


class EbmlTest(unittest.TestCase):
    "Base class for the ebml module tests."

    @classmethod
    def setUpClass(cls):
        cls.file_data = TEST_FILE_DATA

    # Utility methods

    def read_file_data(self):
        "Read file data with the fake Cluster element."
        from ebml.container import File
        ebmlf = File(BytesIO(self.file_data))
        ebmlf[1].read_data(ebmlf.stream)
        return ebmlf

    def info_elt(self, ebmlf):
        "Get Info element from self.file_data."
        return ebmlf[1][3]
    def track_entry_elt(self, ebmlf):
        "Get TrackEntry element from self.file_data."
        return ebmlf[1][-1][0]
    def seek_elt(self, ebmlf):
        "Get Seek element from self.file_data."
        return ebmlf[1][0][0]

    def element_is(self, elt, name, val):
        "Check an element's name and value."
        self.assertEqual(elt.name, name)
        self.assertEqual(elt.value, val)


class UtilityTest(EbmlTest):
    "Test utility module."

    def test_utility(self):
        "Test utility functions."
        from ebml.utility import encode_var_int, decode_var_int, numbytes_var_int
        from ebml.tags import MATROSKA_TAGS

        # numbytes_var_int()
        for size in range(1, 8):
            self.assertEqual(numbytes_var_int((1 << (size*7)) - 2), size)
            self.assertEqual(numbytes_var_int((1 << (size*7)) - 1), size+1)
        self.assertEqual(numbytes_var_int((1 << 56) - 2), 8)
        self.assertEqual(numbytes_var_int((1 << 56) - 1), None)

        # decode_var_int() and encode_var_int()
        for _ in range(100):
            num = random.randrange(1<<56)-2
            self.assertEqual(num, decode_var_int(encode_var_int(num))[0])

        # Encoding with forced size
        num = random.randrange(1000)
        raw = encode_var_int(num, 8)
        self.assertEqual(8, len(raw))
        self.assertEqual(num, decode_var_int(raw)[0])

        with self.assertRaises(ValueError):
            encode_var_int(1<<20, 2)

        # Encoding and decoding ID's
        for ebml_id in MATROSKA_TAGS.keys():
            if isinstance(ebml_id, int):
                self.assertEqual(ebml_id,
                                 decode_var_int(encode_var_int(ebml_id))[0])


class HeaderTest(EbmlTest):
    "Test header module."

    def test_header(self):
        "Test Header."
        from ebml.header import Header
        from ebml.utility import encode_var_int

        for _ in range(100):
            ebml_id = random.randrange(1<<28-1)
            size = random.randrange(1<<56)-2
            raw = encode_var_int(ebml_id, range(1, 5)) \
                  + encode_var_int(size, range(1, 9))
            header = Header(BytesIO(raw))
            header2 = Header(ebml_id=ebml_id, size=size)
            # Test decode
            self.assertEqual(header, header2)
            # Test encode
            header3 = Header(BytesIO(header2.encode()))
            self.assertEqual(header, header3)

        # Size forcing
        header = Header(ebml_id=10, size=10)
        self.assertEqual(header.numbytes_min, 2)
        self.assertEqual(header.numbytes_max, 9)
        for _ in range(5):
            num = random.randrange(2, 10)
            header.numbytes = num
            raw = header.encode()
            self.assertEqual(len(raw), num)
            self.assertEqual(header, Header(BytesIO(raw)))

        header = Header(ebml_id=(1<<28)-200, size=(1<<56)-2)
        self.assertEqual(header.numbytes_min, 12)
        self.assertEqual(header.numbytes_max, 12)
        raw = header.encode()
        self.assertEqual(len(raw), 12)
        self.assertEqual(header, Header(BytesIO(raw)))
        with self.assertRaises(ValueError):
            header.numbytes = 11

        # Growing
        header = Header(ebml_id=10, size=0)
        self.assertEqual(header.numbytes, 2)
        header.size = 0x012233
        self.assertEqual(header.numbytes, 4)
        header.size = 0
        self.assertEqual(header.numbytes, 4)

        # Copy
        header2 = header.copy()
        self.assertEqual(header, header2)
        self.assertEqual(header.numbytes, header2.numbytes)


class TagsTest(EbmlTest):
    "Test tags module."

    def test_tags(self):
        "Test MATROSKA_TAGS."
        from ebml.tags import MATROSKA_TAGS
        from ebml.atomic import ElementFloat

        # Test attributes reading
        tag = MATROSKA_TAGS['Duration']
        self.assertEqual(tag.ebml_id, 0x0489)
        self.assertEqual(tag.name, 'Duration')
        self.assertEqual(tag.cls, ElementFloat)
        self.assertEqual(tag.parent, MATROSKA_TAGS['Info'])
        self.assertIn(tag, tag.parent.children)
        self.assertEqual(tag.mandatory, False)
        self.assertEqual(tag.multiple, False)
        self.assertEqual(tag.webm, True)
        self.assertEqual(tag.minver, 1)
        self.assertEqual(tag.maxver, 4)
        # Not mandatory because of defaut
        self.assertEqual(MATROSKA_TAGS['TimecodeScale'].mandatory, False)
        # Extra elements
        self.assertEqual(tag.min_val, 0.0)
        tag = MATROSKA_TAGS['TrackType']
        self.assertEqual(tag.max_val, 254)
        self.assertEqual(tag.values[1], 'video')
        self.assertEqual(tag.mandatory, True)
        tag = MATROSKA_TAGS['Language']
        self.assertEqual(tag.default, 'eng')
        tag = MATROSKA_TAGS['SimpleTag']
        self.assertEqual(tag.recursive, True)
        # Exceptional cases
        self.assertEqual(MATROSKA_TAGS['Void'].parent, "*")
        self.assertEqual(MATROSKA_TAGS['EBML'].parent, None)
        # Required and unique
        tag = MATROSKA_TAGS['Segment']
        self.assertEqual(list(tag.required_children),
                         [MATROSKA_TAGS['Info']])
        self.assertEqual(set(tag.unique_children),
                         set([MATROSKA_TAGS['Cues'], MATROSKA_TAGS['Chapters'],
                              MATROSKA_TAGS['Attachments']]))
        # Parent/child
        self.assertTrue(MATROSKA_TAGS['Void'].is_child(None))
        self.assertTrue(MATROSKA_TAGS['EBML'].is_child(None))
        self.assertFalse(MATROSKA_TAGS['EBML']
                         .is_child(MATROSKA_TAGS['Segment']))
        self.assertTrue(MATROSKA_TAGS['Void']
                        .is_child(MATROSKA_TAGS['Segment']))
        self.assertTrue(MATROSKA_TAGS['Info']
                        .is_child(MATROSKA_TAGS['Segment']))
        self.assertFalse(MATROSKA_TAGS['TrackEntry']
                         .is_child(MATROSKA_TAGS['Segment']))
        self.assertTrue(MATROSKA_TAGS['SimpleTag']
                        .is_child(MATROSKA_TAGS['SimpleTag']))


class ParsedTest(EbmlTest):
    "Test parsed module."

    def test_parsed(self):
        "Test the functionality of the Parsed property."
        from operator import attrgetter
        from ebml.parsed import Parsed, create_atomic
        from ebml.element import ElementMaster
        from ebml.atomic import ElementUnsigned, ElementUnicode
        from ebml.tags import MATROSKA_TAGS

        class ElementTest(ElementMaster):
            #pylint: disable=too-many-ancestors,missing-docstring,no-self-use
            testval = 3
            did_delete = False
            elt1 = Parsed('TimecodeScale', 'value', 'value')
            elt2 = Parsed('SegmentFilename', 'value', 'value')
            elt3 = Parsed(0x3BA9, 'value', default='default', skip='') # Title
            elt4 = Parsed('Duration', '', default=attrgetter('elt1'))
            def getter_elt5(self, child):
                return child.value + ' getter function'
            elt5 = Parsed('MuxingApp', getter_elt5, default='def')
            def setter_elt6(self, child, val):
                child.value = val + self.testval
            def creator_elt6(self, ebml_id, val):
                return ElementUnsigned.new_with_value(ebml_id,
                                                      val + 2*self.testval)
            def deleter_elt6(self, ebml_id):
                self.did_delete = ebml_id
            elt6 = Parsed('Timecode', 'value', setter_elt6, creator_elt6,
                          deleter_elt6, default=3210)
            elt7 = Parsed('SeekPosition', 'value', 'value',
                          create_atomic(), deleter=False, default=1728)

        # Test getting
        test = ElementTest.new(UNK_ID)
        # Default value from tag
        self.assertEqual(test.elt1, 1000000)
        test.add_child(ElementUnsigned.new_with_value('TimecodeScale', 12345))
        self.assertEqual(test.elt1, 12345)
        # Get value of last child
        test.add_child(ElementUnsigned.new_with_value('TimecodeScale', 54321))
        self.assertEqual(test.elt1, 54321)

        # Fallback default value
        self.assertEqual(test.elt2, None)
        fnelt = ElementUnicode.new_with_value('SegmentFilename', 'test.mkv')
        test.add_child(fnelt)
        self.assertEqual(test.elt2, 'test.mkv')

        # Specified default value
        self.assertEqual(test.elt3, 'default')
        test.add_child(ElementUnicode.new_with_value('Title', 'test title'))
        self.assertEqual(test.elt3, 'test title')
        # Skip blank entry
        test.add_child(ElementUnicode.new_with_value('Title'))
        self.assertEqual(test.elt3, 'test title')

        # Callable default value
        self.assertEqual(test.elt4, 54321)
        # Getter is ''
        elt = ElementUnsigned.new_with_value('Duration', 11111)
        test.add_child(elt)
        self.assertIs(test.elt4, elt)

        # Getter function
        self.assertEqual(test.elt5, 'def')
        test.add_child(ElementUnicode.new_with_value('MuxingApp', 'this plus'))
        self.assertEqual(test.elt5, 'this plus getter function')

        # Test setting
        with self.assertRaises(AttributeError):
            test.elt3 = 'barf.mkv' # Can't set
        test.elt2 = 'new.mkv'
        self.assertEqual(test.elt2, 'new.mkv')
        # Sets last element
        test.elt1 = 22222
        self.assertEqual(test.elt1, 22222)
        self.assertEqual(next(test.children_named('TimecodeScale')).value,
                         12345)
        del test.elt2
        with self.assertRaises(AttributeError):
            test.elt2 = 'barf.mkv' # Can't create

        # Test creating
        self.assertEqual(test.elt6, 3210)
        # Custom creator
        test.elt6 = 1023
        self.assertEqual(test.elt6, 1023 + 2*test.testval)
        self.assertEqual(test[-1].value, 1023 + 2*test.testval)
        self.assertEqual(test[-1].name, 'Timecode')
        # Custom setter
        test.elt6 = 2034
        self.assertEqual(test.elt6, 2034 + test.testval)
        self.assertEqual(test[-1].value, 2034 + test.testval)
        # create_atomic
        self.assertEqual(test.elt7, 1728)
        test.elt7 = 1827
        self.assertEqual(test.elt7, 1827)
        self.assertEqual(test[-1].value, 1827)
        self.assertEqual(test[-1].name, 'SeekPosition')

        # Test deleting
        # Delete all instances
        del test.elt1
        self.assertEqual(test.elt1, 1000000)
        self.assertEqual(list(test.children_named('TimecodeScale')), [])
        # Delete only instance
        del test.elt4
        self.assertEqual(list(test.children_named('Duration')), [])
        # Custom deleter
        del test.elt6
        self.assertEqual(test.did_delete, MATROSKA_TAGS['Timecode'].ebml_id)
        # Deleting disabled
        with self.assertRaises(AttributeError):
            del test.elt7

class FilesTest(EbmlTest):
    "Test reading and writing mkv files."

    files_to_test = []

    def test_files(self):
        """Test loading the files in self.files_to_test.

        This loads the file, reads the first Segment element, and checks that
        the following level 1 elements exist: SeekHead, Info, Tracks,
        Attachments, Tags, Cues.  It then writes those elements, along with
        Chapters (if it exists), but not Cues, to a stream and compares the
        result to the input data.
        """
        from ebml.container import File

        level_ones = ("SeekHead", "Info", "Tracks", "Attachments",
                      "Tags", "Cues")

        for fname in self.files_to_test:
            print("Checking {}...".format(fname))

            with File(fname) as ebmlf:
                segment = next(ebmlf.children_named('Segment'))
                elts = {}
                # Check the important level 1 elements are defined
                for name in level_ones:
                    elts[name] = list(segment.children_named(name))
                    self.assertGreater(len(elts[name]), 0)
                # Add Chapters if it has them
                elts['Chapters'] = list(segment.children_named('Chapters'))
                del elts['Cues']

                # Write the level one elements to a stream
                for key in elts:
                    ones = elts[key]
                    for one in ones:
                        LOG.debug("Testing {!r}".format(one))
                        stream = BytesIO()
                        one.dirty = 'recurse'
                        one.write(stream, seekfirst=False)
                        self.assertEqual(stream.getvalue(),
                                         one.read_raw(ebmlf.stream))
                # Test normalize()
                segment.normalize()
                segment.check_consistency()
                self.assertEqual(len(list(segment.seek_heads)), 1)
                for elt_name in ('Info', 'Tracks', 'Attachments', 'Chapters',
                                 'Cues', 'Tags'):
                    self.assertEqual(
                        list(segment.seek_entries_byname[elt_name]),
                        [elt.pos_relative for elt in
                         segment.children_named(elt_name)])

