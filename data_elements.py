#pylint: disable=too-many-public-methods,too-many-ancestors
#pylint: disable=logging-format-interpolation,too-many-lines
"""
Elements that exist as accessors for their data, using the Parsed property:
EBML, Segment, Seek, Info, TrackEntry, Video, Audio, AttachedFile, Tag, Targets,
SimpleTag.
"""

from collections import defaultdict
from os import SEEK_SET
from itertools import chain
from operator import attrgetter, itemgetter

from . import Inconsistent
from .utility import hex_bytes, encode_var_int, fmt_time
from .tags import MATROSKA_TAGS
from .element import ElementMaster, ElementPlaceholder, ElementVoid, \
    STATE_UNLOADED, STATE_SUMMARY
from .parsed import Parsed, create_atomic
from .sortedlist import SortedList

__all__ = ['ElementEBML', 'ElementSegment', 'ElementSeek', 'ElementInfo',
           'ElementTrackEntry', 'ElementVideo', 'ElementAudio',
           'ElementAttachedFile', 'ElementTag', 'ElementTargets',
           'ElementSimpleTag', 'ElementEditionEntry']

import logging  #pylint: disable=wrong-import-order,wrong-import-position
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

# TODO: write EBMLReadVersion and DocTypeReadVersion correctly

class ElementEBML(ElementMaster):
    """Class to extract metadata from an EBML Element.

    Attributes:
     + version: The value of the EBMLVersion element.
     + read_version: The value of the EBMLReadVersion element.
     + max_id_length: The value of the EBMLMaxIDLength element.
     + max_size_length: The value of the EBMLMaxSizeLength element.
     + doc_type: The value of the DocType element.
     + doc_type_version: The value of the DocTypeVersion element.
     + doc_type_read_version: The value of the DocTypeReadVersion element.
    """

    version = Parsed('EBMLVersion', 'value', 'value', create_atomic())
    read_version = Parsed('EBMLReadVersion', 'value', 'value', create_atomic())
    max_id_length = Parsed('EBMLMaxIDLength', 'value', 'value', create_atomic())
    max_size_length = Parsed('EBMLMaxSizeLength', 'value', 'value',
                             create_atomic())
    doc_type = Parsed('DocType', 'value', 'value', create_atomic())
    doc_type_version = Parsed('DocTypeVersion', 'value', 'value',
                              create_atomic())
    doc_type_read_version = Parsed('DocTypeReadVersion', 'value', 'value',
                                   create_atomic())

    def __str__(self):
        return "{}: V{}/{} ID:{} SZ:{} {!r} V{}/{}" \
            .format(self.__class__.__name__,
                    self.version, self.read_version,
                    self.max_id_length, self.max_size_length,
                    self.doc_type, self.doc_type_version,
                    self.doc_type_read_version)

    def check_read_handled(self):
        "Check if we support reading the file."
        return self.read_version <= 1 and self.max_id_length <= 4 and \
           self.max_size_length <= 8 and \
           self.doc_type.lower() == 'matroska' and \
           self.doc_type_read_version <= 4

    def check_write_handled(self):
        "Check if we support writing the file."
        return self.version <= 1 and self.max_id_length == 4 and \
            self.max_size_length == 8 and \
            self.doc_type.lower() == 'matroska' and \
            self.doc_type_version <= 4


