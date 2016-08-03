python-ebml
===========

Module to parse a Matroska EBML file.

**This module is not packaged for public distribution.**  The code is well-documented
and usable, however, so I decided to make it available in its current state in case
anyone finds it useful.  If you are interested in making an honest package out of
this code, contact me and I can help maintain it.  Or if you prefer, just clone the
repository and do all the work yourself.

## Overview

An EBML file is a sequence of EBML Elements, one after another.  An Element
consists of a two-part header encoding the Element ID and its data size,
followed by that many bytes of data.  The Matroska specification defines some
number of EBML IDs, which can be found in a Matroska project file called
specdata.xml.  Each defined ID has a human-readable name, e.g. 'Segment'.  The
semantics of the data depend on the Element type.  EBML defines the following
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
 + `Header`: stores and manipulates the Element header.
 + `Container`: stores child Elements.  This is subclassed by `ElementMaster` and
   `File`.  As `File` is not an `Element` (it has no header) neither is `Container`.
 + `File`: facilitates reading and writing Elements from a stream.
 + `Element`: base class for all EBML Elements.
 
Immediate subclasses of Element:
 + `ElementMaster`: Inherits both `Element` and `Container`.
 + `ElementAtomic`: Base class for all kinds of Elements that actually know how to
   interpret their data.  Subclassed by `ElementUnsigned`, `ElementUnicode`, etc.
 + `ElementVoid`: Element that ignores its data on read and writes undefined
   values.
 + `ElementUnsupported`: An element this module does not support.  It cannot be
   resized or written.
   
This module provides the `Parsed` descriptor, which is a convenience class that
allows Master Elements to read and write the data in child Elements using
attributes.  For instance, the `ElementInfo` class has the `segment_uid` attribute;
if `info` is an instance of `ElementInfo` then `info.segment_uid` reads and writes the
value of its child `SegmentUID`.  If no such child exists, reading
`info.segment_uid` returns a default value, and setting it creates the child.
This is much easier to use than, say,
```python
uid_elements = list(info.children_named('SegmentUID'))
if uid_elements:
    return uid_elements[-1].value
else
    return default_value
```
The `ElementSegment` class takes advantage of `Parsed` descriptors to give easy
access to the segment metadata.  Classes using this facility: `ElementEBML`,
`ElementSegment`, `ElementSeek`, `ElementInfo`, `ElementTrackEntry`, `ElementVideo`,
`ElementAudio`, `ElementAttachedFile`, etc.

## Reading

The `Container.read()` method reads a list of children.  It calls
`Container.read_element()` for each child, which checks if the `Element` is already
loaded; if so, it returns that `Element`, and otherwise it reads the header and
creates the appropriate `Element` instance.  It then calls `Element.read_data()`,
which for `Master` Elements will recursively call `Container.read()`, and for `Atomic`
Elements will read, decode, and store its data.  A `Void` Element will skip over
its data.

The `Container.read()` method supports a summary option, which causes it to call
`Element.read_summary()` instead of `read_data()`.  The purpose of summary mode is
for large master Elements to read their metadata without reading the entire
Element, which may not even fit in memory.  Currently the Elements implementing
`read_summary()` are `ElementMasterDefer` and `ElementSegment`.  The former simply
skips reading its children in summary mode, and the latter intelligently finds
its metadata using `SeekHead` entries without reading its `Cluster` entries, which
generally comprise over 99% of the file.  For the other Elements, `read_summary()`
simply calls `read_data()`.

An Element stores its state of loadedness in the `read_state` attribute.
`Container.read_element()` will in fact read a partially loaded `Element` when not
in summary mode.

`File` implements the `read_summary()` method, which calls `read_summary()` on each
top-level child.  By default, the constructor of `File` runs `read_summary()`.

## Writing

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
 
The `Element.dirty` property is `True` if any of the above conditions holds.  It is
calculated as follows.  An `Element` stores the position in the stream at which it
was read along with its original size, so that it knows if either has changed.
An `ElementAtomic` also stores its original value (or a way of recognizing its
original value).  An `ElementMaster` recursively checks if any of its children is
dirty.  An element not read from a stream has no stored position or size, so it
is always dirty.

The `Container.write()` method writes its children to a stream.  It only writes
children for which the `dirty` property is `True`.  For each such child it calls the
Element's `write()` method.  Master elements will recursively call the container's
`write()` method, and `Atomic` elements will encode and write their data.  A `Void`
Element just seeks the stream.  An `Atomic` Element which is not dirty should
reproduce the byte stream used to read it when `write()` is called.
Performing modifications may place a `Container` (e.g. a Master element) in an
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
    
If a `Container` is an `Element`, it must satisfy the following properties in
addition:
 8. The end of the last child coincides with the end of the Element's data.
 9. Its parent is not `None`.
 
