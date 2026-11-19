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