class ElementSegment(ElementMaster):
    """Class to extract metadata from a Segment.

    This class takes advantage of SeekHead elements to extract the following
    metadata from a Segment element.

    Elements and element lists:
     + seek_heads: Iterator over SeekHead elements.
     + seek_entries: Iterator over Seek elements.
     + seek_entries_byid: Dict whose keys are EBML IDs and whose values are
       SortedList's of relative positions where that child entry may be found.
     + tracks: Iterator over TrackEntry elements.
     + tracks_bytype: Dict whose keys are track type strings (as defined in the
       TrackType Tag) and whose values are SortedList's of TrackEntry elements.
     + tracks_byuid: Dict whose keys are track UID ints and whose values are the
       corresponding TrackEntry elements.
     + attachments: Iterator over AttachedFile elements.
     + attachments_byname: Dict of AttachedFile elements, stored by FileName.
     + attachments_byuid: Dict of AttachedFile elements, stored by FileUID.
     + editions: Iterator over EditionEntry elements from the Chapters element,
       if any.
     + chapters: Iterator over ChapterAtom elements from the first EditionEntry
       in the Chapters element, if any.
     + tags: Iterator over Tag elements, i.e. tag groups.

    Extracted from Info elements:
     + uid: SegmentUID, a 128-bit bytes object; None if not defined.
     + timecode_scale: TimecodeScale, the timestap scale in nanoseconds
       (unsigned integer).
     + duration: Segment duration in seconds (float); None if not defined.
     + title: Title, the Global title of the segment (string); None if not
       defined.
     + muxing_app: MuxingApp (string); None if not defined.
     + writing_app: WritingApp (string); None if not defined.

    Other:
     + clusters_pos: SortedList of pairs (start, end), where start is the
       relative position of the beginning of a Clusters block and end is
       (probably) where it ends.  Set by read_summary().
    """

    def __init__(self, header, name='Segment'):
        super().__init__(header, name)
        self.clusters_pos = SortedList(key=itemgetter(1))
        self._placeholders_recursion = 0
        self._replaced = {} # Elements replaced by placeholders

    level_ones = {'SeekHead', 'Info', 'Tracks', 'Attachments', 'Chapters',
                  'Tags', 'Cluster', 'Cues'}

    # Properties

    @property
    def seek_heads(self):
        "Iterate over SeekHead elements."
        yield from self.children_named('SeekHead')

    @property
    def seek_entries(self):
        "Iterate over Seek elements."
        for seek_head in self.seek_heads:
            yield from seek_head.children_named('Seek')

    @property
    def seek_entries_byid(self):
        "Get a dict whose keys are EBML IDs and whose values are positions."
        ret = defaultdict(SortedList)
        for seek in self.seek_entries:
            ret[seek.seek_id].insert(seek.seek_pos)
        return ret

    @property
    def seek_entries_byname(self):
        "Get a dict mapping element names to positions."
        ret = defaultdict(SortedList)
        for seek in self.seek_entries:
            ret[MATROSKA_TAGS[seek.seek_id].name].insert(seek.seek_pos)
        return ret

    @property
    def tracks(self):
        "Iterate over TrackEntry elements."
        for tracks in self.children_named('Tracks'):
            yield from tracks.children_named('TrackEntry')

    @property
    def tracks_bytype(self):
        "Get a dict track_type -> list of Track entries."
        ret = defaultdict(list)
        for track in self.tracks:
            ret[track.track_type].append(track)
        return ret

    @property
    def tracks_byuid(self):
        "Get a dict track_uid -> Track entry."
        ret = {}
        for track in self.tracks:
            ret[track.track_uid] = track
        return ret

    @property
    def attachments(self):
        "Iterate over AttachedFile elements."
        for attached_files in self.children_named('Attachments'):
            yield from attached_files.children_named('AttachedFile')

    @property
    def tags(self):
        "Iterate over Tag elements."
        for tags in self.children_named('Tags'):
            yield from tags.children_named('Tag')

    @property
    def attachments_byname(self):
        "Get a dict of AttachedFile elements stored by FileName."
        ret = {}
        for attachment in self.attachments:
            ret[attachment.file_name] = attachment
        return ret

    @property
    def attachments_byuid(self):
        "Get a dict of AttachedFile elements stored by FileUID."
        ret = {}
        for attachment in self.attachments:
            ret[attachment.file_uid] = attachment
        return ret

    def duration_getter(self, child):
        "Get child.duration, scaling to seconds."
        return child.duration * self.timecode_scale / 1e9
    def duration_setter(self, child, val):
        "Set child.duration, scaling to seconds."
        child.duration = val * 1e9 / self.timecode_scale

    def delete_title(self, _):
        "Delete the title from all Info children."
        for child in self.children_named('Info'):
            del child.title

    # From Info elements
    uid = Parsed('Info', 'segment_uid', 'segment_uid', skip=None)
    timecode_scale = Parsed('Info', 'timecode_scale', 'timecode_scale')
    duration = Parsed('Info', duration_getter, duration_setter, skip=None)
    title = Parsed('Info', 'title', 'title', skip=None, deleter=delete_title)
    muxing_app = Parsed('Info', 'muxing_app', 'muxing_app', skip=None)
    writing_app = Parsed('Info', 'writing_app', 'writing_app', skip=None)

    # From Chapters element
    @property
    def editions(self):
        "Iterate over the children of the Chapters element, if any."
        elt = self.child_named('Chapters')
        if elt is None: return
        yield from elt.children_named('EditionEntry')
    @property
    def chapters(self):
        "Iterate over the ChapterAtom children of the first EditionEntry."
        try: edition = next(self.editions)
        except StopIteration: return
        yield from edition.chapters

    # Manipulating children

    def add_attachment(self, file_name, mime_type, description=None):
        """Create a new AttachedFile element if necessary.

        Also create a new Attachments element if necessary.  Return the new
        ElementAttachedFile, or the old one if an attached file of that name
        already existed.
        """
        attachment = self.attachments_byname.get(file_name)
        if attachment is not None:
            attachment.file_mime_type = mime_type
            if description is not None:
                attachment.file_description = description
            return attachment
        attachments = self.child_named('Attachments')
        if attachments is None:
            attachments = ElementMaster.new('Attachments', self, 0)
        attached_file = ElementAttachedFile.new('AttachedFile', attachments)
        attached_file.file_name = file_name
        attached_file.file_mime_type = mime_type
        attached_file.file_data = b''
        import uuid
        attached_file.file_uid = uuid.uuid4().bytes_le[0:8]
        if description is not None:
            attached_file.file_description = description
        return attached_file

    def del_attachment(self, file_name):
        "Delete an attached file if it exists."
        attachment = self.attachments_byname.get(file_name)
        if attachment is not None:
            attachments = attachment.parent
            attachments.remove_child(attachment)
            if not len(list(attachments.children_named('AttachedFile'))):
                # AttachedFile is a mandatory child
                self.remove_child(attachments)

    # Printing

    def summary(self, indent=0):
        ret = super().summary(indent) + "\n"
        ind_str = " " * (indent+4)
        ret += ind_str + "Segment UID: {}\n".format(hex_bytes(self.uid))
        ret += ind_str + "Title:       {!r}\n".format(self.title)
        ret += ind_str + "Duration:    {:.2f} seconds\n".format(self.duration)
        ret += ind_str + "Time scale:  {} nanoseconds\n" \
            .format(self.timecode_scale)
        ret += ind_str + "Muxing app:  {!r}\n".format(self.muxing_app)
        ret += ind_str + "Writing app: {!r}\n".format(self.writing_app)

        ret += ind_str + "Seek entries:\n"
        for ebml_id, positions in self.seek_entries_byid.items():
            if ebml_id in MATROSKA_TAGS:
                ebml_name = MATROSKA_TAGS[ebml_id].name
            else:
                ebml_name = "[{}]".format(
                    hex_bytes(encode_var_int(ebml_id, range(1, 5))))
            ret += ind_str + "    {:<13} {}\n" \
                .format(ebml_name + ":",
                        ", ".join(str(pos) for pos in positions))

        ret += ind_str + "Attachments:\n"
        for attachment in self.attachments:
            ret += attachment.summary(indent+8) + "\n"
        ret += ind_str + "Tracks:\n"
        for track in self.tracks:
            ret += track.summary(indent+8) + "\n"
        ret += ind_str + "Tags:\n"
        for tags in self.tags:
            ret += tags.summary(indent+8) + "\n"
        ret += ind_str + "Chapters:\n"
        for chapter in self.chapters:
            ret += chapter.summary(indent+8) + "\n"
        return ret[:-1]

    # Reading and writing

    def _read_until_clusters(self, stream, cur_pos):
        "Read elements from cur_pos until we hit Clusters or EOS."
        while cur_pos < self.size:
            tag = self.peek_element(stream)
            if tag is None:
                raise EOFError("Unexpected end of stream at {}".format(cur_pos))
            if tag.name == 'Cluster': # At clusters
                return cur_pos
            child = self.read_element(stream, cur_pos,
                                      summary=True, seekfirst=False)
            cur_pos += child.total_size
        return None

    def read_summary(self, stream, seekfirst=True):
        """Partially read this element.

        This method tries to find all non-Cluster elements.  It does this using
        Seek entries and reading after every known element until it hits a
        Cluster.
        """
        if seekfirst:
            stream.seek(self.pos_data_absolute, SEEK_SET)

        # Read everything at the beginning
        cur_pos = self._read_until_clusters(stream, 0)
        if cur_pos is None or cur_pos == 0:
            return # Clusters started immediately or no clusters?
        clusters_pos = [cur_pos]
        # Read after other elements
        while True:
            # Figure out if there might be something left to read
            cur_pos = None
            for child in self:
                end = child.pos_end_relative
                if end in clusters_pos:
                    continue
                try:
                    self.find(end)
                except ValueError:
                    cur_pos = end
                    break
            if cur_pos is None or cur_pos >= self.size:
                break
            stream.seek(self.pos_data_absolute + cur_pos, SEEK_SET)
            cur_pos = self._read_until_clusters(stream, cur_pos)
            if cur_pos is not None:
                clusters_pos.append(cur_pos)

        # Save cluster positions
        self.clusters_pos = SortedList(key=itemgetter(1))
        for cluster_start in clusters_pos:
            if cluster_start == self.size:
                continue
            try:
                child = self.find_gt(cluster_start)
            except ValueError:
                self.clusters_pos.insert((cluster_start, self.size))
            else:
                self.clusters_pos.insert((cluster_start, child.pos_relative))

        stream.seek(self.pos_end_absolute, SEEK_SET)
        self.read_state = STATE_SUMMARY

    def read_data(self, stream, seekfirst=True):
        super().read_data(stream, seekfirst)
        self.clusters_pos = SortedList(key=itemgetter(1))

    def parse_SeekHead(self, child, stream): #pylint: disable=invalid-name
        "Parse SeekHead element and recursively read elements."
        LOG.debug("Segment: parsed {}".format(child))

        recursed = False
        for seek_entry in child.children_named('Seek'):
            try:
                self.find(seek_entry.seek_pos)
            except ValueError:
                # Recurse if this is the first time we've seen this seek entry
                LOG.debug("Segment: adding seek entry {}".format(seek_entry))
                if seek_entry.seek_id_name != 'Cluster' and stream:
                    # This recursively reads any elements this seek entry
                    # points to that haven't been read already.
                    self.read_element(stream, seek_entry.seek_pos,
                                      summary=True, seekfirst=True)
                    recursed = True
        if recursed:
            stream.seek(child.pos_end_absolute, SEEK_SET)

    def _add_placeholders(self):
        """Add LibInternal elements over detected Cluster blocks.

        Also replace loaded Cluster and Cues blocks with placeholders if in
        summary mode since they're MasterDefer elements.
        """
        self._placeholders_recursion += 1
        if self._placeholders_recursion > 1:
            return
        for start, end in self.clusters_pos:
            ElementPlaceholder.of_size('LibInternal', end - start, self, start)
        self.clusters_pos = SortedList(key=itemgetter(1))
        if self.read_state == STATE_SUMMARY:
            for elt in chain(self.children_named('Cluster'),
                             self.children_named('Cues')):
                temp = ElementPlaceholder.of_size(
                    'LibInternal2', elt.total_size, self, elt.pos_relative)
                self._replaced[elt] = temp
                self.remove(elt)

    def _remove_placeholders(self):
        "Remove all LibInternal children."
        self._placeholders_recursion -= 1
        if self._placeholders_recursion > 0:
            return
        for elt, temp in self._replaced.items():
            elt.pos_relative = temp.pos_relative
            self.insert(elt)
            self.remove(temp)
        self._replaced = {}
        for temp in list(self.children_named('LibInternal')):
            self.clusters_pos.insert((temp.pos_relative, temp.pos_end_relative))
            self.remove_child(temp)

    def _placeholders(self):
        "Return a context manager to handle placeholders."
        class CM:
            "Context manager to handle placeholders."
            #pylint: disable=too-few-public-methods,protected-access
            def __init__(self, seg):
                self.seg = seg
            def __enter__(self):
                self.seg._add_placeholders()
            def __exit__(self, exc_type, exc_value, traceback):
                self.seg._remove_placeholders()
        return CM(self)

    def normalize(self):
        """Rearrange level-1 elements into a reasonable configuration.

        This method does several things:

          1. It expands the header to its maximum size.
          2. It reconstructs the SeekHead element, consolidating existing ones
             and placing it at the beginning of the Segment.
          3. It recursively rearranges all other elements to put everything in a
             consistent state.
          4. It grows this element if necessary.  It will not shrink.

        One thing this method will never do is move (from its absolute position)
        or otherwise modify any Cluster or Cues element.

        Raises:
         + Inconsistent, if there is not enough space before the Clusters for
           the SeekHead, or if anything else bizarre happens.  In case of
           non-local exit the Element itself will be in an inconsistent state
           and should be deleted.
        """
        #pylint: disable=too-many-branches
        # For reference, the level-1 elements are (m=multiple):
        #   SeekHead(m), Info(m), Tracks(m), Attachments, Chapters, Tags,
        #   Cluster(m), Cues
        if self.read_state == STATE_UNLOADED:
            raise Inconsistent("Tried to normalize() unloaded Segment")
        to_index = self.level_ones - {'SeekHead', 'Cluster'}
        to_rearrange = self.level_ones - {'Cluster', 'Cues', 'SeekHead'}
        # Delete Voids and SeekHeads
        self.remove_children_named('Void')
        self.remove_children_named('SeekHead')
        # Make new SeekHead.  The positions may get modified, but we use the
        # maximum amount of space to store them so the total size will be
        # unchanged.
        seek_head = ElementMaster.new('SeekHead', self, 0)
        for child in self:
            if child.name in to_index:
                seek_head.add_child(ElementSeek.new_index(child))
        # Add placeholders *after* making the new SeekHead
        self._add_placeholders()
        # Expand header to maximum size
        self.expand_header(self.header.numbytes_size_max)
        # Put children in a consistent state.
        for child in self:
            if child.name in to_rearrange:
                child.rearrange_if_necessary(prefer_grow=False,
                                             allow_shrink=True)
        seek_head.rearrange_resize(prefer_grow=False, allow_shrink=True)
        self.move_child(seek_head, 0)
        # Collect and replace overlapping elements
        to_replace = set(self.get_overlapping(fixed=(
            'SeekHead', 'Cluster', 'Cues', 'LibInternal', 'LibInternal2')))
        to_replace_byname = defaultdict(
            lambda: SortedList(key=attrgetter('total_size')))
        for elt in to_replace:
            to_replace_byname[elt.name].insert(elt)
        clusters_start \
            = min([elt.pos_relative \
                   for elt in chain(self.children_named('Cluster'),
                                    self.children_named('LibInternal'))]
                  + [self.size])
        # Prefer to put these element types at the beginning:
        for elt_name in ('Info', 'Tracks'):
            for elt in reversed(to_replace_byname[elt_name]):
                try:
                    self.place_child(elt, 0, clusters_start)
                except Inconsistent:
                    self.place_child(elt)
                to_replace.remove(elt)
        # Place the rest where they fit best
        to_replace = list(to_replace)
        to_replace.sort(key=attrgetter('total_size'))
        for elt in reversed(to_replace):
            self.place_child(elt)
        # Cleanup
        if self.end_last_child == self.size - 1:
            self.resize(self.size + 1)
        elif self.end_last_child > self.size:
            self.resize(self.end_last_child)
        self._fill_gaps()
        if self.size > self.end_last_child:
            ElementVoid.of_size(self.size - self.end_last_child,
                                self, self.end_last_child)
        self._remove_placeholders()
        # Finalize seek entries
        for seek in seek_head:
            seek.seek_pos = seek.child.pos_relative

    def check_consecutivity(self, child_consistency=False):
        with self._placeholders():
            super().check_consecutivity(child_consistency)

    def write(self, stream, seekfirst=True):
        with self._placeholders():
            super().write(stream, seekfirst)

    # Logging

    def parse_Info(self, child, stream):
        #pylint: disable=invalid-name,unused-argument,no-self-use
        "Log Info parsing."
        LOG.debug("Segment: parsed {}".format(child))
    def parse_Tracks(self, child, stream):
        #pylint: disable=invalid-name,unused-argument,no-self-use
        "Log Tracks parsing."
        LOG.debug("Segment: parsed {}".format(child))
    def parse_Cues(self, child, stream):
        #pylint: disable=invalid-name,unused-argument,no-self-use
        "Log Cues parsing."
        LOG.debug("Segment: parsed {}".format(child))
    def parse_Attachments(self, child, stream):
        #pylint: disable=invalid-name,unused-argument,no-self-use
        "Log Attachments parsing."
        LOG.debug("Segment: parsed {}".format(child))
    def parse_Chapters(self, child, stream):
        #pylint: disable=invalid-name,unused-argument,no-self-use
        "Log Chapters parsing."
        LOG.debug("Segment: parsed {}".format(child))
    def parse_Tags(self, child, stream):
        #pylint: disable=invalid-name,unused-argument,no-self-use
        "Log Tags parsing."
        LOG.debug("Segment: parsed {}".format(child))