A `Container` will generally refuse to write its contents to disk if it is in an
inconsistent state.  To facilitate putting the `Container` in a consistent state,
it provides the `rearrange()` method, which should be called before `write()`.  This
method rearranges the Container's children, potentially shrinking and moving
them, so that there are no overlaps, recursively calling `rearrange()` on each
Master child.  It deletes and creates `Void` elements as necessary, and supports
several options for controlling its behavior.  The `Container` may be in an
inconsistent state after calling `rearrange()` if its contents violate the
Matroska specification in some way (e.g. if it has an impermissible child).

The `Segment` Element has a more intelligent `normalize()` method.  It generates
a `SeekHead` element at the beginning of the file with links to its children.  It
tries to move the more important children before the `Clusters`, and moves the
rest to the end of the file.  Its requirements for consistency are also a bit
more specific than the ones outlined above.

## Viewing

Each `Element` implements `__repr__()` and `__str__()`.  The former returns the class
name and some size information, whereas the latter also includes some
information about the contents of the `Element`.  The return value of each should
fit on one line.

`Element` instances also implement the `summary()` method, which returns a summary
of the `Element` contents.  By default, `summary()` returns the output of `__str__()`.
The output may span multiple lines, although it is not terminated by a newline.
`Container` instances implement two additional methods, `print_children()` and
`print_space()`.  The former recursively runs `__str__()` on all child Elements (up
to a specified recursion depth) and concatenates them with indentation in a
newline-terminated string.  The latter returns a newline-terminated table
summarizing which child (and descendent) elements occupy which blocks of space.

## Example

Load a Matroska file:
```python
from ebml.container import File
ebml_file = File('The_Blues_Brothers.mkv')
```

Output:
```
INFO:ebml.container:Read summary in 0.084 seconds
```

```python
print(ebml_file.summary())
```

Output:
```
File: stream=<_io.BufferedReader name='The_Blues_Brothers.mkv'>, size=27147770837, 2 children
ElementSegment Segment (12+27147770785 @40): 11 children
    Segment UID: CE:C4:57:4C:E0:1E:AD:7C:14:D7:2C:84:44:B4:8E:50
    Title:       'The Blues Brothers'
    Duration:    8866.94 seconds
    Time scale:  1000000 nanoseconds
    Muxing app:  'libmakemkv v1.8.9 (1.3.0/1.4.1) x86_64-linux-gnu'
    Writing app: 'MakeMKV v1.8.9 linux(x64-release)'
    Seek entries:
        Chapters:     1907
        Cues:         27147145828
        Info:         2944
        Tags:         27147331697
        Attachments:  27147336885
        Tracks:       1292
    Attachments:
        ElementAttachedFile: 'myth_metadata.xml' (application/xml), 21232 bytes: 'Master XML metadata'
            UID: 34:4B:C9:07:67:3D:6B:E5
        ElementAttachedFile: 'cover.jpg' (image/jpeg), 200376 bytes: 'Cover image'
            UID: 7C:F7:FC:C9:FF:1F:F1:AD
        ElementAttachedFile: 'fanart.jpg' (image/jpeg), 212080 bytes: 'Fan art image'
            UID: E9:EF:E2:31:8C:12:E3:49
    Tracks:
        ElementTrackEntry: video lang=eng codec=V_MPEG4/ISO/AVC num=1 uid=1
            Flags: enabled default !forced !lacing
            ElementVideo: dims=1920x1080, display=1920x1080, aspect='free resizing'
                Stereo:     mono
                Interlaced: False
        ElementTrackEntry: audio lang=eng codec=A_DTS num=2 uid=2: 'Surround 5.1'
            Flags: enabled default !forced lacing
            ElementAudio: channels=6 sampling=48k
        ElementTrackEntry: audio lang=fra codec=A_DTS num=3 uid=3: 'Stereo'
            Flags: enabled !default !forced lacing
            ElementAudio: channels=2 sampling=48k
        ElementTrackEntry: subtitle lang=eng codec=S_HDMV/PGS num=4 uid=4
            Flags: enabled default !forced !lacing
        ElementTrackEntry: subtitle lang=spa codec=S_HDMV/PGS num=6 uid=6
            Flags: enabled !default !forced !lacing
        ElementTrackEntry: subtitle lang=fra codec=S_HDMV/PGS num=8 uid=8
            Flags: enabled !default !forced !lacing
        ElementTrackEntry: subtitle lang=fra codec=S_HDMV/PGS num=10 uid=10
            Flags: enabled !default forced !lacing
    Tags:
        ElementTag: MOVIE (50), 67 tags
            ElementSimpleTag lang=eng def=True: 'TITLE' => 'The Blues Brothers'
            ElementSimpleTag lang=eng def=True: 'DIRECTOR' => 'John Landis'
            ElementSimpleTag lang=eng def=True: 'GENRE' => 'Comedy'
            ElementSimpleTag lang=eng def=True: 'ACTOR' => 'Dan Aykroyd'
                ElementSimpleTag lang=eng def=True: 'CHARACTER' => 'Elwood Blues (as Elwood)'
            ElementSimpleTag lang=eng def=True: 'ACTOR' => 'John Belushi'
                ElementSimpleTag lang=eng def=True: 'CHARACTER' => "'Joliet' Jake Blues (as Jake)"
            ...
```

