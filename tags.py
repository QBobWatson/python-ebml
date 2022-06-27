"""
Matroska tag processing.
"""

from collections.abc import Mapping

__all__ = ['Tag', 'TagDict', 'MATROSKA_TAGS', 'INTERNAL_ID']

class Tag:
    """Class representing a specific EBML tag.

    This class encodes all of the defining data of an EBML tag, originating from
    Matroska's specdata.xml file.  It serves mainly as an attribute dictionary
    for the tag properties, but it also keeps track of parent-child
    relationships.

    Note that many different tags will correspond to the same Element class.

    Attributes that are always defined:
     + ebml_id: The EBML ID of this tag, an integer.
     + name: The name of this tag, a string.
     + cls: The Element subclass to instantiate in self.__call__().
     + parent: The parent Tag instance.  For level-zero tags this is None, and
       for global tags it is "*".
     + mandatory: Whether this Tag must appear as a child of its parent.  Used
       in consistency checking.  This is always False if the child has a default
       value.
     + multiple: Whether this Tag may appear multiple times.  Used in
       consistency checking.
     + webm: Whether this Tag is part of webm.  Unused by this module.
     + minver, maxver: The range of versions of the Matroska EBML specification
       in which this tag appears.  Unused by this module.

    Attributes with default values:
     + header_size_min: Becomes the Element attribute of the same name.
     + data_size_min: Becomes the Element attribute of the same name.

    Attributes that are sometimes defined:
     + min_val: For numeric types, valid values are greater than this value.
       The inequality is strict for floats.
     + max_val: For numeric types, valid values are smaller than this value.
       The inequality is strict for floats.
     + default: Default value.  This may be a Tag instance, in which case it is
       a sibling tag from which to inherit the default value.
     + recursive: Whether the tag can be a child of itself.
     + values: For Enum types, a dict whose keys are integers and whose values
       are string representations of that value.  For BitField types, a list of
       strings whose ith element is the string representation of the ith bit.

    Properties:
     + required_children: Iterator for required children.
     + unique_children: Iterator for unique children.
    """
    #pylint: disable=too-many-instance-attributes

    def __init__(self, ebml_id, name, cls, parent, mandatory, multiple,
                 webm, minver, maxver, **kwargs):
        #pylint: disable=too-many-arguments
        self.ebml_id = ebml_id
        self.name = name
        self.cls = cls
        if parent is None or parent == "*":
            self.parent = parent
        else:
            self.parent = MATROSKA_TAGS[parent]
            self.parent.children.append(self)
        self._mandatory = mandatory
        self.multiple = multiple
        # Defaults
        self.header_size_min = 0
        self.data_size_min = 0
        # Unused
        self.webm = webm
        self.minver = minver
        self.maxver = maxver
        # The rest
        for name, val in kwargs.items():
            setattr(self, name, val)

        self.children = []

    @property
    def required_children(self):
        "Iterate over required children."
        return (child for child in self.children if child.mandatory)
    @property
    def unique_children(self):
        "Iterate over unique children."
        return (child for child in self.children if not child.multiple)
    @property
    def mandatory(self):
        "Override mandatory property for tags with default values."
        return False if hasattr(self, 'default') else self._mandatory

    def __eq__(self, other):
        return isinstance(other, Tag) and self.ebml_id == other.ebml_id
    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return self.ebml_id

    def __call__(self, header):
        """Create a new Element instance for this tag.

        Args:
         + header: as in Element.__init__().
        """
        return self.cls(header, name=self.name)

    def is_child(self, tag):
        "Decide if this tag is allowed to be contained in tag."
        if tag is None:
            # Level zero
            return self.parent is None or self.parent == "*"
        else:
            if self.parent == tag or self.parent == "*":
                return True
            return hasattr(self, 'recursive') and tag == self