class ElementSeek(ElementMaster):
    """Class for a Seek element.

    Attributes:
     + seek_id: The value of the SeekID child, an EBML ID.
     + seek_id_name: The tag name of ID seek_id.
     + seek_id_raw: The encoded EBML ID.
     + seek_pos: The value of the SeekPosition child; this is the pos_relative
       of the direct child of the Segment element.

    Two instances of this class compare equal if they have the same seek_id and
    seek_pos.
    """

    @classmethod
    def new_index(cls, elt):
        """Create a new SeekHead indexing elt."""
        ret = cls.new('Seek')
        ret.seek_id = elt.ebml_id
        ret.seek_pos = max([0, elt.pos_relative])
        ret.child = elt # for internal use
        return ret

    def __init__(self, header, name='SeekHead'):
        super().__init__(header, name)
        self.child = None

    seek_id = Parsed('SeekID', 'value', 'value', create_atomic())
    seek_id_name = Parsed('SeekID', 'string_name', default="NOT DEFINED")
    seek_id_raw = Parsed('SeekID', 'raw')
    seek_pos = Parsed('SeekPosition', 'value', 'value', create_atomic())

    def __str__(self):
        return "{}: [{}] ({}) at {}".format(self.__class__.__name__,
                                            hex_bytes(self.seek_id_raw),
                                            self.seek_id_name, self.seek_pos)


