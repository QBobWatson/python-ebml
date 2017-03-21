#pylint: disable=too-many-locals,no-self-use
#pylint: disable=too-many-public-methods,too-many-statements
"""
Data element tests, mainly Segment.
"""

from io import BytesIO

from .test import EbmlTest

__all__ = ['DataElementTest']

class DataElementTest(EbmlTest):
    "Data element tests."

    def test_1_segment_read(self):
        """Test ElementEBML and ElementSegment parsing.

        This just checks whether the parsed attributes are accessed correctly.
        """
        #pylint: disable=too-many-locals

        from ebml.tags import MATROSKA_TAGS
        from ebml.sortedlist import SortedList

        ebmlf = self.read_file_data()
        self.assertEqual(len(ebmlf), 2)
        ebml = ebmlf[0]
        seg = ebmlf[1]
        self.assertEqual(seg.name, 'Segment')

        # EBML
        self.assertEqual(len(ebml), 7)
        self.assertEqual(ebml.version, 1)
        self.assertEqual(ebml.read_version, 1)
        self.assertEqual(ebml.max_id_length, 4)
        self.assertEqual(ebml.max_size_length, 8)
        self.assertEqual(ebml.doc_type, 'matroska')
        self.assertEqual(ebml.doc_type_version, 4)
        self.assertEqual(ebml.doc_type_read_version, 2)

        # Segment
        self.assertEqual(len(seg), 14)
        self.assertEqual(len(list(seg.seek_heads)), 4)
        self.assertEqual(len(list(seg.seek_entries)), 9)
        self.assertEqual(len(seg.seek_entries_byid), 7)
        entries_byid \
            = {MATROSKA_TAGS['SeekHead'].ebml_id : SortedList((10513, 37)),
               MATROSKA_TAGS['Cues'].ebml_id : SortedList((3823, 3823)),
               MATROSKA_TAGS['Tracks'].ebml_id : SortedList((268,)),
               MATROSKA_TAGS['Chapters'].ebml_id : SortedList((2005,)),
               MATROSKA_TAGS['Info'].ebml_id : SortedList((61,)),
               MATROSKA_TAGS['Tags'].ebml_id : SortedList((3900,)),
               MATROSKA_TAGS['Attachments'].ebml_id : SortedList((1803,))}
        for ebml_id in entries_byid:
            self.assertEqual(seg.seek_entries_byid[ebml_id],
                             entries_byid[ebml_id])
        self.assertEqual(len(list(seg.tracks)), 32)
        self.assertEqual(len(seg.tracks_bytype['video']), 1)
        self.assertEqual(len(seg.tracks_bytype['audio']), 3)
        self.assertEqual(len(seg.tracks_bytype['subtitle']), 28)
        attachments = list(seg.attachments)
        self.assertEqual(len(attachments), 2)
        self.assertIs(seg.attachments_byname['myth_metadata.xml'],
                      attachments[0])
        self.assertIs(seg.attachments_byname['cover.jpg'], attachments[1])
        self.assertIs(seg.attachments_byuid[b'\x9d\xdb\xf4,\x9d4p\x91'],
                      attachments[0])
        self.assertIs(seg.attachments_byuid[b'd\xcc\x99\x00\xf9\xa7oV'],
                      attachments[1])
        self.assertEqual(seg.uid, b'\xb0WRGrIO#{;\x88\xb0\x0e\x06\xaaK')
        self.assertEqual(seg.timecode_scale, 1000000)
        self.assertEqual(seg.duration, 9425.504)
        self.assertEqual(seg.title, 'Harry Potter 4: The Goblet of Fire')
        self.assertEqual(seg.muxing_app, 'libebml v1.3.0 + libmatroska v1.4.1')
        self.assertEqual(seg.writing_app,
                         "mkvmerge v6.8.0 ('Theme for Great Cities') 64bit " \
                         "built on Mar  3 2014 16:19:32")

        # Seek
        seek = next(seg.seek_entries)
        self.assertEqual(seek.seek_id, MATROSKA_TAGS['SeekHead'].ebml_id)
        self.assertEqual(seek.seek_id_name, 'SeekHead')
        self.assertEqual(seek.seek_id_raw, b'\x11M\x9bt')
        self.assertEqual(seek.seek_pos, 10513)

        # Info
        info = next(seg.children_named('Info'))
        self.assertEqual(info.segment_uid,
                         b'\xb0WRGrIO#{;\x88\xb0\x0e\x06\xaaK')
        self.assertEqual(info.timecode_scale, 1000000)
        self.assertEqual(info.duration, 9425504.0)
        self.assertEqual(info.title, 'Harry Potter 4: The Goblet of Fire')
        self.assertEqual(info.muxing_app, 'libebml v1.3.0 + libmatroska v1.4.1')
        self.assertEqual(info.writing_app,
                         "mkvmerge v6.8.0 ('Theme for Great Cities') 64bit " \
                         "built on Mar  3 2014 16:19:32")

        # TrackEntry
        # Not tested (no child): codec_name, flag_enabled, flag_forced
        # Not tested (is default): timecode_scale
        track = seg.tracks_bytype['video'][0]
        self.assertEqual(track.track_type, 'video')
        self.assertEqual(track.track_name, None)
        self.assertEqual(track.track_language, 'eng')
        self.assertEqual(track.codec_id, 'V_MPEG4/ISO/AVC')
        self.assertEqual(track.codec_name, None)
        self.assertEqual(track.track_number, 1)
        self.assertEqual(track.track_uid, 941808940)
        self.assertEqual(track.flag_enabled, True)
        self.assertEqual(track.flag_default, True)
        self.assertEqual(track.flag_forced, False)
        self.assertEqual(track.flag_lacing, False)
        self.assertEqual(track.audio, None)
        video = track.video

        track = seg.tracks_bytype['audio'][1]
        self.assertEqual(track.track_type, 'audio')
        self.assertEqual(track.track_name, 'Surround 5.1')
        self.assertEqual(track.track_language, 'fre')
        self.assertEqual(track.codec_id, 'A_AC3')
        self.assertEqual(track.codec_name, None)
        self.assertEqual(track.track_number, 3)
        self.assertEqual(track.track_uid, 3)
        self.assertEqual(track.flag_enabled, True)
        self.assertEqual(track.flag_default, False)
        self.assertEqual(track.flag_forced, False)
        self.assertEqual(track.flag_lacing, True)
        self.assertEqual(track.video, None)
        audio = track.audio

        track = seg.tracks_bytype['subtitle'][10]
        self.assertEqual(track.track_type, 'subtitle')
        self.assertEqual(track.track_name, None)
        self.assertEqual(track.track_language, 'jpn')
        self.assertEqual(track.codec_id, 'S_HDMV/PGS')
        self.assertEqual(track.codec_name, None)
        self.assertEqual(track.track_number, 15)
        self.assertEqual(track.track_uid, 25)
        self.assertEqual(track.flag_enabled, True)
        self.assertEqual(track.flag_default, False)
        self.assertEqual(track.flag_forced, False)
        self.assertEqual(track.flag_lacing, False)
        self.assertEqual(track.audio, None)
        self.assertEqual(track.video, None)

        # Video
        # Not tested (no child): display_unit, pixel_crop, stereo_mode,
        #     aspect_ratio_type, colour_space, flag_interlaced
        # Not tested (is default): display_dims
        self.assertEqual(video.pixel_dims, (1920, 800))
        self.assertEqual(video.display_dims, (1920, 800))
        self.assertEqual(video.display_unit, 'pixels')
        self.assertEqual(video.pixel_crop, (0, 0, 0, 0))
        self.assertEqual(video.stereo_mode, 'mono')
        self.assertEqual(video.aspect_ratio_type, 'free resizing')
        self.assertEqual(video.colour_space, None)
        self.assertEqual(video.alpha_mode, 0)
        self.assertEqual(video.flag_interlaced, False)

        # Audio
        # Not tested (no child): bit_depth, output_sampling_frequency
        self.assertEqual(audio.channels, 6)
        self.assertEqual(audio.bit_depth, None)
        self.assertEqual(audio.sampling_frequency, 48000.0)
        self.assertEqual(audio.output_sampling_frequency, 48000.0)

        # AttachedFile
        attach = attachments[0]
        self.assertEqual(attach.file_name, 'myth_metadata.xml')
        self.assertEqual(attach.file_uid, b'\x9d\xdb\xf4,\x9d4p\x91')
        self.assertEqual(attach.file_description, 'MythTV grabber XML output')
        self.assertEqual(attach.file_mime_type, 'application/xml')
        self.assertEqual(attach.file_data, b'this is where the metadata goes')
        self.assertEqual(attach.file_size, 31)

        # Tag, Targets, SimpleTag
        tags = next(seg.tags)
        self.assertEqual(tags.target_type_value, 50)
        self.assertEqual(tags.target_type, None)
        tag = list(tags.simple_tags)[14]
        self.assertEqual(tag.tag_name, 'ACTOR')
        self.assertEqual(tag.language, 'eng')
        self.assertEqual(tag.default, True)
        self.assertEqual(tag.string_val, 'Daniel Radcliffe')
        sub_tags = list(tag.sub_tags)
        self.assertEqual(len(sub_tags), 1)
        self.assertEqual(sub_tags[0].tag_name, 'CHARACTER')
        self.assertEqual(sub_tags[0].string_val, 'Harry Potter')

        # Chapters
        edition = next(seg.editions)
        self.assertEqual(edition.edition_uid, 15869277706556786643)
        self.assertEqual(edition.flag_hidden, False)
        self.assertEqual(edition.flag_default, True)
        self.assertEqual(edition.flag_ordered, False)
        chapters = list(seg.chapters)
        self.assertEqual(chapters, list(edition.chapters))
        self.assertEqual(len(chapters), 30)
        chapter = chapters[5]
        self.assertEqual(chapter.chapter_uid, 2972522551968254461)
        self.assertIs(chapter.identifier, None)
        self.assertEqual(chapter.time_start, 1154820333333)
        self.assertEqual(chapter.time_end, 1389054333333)
        self.assertEqual(chapter.flag_hidden, False)
        self.assertEqual(chapter.flag_enabled, True)
        self.assertEqual(chapter.display_name(), 'Chapter 06')
        self.assertIs(chapter.display_name('fra'), None)

        ebmlf.stream.close()

    def test_2_segment_normalize(self):
        "Test Segment.normalize() and writing."
        from ebml.container import File
        stream = BytesIO(self.file_data)
        ebmlf = File(stream)
        segment = ebmlf[1]

        # Check it correctly detected the Cluster block
        segment_full = self.read_file_data()[1]
        cluster = next(segment_full.children_named('Cluster'))
        self.assertEqual(list(segment.clusters_pos),
                         [(cluster.pos_relative, cluster.pos_end_relative)])

        second_tracks_elt = segment[-1]

        # This is the way it started:
        #1> 0    --23   | 0    --23   |  23 bytes: [ 0] SeekHead
        #1> 23   --37   | 23   --37   |  14 bytes: [ 1] Void
        #1> 37   --61   | 37   --61   |  24 bytes: [ 2] SeekHead
        #1> 61   --268  | 61   --268  | 207 bytes: [ 3] Info
        #1> 268  --1803 | 268  --1803 |1535 bytes: [ 4] Tracks
        #1> 1803 --2005 | 1803 --2005 | 202 bytes: [ 5] Attachments
        #1> 2005 --3701 | 2005 --3701 |1696 bytes: [ 6] Chapters
        #1> 3701 --3804 | 3701 --3804 | 103 bytes: [ 7] Void
        #1> 3804 --3823 | 3804 --3823 |  19 bytes: [ 8] Cluster
        #1> 3823 --3846 | 3823 --3846 |  23 bytes: [ 9] Cues
        #1> 3846 --3900 | 3846 --3900 |  54 bytes: [10] SeekHead
        #1> 3900 --10513| 3900 --10513|6613 bytes: [11] Tags
        #1> 10513--10579| 10513--10579|  66 bytes: [12] SeekHead
        #1> 10579--10657| 10579--10657|  78 bytes: [13] Tracks
        segment.normalize()
        segment.check_consistency()
        # This should be the result:
        #1> 0    --153  | 0    --153  | 153 bytes: [ 0] SeekHead
        #1> 153  --262  | 153  --262  | 109 bytes: [ 1] Void
        #1> 262  --1797 | 262  --1797 |1535 bytes: [ 2] Tracks
        #1> 1797 --1999 | 1797 --1999 | 202 bytes: [ 3] Attachments
        #1> 1999 --3695 | 1999 --3695 |1696 bytes: [ 4] Chapters
        #1> 3695 --3798 | 3695 --3798 | 103 bytes: [ 5] Void
        #1> 3798 --3817 | 3798 --3817 |  19 bytes: ***NO CHILD***
        #1> 3817 --3840 | 3817 --3840 |  23 bytes: [ 6] Cues
        #1> 3840 --3894 | 3840 --3894 |  54 bytes: [ 7] Void
        #1> 3894 --10507| 3894 --10507|6613 bytes: [ 8] Tags
        #1> 10507--10573| 10507--10573|  66 bytes: [ 9] Void
        #1> 10573--10651| 10573--10651|  78 bytes: [10] Tracks
        #1> 10651--10858| 10651--10858| 207 bytes: [11] Info

        #print(segment.print_space())
        #print(segment_full.print_space())
        self.assertEqual(segment.header_size, segment.header.numbytes_max)
        # Make sure it left a blank space where it should
        self.assertEqual(
            segment.find_le(segment.clusters_pos[0][0]).pos_end_relative,
            segment.clusters_pos[0][0])
        self.assertEqual(
            segment.find_ge(segment.clusters_pos[0][1]).pos_relative,
            segment.clusters_pos[0][1])
        # Test new SeekHead
        self.assertEqual(len(list(segment.seek_heads)), 1)
        for elt_name in ('Info', 'Tracks', 'Attachments', 'Chapters', 'Cues',
                         'Tags'):
            self.assertEqual(list(segment.seek_entries_byname[elt_name]),
                             [elt.pos_relative for elt in
                              segment.children_named(elt_name)])

        # This should swap Info and Tracks
        info_elt = next(segment.children_named('Info'))
        old_info_pos = info_elt.pos_relative
        tracks_elt = next(segment.children_named('Tracks'))
        tags_elt = next(segment.children_named('Tags'))
        segment.move_child(info_elt, tags_elt.pos_relative + 5)
        segment.move_child(tracks_elt, 5)
        segment.normalize()
        segment.check_consistency()
        #print(segment.print_space())
        # Info gets moved back even though there's a better fit at the end
        self.assertEqual(info_elt.pos_relative, segment[0].pos_end_relative)
        # Tracks gets moved where Info used to be
        self.assertEqual(tracks_elt.pos_relative, old_info_pos)

        # New state:
        # 0          --153         |         153 bytes: [ 0] SeekHead
        # 153        --360         |         207 bytes: [ 1] Info
        # 360        --1797        |        1437 bytes: [ 2] Void
        # 1797       --1999        |         202 bytes: [ 3] Attachments
        # 1999       --3695        |        1696 bytes: [ 4] Chapters
        # 3695       --3798        |         103 bytes: [ 5] Void
        # 3798       --3817        |          19 bytes: ***NO CHILD***
        # 3817       --3840        |          23 bytes: [ 6] Cues
        # 3840       --3894        |          54 bytes: [ 7] Void
        # 3894       --10507       |        6613 bytes: [ 8] Tags
        # 10507      --10573       |          66 bytes: [ 9] Void
        # 10573      --10651       |          78 bytes: [10] Tracks
        # 10651      --12186       |        1535 bytes: [11] Tracks

        cues_elt = next(segment.children_named('Cues'))
        tags_elt = next(segment.children_named('Tags'))
        att_elt = next(segment.children_named('Attachments'))
        segment.move_child(tags_elt, cues_elt.pos_relative + 10)
        segment.move_child(att_elt, cues_elt.pos_relative + 11)
        segment.move_child(tracks_elt, cues_elt.pos_relative + 12)
        segment.normalize()
        segment.check_consistency()
        self.assertEqual(tracks_elt.pos_relative, info_elt.pos_end_relative)
        self.assertEqual(tags_elt.pos_relative, cues_elt.pos_end_relative)
        self.assertEqual(att_elt.pos_relative,
                         second_tracks_elt.pos_end_relative)

        # New state
        # 0          --153         |         153 bytes: [ 0] SeekHead
        # 153        --360         |         207 bytes: [ 1] Info
        # 360        --1895        |        1535 bytes: [ 2] Tracks
        # 1895       --1999        |         104 bytes: [ 3] Void
        # 1999       --3695        |        1696 bytes: [ 4] Chapters
        # 3695       --3798        |         103 bytes: [ 5] Void
        # 3798       --3817        |          19 bytes: ***NO CHILD***
        # 3817       --3840        |          23 bytes: [ 6] Cues
        # 3840       --10453       |        6613 bytes: [ 7] Tags
        # 10453      --10573       |         120 bytes: [ 8] Void
        # 10573      --10651       |          78 bytes: [ 9] Tracks
        # 10651      --10853       |         202 bytes: [10] Attachments
        # 10853      --12186       |        1333 bytes: [11] Void

        chapters_elt = next(segment.children_named('Chapters'))
        self.assertFalse(chapters_elt.dirty)
        self.assertFalse(second_tracks_elt.dirty)

        # Test writing
        ebmlf.save_changes(ebmlf.stream)
        stream.seek(0)
        ebmlf2 = File(stream)
        self.assertTrue(ebmlf.intrinsic_equal(ebmlf2))
        self.assertEqual(
            self.file_data[cluster.pos_absolute:cluster.pos_end_absolute],
            stream.getvalue()[cluster.pos_absolute:cluster.pos_end_absolute])

    def test_3_segment_manipulate(self):
        "Test Segment child manipulation."
        from ebml.container import File
        from ebml.element import ElementMaster
        from ebml.data_elements import ElementTag, ElementSimpleTag
        stream = BytesIO(self.file_data)
        ebmlf = File(stream)
        segment = ebmlf[1]

        self.assertEqual(
            frozenset({att.file_name for att in segment.attachments}),
            frozenset({'myth_metadata.xml', 'cover.jpg'}))

        # Test del_attachment()
        segment.del_attachment('myth_metadata.xml')
        self.assertEqual(
            frozenset({att.file_name for att in segment.attachments}),
            frozenset({'cover.jpg'}))
        segment.del_attachment('cover.jpg')
        self.assertEqual(len(list(segment.children_named('Attachments'))), 0)

        # Test add_attachment()
        segment.add_attachment('test name', 'test mime', 'test descr')
        self.assertEqual(len(list(segment.children_named('Attachments'))), 1)
        self.assertEqual(len(list(segment.attachments)), 1)
        attachment = segment.attachments_byname['test name']
        self.assertEqual(attachment.file_name, 'test name')
        self.assertEqual(attachment.file_mime_type, 'test mime')
        self.assertEqual(attachment.file_description, 'test descr')
        self.assertEqual(attachment.file_data, b'')
        self.assertEqual(len(attachment.file_uid), 8)
        segment.add_attachment('test name 2', 'test mime 2')
        self.assertEqual(len(list(segment.children_named('Attachments'))), 1)
        self.assertEqual(len(list(segment.attachments)), 2)
        attachment = segment.attachments_byname['test name 2']
        self.assertEqual(attachment.file_description, None)
        segment.add_attachment('test name 2', 'test mime 3', 'test descr 2')
        self.assertEqual(len(list(segment.children_named('Attachments'))), 1)
        self.assertEqual(len(list(segment.attachments)), 2)
        attachment = segment.attachments_byname['test name 2']
        self.assertEqual(attachment.file_mime_type, 'test mime 3')
        self.assertEqual(attachment.file_description, 'test descr 2')

        # Test tag creation
        tag_groups = ElementMaster.new('Tags')
        tag_group = ElementTag.new_with_value(60, 'SEASON', tag_groups)
        ElementSimpleTag.new_with_value('PART_NUMBER', '5', tag_group)
        tag_group = ElementTag.new_with_value(50, 'MOVIE', tag_groups)
        ElementSimpleTag.new_with_value('TITLE', 'test title', tag_group)
        ElementSimpleTag.new_with_value('SUBTITLE', 'test subtitle', tag_group,
                                        lang='fre')
        segment.remove_children_named('Tags')
        segment.add_child(tag_groups, 0)

        segment.normalize()
        segment.check_consistency()

        tag_groups = list(segment.tags)
        self.assertEqual(len(tag_groups), 2)
        tag_group = tag_groups[0]
        self.assertEqual(tag_group.target_type_value, 60)
        self.assertEqual(tag_group.target_type, 'SEASON')
        tags = list(tag_group.simple_tags)
        self.assertEqual(len(tags), 1)
        tag = tags[0]
        self.assertEqual(tag.tag_name, 'PART_NUMBER')
        self.assertEqual(tag.string_val, '5')
        self.assertEqual(tag.language, ElementSimpleTag.default_lang)
        self.assertEqual(tag.default, True)
        tag_group = tag_groups[1]
        self.assertEqual(tag_group.target_type_value, 50)
        self.assertEqual(tag_group.target_type, 'MOVIE')
        tags = list(tag_group.simple_tags)
        self.assertEqual(len(tags), 2)
        self.assertEqual((tags[0].tag_name, tags[0].string_val),
                         ('TITLE', 'test title'))
        self.assertEqual((tags[1].tag_name, tags[1].string_val),
                         ('SUBTITLE', 'test subtitle'))
        self.assertEqual(tags[1].language, 'fre')
