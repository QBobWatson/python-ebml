#pylint: disable=too-many-locals,no-self-use
#pylint: disable=too-many-public-methods,too-many-statements
"""
Atomic element tests.
"""

from io import BytesIO
import datetime, random

from .test import EbmlTest, UNK_ID

__all__ = ['AtomicTest']


class AtomicTest(EbmlTest):
    "Test atomic module."

    def test_atomic(self):
        """Test atomic elements.

        The atomic elements are Element- Raw, Signed, Unsigned, Boolean,
        Enum, BitField, Float, String, Unicode, Date, and ID.

        This tests reading, setting, and writing these elements.  All sample
        data comes from actual MKV files.
        """
        #pylint: disable=too-many-locals

        from ebml.container import File
        from ebml.atomic import ElementRaw, ElementUnsigned, \
            ElementBoolean, ElementEnum, ElementBitField, \
            ElementFloat, ElementString, ElementUnicode, \
            ElementDate, ElementID

        # Currently doesn't have a real-world example of a Signed element,
        # excepting the Date element.

        # Info element.
        # Contains Unsigned, Unicode, Float, Date, and Raw elements.
        ebmlf = self.read_file_data()

        # Test writing
        stream2 = BytesIO()
        ebmlf.force_dirty()
        ebmlf.write(stream2)
        self.assertEqual(stream2.getvalue(), self.file_data)

        infoelt = self.info_elt(ebmlf)

        # Test reading
        self.assertEqual(infoelt.name, 'Info')
        self.assertEqual(len(ebmlf), 2)
        self.assertEqual(len(infoelt), 7)
        self.element_is(infoelt[0], 'TimecodeScale', 1000000)
        self.element_is(infoelt[1], 'MuxingApp',
                        'libebml v1.3.0 + libmatroska v1.4.1')
        self.element_is(infoelt[2], 'WritingApp',
                        "mkvmerge v6.8.0 ('Theme for Great Cities')" \
                        " 64bit built on Mar  3 2014 16:19:32")
        self.element_is(infoelt[3], 'Duration', 9425504.0)
        self.element_is(infoelt[4], 'DateUTC',
                        datetime.datetime(2014, 4, 20, 2, 3, 14))
        self.element_is(infoelt[5], 'Title',
                        'Harry Potter 4: The Goblet of Fire')
        self.element_is(infoelt[6], 'SegmentUID',
                        b'\xb0WRGrIO#{;\x88\xb0\x0e\x06\xaaK')

        # Test assigning without changing size
        oldsizes = [elt.total_size for elt in infoelt]
        infoelt[0].value = random.randrange(1000000)
        infoelt[1].value = 'libebml SAME LENGTH DIFFERENT STR.1'
        infoelt[3].value = 12345.0
        infoelt[4].value = datetime.datetime(1914, 2, 21, 1, 2, 3) # negative
        infoelt[6].value = bytes([random.randrange(256) for i in range(16)])
        newvals = [elt.value for elt in infoelt]
        for i in range(len(oldsizes)):
            self.assertEqual(infoelt[i].total_size, oldsizes[i])

        stream2 = BytesIO()
        infoelt.force_dirty()
        infoelt.write(stream2, seekfirst=False)
        stream2.seek(0)
        ebmlf2 = File(stream2)
        ebmlf2.read_all()
        infoelt2 = ebmlf2[0]
        self.assertTrue(infoelt.intrinsic_equal(infoelt2))
        for i in range(len(infoelt)):
            self.assertEqual(infoelt[i].name, infoelt2[i].name)
            self.assertEqual(newvals[i], infoelt2[i].value)

        # Test assigning
        elt = infoelt[0] # Unsigned
        elt.value = 1 << 63
        self.assertEqual(elt.value, 1 << 63)
        self.assertEqual(elt.size, 8)
        with self.assertRaises(ValueError):
            elt.value = 1<<64 # too big
        with self.assertRaises(ValueError):
            elt.value = 3.0 # wrong type

        elt = infoelt[1] # Unicode
        oldlen = len(elt.value)
        elt.value = "abc"
        self.assertEqual(elt.value, "abc")
        self.assertEqual(elt.size, oldlen)
        with self.assertRaises(ValueError):
            elt.value = 20 # wrong type

        elt = infoelt[3] # Float
        elt.value = 123.456
        self.assertEqual(elt.value, 123.456)
        self.assertEqual(elt.size, 4)
        elt.resize(8)
        elt.value = 456
        self.assertEqual(elt.value, 456.0)
        self.assertEqual(elt.size, 8)
        with self.assertRaises(ValueError):
            elt.value = b'123' # Wrong type

        elt = infoelt[4]
        elt.value = datetime.datetime(1981, 2, 21, 3, 2, 1)
        self.assertEqual(elt.value, datetime.datetime(1981, 2, 21, 3, 2, 1))
        self.assertEqual(elt.size, 8)
        with self.assertRaises(ValueError):
            elt.value = 123 # Wrong type

        elt = infoelt[6] # Raw
        elt.value = b'123'
        self.assertEqual(elt.value, b'123')
        self.assertEqual(elt.size, 3)
        with self.assertRaises(ValueError):
            elt.value = "123" # Wrong type

        # TrackEntry element.
        # Contains Unsigned, Enum, Boolean, String, and Bitfield
        # elements.
        ebmlf = self.read_file_data()
        elts = self.track_entry_elt(ebmlf)

        # Test reading
        self.assertEqual(elts.name, 'TrackEntry')
        self.assertEqual(len(elts), 12)
        self.element_is(elts[0], 'TrackNumber', 4)
        self.element_is(elts[1], 'TrackUID', 4)
        self.element_is(elts[2], 'TrackType', 17) # enum
        self.assertEqual(elts[2].string_val, 'subtitle')
        self.element_is(elts[3], 'FlagDefault', 0)
        self.element_is(elts[4], 'FlagLacing', 0)
        self.element_is(elts[5], 'CodecID', 'S_HDMV/PGS') # string
        self.assertEqual(elts[6].name, 'ContentEncodings')
        self.assertEqual(len(elts[6]), 1)
        eltss = elts[6]
        self.assertEqual(eltss[0].name, 'ContentEncoding')
        self.assertEqual(len(eltss[0]), 4)
        eltsss = eltss[0]
        self.assertEqual(eltsss[0].name, 'ContentCompression')
        self.assertEqual(len(eltsss[0]), 1)
        self.element_is(eltsss[0][0], 'ContentCompAlgo', 0) # enum
        self.element_is(eltsss[1], 'ContentEncodingOrder', 0)
        self.element_is(eltsss[2], 'ContentEncodingScope', 1) # BitField
        self.element_is(eltsss[3], 'ContentEncodingType', 0) # enum

        # Test assigning without changing size
        to_test = [elts[2], elts[4], elts[5], eltsss[0][0], eltsss[2]]
        oldsizes = [elt.total_size for elt in to_test]
        elts[2].value = 'audio'
        self.assertEqual(elts[2].value, 2)
        elts[4].value = 1
        elts[5].value = 'abc' # pads with zeros
        eltsss[0][0].value = 1
        self.assertEqual(eltsss[0][0].string_val, 'bzlib')
        eltsss[2].value = 0b101
        newvals = [elt.value for elt in to_test]
        for i in range(len(oldsizes)):
            self.assertEqual(to_test[i].total_size, oldsizes[i])

        stream2 = BytesIO()
        elts.force_dirty()
        elts.write(stream2, seekfirst=False)
        stream2.seek(0)
        ebmlf2 = File(stream2)
        ebmlf2.read_all()
        elts2 = ebmlf2[0]
        self.assertTrue(elts.intrinsic_equal(elts2))
        newelts = [elts2[2], elts2[4], elts2[5], elts2[6][0][0][0],
                   elts[6][0][2]]
        for i in range(len(to_test)):
            self.assertEqual(to_test[i].name, newelts[i].name)
            self.assertEqual(newvals[i], newelts[i].value)

        # Test assigning
        elt = elts[2] # Enum
        elt.value = 215
        self.assertEqual(elt.string_val, "UNKNOWN")
        self.assertEqual(elt.value, 215)
        self.assertEqual(elt.size, 1)
        elt.value = 2
        self.assertEqual(elt.string_val, "audio")
        elt.value = 'video'
        self.assertEqual(elt.value, 1)
        with self.assertRaises(ValueError):
            elt.value = 'invalid'

        elt = elts[4] # Boolean
        elt.value = True
        self.assertEqual(elt.value, 1)
        elt.value = False
        self.assertEqual(elt.value, 0)
        self.assertEqual(elt.size, 1)
        # Comparison
        elts[3].value = True
        elts[4].value = 1
        self.assertFalse(elts[3].intrinsic_equal(elts[4])) # different id
        elts2[3].value = 10
        self.assertTrue(elts[3].intrinsic_equal(elts2[3]))

        elt = elts[5] # String
        elt.value = "01234567890123456789"
        self.assertEqual(elt.value, "01234567890123456789")
        self.assertEqual(elt.size, 20)
        with self.assertRaises(ValueError):
            elt.value = 20 # wrong type

        elt = eltsss[2] # BitField
        elt.value = 0b101
        self.assertEqual(elt.string_val,
                         'all-frame-contents, the-next-ContentEncoding')
        self.assertEqual(elt.size, 1)
        with self.assertRaises(ValueError):
            elt.value = 1.0 # wrong type


        # Seek element.
        # Contains Unsigned and ID elements.
        ebmlf = self.read_file_data()
        seek = self.seek_elt(ebmlf)

        # Test reading
        self.assertEqual(seek.name, 'Seek')
        self.assertEqual(len(seek), 2)
        self.element_is(seek[0], 'SeekID', 0x014d9b74)
        self.element_is(seek[1], 'SeekPosition', 10513)

        # Test assigning without changing size
        oldsize = seek[0].total_size
        seek[0].value = 0x0F43B675
        self.assertEqual(seek[0].total_size, oldsize)

        stream2 = BytesIO()
        seek.force_dirty()
        seek.write(stream2, seekfirst=False)
        stream2.seek(0)
        ebmlf2 = File(stream2)
        ebmlf2.read_all()
        seek2 = ebmlf2[0]
        self.assertTrue(seek.intrinsic_equal(seek2))
        self.assertEqual(seek2[0].name, seek[0].name)
        self.assertEqual(seek2[0].value, seek[0].value)

        # Test assigning
        elt = seek[0]
        elt.value = 0x43A770
        self.assertEqual(elt.raw, bytes([0x10, 0x43, 0xA7, 0x70]))
        self.assertEqual(elt.string_name, 'Chapters')
        self.assertEqual(elt.size, 4)
        elt.value = 0x05BD
        self.assertEqual(elt.raw, bytes([0x45, 0xBD]))
        self.assertEqual(elt.string_name, 'EditionFlagHidden')
        self.assertEqual(elt.size, 2)
        elt.value = 0x01223344
        self.assertEqual(elt.string_name, 'Unknown')
        with self.assertRaises(ValueError):
            elt.value = 0x1122334455 # Too large

        # Test new_with_value
        # Raw
        elt = ElementRaw.new_with_value(UNK_ID)
        self.assertEqual(elt.size, 0)
        self.assertEqual(elt.value, b'')
        elt = ElementRaw.new_with_value(UNK_ID, b'123')
        self.assertEqual(elt.size, 3)
        self.assertEqual(elt.value, b'123')
        # Hashing of value signature
        elt = ElementRaw.new_with_value(
            UNK_ID, bytes([random.randrange(256) for i in range(2048)]))
        self.assertIsInstance(elt.value_signature(elt.value), tuple)
        self.assertEqual(elt.value_signature(elt.value),
                         elt.value_signature(elt.value))
        # Unsigned
        elt2 = elt = ElementUnsigned.new_with_value(UNK_ID)
        self.assertEqual(elt.size, 4)
        self.assertEqual(elt.value, 0)
        elt = ElementUnsigned.new_with_value(UNK_ID, 0x1122334455)
        self.assertEqual(elt.size, 5)
        self.assertEqual(elt.value, 0x1122334455)
        self.assertFalse(elt.intrinsic_equal(elt2))
        # Signed: no new methods
        # Boolean
        elt = ElementBoolean.new_with_value(UNK_ID)
        self.assertEqual(elt.size, 1)
        self.assertEqual(elt.value, False)
        elt.value = 100
        elt2 = elt
        elt = ElementBoolean.new_with_value(UNK_ID, True)
        self.assertEqual(elt.size, 1)
        self.assertEqual(elt.value, True)
        self.assertTrue(elt.intrinsic_equal(elt2))
        # Enum
        elt = ElementEnum.new_with_value('ContentEncodingType')
        self.assertEqual(elt.size, 1)
        self.assertEqual(elt.value, 0)
        self.assertEqual(elt.string_val, 'compression')
        elt = ElementEnum.new_with_value('ContentEncodingType',
                                         'encryption')
        self.assertEqual(elt.size, 1)
        self.assertEqual(elt.value, 1)
        self.assertEqual(elt.string_val, 'encryption')
        # BitField
        elt = ElementBitField.new_with_value('ContentEncodingScope')
        self.assertEqual(elt.size, 4)
        self.assertEqual(elt.value, 0)
        self.assertEqual(elt.string_val, '[empty]')
        elt = ElementBitField.new_with_value('ContentEncodingScope', 0x1122)
        self.assertEqual(elt.size, 4)
        self.assertEqual(elt.value, 0x1122)
        self.assertEqual(elt.string_val, 'track-private-data')
        # Float
        elt = ElementFloat.new_with_value(UNK_ID)
        self.assertEqual(elt.size, 4)
        self.assertEqual(elt.value, 0.0)
        elt = ElementFloat.new_with_value(UNK_ID, 1.1)
        elt.resize(8)
        self.assertEqual(elt.size, 8)
        self.assertEqual(elt.value, 1.1)
        # String
        elt = ElementString.new_with_value(UNK_ID)
        self.assertEqual(elt.size, 0)
        self.assertEqual(elt.value, '')
        elt = ElementString.new_with_value(UNK_ID, 'test')
        self.assertEqual(elt.size, 4)
        self.assertEqual(elt.value, 'test')
        # Unicode
        elt = ElementUnicode.new_with_value(UNK_ID, 'étale')
        self.assertEqual(elt.size, 6) # 6 bytes encoded
        self.assertEqual(elt.value, 'étale')
        # Date
        elt = ElementDate.new_with_value(UNK_ID)
        self.assertEqual(elt.size, 8)
        self.assertEqual(elt.value, ElementDate.epoch)
        elt = ElementDate.new_with_value(
            UNK_ID, datetime.datetime(1981, 2, 21, 3, 2, 1))
        self.assertEqual(elt.size, 8)
        self.assertEqual(elt.value, datetime.datetime(1981, 2, 21, 3, 2, 1))
        # ID
        elt = ElementID.new_with_value(UNK_ID)
        self.assertEqual(elt.size, 1)
        self.assertEqual(elt.value, 0)
        self.assertEqual(elt.raw, bytes([1<<7]))
        self.assertEqual(elt.string_name, 'ChapterDisplay')
        elt = ElementID.new_with_value(UNK_ID, 0x0254C367)
        self.assertEqual(elt.size, 4)
        self.assertEqual(elt.value, 0x0254C367)
        self.assertEqual(elt.raw, bytes([0x12, 0x54, 0xC3, 0x67]))
        self.assertEqual(elt.string_name, 'Tags')
        elt = ElementID.new_with_value(UNK_ID, 0x01223344)
        self.assertEqual(elt.size, 4)
        self.assertEqual(elt.value, 0x01223344)
        self.assertEqual(elt.string_name, 'Unknown')