class ElementInfo(ElementMaster):
    """Class for an Info element.

    Attributes:
     + segment_uid: The value of the SegmentUID element, if any; None otherwise.
     + timecode_scale: The value of the TimecodeScale element, if any; 1000000
       otherwise (the Matroska default).
     + duration: The value of the Duration element, if any; None otherwise.
     + title: The value of the Title element, if any; None otherwise.
     + muxing_app: The value of the MuxingApp element, if any; None otherwise.
     + writing_app: The value of the WritingApp element, if any; None otherwise.
    """

    segment_uid = Parsed('SegmentUID', 'value', 'value', create_atomic())
    timecode_scale = Parsed('TimecodeScale', 'value', 'value', create_atomic())
    duration = Parsed('Duration', 'value', 'value', create_atomic())
    title = Parsed('Title', 'value', 'value', create_atomic())
    muxing_app = Parsed('MuxingApp', 'value', 'value', create_atomic())
    writing_app = Parsed('WritingApp', 'value', 'value', create_atomic())


class ElementTrackEntry(ElementMaster):
    """Class for a TrackEntry element.

    Extract track metadata from a TrackEntry element.

    Attributes:
     + track_type: The value of the TrackType element, a string representing the
       enum value.
     + track_name: The value of the Name element, if any; None otherwise
       (string).
     + track_language: The value of the Language element, if any; "eng"
       otherwise (the Matroska default).
     + codec_id: The value of the CodecID element (string).
     + codec_name: The value of the CodecName element, if any; None otherwise
       (string).
     + track_number: The value of the TrackNumber element (int).
     + track_uid: The value of the TrackUID element (int).
     + flag_enabled: The value of the FlagEnabled element (bool).
     + flag_default: The value of the FlagDefault element (bool).
     + flag_forced: The value of the FlagForced element (bool).
     + flag_lacing: The value of the FlagLacing element (bool).
     + video: ElementVideo instance, for tracks of type 'video'.
     + audio: ElementAudio instance, for tracks of type 'audio'.
     + track_index: The index of this TrackEntry in the list of tracks in its
       segment.
    """

    track_type = Parsed('TrackType', 'string_val', 'value',
                        create_atomic(), default='UNKNOWN')
    track_name = Parsed('Name', 'value', 'value', create_atomic())
    track_language = Parsed('Language', 'value', 'value', create_atomic())
    codec_id = Parsed('CodecID', 'value', 'value', create_atomic())
    codec_name = Parsed('CodecName', 'value', 'value', create_atomic())
    track_number = Parsed('TrackNumber', 'value', 'value', create_atomic())
    track_uid = Parsed('TrackUID', 'value', 'value', create_atomic())
    flag_enabled = Parsed('FlagEnabled', 'value', 'value', create_atomic())
    flag_default = Parsed('FlagDefault', 'value', 'value', create_atomic())
    flag_forced = Parsed('FlagForced', 'value', 'value', create_atomic())
    flag_lacing = Parsed('FlagLacing', 'value', 'value', create_atomic())
    video = Parsed('Video', '')
    audio = Parsed('Audio', '')

    @property
    def track_index(self):
        "Return the index of this TrackEntry in its containing segment."
        segment = self.parent.parent
        if not isinstance(segment, ElementSegment):
            raise ValueError("Track is not contained in a segment")
        for idx, other in enumerate(segment.tracks):
            if other is self:
                return idx

    def __str__(self):
        ret = "{}: {} lang={} codec={} num={} uid={}" \
            .format(self.__class__.__name__, self.track_type,
                    self.track_language, self.codec_id, self.track_number,
                    self.track_uid)
        if self.track_name:
            ret += ": " + repr(self.track_name)
        return ret

    def summary(self, indent=0):
        ret = super().summary(indent) + "\n"
        ind_str = " " * (indent+4)
        if self.codec_name:
            ret += ind_str + "Codec: {!r}\n".format(self.codec_name)
        flags = ["enabled", "default", "forced", "lacing"]
        flags_vals = []
        for flag in flags:
            if getattr(self, "flag_" + flag):
                flags_vals.append(flag)
            else:
                flags_vals.append("!" + flag)
        ret += ind_str + "Flags: {}\n".format(" ".join(flags_vals))

        if self.video:
            ret += self.video.summary(indent+4) + "\n"
        if self.audio:
            ret += self.audio.summary(indent+4) + "\n"

        return ret[:-1]