Get the main segment of the file:
```python
segment = next(ebml_file.children_named('Segment'))
segment
```

Output (`__repr__()` version):
```
<ElementSegment [18:53:80:67] 'Segment' size=12+27147770785 @40>
```

```python
str(segment)
```

output (`__str__()` version):
```
'ElementSegment Segment (12+27147770785 @40): 11 children'
```

Add an attached file with the `Segment.add_attachment()` convenience function.
```python
with open('banner.jpg', 'rb') as f:
    banner_contents = f.read()
attachment = segment.add_attachment('banner.jpg', 'image/jpeg', 'Banner image')
attachment.file_data = banner_contents
attachment.summary()
```

Output:
```
"ElementAttachedFile: 'banner.jpg' (image/jpeg), 104464 bytes: 'Banner image'\n    UID: 07:10:12:34:11:A3:F1:43"
```

```python
print(ebml_file.summary())
```

Output (note that it lists the new attachment):
```
File: stream=<_io.BufferedReader name='The_Blues_Brothers.mkv'>, size=27147770837, 2 children
ElementSegment Segment (12+27147770785 @40): 11 children
    Segment UID: CE:C4:57:4C:E0:1E:AD:7C:14:D7:2C:84:44:B4:8E:50
    Title:       'The Blues Brothers'
    Duration:    8866.94 seconds
    Time scale:  1000000 nanoseconds
    Muxing app:  'libmakemkv v1.8.9 (1.3.0/1.4.1) x86_64-linux-gnu'
    Writing app: 'MakeMKV v1.8.9 linux(x64-release)'
    Seek entries:
        Chapters:     1907
        Cues:         27147145828
        Info:         2944
        Tags:         27147331697
        Attachments:  27147336885
        Tracks:       1292
    Attachments:
        ElementAttachedFile: 'myth_metadata.xml' (application/xml), 21232 bytes: 'Master XML metadata'
            UID: 34:4B:C9:07:67:3D:6B:E5
        ElementAttachedFile: 'cover.jpg' (image/jpeg), 200376 bytes: 'Cover image'
            UID: 7C:F7:FC:C9:FF:1F:F1:AD
        ElementAttachedFile: 'fanart.jpg' (image/jpeg), 212080 bytes: 'Fan art image'
            UID: E9:EF:E2:31:8C:12:E3:49
        ElementAttachedFile: 'banner.jpg' (image/jpeg), 104464 bytes: 'Banner image'
            UID: 07:10:12:34:11:A3:F1:43
    Tracks:
        ElementTrackEntry: video lang=eng codec=V_MPEG4/ISO/AVC num=1 uid=1
            Flags: enabled default !forced !lacing
            ElementVideo: dims=1920x1080, display=1920x1080, aspect='free resizing'
                Stereo:     mono
                Interlaced: False
        ElementTrackEntry: audio lang=eng codec=A_DTS num=2 uid=2: 'Surround 5.1'
            Flags: enabled default !forced lacing
            ElementAudio: channels=6 sampling=48k
        ElementTrackEntry: audio lang=fra codec=A_DTS num=3 uid=3: 'Stereo'
            Flags: enabled !default !forced lacing
            ElementAudio: channels=2 sampling=48k
        ElementTrackEntry: subtitle lang=eng codec=S_HDMV/PGS num=4 uid=4
            Flags: enabled default !forced !lacing
        ElementTrackEntry: subtitle lang=spa codec=S_HDMV/PGS num=6 uid=6
            Flags: enabled !default !forced !lacing
        ElementTrackEntry: subtitle lang=fra codec=S_HDMV/PGS num=8 uid=8
            Flags: enabled !default !forced !lacing
        ElementTrackEntry: subtitle lang=fra codec=S_HDMV/PGS num=10 uid=10
            Flags: enabled !default forced !lacing
    Tags:
        ElementTag: MOVIE (50), 67 tags
            ElementSimpleTag lang=eng def=True: 'TITLE' => 'The Blues Brothers'
            ElementSimpleTag lang=eng def=True: 'DIRECTOR' => 'John Landis'
            ElementSimpleTag lang=eng def=True: 'GENRE' => 'Comedy'
            ElementSimpleTag lang=eng def=True: 'ACTOR' => 'Dan Aykroyd'
                ElementSimpleTag lang=eng def=True: 'CHARACTER' => 'Elwood Blues (as Elwood)'
            ElementSimpleTag lang=eng def=True: 'ACTOR' => 'John Belushi'
                ElementSimpleTag lang=eng def=True: 'CHARACTER' => "'Joliet' Jake Blues (as Jake)"
            ...
```

