"""Unit tests for YouTube and Twitch discovery adapters."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from gaming_intelligence.discovery import TwitchDiscoveryAdapter, YouTubeDiscoveryAdapter


@patch("gaming_intelligence.discovery.requests.get")
def test_youtube_api_discovery_separates_live_and_vod(mock_get) -> None:
    search_live = MagicMock()
    search_live.json.return_value = {"items": [{"id": {"videoId": "live_1"}}]}
    search_vod = MagicMock()
    search_vod.json.return_value = {"items": [{"id": {"videoId": "vod_1"}}]}
    videos_live = MagicMock()
    videos_live.json.return_value = {
        "items": [{
            "id": "live_1",
            "snippet": {"title": "GTA 6 Live", "channelId": "c1", "channelTitle": "Ch1", "liveBroadcastContent": "live"},
            "statistics": {"viewCount": "1000"},
            "contentDetails": {"duration": "PT0S"},
            "liveStreamingDetails": {"concurrentViewers": "5400"},
        }]
    }
    videos_vod = MagicMock()
    videos_vod.json.return_value = {
        "items": [{
            "id": "vod_1",
            "snippet": {"title": "GTA 6 VOD", "channelId": "c2", "channelTitle": "Ch2", "liveBroadcastContent": "none"},
            "statistics": {"viewCount": "120000", "likeCount": "8000", "commentCount": "400"},
            "contentDetails": {"duration": "PT45M10S"},
            "liveStreamingDetails": {},
        }]
    }
    mock_get.side_effect = [search_live, videos_live, search_vod, videos_vod]

    adapter = YouTubeDiscoveryAdapter(api_key="yt_key")
    results = adapter.discover("GTA 6", limit=5)

    assert len(results) == 2
    assert results[0].source_type == "live"
    assert results[0].concurrent_viewers == 5400
    assert results[1].source_type == "vod"
    assert results[1].duration_sec == 2710.0
    assert results[1].metadata_confidence == 100.0


@patch("gaming_intelligence.discovery.requests.get")
@patch("gaming_intelligence.discovery.requests.post")
def test_twitch_discovery_resolves_game_id_and_dedups_vods(mock_post, mock_get) -> None:
    tok = MagicMock()
    tok.json.return_value = {"access_token": "tw_tok"}
    mock_post.return_value = tok

    games = MagicMock()
    games.json.return_value = {"data": [{"id": "999", "name": "Grand Theft Auto VI"}]}
    streams = MagicMock()
    streams.json.return_value = {
        "data": [{
            "id": "s1", "user_id": "u1", "user_login": "streamer1", "user_name": "Streamer1",
            "title": "Live GTA", "viewer_count": 3200, "started_at": "2026-11-20T10:00:00Z", "game_name": "GTA 6",
        }]
    }
    vods_views = MagicMock()
    vods_views.json.return_value = {
        "data": [{
            "id": "v1", "user_id": "u2", "user_name": "Streamer2",
            "title": "VOD 1", "view_count": 45000, "duration": "2h10m5s", "created_at": "2026-11-19T10:00:00Z",
        }]
    }
    vods_trending = MagicMock()
    vods_trending.json.return_value = {
        "data": [{
            "id": "v1", "user_id": "u2", "user_name": "Streamer2",
            "title": "VOD 1", "view_count": 45000, "duration": "2h10m5s", "created_at": "2026-11-19T10:00:00Z",
        }]
    }
    mock_get.side_effect = [games, streams, vods_views, vods_trending]

    adapter = TwitchDiscoveryAdapter("cid", "csec")
    results = adapter.discover("GTA 6", limit=5)

    assert len(results) == 2
    assert results[0].source_type == "live"
    assert results[1].source_type == "vod"
    assert results[1].duration_sec == 7805.0
