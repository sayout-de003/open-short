"""Unit tests for Buffer API integration module."""

import unittest
from unittest.mock import MagicMock, patch
import buffer_publisher


class TestBufferPublisher(unittest.TestCase):
    def test_is_buffer_configured_true(self):
        with patch.dict("os.environ", {"BUFFER_ACCESS_TOKEN": "mock_token_123"}):
            self.assertTrue(buffer_publisher.is_buffer_configured())

    def test_is_buffer_configured_false(self):
        with patch.dict("os.environ", {"BUFFER_ACCESS_TOKEN": ""}, clear=True):
            with patch("buffer_publisher.ENV_PATH", "/tmp/nonexistent_env"):
                self.assertFalse(buffer_publisher.is_buffer_configured())

    @patch("buffer_publisher.requests.post")
    def test_get_account_info(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "account": {
                    "id": "acc_123",
                    "email": "test@example.com",
                    "organizations": [
                        {"id": "org_456", "name": "Test Org", "channelCount": 2}
                    ]
                }
            }
        }
        mock_post.return_value = mock_response

        account = buffer_publisher.get_account_info(token="mock_token_123")
        self.assertEqual(account["id"], "acc_123")
        self.assertEqual(account["email"], "test@example.com")
        self.assertEqual(len(account["organizations"]), 1)

    @patch("buffer_publisher.execute_graphql")
    def test_list_channels(self, mock_exec):
        def side_effect(query, variables=None, token=None):
            if "GetAccountInfo" in query:
                return {
                    "account": {
                        "id": "acc_123",
                        "organizations": [{"id": "org_456", "name": "Org 1"}]
                    }
                }
            elif "GetOrgChannels" in query:
                return {
                    "channels": [
                        {
                            "id": "ch_1",
                            "name": "MyInsta",
                            "service": "instagram",
                            "type": "business"
                        },
                        {
                            "id": "ch_2",
                            "name": "MyYouTube",
                            "service": "youtube",
                            "type": "channel"
                        }
                    ]
                }
            return {}

        mock_exec.side_effect = side_effect
        channels = buffer_publisher.list_channels(token="mock_token_123")
        self.assertEqual(len(channels), 2)
        self.assertEqual(channels[0]["service"], "instagram")
        self.assertEqual(channels[1]["service"], "youtube")

    @patch("buffer_publisher.execute_graphql")
    def test_create_post_success(self, mock_exec):
        mock_exec.return_value = {
            "createPost": {
                "__typename": "PostActionSuccess",
                "post": {
                    "id": "post_789",
                    "status": "buffer",
                    "channelId": "ch_1",
                    "channelService": "instagram"
                }
            }
        }

        res = buffer_publisher.create_post(
            channel_id="ch_1",
            text="Check out this awesome viral short!",
            video_url="https://example.com/video.mp4",
            service="instagram",
            token="mock_token_123"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["post"]["id"], "post_789")

    @patch("buffer_publisher.execute_graphql")
    def test_create_post_mutation_error(self, mock_exec):
        mock_exec.return_value = {
            "createPost": {
                "__typename": "InvalidInputError",
                "message": "Video length exceeds Instagram limit"
            }
        }

        with self.assertRaises(RuntimeError) as ctx:
            buffer_publisher.create_post(
                channel_id="ch_1",
                text="Test clip",
                token="mock_token_123"
            )
        self.assertIn("Instagram limit", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
