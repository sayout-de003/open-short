"""
template_library/models.py - Persistent database storage and registry for editing templates.

Supports SQLite backing (standard library, zero external dependencies) for standalone mode,
with full CRUD operations, JSON serialization, and automatic seeding of the 30+ niche presets.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "templates.db")


BUILTIN_TEMPLATES: List[Dict[str, Any]] = [
    # 1. Gaming & Streaming
    {
        "id": "gaming_cinematic",
        "name": "Gaming Cinematic",
        "category": "gaming",
        "style": "cinematic_action",
        "layout": "gameplay_center",
        "caption_preset": "impact",
        "transition_preset": "action_cuts",
        "audio_preset": "gaming_dynamic",
        "aspect_ratios": ["9:16", "16:9", "1:1"],
        "duration_range": [15, 60],
        "effects": ["impact_zoom", "motion_blur", "speed_ramp"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "streamer_reaction",
        "name": "Streamer Reaction",
        "category": "gaming",
        "style": "reaction_emphasis",
        "layout": "gameplay_with_facecam",
        "caption_preset": "highlight",
        "transition_preset": "reaction_zoom",
        "audio_preset": "streamer_vocal",
        "aspect_ratios": ["9:16", "16:9"],
        "duration_range": [15, 60],
        "effects": ["reaction_inset", "shake", "text_punch"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "esports_highlights",
        "name": "Esports Highlights",
        "category": "gaming",
        "style": "fast_paced",
        "layout": "gameplay_center",
        "caption_preset": "bold_box",
        "transition_preset": "whip_pan",
        "audio_preset": "esports_boost",
        "aspect_ratios": ["9:16"],
        "duration_range": [15, 45],
        "effects": ["kill_counter", "flash", "slow_mo_impact"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "gaming_meme",
        "name": "Gaming Meme",
        "category": "gaming",
        "style": "comedic",
        "layout": "stacked_gameplay",
        "caption_preset": "comic",
        "transition_preset": "cut",
        "audio_preset": "meme_sfx",
        "aspect_ratios": ["9:16"],
        "duration_range": [10, 40],
        "effects": ["sound_bites", "funny_zoom", "freeze_frame"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "streamer_stacked_top",
        "name": "Streamer Top Cam (Stacked)",
        "category": "gaming",
        "style": "top_cam_split",
        "layout": "stacked_top_cam",
        "caption_preset": "highlight",
        "transition_preset": "action_cuts",
        "audio_preset": "streamer_dynamic",
        "aspect_ratios": ["9:16"],
        "duration_range": [15, 60],
        "effects": ["top_cam_crop", "bottom_gameplay", "divider_accent"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "gta_story",
        "name": "GTA Story",
        "category": "gaming",
        "style": "cinematic_story",
        "layout": "gameplay_center",
        "caption_preset": "cinematic_sub",
        "transition_preset": "fade_black",
        "audio_preset": "atmospheric",
        "aspect_ratios": ["9:16", "16:9"],
        "duration_range": [20, 60],
        "effects": ["vignette", "letterbox", "slow_zoom"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "gaming_fails",
        "name": "Gaming Fails",
        "category": "gaming",
        "style": "fail_compilation",
        "layout": "gameplay_center",
        "caption_preset": "red_bold",
        "transition_preset": "record_scratch",
        "audio_preset": "comedic_fail",
        "aspect_ratios": ["9:16"],
        "duration_range": [10, 35],
        "effects": ["bw_pause", "record_scratch", "zoom_on_fail"],
        "is_builtin": True,
        "editable": True,
    },

    # 2. Podcast & Interviews
    {
        "id": "podcast_kinetic",
        "name": "Podcast Kinetic",
        "category": "podcast",
        "style": "kinetic_typography",
        "layout": "talking_head_center",
        "caption_preset": "karaoke",
        "transition_preset": "subtle_cut",
        "audio_preset": "voice_clarity",
        "aspect_ratios": ["9:16"],
        "duration_range": [25, 75],
        "effects": ["word_pop", "blurred_backdrop"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "podcast_split",
        "name": "Podcast Split Screen",
        "category": "podcast",
        "style": "interview_split",
        "layout": "split_two_speaker",
        "caption_preset": "centered_clean",
        "transition_preset": "speaker_focus",
        "audio_preset": "dual_dialogue",
        "aspect_ratios": ["9:16"],
        "duration_range": [30, 90],
        "effects": ["speaker_border", "name_tags"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "podcast_cinematic",
        "name": "Podcast Cinematic",
        "category": "podcast",
        "style": "deep_talk",
        "layout": "talking_head_center",
        "caption_preset": "minimal_serif",
        "transition_preset": "slow_dissolve",
        "audio_preset": "studio_warmth",
        "aspect_ratios": ["9:16", "16:9"],
        "duration_range": [30, 90],
        "effects": ["dark_backdrop", "film_grain"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "podcast_reaction",
        "name": "Podcast Reaction",
        "category": "podcast",
        "style": "banter",
        "layout": "active_speaker_switch",
        "caption_preset": "yellow_pop",
        "transition_preset": "fast_cut",
        "audio_preset": "laughter_boost",
        "aspect_ratios": ["9:16"],
        "duration_range": [20, 60],
        "effects": ["punch_in_reaction"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "controversial_opinion",
        "name": "Controversial Opinion",
        "category": "podcast",
        "style": "dramatic_hook",
        "layout": "talking_head_center",
        "caption_preset": "impact_headline",
        "transition_preset": "hard_cut",
        "audio_preset": "tension_riser",
        "aspect_ratios": ["9:16"],
        "duration_range": [20, 60],
        "effects": ["hook_banner", "dramatic_zoom"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "educational_insight",
        "name": "Educational Insight",
        "category": "podcast",
        "style": "thought_leadership",
        "layout": "talking_head_center",
        "caption_preset": "clean_subtitle",
        "transition_preset": "slide_left",
        "audio_preset": "clear_speech",
        "aspect_ratios": ["9:16"],
        "duration_range": [30, 80],
        "effects": ["key_takeaway_card"],
        "is_builtin": True,
        "editable": True,
    },

    # 3. Education & Tutorials
    {
        "id": "edu_explainer",
        "name": "Explainer",
        "category": "educational",
        "style": "visual_explanation",
        "layout": "screen_and_presenter",
        "caption_preset": "bullet_points",
        "transition_preset": "smooth_slide",
        "audio_preset": "narrator_balance",
        "aspect_ratios": ["9:16", "16:9"],
        "duration_range": [30, 90],
        "effects": ["diagram_callout", "progress_bar"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "code_tutorial",
        "name": "Code Tutorial",
        "category": "educational",
        "style": "developer_focus",
        "layout": "code_viewport_focus",
        "caption_preset": "code_syntax_highlight",
        "transition_preset": "code_pan",
        "audio_preset": "clear_narration",
        "aspect_ratios": ["9:16", "16:9"],
        "duration_range": [25, 90],
        "effects": ["magnifier_zoom", "line_highlight"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "whiteboard",
        "name": "Whiteboard",
        "category": "educational",
        "style": "whiteboard_draw",
        "layout": "whiteboard_canvas",
        "caption_preset": "clean_sans",
        "transition_preset": "draw_reveal",
        "audio_preset": "lecture_audio",
        "aspect_ratios": ["9:16", "16:9"],
        "duration_range": [30, 90],
        "effects": ["pen_tracker", "concept_circle"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "step_by_step",
        "name": "Step by Step",
        "category": "educational",
        "style": "structured_steps",
        "layout": "step_card_overlay",
        "caption_preset": "step_numbering",
        "transition_preset": "step_swipe",
        "audio_preset": "instructional",
        "aspect_ratios": ["9:16"],
        "duration_range": [30, 90],
        "effects": ["numbered_badge", "checklist_tick"],
        "is_builtin": True,
        "editable": True,
    },

    # 4. Commentary & Vlogs
    {
        "id": "reaction_punch",
        "name": "Reaction Punch",
        "category": "commentary",
        "style": "energetic_reaction",
        "layout": "presenter_and_clip",
        "caption_preset": "dynamic_pop",
        "transition_preset": "snap_zoom",
        "audio_preset": "reaction_mix",
        "aspect_ratios": ["9:16"],
        "duration_range": [15, 60],
        "effects": ["side_by_side_inset", "reaction_emoji"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "story_vlog",
        "name": "Story Vlog",
        "category": "commentary",
        "style": "cinematic_vlog",
        "layout": "vlog_framing",
        "caption_preset": "warm_modern",
        "transition_preset": "film_dissolve",
        "audio_preset": "lofi_background",
        "aspect_ratios": ["9:16"],
        "duration_range": [20, 60],
        "effects": ["color_grade", "light_leak"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "commentary_news",
        "name": "Commentary News",
        "category": "commentary",
        "style": "headline_review",
        "layout": "news_anchor_inset",
        "caption_preset": "bold_headline",
        "transition_preset": "lower_third_slide",
        "audio_preset": "broadcast_vocal",
        "aspect_ratios": ["9:16"],
        "duration_range": [20, 60],
        "effects": ["breaking_news_bar", "screenshot_popup"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "lifestyle_minimal",
        "name": "Lifestyle Minimal",
        "category": "commentary",
        "style": "aesthetic_clean",
        "layout": "full_frame_soft",
        "caption_preset": "minimal_caps",
        "transition_preset": "fade_white",
        "audio_preset": "acoustic_gentle",
        "aspect_ratios": ["9:16"],
        "duration_range": [15, 45],
        "effects": ["soft_glow", "smooth_tracking"],
        "is_builtin": True,
        "editable": True,
    },

    # 5. Fitness & Sports
    {
        "id": "fitness_intense",
        "name": "Fitness Intense",
        "category": "fitness",
        "style": "high_energy",
        "layout": "full_athlete_frame",
        "caption_preset": "heavy_impact",
        "transition_preset": "glitch_flash",
        "audio_preset": "bass_boost",
        "aspect_ratios": ["9:16"],
        "duration_range": [15, 50],
        "effects": ["rep_counter", "timer_countdown"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "sports_highlight",
        "name": "Sports Highlight",
        "category": "fitness",
        "style": "athlete_clutch",
        "layout": "wide_field_track",
        "caption_preset": "score_ticker",
        "transition_preset": "speed_ramp",
        "audio_preset": "stadium_cheer",
        "aspect_ratios": ["9:16", "16:9"],
        "duration_range": [15, 45],
        "effects": ["instant_replay", "circle_spotlight"],
        "is_builtin": True,
        "editable": True,
    },

    # 6. Business & Entrepreneurship
    {
        "id": "business_premium",
        "name": "Business Premium",
        "category": "business",
        "style": "executive",
        "layout": "talking_head_center",
        "caption_preset": "financial_clean",
        "transition_preset": "corporate_wipe",
        "audio_preset": "crisp_podcast",
        "aspect_ratios": ["9:16"],
        "duration_range": [25, 75],
        "effects": ["stat_counter", "brand_badge"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "business_explainer",
        "name": "Business Explainer",
        "category": "business",
        "style": "data_insight",
        "layout": "chart_and_presenter",
        "caption_preset": "metric_callout",
        "transition_preset": "slide_cards",
        "audio_preset": "confident_narration",
        "aspect_ratios": ["9:16"],
        "duration_range": [30, 85],
        "effects": ["graph_overlay", "quote_card"],
        "is_builtin": True,
        "editable": True,
    },

    # 7. Storytelling & Entertainment
    {
        "id": "cinematic_story",
        "name": "Cinematic Story",
        "category": "storytelling",
        "style": "narrative_drama",
        "layout": "cinematic_widescreen_boxed",
        "caption_preset": "movie_subs",
        "transition_preset": "slow_burn",
        "audio_preset": "cinematic_orchestral",
        "aspect_ratios": ["9:16"],
        "duration_range": [30, 90],
        "effects": ["letterbox_235", "subtle_dolly"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "mystery_suspense",
        "name": "Mystery Suspense",
        "category": "storytelling",
        "style": "true_crime_suspense",
        "layout": "dark_frame",
        "caption_preset": "typewriter",
        "transition_preset": "flicker",
        "audio_preset": "drone_tension",
        "aspect_ratios": ["9:16"],
        "duration_range": [25, 80],
        "effects": ["redact_reveal", "film_dust"],
        "is_builtin": True,
        "editable": True,
    },

    # 8. Travel & Food
    {
        "id": "travel_cinematic",
        "name": "Travel Cinematic",
        "category": "travel_food",
        "style": "scenic_wanderlust",
        "layout": "landscape_fill",
        "caption_preset": "destination_tag",
        "transition_preset": "whip_zoom",
        "audio_preset": "ambient_soundtrack",
        "aspect_ratios": ["9:16"],
        "duration_range": [15, 60],
        "effects": ["geo_pin", "color_pop"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "food_recipe",
        "name": "Food Recipe",
        "category": "travel_food",
        "style": "cooking_step",
        "layout": "top_down_view",
        "caption_preset": "ingredient_badge",
        "transition_preset": "sizzle_cut",
        "audio_preset": "asmr_cooking",
        "aspect_ratios": ["9:16"],
        "duration_range": [20, 60],
        "effects": ["measurement_card", "recipe_step_bar"],
        "is_builtin": True,
        "editable": True,
    },

    # 9. Music & Dance
    {
        "id": "music_visualizer",
        "name": "Music Visualizer",
        "category": "music_dance",
        "style": "audio_reactive",
        "layout": "centered_visualizer",
        "caption_preset": "lyric_pulse",
        "transition_preset": "beat_snap",
        "audio_preset": "full_music",
        "aspect_ratios": ["9:16"],
        "duration_range": [15, 60],
        "effects": ["audio_wave", "glow_pulse"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "dance_beat_sync",
        "name": "Dance Beat Sync",
        "category": "music_dance",
        "style": "choreography_sync",
        "layout": "full_dancer_track",
        "caption_preset": "minimal_corner",
        "transition_preset": "impact_cut",
        "audio_preset": "beat_emphasis",
        "aspect_ratios": ["9:16"],
        "duration_range": [15, 45],
        "effects": ["speed_ramp_drop", "flash_on_beat"],
        "is_builtin": True,
        "editable": True,
    },

    # 10. News & Documentary
    {
        "id": "news_bulletin",
        "name": "News Bulletin",
        "category": "news_documentary",
        "style": "breaking_report",
        "layout": "broadcast_lower_third",
        "caption_preset": "ticker_tape",
        "transition_preset": "broadcast_wipe",
        "audio_preset": "studio_news",
        "aspect_ratios": ["9:16"],
        "duration_range": [20, 60],
        "effects": ["live_indicator", "news_ticker"],
        "is_builtin": True,
        "editable": True,
    },
    {
        "id": "mini_documentary",
        "name": "Mini Documentary",
        "category": "news_documentary",
        "style": "journalistic",
        "layout": "archival_and_narration",
        "caption_preset": "documentary_sans",
        "transition_preset": "ken_burns_pan",
        "audio_preset": "dramatic_score",
        "aspect_ratios": ["9:16", "16:9"],
        "duration_range": [30, 90],
        "effects": ["sepia_transition", "quote_callout"],
        "is_builtin": True,
        "editable": True,
    },
]


class TemplateStore:
    """Manages SQLite storage for template presets."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS template_presets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    style TEXT NOT NULL,
                    layout TEXT NOT NULL,
                    caption_preset TEXT NOT NULL,
                    transition_preset TEXT NOT NULL,
                    audio_preset TEXT NOT NULL,
                    aspect_ratios_json TEXT NOT NULL,
                    duration_min REAL NOT NULL,
                    duration_max REAL NOT NULL,
                    effects_json TEXT NOT NULL,
                    is_builtin INTEGER NOT NULL DEFAULT 0,
                    editable INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS ix_template_category ON template_presets(category)")
            conn.commit()

        # Seed defaults if empty
        self._seed_builtins()

    def _seed_builtins(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = time.time()
            for t in BUILTIN_TEMPLATES:
                cursor.execute("""
                    INSERT INTO template_presets (
                        id, name, category, style, layout,
                        caption_preset, transition_preset, audio_preset,
                        aspect_ratios_json, duration_min, duration_max,
                        effects_json, is_builtin, editable, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        category = excluded.category,
                        style = excluded.style,
                        layout = excluded.layout,
                        caption_preset = excluded.caption_preset,
                        transition_preset = excluded.transition_preset,
                        audio_preset = excluded.audio_preset,
                        aspect_ratios_json = excluded.aspect_ratios_json,
                        duration_min = excluded.duration_min,
                        duration_max = excluded.duration_max,
                        effects_json = excluded.effects_json,
                        updated_at = excluded.updated_at
                    WHERE is_builtin = 1
                """, (
                    t["id"],
                    t["name"],
                    t["category"],
                    t["style"],
                    t["layout"],
                    t["caption_preset"],
                    t["transition_preset"],
                    t["audio_preset"],
                    json.dumps(t.get("aspect_ratios", ["9:16"])),
                    float(t.get("duration_range", [15, 60])[0]),
                    float(t.get("duration_range", [15, 60])[1]),
                    json.dumps(t.get("effects", [])),
                    1,
                    1 if t.get("editable", True) else 0,
                    now,
                    now,
                ))
            conn.commit()

    def list_templates(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute("SELECT * FROM template_presets WHERE category = ? ORDER BY is_builtin DESC, name ASC", (category.lower(),))
            else:
                cursor.execute("SELECT * FROM template_presets ORDER BY category ASC, is_builtin DESC, name ASC")
            rows = cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM template_presets WHERE id = ?", (template_id,))
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None

    def save_template(self, data: Dict[str, Any]) -> Dict[str, Any]:
        template_id = str(data.get("id") or "").strip().lower()
        if not template_id:
            raise ValueError("Template preset must have a valid non-empty 'id'")

        now = time.time()
        duration_range = data.get("duration_range", [15.0, 60.0])
        dur_min = float(duration_range[0])
        dur_max = float(duration_range[1])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_builtin, created_at FROM template_presets WHERE id = ?", (template_id,))
            existing = cursor.fetchone()

            is_builtin = existing["is_builtin"] if existing else (1 if data.get("is_builtin") else 0)
            created_at = existing["created_at"] if existing else now

            cursor.execute("""
                INSERT INTO template_presets (
                    id, name, category, style, layout,
                    caption_preset, transition_preset, audio_preset,
                    aspect_ratios_json, duration_min, duration_max,
                    effects_json, is_builtin, editable, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    style = excluded.style,
                    layout = excluded.layout,
                    caption_preset = excluded.caption_preset,
                    transition_preset = excluded.transition_preset,
                    audio_preset = excluded.audio_preset,
                    aspect_ratios_json = excluded.aspect_ratios_json,
                    duration_min = excluded.duration_min,
                    duration_max = excluded.duration_max,
                    effects_json = excluded.effects_json,
                    editable = excluded.editable,
                    updated_at = excluded.updated_at
            """, (
                template_id,
                str(data.get("name", template_id)),
                str(data.get("category", "general")),
                str(data.get("style", "standard")),
                str(data.get("layout", "auto")),
                str(data.get("caption_preset", "default")),
                str(data.get("transition_preset", "cut")),
                str(data.get("audio_preset", "standard")),
                json.dumps(data.get("aspect_ratios", ["9:16"])),
                dur_min,
                dur_max,
                json.dumps(data.get("effects", [])),
                is_builtin,
                1 if data.get("editable", True) else 0,
                created_at,
                now,
            ))
            conn.commit()

        return self.get_template(template_id)  # type: ignore

    def delete_template(self, template_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_builtin FROM template_presets WHERE id = ?", (template_id,))
            row = cursor.fetchone()
            if not row:
                return False
            if row["is_builtin"]:
                raise ValueError("Cannot delete built-in template preset.")
            cursor.execute("DELETE FROM template_presets WHERE id = ?", (template_id,))
            conn.commit()
            return True

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "style": row["style"],
            "layout": row["layout"],
            "caption_preset": row["caption_preset"],
            "transition_preset": row["transition_preset"],
            "audio_preset": row["audio_preset"],
            "aspect_ratios": json.loads(row["aspect_ratios_json"]),
            "duration_range": [row["duration_min"], row["duration_max"]],
            "effects": json.loads(row["effects_json"]),
            "is_builtin": bool(row["is_builtin"]),
            "editable": bool(row["editable"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


# Global store instance for convenience
_default_store: Optional[TemplateStore] = None


def get_template_store() -> TemplateStore:
    global _default_store
    if _default_store is None:
        _default_store = TemplateStore()
    return _default_store
