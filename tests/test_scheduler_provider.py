import os
import unittest
from unittest.mock import patch, MagicMock
import scheduler


class TestSchedulerProvider(unittest.TestCase):
    def setUp(self):
        self.tmp_sched_file = "/tmp/test_schedules.json"
        self._orig_file = scheduler.SCHEDULE_FILE
        scheduler.SCHEDULE_FILE = self.tmp_sched_file
        if os.path.exists(self.tmp_sched_file):
            os.remove(self.tmp_sched_file)

    def tearDown(self):
        if os.path.exists(self.tmp_sched_file):
            os.remove(self.tmp_sched_file)
        scheduler.SCHEDULE_FILE = self._orig_file

    def test_schedule_clip_post_with_buffer_provider(self):
        entry = scheduler.schedule_clip_post(
            job_id="job_abc",
            clip_index=1,
            scheduled_at="2026-11-20T10:00:00Z",
            platforms=["youtube", "instagram"],
            provider="buffer",
            title="Cool Clip",
        )
        self.assertEqual(entry["provider"], "buffer")
        self.assertEqual(entry["job_id"], "job_abc")
        self.assertEqual(entry["clip_index"], 1)
        self.assertEqual(entry["status"], "pending")

        schedules = scheduler.list_schedules(job_id="job_abc")
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]["provider"], "buffer")

    def test_auto_schedule_project_with_provider(self):
        clips = [{"title": "C1"}, {"title": "C2"}, {"title": "C3"}]
        entries = scheduler.auto_schedule_project(
            job_id="job_xyz",
            clips=clips,
            interval_hours=2.0,
            provider="youtube",
        )
        self.assertEqual(len(entries), 3)
        for e in entries:
            self.assertEqual(e["provider"], "youtube")

    def test_generate_smart_jitter_schedule_10_clips_varied_times(self):
        # Verify 10 clips get scheduled with varying hours and jitter across days
        times = scheduler.generate_smart_jitter_schedule(
            clip_count=10,
            start_time="2026-11-20T08:00:00Z",
            posts_per_day=1,
            jitter_seed="test_job_123",
        )
        self.assertEqual(len(times), 10)
        # Check that consecutive days do not have identical hour/minute
        for i in range(len(times) - 1):
            t1, t2 = times[i], times[i + 1]
            self.assertTrue(t2 > t1)
            # Consecutive days should have different hours
            self.assertNotEqual(t1.hour, t2.hour)

    def test_auto_schedule_dual_platforms_smart_jitter(self):
        clips = [{"title": f"Viral Short {i}"} for i in range(10)]
        entries = scheduler.auto_schedule_project(
            job_id="job_dual",
            clips=clips,
            scheduling_mode="smart_jitter",
            posts_per_day=1,
            platforms=["instagram", "youtube"],
            provider="buffer",
        )
        self.assertEqual(len(entries), 10)
        for e in entries:
            self.assertEqual(e["provider"], "buffer")
            self.assertEqual(e["platforms"], ["instagram", "youtube"])
            self.assertEqual(e["scheduling_mode"], "smart_jitter")

    def test_auto_schedule_buffer_queue_mode(self):
        clips = [{"title": f"Clip {i}"} for i in range(5)]
        entries = scheduler.auto_schedule_project(
            job_id="job_queue",
            clips=clips,
            scheduling_mode="buffer_queue",
            platforms=["instagram", "youtube"],
            provider="buffer",
        )
        self.assertEqual(len(entries), 5)
        for e in entries:
            self.assertEqual(e["scheduling_mode"], "buffer_queue")

    def test_buffer_publisher_filter_channels(self):
        import buffer_publisher
        channels = [
            {"id": "ch1", "service": "instagram", "name": "IG Account"},
            {"id": "ch2", "service": "youtube", "name": "YT Account"},
            {"id": "ch3", "service": "tiktok", "name": "TikTok Account"},
            {"id": "ch4", "service": "instagram", "isDisconnected": True},
        ]
        matched = buffer_publisher.filter_channels_for_services(channels, ["instagram", "youtube"])
        self.assertEqual(len(matched), 2)
        self.assertEqual({c["id"] for c in matched}, {"ch1", "ch2"})