Where did the attachment go?  Here's how the segment tracks its space:
```python
print(segment.print_space())
```

Output:
```
1> 0          --131         | 0          --131         |         131 bytes: [ 0] SeekHead
1> 131        --1292        | 131        --1292        |        1161 bytes: [ 1] Void
1> 1292       --1877        | 1292       --1877        |         585 bytes: [ 2] Tracks
1> 1877       --1907        | 1877       --1907        |          30 bytes: [ 3] Void
1> 1907       --2944        | 1907       --2944        |        1037 bytes: [ 4] Chapters
1> 2944       --3102        | 2944       --3102        |         158 bytes: [ 5] Info
1> 3102       --3968        | 3102       --3968        |         866 bytes: [ 6] Void
1> 3968       --27147145828 | 3968       --27147145828 | 27147141860 bytes: ***NO CHILD***
1> 27147145828--27147331697 | 27147145828--27147331697 |      185869 bytes: [ 7] Cues
1> 27147331697--27147336787 | 27147331697--27147336787 |        5090 bytes: [ 8] Tags
1> 27147336787--27147336885 | 27147336787--27147336885 |          98 bytes: [ 9] Void
1> 27147336885--27147770785 | 27147336885--27147770785 |      433900 bytes: [10] Attachments
```

As far as the segment knows, it's still in a consistent state, because attachments are
actually grandchildren of the Segment.
```python
attachments = next(segment.children_named('Attachments'))
print(attachments.print_space())
```

Output: you can see that it still only has 6 bytes allocated to the new attached file.
```
1> 0          --21313       | 0          --21313       |       21313 bytes: [ 0] AttachedFile
1> 21313      --221749      | 21313      --221749      |      200436 bytes: [ 1] AttachedFile
1> 221749     --433893      | 221749     --433893      |      212144 bytes: [ 2] AttachedFile
1> 433893     --433899      | 433893     --433899      |           6 bytes: [ 3] AttachedFile
1> 433893     --433899      | 433893     --433899      |           6 bytes: ***OVERFLOW***
```

The call to `segment.normalize()` is the most intellegent, catch-all method for 
recursively rearranging an mkv file without moving Cues or Clusters (i.e. the parts 
that take up 99% of the file).  Of course, in this case it doesn't have to work very
hard since the attachments are already at the end of the file.
```python
segment.normalize()
print(segment.print_space())
```

Output: note that Attachments has grown.
```
1> 0          --131         | 0          --131         |         131 bytes: [ 0] SeekHead
1> 131        --1292        | 131        --1292        |        1161 bytes: [ 1] Void
1> 1292       --1877        | 1292       --1877        |         585 bytes: [ 2] Tracks
1> 1877       --1907        | 1877       --1907        |          30 bytes: [ 3] Void
1> 1907       --2944        | 1907       --2944        |        1037 bytes: [ 4] Chapters
1> 2944       --3102        | 2944       --3102        |         158 bytes: [ 5] Info
1> 3102       --3968        | 3102       --3968        |         866 bytes: [ 6] Void
1> 3968       --27147145828 | 3968       --27147145828 | 27147141860 bytes: ***NO CHILD***
1> 27147145828--27147331697 | 27147145828--27147331697 |      185869 bytes: [ 7] Cues
1> 27147331697--27147336787 | 27147331697--27147336787 |        5090 bytes: [ 8] Tags
1> 27147336787--27147336885 | 27147336787--27147336885 |          98 bytes: [ 9] Void
1> 27147336885--27147875312 | 27147336885--27147875312 |      538427 bytes: [10] Attachments
```

```python
print(attachments.print_space())
```

Output: now there's enough space for the attached file.
```
1> 0          --21313       | 0          --21313       |       21313 bytes: [ 0] AttachedFile
1> 21313      --221749      | 21313      --221749      |      200436 bytes: [ 1] AttachedFile
1> 221749     --433893      | 221749     --433893      |      212144 bytes: [ 2] AttachedFile
1> 433893     --538420      | 433893     --538420      |      104527 bytes: [ 3] AttachedFile
```

Save the changes to the file:
```python
with open('/dev/null', 'wb') as f:
    ebml_file.save_changes(f)
```