class ElementVideo(ElementMaster):
    """Class for a Video element.

    Extract track metadata from a Video element.

    Attributes:
     + pixel_dims: Pair (width, height) of int's consisting of the values of the
       PixelWidth and PixelHeight elements.
     + display_dims: Pair (width, height) of int's consisting of the values of
       the DisplayWidth and DisplayHeight elements.  Defaults to pixel_dims.
     + display_unit: The value of the DisplayUnit element, if any; 'pixels'
       otherwise.  This is the string representing the enum value.
     + pixel_crop: List (top, bottom, left, right) of int's consisting of the
       values of the PixelCrop* elements.  They default to 0.
     + stereo_mode: The value of the StereoMode element, if any; 'mono'
       otherwise.  This is the string representing the enum value.
     + aspect_ratio_type: The value of the AspectRatioType element, if any;
       'free resizing' otherwise.  This is the string representing the enum
       value.
     + colour_space: The value of the ColourSpace element, if any; None
       otherwise (bytes).
     + alpha_mode: value of the AlphaMode element, if any; 0 otherwise (int).
     + flag_interlaced: The value of the FlagInterlaced element (bool).
    """
    #pylint: disable=too-many-instance-attributes

    pixel_width = Parsed('PixelWidth', 'value', 'value', create_atomic())
    pixel_height = Parsed('PixelHeight', 'value', 'value', create_atomic())
    display_width = Parsed('DisplayWidth', 'value', 'value', create_atomic(),
                           default=attrgetter('pixel_width'))
    display_height = Parsed('DisplayHeight', 'value', 'value', create_atomic(),
                            default=attrgetter('pixel_height'))
    pixel_crop_top = Parsed('PixelCropTop', 'value', 'value', create_atomic())
    pixel_crop_bottom = Parsed('PixelCropBottom', 'value', 'value',
                               create_atomic())
    pixel_crop_left = Parsed('PixelCropLeft', 'value', 'value', create_atomic())
    pixel_crop_right = Parsed('PixelCropRight', 'value', 'value',
                              create_atomic())

    display_unit = Parsed('DisplayUnit', 'string_val', 'value',
                          create_atomic(), default='pixels')
    stereo_mode = Parsed('StereoMode', 'string_val', 'value',
                         create_atomic(), default='mono')
    aspect_ratio_type \
        = Parsed('AspectRatioType', 'string_val', 'value',
                 create_atomic(), default='free resizing')
    colour_space = Parsed('ColourSpace', 'value', 'value', create_atomic())
    alpha_mode = Parsed('AlphaMode', 'value', 'value', create_atomic())
    flag_interlaced = Parsed('FlagInterlaced', 'value', 'value',
                             create_atomic())

    @property
    def pixel_dims(self):
        "Get pixel dims as (width, height)."
        return (self.pixel_width, self.pixel_height)
    @pixel_dims.setter
    def pixel_dims(self, val):
        "Set pixel_dims to val=(width, height)."
        self.pixel_width, self.pixel_height = val

    @property
    def display_dims(self):
        "Get display dims as (width, height), defaulting to pixel_dims."
        return (self.display_width, self.display_height)
    @display_dims.setter
    def display_dims(self, val):
        "Set display_dims to val=(width, height)."
        self.display_width, self.display_height = val

    @property
    def pixel_crop(self):
        "Get pixel crop as (top, bottom, left, right)."
        return (self.pixel_crop_top, self.pixel_crop_bottom,
                self.pixel_crop_left, self.pixel_crop_right)
    @pixel_crop.setter
    def pixel_crop(self, val):
        "Set pixel crop to val=(top, bottom, left, right)."
        self.pixel_crop_top, self.pixel_crop_bottom, \
            self.pixel_crop_left, self.pixel_crop_right = val

    def __str__(self):
        return "{0}: dims={p[0]}x{p[1]}, display={d[0]}x{d[1]}, aspect={1!r}" \
            .format(self.__class__.__name__, self.aspect_ratio_type,
                    p=self.pixel_dims, d=self.display_dims)

    def summary(self, indent=0):
        ret = super().summary(indent) + "\n"
        ind_str = " " * (indent+4)
        ret += ind_str + "Stereo:     {}\n".format(self.stereo_mode)
        ret += ind_str + "Interlaced: {}\n".format(bool(self.flag_interlaced))
        if self.pixel_crop != (0, 0, 0, 0):
            ret += ind_str + "Crop:       {}:{}:{}:{}\n" \
                .format(*self.pixel_crop)
        return ret[:-1]


