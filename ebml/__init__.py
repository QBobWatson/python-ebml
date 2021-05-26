"""
Module to parse a Matroska EBML file.

* Overview

An EBML file is a sequence of EBML Elements one after another.  An Element
consists of a two-part header encoding the Element ID and its data size,
followed by that many bytes of data.  The Matroska specification defines some
number of EBML IDs, which can be found in a Matroska project file called
specdata.xml.  Each defined ID has a human-readable name, e.g. 'Segment'.  The
semantics of the data depends on the Element type.  EBML defines the following
primitive Element types:

 + Master: the data is a sequence of child Elements.
 + Unsigned, Signed: the data is an integer in big-endian form.
 + String, Unicode: the data is a string encoded in ascii or utf-8.
 + Float: the data is a 4-byte or 8-byte floating point number.
 + Date: the data is an 8-byte signed integer representing the number of
   nanoseconds since the Matroska epoch.
 + Binary: the data is opaque.

The Matroska EBML Element specifications are stored in a special-purpose
dictionary called MATROSKA_TAGS which is used to create Elements of the
appropriate class when reading them from a stream.

This module defines the following classes for reading, storing, editing, and
writing the data in a Matroska file.

 + Header: stores and manipulates the Element header.
 + Container: stores child Elements.  This is subclassed by ElementMaster and
   File.  As File is not an Element -- it has no header -- neither is Container.
 + File: facilitates reading and writing Elements from a stream.
 + Element: base class for all EBML Elements.

Immediate subclasses of Element:

 + ElementMaster: Inherits both Element and Container.
 + ElementAtomic: Base class for all kinds of Elements that actually know how to
   interpret their data.  Subclassed by ElementUnsigned, ElementUnicode, etc.
 + ElementVoid: Element that ignores its data on read and writes undefined
   values.
 + ElementUnsupported: An element this module does not support.  It cannot be
   resized or written.

This module provides the Parsed descriptor, which is a convenience class that
allows Master Elements to read and write the data in child Elements using
attributes.  For instance, the ElementInfo class has the segment_uid attribute;
if info is an instance of ElementInfo then info.segment_uid reads and writes the
value of its child SegmentUID.  If no such child exists, reading
info.segment_uid returns a default value, and setting it creates the child.
This is much easier to use than, say,

  uid_elements = list(info.children_named('SegmentUID'))
  if uid_elements:
      return uid_elements[-1].value
  else
      return default_value

The ElementSegment class takes advantage of Parsed descriptors to give easy
access to the segment metadata.  Classes using this facility: ElementEBML,
ElementSegment, ElementSeek, ElementInfo, ElementTrackEntry, ElementVideo,
ElementAudio, ElementAttachedFile, etc.

* Reading

The Container.read() method reads a list of children.  It calls
Container.read_element() for each child, which checks if the Element is already
loaded; if so, it returns that Element, and otherwise it reads the header and
creates the appropriate Element instance.  It then calls Element.read_data(),
which for Master Elements will recursively call Container.read(), and for Atomic
Elements will read, decode, and store its data.  A Void Element will skip over
its data.

The Container.read() method supports a summary option, which causes it to call
Element.read_summary() instead of read_data().  The purpose of summary mode is
for large master Elements to read their metadata without reading the entire
Element, which may not even fit in memory.  Currently the Elements implementing
read_summary() are ElementMasterDefer and ElementSegment.  The former simply
skips reading its children in summary mode, and the latter intelligently finds
its metadata using SeekHead entries without reading its Cluster entries, which
generally comprise over 99% of the file.  For the other Elements, read_summary()
simply calls read_data().

An Element stores its state of loadedness in the read_state attribute.
Container.read_element() will in fact read a partially loaded Element when not
in summary mode.

File implements the read_summary() method, which calls read_summary() on each
top-level child.  By default, the constructor of File runs read_summary().

* Writing

This module supports in-place modification of Matroska EBML files.  In theory it
supports creating such files from scratch, except that it has no facility for
creating EBML Header elements (beyond doing so "by hand") or for writing
elements incrementally (so any data to be written must be stored in memory).
The system for in-place modifications is described here.

When modifying potentially very large EBML files, it is important only to write
the elements that have actually changed.  The following are the ways in which an
Element may differ from its state in a stream:

 1. Its position in the stream can be changed.
 2. It can be resized.
 3. Its value can be changed.
 4. Child elements can be added, deleted, or moved.
 5. It can be created programatically.

The Element.dirty property is True if any of the above conditions holds.  It is
calculated as follows.  An Element stores the position in the stream at which it
was read along with its original size, so that it knows if either has changed.
An ElementAtomic also stores its original value (or a way of recognizing its
original value).  An ElementMaster recursively checks if any of its children is
dirty.  An element not read from a stream has no stored position or size, so it
is always dirty.

The Container.write() method writes its children to a stream.  It only writes
children for which the dirty property is True.  For each such child it calls the
Element's write() method.  Master elements will recursively call the container's
write() method, and Atomic elements will encode and write their data.  A Void
Element just seeks the stream.  An Atomic Element which is not dirty should
reproduce the byte stream used to read it when write() is called.

Performing modifications may place a Container (e.g. a Master element) in an
inconsistent state.  For example, a child element might grow, so that its data
overlaps the beginning of the next element, or a child might be deleted, which
leaves empty space.  A Container's state is said to be consistent if the
following hold:

 1. The first element starts at relative position zero.
 2. Element i+1 starts immediately after element i ends.
 3. The container's children are allowed children by the Matroska specification.
 4. Required children (as defined by the Matroska specification) are present.
 5. Children that are required to be unique by the Matroska specification are in
    fact unique.
 6. Every child container is consistent.
 7. The values of non-container children are consistent with the Matroksa
    specification (e.g. are contained in a specified range of values).

If a Container is an Element, it must satisfy the following properties in
addition:

 8. The end of the last child coincides with the end of the Element's data.
 9. Its parent is not None.

A Container will generally refuse to write its contents to disk if it is in an
inconsistent state.  To facilitate putting the Container in a consistent state,
it provides the rearrange() method, which should be called before write().  This
method rearranges the Container's children, potentially shrinking and moving
them, so that there are no overlaps, recursively calling rearrange() on each
Master child.  It deletes and creates Void elements as necessary, and supports
several options for controlling its behavior.  The Container may be in an
inconsistent state after calling rearrange() if its contents violate the
Matroska specification in some way (e.g. if it has an impermissible child).

The Segment Element is more intelligent in its rearrange() method.  It generates
a SeekHead element at the beginning of the file with links to its children.  It
tries to move the more important children before the Clusters, and moves the
rest to the end of the file.  Its requirements for consistency are also a bit
more specific than the ones outlined above.

* Viewing

Each Element implements __repr__() and __str__().  The former returns the class
name and some size information, whereas the latter also includes some
information about the contents of the Element.  The return value of each should
fit on one line.

Element instances also implement the summary() method, which returns a summary
of the Element contents.  By default, summary() returns the output of __str__().
The output may span multiple lines, although it is not terminated by a newline.

Container instances implement two additional methods, print_children() and
print_space().  The former recursively runs __str__() on all child Elements (up
to a specified recursion depth) and concatenates them with indentation in a
newline-terminated string.  The latter returns a newline-terminated table
summarizing which child (and descendent) elements occupy which blocks of space.
"""

__all__ = ['EbmlException', 'Inconsistent', 'DecodeError', 'MAX_DATA_SIZE']

################################################################################
# * Exception

class EbmlException(Exception):
    """Class for general EBML exceptions."""

class Inconsistent(EbmlException):
    """Raised when a Container is not in a consistent state."""

class DecodeError(EbmlException):
    """Class for EBML decoding errors."""


################################################################################
# * Constants

# Maximum data size that EBML can encode
MAX_DATA_SIZE = (1<<56) - 2