class TagDict(Mapping):
    """Dictionary for storing Tag instances.

    This dictionary does not support __setitem__(); instead Tag instances must
    be added using insert().  They are stored under both their name and ID.

    The tags are loaded on demand to prevent circular import dependencies.
    """
    def __init__(self):
        self._dict = {}
        self._initialized = False

    def __getitem__(self, key):
        self.delayed_init()
        try:
            return self._dict[key]
        except KeyError:
            if isinstance(key, int):
                from .element import ElementUnsupported
                return Tag(key, 'Unknown', ElementUnsupported, "*",
                           False, True, True, 1, 4)
            raise

    def __len__(self):
        self.delayed_init()
        return len(self._dict)
    def __iter__(self):
        self.delayed_init()
        return iter(self._dict)
    def __contains__(self, item):
        self.delayed_init()
        return self._dict.__contains__(item)
    def keys(self):
        self.delayed_init()
        return self._dict.keys()
    def items(self):
        self.delayed_init()
        return self._dict.items()
    def values(self):
        self.delayed_init()
        return self._dict.values()
    def get(self, key, default=None):
        self.delayed_init()
        return self._dict.get(key, default)

    def insert(self, tag):
        """Store tag in self under its name and ebml_id.

        This is roughly equivalent to:
           self[tag.ebml_id] = tag
           self[tag.name] = tag

        Args:
         + tag: A Tag instance.
        Returns:
           tag
        Raises:
         + EbmlException, if tag is not an instance of Tag.
        """
        if isinstance(tag, Tag):
            self._dict[tag.ebml_id] = tag
            self._dict[tag.name] = tag
        else:
            raise ValueError("Tried to insert() a non-Tag instance {!r}"
                             .format(tag))

    def remove(self, ebml_id):
        "Remove a tag.  For testing purposes."
        tag = self._dict[ebml_id]
        del self._dict[ebml_id]
        del self._dict[tag.name]

    def level0s(self):
        "Iterate over Tag instances with parent equal to None."
        for ebml_id, val in self.items():
            if isinstance(ebml_id, int) and val.parent is None:
                yield val

    def delayed_init(self):
        "Initialize the Tags."
        #pylint: disable=too-many-statements,too-many-locals,unused-variable
        if self._initialized:
            return
        self._initialized = True

        from .tagdata import MATROSKA_TAG_DATA
        from .element import ElementUnsupported, ElementPlaceholder, \
            ElementVoid, ElementMaster, ElementMasterDefer
        from .atomic import ElementAtomic, ElementRaw, ElementUnsigned, \
            ElementSigned, ElementBoolean, ElementEnum, ElementBitField, \
            ElementFloat, ElementString, ElementUnicode, ElementDate, ElementID
        from .data_elements import ElementEBML, ElementSegment, ElementSeek, \
            ElementInfo, ElementTrackEntry, ElementVideo, ElementAudio, \
            ElementAttachedFile, ElementTag, ElementTargets, ElementSimpleTag, \
            ElementEditionEntry, ElementChapterAtom

        # For internal use
        MATROSKA_TAG_DATA.append(
            dict(ebml_id=INTERNAL_ID, name='LibInternal',
                 cls_name='ElementPlaceholder', parent='*', mandatory=False,
                 multiple=True, webm=True, minver=1, maxver=4))
        MATROSKA_TAG_DATA.append(
            dict(ebml_id=INTERNAL_ID, name='LibInternal2',
                 cls_name='ElementPlaceholder', parent='*', mandatory=False,
                 multiple=True, webm=True, minver=1, maxver=4))

        for tag_data in MATROSKA_TAG_DATA:
            cls_name = tag_data['cls_name']
            del tag_data['cls_name']
            tag_data['cls'] = locals()[cls_name]
            self.insert(Tag(**tag_data))

        # Override some automatically generated values
        self['EBML'].cls = ElementEBML
        self['Void'].cls = ElementVoid
        self['SignedElement'].cls = ElementID
        self['Segment'].cls = ElementSegment
        self['Segment'].header_size_min = 8
        self['Seek'].cls = ElementSeek
        self['SeekID'].cls = ElementID
        self['SeekPosition'].data_size_min = 8
        self['Info'].cls = ElementInfo
        self['Title'].data_size_min = 100
        self['EditionEntry'].cls = ElementEditionEntry
        self['ChapterAtom'].cls = ElementChapterAtom
        self['ChapterTranslateCodec'].cls = ElementEnum
        self['ChapterTranslateCodec'].values \
            = {0 : 'Matroska Script', 1 : 'DVD-menu'}
        self['SimpleBlock'].cls = ElementUnsupported
        self['Block'].cls = ElementUnsupported
        self['BlockVirtual'].cls = ElementUnsupported
        self['BlockAdditional'].cls = ElementUnsupported
        self['CodecState'].cls = ElementUnsupported
        self['EncryptedBlock'].cls = ElementUnsupported
        self['TrackEntry'].cls = ElementTrackEntry
        self['TrackType'].cls = ElementEnum
        self['TrackType'].values \
            = {0x1 : 'video', 0x2 : 'audio', 0x3 : 'complex', 0x10 : 'logo',
               0x11 : 'subtitle', 0x12 : 'buttons', 0x20 : 'control'}
        self['TrackTranslateCodec'].cls = ElementEnum
        self['TrackTranslateCodec'].values \
            = {0 : 'Matroska Script', 1 : 'DVD-menu'}
        self['Video'].cls = ElementVideo
        self['StereoMode'].cls = ElementEnum
        self['StereoMode'].values \
            = {0 : 'mono', 1 : 'side-by-side (left)', 2 : 'top-bottom (right)',
               3 : 'top-bottom (left)', 4 : 'checkerboard (right)',
               5 : 'checkerboard (left)', 6 : 'row interleaved (right)',
               7 : 'row interleaved (left)', 8 : 'col interleaved (right)',
               9 : 'col interleaved (left)', 10 : 'anaglyph (cyan/red)',
               11 : 'side-by-side (right)', 12 : 'anaglyph (green/magenta)',
               13 : 'both (left)', 14 : 'both (right)'}
        self['DisplayWidth'].default = self['PixelWidth']
        self['DisplayHeight'].default = self['PixelHeight']
        self['DisplayUnit'].cls = ElementEnum
        self['DisplayUnit'].values \
            = {0 : 'pixels', 1 : 'centimeters',
               2 : 'inches', 3 : 'Display Aspect Ratio'}
        self['AspectRatioType'].cls = ElementEnum
        self['AspectRatioType'].values \
            = {0 : 'free resizing', 1 : 'keep aspect ratio', 2 : 'fixed'}
        self['Audio'].cls = ElementAudio
        self['OutputSamplingFrequency'].default \
            = self['SamplingFrequency']
        self['TrackPlaneType'].cls = ElementEnum
        self['TrackPlaneType'].values \
            = {0 : 'left eye', 1 : 'right eye', 2 : 'background'}
        self['ContentEncodingScope'].cls = ElementBitField
        self['ContentEncodingScope'].values \
            = ['all-frame-contents', 'track-private-data',
               'the-next-ContentEncoding']
        self['ContentEncodingType'].cls = ElementEnum
        self['ContentEncodingType'].values \
            = {0 : 'compression', 1 : 'encryption'}
        self['ContentCompAlgo'].cls = ElementEnum
        self['ContentCompAlgo'].values \
            = {0 : 'zlib', 1 : 'bzlib', 2 : 'lzo1x', 3 : 'Header Stripping'}
        self['ContentEncAlgo'].cls = ElementEnum
        self['ContentEncAlgo'].values \
            = {0 : 'signed only', 1 : 'DES', 2 : '3DES', 3 : 'Twofish',
               4 : 'Blowfish', 5 : 'AES'}
        self['ContentSigAlgo'].cls = ElementEnum
        self['ContentSigAlgo'].values \
            = {0 : 'signed only', 1 : 'RSA'}
        self['ContentSigHashAlgo'].cls = ElementEnum
        self['ContentSigHashAlgo'].values \
            = {0 : 'signed only', 1 : 'SHA1-160', 2 : 'MD5'}
        self['Cues'].cls = ElementMasterDefer
        self['Attachments'].header_size_min = 4
        self['AttachedFile'].cls = ElementAttachedFile
        self['AttachedFile'].header_size_min = 4
        self['FileUID'].cls = ElementRaw
        self['Tag'].cls = ElementTag
        self['Targets'].cls = ElementTargets
        self['SimpleTag'].cls = ElementSimpleTag


# This dictionary contains the tags that the parser recognizes.  The tags are
# Tag instances and the keys are the tag IDs and names.
MATROSKA_TAGS = TagDict()

INTERNAL_ID = 66