class ElementAudio(ElementMaster):
    """Class for an Audio element.

    Extract track metadata from an Audio element.

    Attributes:
     + channels: The value of the Channels element (int).
     + bit_depth: The value of the BitDepth element, if any; None otherwise
       (int).
     + sampling_frequency: The value of the SamplingFrequency element, in Hz
       (float).
     + output_sampling_frequency: The value of the OutputSamplingFrequency
       element, if any, in Hz (float).  Defaults to sampling_frequency.
    """

    channels = Parsed('Channels', 'value', 'value', create_atomic())
    bit_depth = Parsed('BitDepth', 'value', 'value', create_atomic())
    sampling_frequency = Parsed('SamplingFrequency', 'value', 'value',
                                create_atomic())
    output_sampling_frequency \
        = Parsed('OutputSamplingFrequency', 'value', 'value', create_atomic(),
                 default=attrgetter('sampling_frequency'))

    def __str__(self):
        return "{}: channels={} sampling={}k" \
            .format(self.__class__.__name__, self.channels,
                    int(self.sampling_frequency/1000))

    def summary(self, indent=0):
        ret = super().summary(indent) + "\n"
        ind_str = " " * (indent+4)
        if self.bit_depth:
            ret += ind_str + "Bit depth:   {}\n".format(self.bit_depth)
        if self.sampling_frequency != self.output_sampling_frequency:
            ret += ind_str + "Output freq: {}\n" \
                   .format(int(self.output_sampling_frequency/1000))
        return ret[:-1]


