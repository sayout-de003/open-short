"""Unit tests for YouTube Data API v3 direct publishing module."""

import os
import unittest
from unittest.mock import MagicMock, patch

import pytest
import youtube_publisher


class TestYouTubePublisher(unittest.TestCase):
    def test_prepare_shorts_title(self):
        title = "Incredible Clutch Play"
        formatted = youtube_publisher.prepare_shorts_title(title)
        self.assertIn("#Shorts", formatted)
        self.assertTrue(len(formatted) <= 100)

    def test_prepare_shorts_title_already_has_tag(self):
        title = "Epic Win #Shorts"
        formatted = youtube_publisher.prepare_shorts_title(title)
        self.assertEqual(formatted, "Epic Win #Shorts")

    def test_prepare_shorts_description(self):
        desc = "Check out this gaming clip"
        formatted = youtube_publisher.prepare_shorts_description(desc)
        self.assertIn("#Shorts", formatted)

    def test_is_direct_youtube_configured_false_when_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(youtube_publisher.is_direct_youtube_configured())

    def test_is_direct_youtube_configured_true_with_oauth(self):
        env = {
            "YOUTUBE_CLIENT_ID": "client_123",
            "YOUTUBE_CLIENT_SECRET": "secret_456",
            "YOUTUBE_REFRESH_TOKEN": "refresh_789",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(youtube_publisher.is_direct_youtube_configured())

    def test_is_direct_youtube_configured_true_with_access_token(self):
        with patch.dict(os.environ, {"YOUTUBE_ACCESS_TOKEN": "ya29.xyz"}, clear=True):
            self.assertTrue(youtube_publisher.is_direct_youtube_configured())

    @patch("youtube_publisher.get_youtube_service")
    def test_upload_video_mock(self, mock_get_service):
        mock_service = MagicMock()
        mock_videos = MagicMock()
        mock_insert = MagicMock()

        # Mock resumable next_chunk loop: returns (status, None), then (status, response)
        mock_status = MagicMock()
        mock_status.progress.return_value = 1.0

        mock_insert.next_chunk.side_effect = [
            (mock_status, None),
            (mock_status, {"id": "test_video_123"}),
        ]
        mock_videos.insert.return_value = mock_insert
        mock_service.videos.return_value = mock_videos
        mock_get_service.return_value = mock_service

        # Create dummy file
        dummy_file = "/tmp/test_dummy_video.mp4"
        with open(dummy_file, "wb") as f:
            f.write(b"dummy mp4 content")

        try:
            result = youtube_publisher.upload_video_to_youtube(
                file_path=dummy_file,
                title="Amazing Round",
                description="Sub for more",
                privacy_status="unlisted",
            )
            self.assertTrue(result["success"])
            self.assertEqual(result["video_id"], "test_video_123")
            self.assertEqual(result["url"], "https://youtu.be/test_video_123")
            self.assertEqual(result["shorts_url"], "https://www.youtube.com/shorts/test_video_123")
            self.assertEqual(result["privacy_status"], "unlisted")
        finally:
            if os.path.exists(dummy_file):
                os.remove(dummy_file)