class ElementAttachedFile(ElementMaster):
    """Class for an AttachedFile element.

    Attributes:
     + file_name: The value of the FileName element, a string.
     + file_uid: The value of the FileUID element, a bytes object.
     + file_description: The value of the FileDescription element, if any; None
       otherwise.
     + file_mime_type: The value of the FileMimeType element, a string.
     + file_data: The FileData element's data.  This can be large.
     + file_size: The size of self.file_data.
    """

    file_name = Parsed('FileName', 'value', 'value', create_atomic())
    file_uid = Parsed('FileUID', 'value', 'value', create_atomic())
    file_description = Parsed('FileDescription', 'value', 'value',
                              create_atomic())
    file_mime_type = Parsed('FileMimeType', 'value', 'value', create_atomic())
    file_data = Parsed('FileData', 'value', 'value', create_atomic())
    file_size = Parsed('FileData', 'size', default=0)

    def __str__(self):
        ret = "{}: {!r} ({}), {} bytes" \
            .format(self.__class__.__name__, self.file_name,
                    self.file_mime_type, self.file_size)
        if self.file_description:
            ret += ": " + repr(self.file_description)
        return ret

    def summary(self, indent=0):
        ret = super().summary(indent) + "\n"
        ind_str = " " * (indent+4)
        ret += ind_str + "UID: {}\n".format(hex_bytes(self.file_uid))
        return ret[:-1]


class ElementTag(ElementMaster):
    """Class for a Tag element, i.e. a tag group.

    Attributes:
     + targets: The Targets element.
     + target_type_value: The TargetTypeValue child of the Targets element.
     + target_type: The TargetType child of the Targets element.
     + simple_tags: Iterator over SimpleTag children.
    """

    @classmethod
    def new_with_value(cls, target_type_value, target_type,
                       parent=None, pos_relative=None):
        "Create a new tag group."
        ret = cls.new('Tag', parent, pos_relative)
        targets = ElementTargets.new('Targets', ret)
        targets.target_type_value = target_type_value
        targets.target_type = target_type
        return ret

    @property
    def simple_tags(self):
        "Iterate over SimpleTag elements."
        yield from self.children_named('SimpleTag')

    targets = Parsed('Targets', '')
    target_type_value = Parsed('Targets', 'target_type_value',
                               'target_type_value')
    target_type = Parsed('Targets', 'target_type', 'target_type')

    def __str__(self):
        return "{}: {} ({}), {} tags" \
            .format(self.__class__.__name__, self.target_type,
                    self.target_type_value, len(list(self.simple_tags)))

    def summary(self, indent=0):
        ret = super().summary(indent) + "\n"
        for tag in self.simple_tags:
            ret += tag.summary(indent+4) + "\n"
        return ret[:-1]


class ElementTargets(ElementMaster):
    """Class for a Targets element.

    Attributes:
     + target_type_value: The value of the TargetTypeValue element.
     + target_type: The value of the TargetType element.
    """
    target_type_value = Parsed('TargetTypeValue', 'value', 'value',
                               create_atomic(), default=50)
    target_type = Parsed('TargetType', 'value', 'value', create_atomic())


class ElementSimpleTag(ElementMaster):
    """Class for a SimpleTag element.

    Attributes:
     + tag_name: The value of the TagName element.
     + language: The value of the TagLanguage element.
     + default: The value of the TagDefault element.
     + string_val: The value of the TagString element.
     + binary_val: The value of the TagBinary element.
     + sub_tags: Iterate over SimpleTag children.
    """

    default_lang = 'eng'

    @classmethod
    def new_with_value(cls, tag_name, string_val,
                       parent=None, pos_relative=None, *, lang=None):
        "Create a new SimpleTag with a name and a value."
        ret = cls.new('SimpleTag', parent, pos_relative)
        ret.tag_name = tag_name
        if lang is None:
            ret.language = cls.default_lang
        else:
            ret.language = lang
        ret.default = True
        ret.string_val = string_val
        return ret

    @property
    def sub_tags(self):
        "Iterate over SimpleTag elements."
        yield from self.children_named('SimpleTag')

    tag_name = Parsed('TagName', 'value', 'value', create_atomic())
    language = Parsed('TagLanguage', 'value', 'value', create_atomic(),
                      default='und')
    default = Parsed('TagDefault', 'value', 'value', create_atomic(),
                     default=True)
    string_val = Parsed('TagString', 'value', 'value', create_atomic())
    binary_val = Parsed('TagBinary', 'value', 'value', create_atomic())

    def __str__(self):
        return "{} lang={} def={!r}: {!r} => {!r}" \
            .format(self.__class__.__name__, self.language,
                    bool(self.default), self.tag_name, self.string_val)

    def summary(self, indent=0):
        ret = super().summary(indent) + "\n"
        for tag in self.sub_tags:
            ret += tag.summary(indent+4) + "\n"
        return ret[:-1]


class ElementChapterAtom(ElementMaster):
    """Class to extract metadata from a ChapterAtom element.

    This class represents a single chapter definition.  It consists of, among
    other things, the following attributes:
     + time_start: the start time of the chapter (nanoseconds, unscaled).
     + time_end: the end time of the chapter (nanoseconds, unscaled; optional).
     + identifier: the string ID for WebVTT cue identifier storage.
     + display names in different languages
    """

    chapter_uid = Parsed('ChapterUID', 'value', 'value', create_atomic())
    identifier = Parsed('ChapterStringUID', 'value', 'value', create_atomic())
    time_start = Parsed('ChapterTimeStart', 'value', 'value', create_atomic())
    time_end = Parsed('ChapterTimeEnd', 'value', 'value', create_atomic())
    flag_hidden = Parsed('ChapterFlagHidden', 'value', 'value', create_atomic())
    flag_enabled = Parsed('ChapterFlagEnabled', 'value', 'value',
                          create_atomic())
    segment_uid = Parsed('ChapterSegmentUID', 'value', 'value', create_atomic())
    segment_edition_uid = Parsed('ChapterSegmentEditionUID', 'value', 'value',
                                 create_atomic())
    physical_equiv = Parsed('ChapterPhysicalEquiv', 'value', 'value',
                            create_atomic())

    @property
    def chapter_tracks(self):
        "Return a list of track numbers to which this chapter applies."
        chapter_track = self.child_named('ChapterTrack')
        if chapter_track is None:
            return []
        return [c.value for c in chapter_track]

    def display_name(self, lang='eng'):
        """Return the name of the chapter in the specified language, or None.

        Note that the display name is an optional child of a ChapterAtom, and
        there may be more than one display name for a given language.  In the
        latter case, the first such is returned.

        The language is the ISO-639-2 alpha-3 form.
        """
        for display in self.children_named('ChapterDisplay'):
            langs = [l.value for l in display.children_named('ChapLanguage')] \
                    or ['eng']
            if lang in langs:
                return display.child_named('ChapString').value
        return None

    def __str__(self):
        return "{} id={!r} {} --> {} {}hid {}enab" \
            .format(self.__class__.__name__, self.identifier,
                    fmt_time(self.time_start, 3),
                    fmt_time(self.time_end, 3)
                    if self.time_end is not None else "[--]",
                    '!' if not self.flag_hidden else '',
                    '!' if not self.flag_enabled else '')

    def summary(self, indent=0):
        ret = super().summary(indent) + "\n"
        for display in self.children_named('ChapterDisplay'):
            langs = [l.value for l in display.children_named('ChapLanguage')] \
                    or ['eng']
            langs = ",".join(langs)
            ret += " " * (indent+4) + "{}: {!r}\n" \
                   .format(langs, display.child_named('ChapString').value)
        return ret[:-1]


class ElementEditionEntry(ElementMaster):
    """Class to extract metadata from an EditionEntry element.

    An EditionEntry contains one set of chapter definitions.  The important
    attribute is 'chapters'.
    """

    edition_uid = Parsed('EditionUID', 'value', 'value', create_atomic())
    flag_hidden = Parsed('EditionFlagHidden', 'value', 'value', create_atomic())
    flag_default = Parsed('EditionFlagDefault', 'value', 'value',
                          create_atomic())
    flag_ordered = Parsed('EditionFlagOrdered', 'value', 'value',
                          create_atomic())

    @property
    def chapters(self):
        "Return an iterator of ElementChapterAtom instances."
        yield from self.children_named('ChapterAtom')

    def __str__(self):
        return "{} {}hid {}def ord={!r}: {} chapters" \
            .format(self.__class__.__name__, self.flag_hidden,
                    '!' if not self.flag_default else '',
                    '!' if not self.flag_ordered else '',
                    len(list(self.chapters)))
