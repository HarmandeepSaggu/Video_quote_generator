#!/usr/bin/env python3
"""Add one restrained, warm-ivory quote overlay to existing videos."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - exercised by an installation error
    raise SystemExit("Pillow is required. Install project dependencies with: python -m pip install -r requirements.txt") from exc

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover - exercised by an installation error
    raise SystemExit("python-dotenv is required. Install project dependencies with: python -m pip install -r requirements.txt") from exc


LOGGER = logging.getLogger("astra")
SUPPORTED_EXTENSIONS = {".mp4", ".mov"}
DEFAULT_CONFIG = {
    "input_dir": "input",
    "output_dir": "output",
    "recursive_scan": True,
    "quote_provider": "groq",
    "quote_model": "openai/gpt-oss-120b",
    "quote_category_distribution": {
        "misunderstood": 0.20,
        "overthinking": 0.16,
        "loneliness": 0.14,
        "letting_go": 0.14,
        "self_respect": 0.14,
        "healing": 0.12,
        "hard_truths": 0.10,
    },
    "quote_candidate_count": 4,
    "quote_min_words": 6,
    "quote_max_words": 22,
    "quote_min_score": 6.0,
    "quote_similarity_threshold": 0.78,
    "quote_history_file": ".quote_history.json",
    "quote_history_limit": 100,
    "font_path": "assets/fonts/CormorantGaramond-Variable.ttf",
    "font_weight": 600,
    "font_size": 34,
    "text_color": "#E8C547",
    "text_colors_by_folder": {
        "White Font": "#F2F0EB",
        "Yellow Font": "#F2D675",
    },
    "text_alignment": "left",
    "left_margin_percent": 13,
    "top_position_percent": 33,
    "right_margin_percent": 10,
    "line_spacing": 1.2,
    "max_line_characters": 42,
    "adaptive_position": False,
    "position_analysis_samples": 8,
    "vertical_safe_margin_percent": 12,
    "quote_end_symbols": ["—", ">>", ":)"],
    "text_shadow": False,
    "text_animation": "static",
    "preserve_source_audio": True,
    "preserve_source_duration": True,
    "preserve_source_resolution": True,
    "output_container": "mp4",
    "output_video_codec": "libx264",
    "output_audio_codec": "aac",
    "selection_state_file": ".video_selection_state.json",
    "publish_state_file": ".instagram_publish_state.json",
    "cloudinary_folder": "glimpse-of-thoughts/reels",
    "cloudinary_unsigned_upload": False,
    "instagram_api_version": "v21.0",
    "instagram_api_host": "",
    "instagram_caption": "",
    "instagram_hashtag_count": 7,
    "instagram_share_to_feed": True,
    "instagram_processing_timeout_seconds": 600,
    "instagram_poll_interval_seconds": 10,
    "dry_run": False,
    "strict": False,
    "ffmpeg_path": "",
    "ffprobe_path": "",
}

CATEGORY_DESCRIPTIONS = {
    "misunderstood": "feeling emotionally unseen, unheard, or misunderstood by people who should notice",
    "overthinking": "late-night thoughts, unanswered messages, imagined meanings, and mental spirals",
    "loneliness": "feeling alone while surrounded by people, or missing the feeling of being truly known",
    "letting_go": "heartbreak, changing relationships, acceptance, and releasing what no longer fits",
    "self_respect": "boundaries, self-worth, choosing peace, and refusing to abandon yourself for approval",
    "healing": "quiet recovery, hope, resilience, and learning to trust yourself again",
    "hard_truths": "honest observations about human behaviour, attachment, and relationships",
}

CATEGORY_KEYWORDS = {
    "misunderstood": {"understand", "heard", "unseen", "explain", "notice", "listen", "known"},
    "overthinking": {"mind", "think", "thought", "replay", "silence", "message", "late", "question"},
    "loneliness": {"alone", "lonely", "room", "people", "known", "company", "presence", "miss"},
    "letting_go": {"let", "letting", "leave", "past", "end", "ended", "return", "release", "change"},
    "self_respect": {"respect", "boundary", "boundaries", "peace", "chasing", "choose", "choosing", "yourself"},
    "healing": {"heal", "healing", "calm", "trust", "hope", "grow", "progress", "recovery"},
    "hard_truths": {"people", "love", "needed", "priority", "access", "truth", "reason", "hurt"},
}

SOCIAL_CAPTION_OPTIONS = {
    "misunderstood": ("Still Unseen 🕯️", "Unheard Again 🫥", "Seen By Few 👁️"),
    "overthinking": ("Mind Won't Rest 🌀", "Lost In Thought 🌙", "Quiet Mind Please 🫧"),
    "loneliness": ("Alone Together 🌙", "Quietly Missing You 🕯️", "Crowded But Lonely 🫥"),
    "letting_go": ("Release The Weight 🍂", "Learning To Let Go 🌅", "Peace After Goodbye 🕊️"),
    "self_respect": ("Choose Your Peace 🕊️", "No More Shrinking 🖤", "Boundaries Feel Good 🧱"),
    "healing": ("Healing Quietly 🌱", "Becoming Whole Again 🌤️", "Softly Finding Peace 🌿"),
    "hard_truths": ("Truth Hits Different 🖤", "Love Needs Honesty 🪞", "Some Truths Hurt 🥀"),
}

SOCIAL_HASHTAGS_BY_CATEGORY = {
    "misunderstood": ("#FeelingUnseen", "#DeepFeelings", "#SilentStruggles"),
    "overthinking": ("#Overthinking", "#LateNightThoughts", "#MindSpiral"),
    "loneliness": ("#LonelyThoughts", "#FeelingAlone", "#InnerThoughts"),
    "letting_go": ("#LettingGo", "#HealingJourney", "#MovingOn"),
    "self_respect": ("#SelfRespect", "#ProtectYourPeace", "#KnowYourWorth"),
    "healing": ("#HealingJourney", "#InnerHealing", "#ChoosePeace"),
    "hard_truths": ("#HardTruths", "#RelationshipTruths", "#RealTalk"),
}

SOCIAL_HASHTAG_SIGNALS = (
    ("#UnspokenFeelings", {"understand", "heard", "unseen", "unheard", "explain"}),
    ("#Overthinking", {"mind", "think", "thought", "replay", "question", "wondering"}),
    ("#LateNightThoughts", {"midnight", "night", "awake", "silence", "text"}),
    ("#HeartbreakHealing", {"heartbreak", "goodbye", "broke", "broken", "absence"}),
    ("#EmotionalBoundaries", {"boundary", "boundaries", "shrink", "approval", "chasing"}),
    ("#QuietGrowth", {"heal", "healing", "rebuild", "grow", "steadier", "progress"}),
    ("#RelationshipQuotes", {"love", "attachment", "people", "conversation", "relationship"}),
)

SOCIAL_GENERAL_HASHTAGS = ("#RelatableReels", "#DeepQuotes", "#WordsThatHeal", "#TheSilentJournal")

# These are deliberately original, reflective fallback quotes. They are not
# attributed to anybody and keep local mode useful without an API key.
LOCAL_QUOTES_BY_CATEGORY = {
    "misunderstood": (
        "I stopped explaining myself when being misunderstood became easier for them than listening.",
        "Some people hear your words but never notice the feeling underneath them.",
        "I was not asking to be fixed; I was asking to be understood.",
        "The loneliest conversations are the ones where you explain everything and still feel unseen.",
        "I can describe the facts and still feel like nobody heard what they meant to me.",
    ),
    "overthinking": (
        "My mind turns quiet moments into questions nobody else knows I am asking.",
        "I replay simple conversations until they sound like proof that I mattered less.",
        "Late at night, every unanswered message feels louder than it should.",
        "I keep preparing for endings that nobody said were coming.",
        "I know the answer is probably simple; my mind keeps looking for the wound beneath it.",
    ),
    "loneliness": (
        "You can feel alone in a room full of people who only know your easy version.",
        "The hardest loneliness is having people around you and nowhere to place your honest feelings.",
        "I learned that being included is not the same as being known.",
        "Sometimes I miss being understood more than I miss the person.",
        "I do not need more people; I need one place where I can stop pretending.",
    ),
    "letting_go": (
        "Letting go hurt less when I stopped confusing familiar pain with love.",
        "Some relationships end long before either person finds the courage to say it.",
        "I still care, but I no longer need the past to return what it took.",
        "Healing began when I stopped asking old memories to become new promises.",
        "Missing someone does not mean returning to the version of yourself you lost with them.",
    ),
    "self_respect": (
        "Self-respect is leaving quietly when staying requires you to keep abandoning yourself.",
        "I stopped chasing clarity from people who benefited from keeping me confused.",
        "Boundaries are what remain when you finally believe your own discomfort.",
        "Growing up meant choosing peace over being understood by everyone.",
        "I became easier to love when I stopped making myself smaller to keep someone close.",
    ),
    "healing": (
        "Healing is noticing that the same silence no longer scares you.",
        "I am learning to trust the calm that once felt unfamiliar.",
        "Some days, progress looks like not returning to what hurt you.",
        "Hope became quieter, but it never completely left.",
        "The small peace I feel today is proof that I am not where I started.",
    ),
    "hard_truths": (
        "People reveal their priorities in what they repeatedly make you explain.",
        "Sometimes closure is accepting that their reason will never make the hurt reasonable.",
        "Being needed is not the same as being loved well.",
        "Some people miss your access, not your presence.",
        "Some apologies protect a person's image more than they repair what happened.",
    ),
}
LOCAL_QUOTES = tuple(quote for quotes in LOCAL_QUOTES_BY_CATEGORY.values() for quote in quotes)

CLICHE_PHRASES = (
    "everything happens for a reason",
    "time heals all wounds",
    "what does not kill you",
    "better days are coming",
    "you are stronger than you think",
    "never give up",
    "everything will be okay",
)


class AstraError(RuntimeError):
    """A user-facing project error."""


class PublishError(AstraError):
    """A user-facing publishing or cleanup error."""


class PublishUncertainError(PublishError):
    """A request may have succeeded but its response was not confirmed."""


class PublishTransportError(PublishError):
    """A network or response transport failed before the outcome was known."""


@dataclass(frozen=True)
class QuoteSelection:
    """A validated quote and the evidence used to select it."""

    text: str
    category: str
    score: float
    component_scores: dict[str, float]


@dataclass(frozen=True)
class SocialMetadata:
    """Short caption, related hashtags, and the exact Instagram caption payload."""

    short_caption: str
    hashtags: tuple[str, ...]
    instagram_caption: str


@dataclass(frozen=True)
class ProcessedVideo:
    """A verified local output together with metadata prepared for publishing."""

    path: Path
    quote: str
    social: SocialMetadata


def run_command(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run a subprocess without passing user text through a shell."""
    try:
        return subprocess.run(
            command,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise AstraError(f"Could not run {command[0]!r}: {exc}") from exc


def executable(project_root: Path, configured: str, command: str) -> str:
    """Resolve system, configured, or bundled FFmpeg executables."""
    candidates: list[str] = []
    if configured:
        configured_path = resolve_path(project_root, configured)
        candidates.append(str(configured_path))
    system_path = shutil.which(command)
    if system_path:
        candidates.append(system_path)
    bundled = sorted(project_root.glob(f"tools/ffmpeg-*-amd64-static/{command}"))
    candidates.extend(str(path) for path in bundled)
    for candidate in candidates:
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise AstraError(
        f"Missing required dependency: {command}. Install FFmpeg (which includes ffprobe), "
        "put it on PATH, or set its path in config.json."
    )


def require_dependencies(project_root: Path, config: dict[str, Any]) -> tuple[str, str]:
    try:
        ffmpeg = executable(project_root, config.get("ffmpeg_path", ""), "ffmpeg")
        ffprobe = executable(project_root, config.get("ffprobe_path", ""), "ffprobe")
    except AstraError as exc:
        raise AstraError(
            f"{exc} Install instructions are in README.md."
        ) from exc
    return ffmpeg, ffprobe


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise AstraError(f"Configuration file not found: {config_path}")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AstraError(f"Invalid JSON in {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise AstraError("config.json must contain a JSON object")
    config = {**DEFAULT_CONFIG, **raw}
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    positive_numbers = ("font_size", "line_spacing")
    for key in positive_numbers:
        if not isinstance(config[key], (int, float)) or config[key] <= 0:
            raise AstraError(f"{key} must be a positive number")
    if type(config["font_weight"]) is not int or not 300 <= config["font_weight"] <= 700:
        raise AstraError("font_weight must be an integer from 300 to 700")
    for key in ("left_margin_percent", "top_position_percent", "right_margin_percent"):
        value = config[key]
        if not isinstance(value, (int, float)) or not 0 <= value < 100:
            raise AstraError(f"{key} must be between 0 and 100")
    if config["left_margin_percent"] + config["right_margin_percent"] >= 100:
        raise AstraError("left and right margins leave no room for text")
    if config["text_alignment"] != "left":
        raise AstraError("Only left text alignment is supported by the specification")
    if config["output_container"].lower() != "mp4":
        raise AstraError("output_container must be mp4")
    if config["output_video_codec"] != "libx264":
        raise AstraError("output_video_codec must be libx264")
    if config["quote_provider"] not in {"local", "groq"}:
        raise AstraError("quote_provider must be 'local' or 'groq'")
    distribution = config["quote_category_distribution"]
    if not isinstance(distribution, dict) or not distribution:
        raise AstraError("quote_category_distribution must be a non-empty object")
    for category, weight in distribution.items():
        if category not in CATEGORY_DESCRIPTIONS:
            raise AstraError(f"Unknown quote category: {category}")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0:
            raise AstraError("quote category weights must be non-negative numbers")
    if not any(weight > 0 for weight in distribution.values()):
        raise AstraError("quote_category_distribution must enable at least one category")
    candidate_count = config["quote_candidate_count"]
    if type(candidate_count) is not int or not 3 <= candidate_count <= 5:
        raise AstraError("quote_candidate_count must be an integer from 3 to 5")
    minimum_words = config["quote_min_words"]
    maximum_words = config["quote_max_words"]
    if type(minimum_words) is not int or type(maximum_words) is not int or not 1 <= minimum_words <= maximum_words <= 45:
        raise AstraError("quote_min_words and quote_max_words must be integers from 1 to 45 with min <= max")
    minimum_score = config["quote_min_score"]
    if isinstance(minimum_score, bool) or not isinstance(minimum_score, (int, float)) or not 1 <= minimum_score <= 10:
        raise AstraError("quote_min_score must be between 1 and 10")
    similarity_threshold = config["quote_similarity_threshold"]
    if isinstance(similarity_threshold, bool) or not isinstance(similarity_threshold, (int, float)) or not 0 <= similarity_threshold <= 1:
        raise AstraError("quote_similarity_threshold must be between 0 and 1")
    if not isinstance(config["quote_history_file"], str) or not config["quote_history_file"].strip():
        raise AstraError("quote_history_file must be a non-empty path")
    history_limit = config["quote_history_limit"]
    if type(history_limit) is not int or history_limit < 0:
        raise AstraError("quote_history_limit must be a non-negative integer")
    if type(config["max_line_characters"]) is not int or config["max_line_characters"] < 10:
        raise AstraError("max_line_characters must be an integer of at least 10")
    if not isinstance(config["adaptive_position"], bool):
        raise AstraError("adaptive_position must be true or false")
    if type(config["position_analysis_samples"]) is not int or not 3 <= config["position_analysis_samples"] <= 20:
        raise AstraError("position_analysis_samples must be an integer from 3 to 20")
    vertical_margin = config["vertical_safe_margin_percent"]
    if not isinstance(vertical_margin, (int, float)) or not 0 <= vertical_margin < 50:
        raise AstraError("vertical_safe_margin_percent must be between 0 and 50")
    end_symbols = config["quote_end_symbols"]
    if not isinstance(end_symbols, list) or not all(
        isinstance(symbol, str) and 1 <= len(symbol) <= 8
        and symbol.isprintable() and not any(character.isspace() for character in symbol)
        for symbol in end_symbols
    ):
        raise AstraError("quote_end_symbols must be a list of short text symbols without whitespace (or [] to disable)")
    color = config["text_color"]
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise AstraError("text_color must be a six-digit hex color such as #E8C547")
    folder_colors = config["text_colors_by_folder"]
    if not isinstance(folder_colors, dict) or not all(
        isinstance(folder, str) and folder.strip()
        and isinstance(folder_color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", folder_color)
        for folder, folder_color in folder_colors.items()
    ):
        raise AstraError("text_colors_by_folder must map folder names to six-digit hex colors")
    if not isinstance(config["recursive_scan"], bool):
        raise AstraError("recursive_scan must be true or false")
    if not isinstance(config["selection_state_file"], str) or not config["selection_state_file"].strip():
        raise AstraError("selection_state_file must be a non-empty path")
    if not isinstance(config["publish_state_file"], str) or not config["publish_state_file"].strip():
        raise AstraError("publish_state_file must be a non-empty path")
    if not isinstance(config["cloudinary_folder"], str) or not config["cloudinary_folder"].strip():
        raise AstraError("cloudinary_folder must be a non-empty path")
    if not isinstance(config["cloudinary_unsigned_upload"], bool):
        raise AstraError("cloudinary_unsigned_upload must be true or false")
    if not isinstance(config["instagram_api_version"], str) or not re.fullmatch(
        r"v\d+\.\d+", config["instagram_api_version"]
    ):
        raise AstraError("instagram_api_version must look like v21.0")
    if not isinstance(config["instagram_api_host"], str):
        raise AstraError("instagram_api_host must be empty, graph.facebook.com, or graph.instagram.com")
    configured_host = config["instagram_api_host"].strip()
    if configured_host:
        configured_host = configured_host.removeprefix("https://").removeprefix("http://").rstrip("/")
        if configured_host not in {"graph.facebook.com", "graph.instagram.com"}:
            raise AstraError("instagram_api_host must be empty, graph.facebook.com, or graph.instagram.com")
    if not isinstance(config["instagram_caption"], str) or len(config["instagram_caption"]) > 2200:
        raise AstraError("instagram_caption must be a string of at most 2200 characters")
    hashtag_count = config["instagram_hashtag_count"]
    if type(hashtag_count) is not int or not 6 <= hashtag_count <= 7:
        raise AstraError("instagram_hashtag_count must be 6 or 7")
    if not isinstance(config["instagram_share_to_feed"], bool):
        raise AstraError("instagram_share_to_feed must be true or false")
    timeout = config["instagram_processing_timeout_seconds"]
    if type(timeout) is not int or timeout < 30:
        raise AstraError("instagram_processing_timeout_seconds must be an integer of at least 30")
    poll_interval = config["instagram_poll_interval_seconds"]
    if type(poll_interval) is not int or not 1 <= poll_interval <= 60:
        raise AstraError("instagram_poll_interval_seconds must be an integer from 1 to 60")


def resolve_path(project_root: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else project_root / candidate


def resolve_font(project_root: Path, configured: str) -> Path:
    """Use the bundled primary font, then the documented fallback fonts."""
    candidates = [resolve_path(project_root, configured)]
    # Common Linux locations are useful when a user intentionally removes the
    # bundled font. fc-match is used only as a fallback and never for quoting.
    for family in ("Cormorant Garamond", "Libre Baskerville", "Georgia"):
        if shutil.which("fc-match"):
            result = run_command(["fc-match", "-f", "%{file}", family])
            if result.returncode == 0 and result.stdout.strip():
                candidates.append(Path(result.stdout.strip()))
    candidates.extend(
        Path(path)
        for path in (
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise AstraError(
        "No usable font was found. Add CormorantGaramond-Variable.ttf at "
        f"{candidates[0]} or install Cormorant Garamond, Libre Baskerville, or Georgia."
    )


def load_font(font_path: Path, size: int, weight: int) -> ImageFont.FreeTypeFont:
    """Load a font at the requested weight, including variable fonts."""
    font = ImageFont.truetype(str(font_path), size)
    axes = font.get_variation_axes()
    if axes:
        weight_axis = next(
            (index for index, axis in enumerate(axes) if axis.get("name") in {b"Weight", "Weight"}),
            None,
        )
        if weight_axis is not None:
            values = [axis["default"] for axis in axes]
            values[weight_axis] = weight
            font.set_variation_by_axes(values)
    return font


def scan_inputs(input_dir: Path, recursive: bool) -> list[Path]:
    if not input_dir.is_dir():
        raise AstraError(f"Input folder not found: {input_dir}")
    iterator = input_dir.rglob("*") if recursive else input_dir.glob("*")
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda path: str(path).lower(),
    )


def text_color_for_source(source: Path, input_dir: Path, config: dict[str, Any]) -> str:
    """Select the configured quote color for the source video's input subfolder."""
    try:
        relative_source = source.relative_to(input_dir)
    except ValueError:
        return config["text_color"]

    folder_colors = config["text_colors_by_folder"]
    for folder_name in reversed(relative_source.parts[:-1]):
        for configured_folder, color in folder_colors.items():
            if folder_name.casefold() == configured_folder.casefold():
                return color
    return config["text_color"]


def source_key(source: Path, input_dir: Path) -> str:
    """Return a stable, portable key for a video inside the input directory."""
    return source.relative_to(input_dir).as_posix()


def load_selection_state(state_path: Path) -> set[str]:
    """Load the paths already used in the current selection cycle."""
    if not state_path.is_file():
        return set()
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AstraError(f"Could not read selection state {state_path}: {exc}") from exc
    used_sources = raw.get("used_sources") if isinstance(raw, dict) else None
    if not isinstance(used_sources, list) or not all(isinstance(item, str) for item in used_sources):
        raise AstraError(f"Invalid selection state in {state_path}")
    return set(used_sources)


def save_selection_state(state_path: Path, used_sources: set[str]) -> None:
    """Persist selection progress so separate CLI runs share one rotation."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_name(f"{state_path.name}.tmp")
    try:
        temporary_path.write_text(
            json.dumps({"used_sources": sorted(used_sources)}, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(state_path)
    except OSError as exc:
        raise AstraError(f"Could not save selection state {state_path}: {exc}") from exc


def select_sources(
    sources: list[Path],
    input_dir: Path,
    state_path: Path,
    count: int | None,
) -> tuple[list[Path], set[str]]:
    """Select unused videos, resetting the cycle only after every video was used."""
    if not sources:
        return [], set()
    current_keys = {source_key(source, input_dir) for source in sources}
    used_sources = load_selection_state(state_path) & current_keys
    unused_sources = [source for source in sources if source_key(source, input_dir) not in used_sources]
    if not unused_sources:
        LOGGER.info("All input videos have been used once; starting a new selection cycle")
        used_sources = set()
        unused_sources = list(sources)
    selected = unused_sources if count is None else unused_sources[:count]
    LOGGER.info("Selected %d unused video(s); %d remain in this cycle", len(selected), len(unused_sources) - len(selected))
    return selected, used_sources


def probe(path: Path, ffprobe: str) -> dict[str, Any]:
    result = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown ffprobe error"
        raise AstraError(f"Could not inspect {path.name}: {detail}")
    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AstraError(f"ffprobe returned invalid metadata for {path.name}") from exc
    video = next((stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video"), None)
    if not video:
        raise AstraError(f"{path.name} has no video stream")
    return metadata


def video_dimensions(metadata: dict[str, Any]) -> tuple[int, int]:
    video = next(stream for stream in metadata["streams"] if stream.get("codec_type") == "video")
    return int(video["width"]), int(video["height"])


def duration_seconds(metadata: dict[str, Any]) -> float:
    value = metadata.get("format", {}).get("duration")
    if value is None:
        video = next(stream for stream in metadata["streams"] if stream.get("codec_type") == "video")
        value = video.get("duration", 0)
    return float(value or 0)


def has_audio(metadata: dict[str, Any]) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in metadata.get("streams", []))


def load_quote_history(history_path: Path) -> list[dict[str, Any]]:
    """Load prior selected quotes without adding a database dependency."""
    if not history_path.is_file():
        return []
    try:
        raw = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AstraError(f"Could not read quote history {history_path}: {exc}") from exc
    entries = raw.get("quotes") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise AstraError(f"Invalid quote history in {history_path}")
    history: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("quote"), str) or not isinstance(entry.get("category"), str):
            raise AstraError(f"Invalid quote history entry in {history_path}")
        history.append({
            "quote": entry["quote"],
            "category": entry["category"],
            "source": entry.get("source", ""),
        })
    return history


def save_quote_history(history_path: Path, history: list[dict[str, Any]], limit: int) -> None:
    """Atomically save the bounded quote history after a verified render."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    bounded = history[-limit:] if limit else []
    temporary_path = history_path.with_name(f"{history_path.name}.tmp")
    try:
        temporary_path.write_text(json.dumps({"quotes": bounded}, indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(history_path)
    except OSError as exc:
        raise AstraError(f"Could not save quote history {history_path}: {exc}") from exc


def quote_normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def quote_similarity(first: str, second: str) -> float:
    return SequenceMatcher(None, quote_normalized(first), quote_normalized(second)).ratio()


def history_similarity(text: str, history: list[dict[str, Any]]) -> float:
    return max((quote_similarity(text, entry["quote"]) for entry in history), default=0.0)


def choose_quote_category(config: dict[str, Any], history: list[dict[str, Any]]) -> str:
    """Choose by configured weight while avoiding the most recent themes."""
    distribution = config["quote_category_distribution"]
    enabled = [(category, weight) for category, weight in distribution.items() if weight > 0]
    recent = [entry.get("category") for entry in history[-2:] if entry.get("category") in distribution]
    alternatives = [(category, weight) for category, weight in enabled if category not in recent]
    choices = alternatives or enabled
    return random.SystemRandom().choices(
        [category for category, _ in choices],
        weights=[weight for _, weight in choices],
        k=1,
    )[0]


def local_quote_candidates(
    path: Path,
    category: str,
    count: int,
    history: list[dict[str, Any]],
    similarity_threshold: float,
) -> list[str]:
    """Return deterministic local candidates, rotated per source and history size."""
    pool = list(LOCAL_QUOTES_BY_CATEGORY[category])
    digest = hashlib.sha256(f"{path.name}:{category}:{len(history)}".encode("utf-8")).digest()
    random.Random(int.from_bytes(digest[:8], "big")).shuffle(pool)
    fresh = [candidate for candidate in pool if history_similarity(candidate, history) < similarity_threshold]
    ordered = fresh + [candidate for candidate in pool if candidate not in fresh]
    return ordered[:count]


def parse_quote_candidates(content: str, expected_count: int) -> list[str]:
    """Parse the model's JSON response while tolerating fenced JSON."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("the API returned malformed candidate JSON") from exc
    if isinstance(parsed, dict):
        parsed = parsed.get("candidates")
    if not isinstance(parsed, list):
        raise ValueError("the API response did not contain a candidates list")
    candidates = [candidate for candidate in parsed if isinstance(candidate, str) and candidate.strip()]
    if len(candidates) < expected_count:
        raise ValueError(f"the API returned {len(candidates)} candidates; expected {expected_count}")
    return candidates[:expected_count]


def score_quote_candidate(
    candidate: str,
    category: str,
    history: list[dict[str, Any]],
) -> dict[str, float]:
    """Score a candidate consistently with lightweight local heuristics."""
    words = re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", candidate.lower())
    word_count = len(words)
    word_set = set(words)
    category_hits = len(word_set & CATEGORY_KEYWORDS[category])
    emotional_words = {
        "alone", "lonely", "miss", "missing", "hurt", "quiet", "silence", "love", "fear",
        "understand", "unseen", "peace", "healing", "hope", "trust", "loss", "leave", "remember",
    }
    emotional_hits = len(word_set & emotional_words)
    similarity = history_similarity(candidate, history)
    cliche_hits = sum(phrase in candidate.lower() for phrase in CLICHE_PHRASES)
    hook_starters = ("i ", "some ", "the ", "you ", "people ", "my ", "sometimes ", "when ", "one day")
    hook_bonus = 0.8 if candidate.lower().startswith(hook_starters) else 0.0
    first_person = bool(word_set & {"i", "my", "me", "we", "our"})
    second_person = bool(word_set & {"you", "your"})
    long_words = sum(len(word) >= 12 for word in words)

    impact = 5.2 + min(2.2, emotional_hits * 0.4) + hook_bonus + (0.5 if first_person or second_person else 0)
    relatability = 5.5 + (0.8 if first_person or second_person else 0) + (0.5 if 8 <= word_count <= 18 else 0)
    originality = 9.5 - min(7.5, similarity * 8.0) - cliche_hits * 2.0
    clarity = 9.5 - max(0, word_count - 22) * 0.4 - max(0, long_words - 2) * 0.35
    shareability = 5.0 + hook_bonus + (1.0 if 8 <= word_count <= 18 else 0) - cliche_hits * 1.5
    theme_fit = 4.5 + min(4.0, category_hits * 0.8) + (0.5 if emotional_hits else 0)

    def bounded(value: float) -> float:
        return round(max(1.0, min(10.0, value)), 2)

    component_scores = {
        "impact": bounded(impact),
        "relatability": bounded(relatability),
        "originality": bounded(originality),
        "clarity": bounded(clarity),
        "shareability": bounded(shareability),
        "theme_fit": bounded(theme_fit),
    }
    total = (
        component_scores["impact"] * 0.22
        + component_scores["relatability"] * 0.18
        + component_scores["originality"] * 0.18
        + component_scores["clarity"] * 0.16
        + component_scores["shareability"] * 0.12
        + component_scores["theme_fit"] * 0.14
    )
    component_scores["total"] = round(total, 2)
    component_scores["history_similarity"] = round(similarity, 3)
    return component_scores


def select_best_quote(
    candidates: list[str],
    category: str,
    config: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    allow_repeated_fallback: bool = False,
) -> QuoteSelection:
    valid: list[tuple[str, dict[str, float]]] = []
    repeated: list[tuple[str, dict[str, float]]] = []
    for candidate in candidates:
        try:
            cleaned = clean_quote(candidate, config)
        except AstraError as exc:
            LOGGER.warning("Rejected quote candidate: %s", exc)
            continue
        scores = score_quote_candidate(cleaned, category, history)
        if scores["history_similarity"] >= config["quote_similarity_threshold"]:
            repeated.append((cleaned, scores))
            continue
        valid.append((cleaned, scores))
    if not valid and allow_repeated_fallback and repeated:
        LOGGER.warning("No fresh local candidate remained; selecting the strongest valid fallback")
        valid = repeated
    if not valid:
        raise AstraError("No quote candidate passed validation and repetition checks")
    text, scores = max(valid, key=lambda item: item[1]["total"])
    if scores["total"] < config["quote_min_score"]:
        raise AstraError(
            f"Best quote candidate scored {scores['total']:.2f}, below the configured minimum "
            f"of {config['quote_min_score']:.2f}"
        )
    return QuoteSelection(text=text, category=category, score=scores["total"], component_scores=scores)


def local_quote(path: Path) -> str:
    digest = hashlib.sha256(path.name.encode("utf-8")).digest()
    return LOCAL_QUOTES[digest[0] % len(LOCAL_QUOTES)]


def request_quote_candidates(path: Path, category: str, config: dict[str, Any], history: list[dict[str, Any]], api_key: str) -> list[str]:
    candidate_count = config["quote_candidate_count"]
    recent_quotes = [entry["quote"] for entry in history[-10:]]
    recent_context = "\n".join(f"- {quote}" for quote in recent_quotes) or "(none yet)"
    payload = {
        "model": config.get("quote_model") or "openai/gpt-oss-120b",
        "temperature": 0.85,
        "max_completion_tokens": max(260, candidate_count * 80),
        "reasoning_effort": "low",
        "reasoning_format": "hidden",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the quote writer for ASTRA, a cinematic Instagram short-form brand. "
                    "Write original emotionally resonant lines about real inner experiences. The audience relates to "
                    "feeling misunderstood, overthinking, loneliness, changing relationships, self-respect, healing, "
                    "and hard truths about human behaviour. Use simple conversational English, one clear emotional idea, "
                    "specific but broadly relatable details, and no fake attribution. Avoid cliches, generic motivation, "
                    "hopelessness, manipulation, engagement bait, hashtags, emojis, quotation marks, and decorative symbols. "
                    f"Return exactly {candidate_count} fresh candidates as a JSON object with this shape: "
                    '{"candidates":["candidate 1", "candidate 2"]}. Return JSON only.'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Create {candidate_count} candidates for the category {category!r}: {CATEGORY_DESCRIPTIONS[category]}. "
                    f"Each candidate should be {config['quote_min_words']}–{config['quote_max_words']} words and usually fit 2–4 short lines. "
                    "Vary the opening, sentence structure, perspective, and ending. Do not reuse wording or ideas from these recent quotes:\n"
                    f"{recent_context}\nThe source file is named {path.stem!r}."
                ),
            },
        ],
    }
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "astra-quote-overlay/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("the API returned no candidate text")
        return parse_quote_candidates(content, config["quote_candidate_count"])
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AstraError(f"Quote API failed: {exc}") from exc


def generate_quote_selection(
    path: Path,
    config: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> QuoteSelection:
    history = history or []
    category = choose_quote_category(config, history)
    candidate_count = config["quote_candidate_count"]
    provider = config["quote_provider"]
    api_key = os.environ.get("GROQ_API_KEY")
    using_local = provider == "local" or not api_key
    if provider != "local" and not api_key:
        LOGGER.warning("GROQ_API_KEY is not set; using local candidate generation for %s", path.name)

    if using_local:
        candidates = local_quote_candidates(
            path, category, candidate_count, history, config["quote_similarity_threshold"]
        )
        return select_best_quote(candidates, category, config, history, allow_repeated_fallback=True)

    try:
        candidates = request_quote_candidates(path, category, config, history, api_key)
        selection = select_best_quote(candidates, category, config, history)
    except AstraError as exc:
        LOGGER.warning("%s; using local candidate fallback for %s", exc, path.name)
        candidates = local_quote_candidates(
            path, category, candidate_count, history, config["quote_similarity_threshold"]
        )
        selection = select_best_quote(candidates, category, config, history, allow_repeated_fallback=True)
    LOGGER.info(
        "Quote candidates selected: category=%s score=%.2f components=%s",
        selection.category,
        selection.score,
        selection.component_scores,
    )
    return selection


def generate_quote(path: Path, config: dict[str, Any], history: list[dict[str, Any]] | None = None) -> str:
    """Backward-compatible wrapper returning only the selected quote text."""
    return generate_quote_selection(path, config, history).text


def clean_quote(quote: str, config: dict[str, Any] | None = None) -> str:
    quote = " ".join(quote.replace("\r", " ").replace("\n", " ").split())
    quote = quote.strip(" \"'“”‘’")
    if not quote:
        raise AstraError("Quote generation returned empty text")
    if any(ord(character) > 0xFFFF for character in quote) or any(symbol in quote for symbol in ("😀", "😂", "✨")):
        raise AstraError("Quote contains an unsupported emoji")
    if any(marker in quote.lower() for marker in ("#", "http://", "https://", "@")):
        raise AstraError("Quote contains a hashtag, link, or social handle")
    word_count = len(quote.split())
    minimum_words = config.get("quote_min_words", 8) if config else 8
    maximum_words = config.get("quote_max_words", 45) if config else 45
    if word_count < minimum_words or word_count > maximum_words:
        raise AstraError(
            f"Quote must contain {minimum_words}–{maximum_words} words after validation; got {word_count}"
        )
    return quote


def add_quote_end_symbol(quote: str, source: Path, config: dict[str, Any]) -> str:
    """Choose a repeatable accent and attach it only to the quote's end."""
    symbols = config["quote_end_symbols"]
    if not symbols:
        return quote
    digest = hashlib.sha256(source.name.encode("utf-8")).digest()
    symbol = symbols[digest[1] % len(symbols)]
    return f"{quote.rstrip()}\u00a0{symbol}"


def generate_social_metadata(quote: str, category: str, config: dict[str, Any]) -> SocialMetadata:
    """Create a concise quote-led caption and related hashtags without another API call."""
    if category not in SOCIAL_CAPTION_OPTIONS or category not in SOCIAL_HASHTAGS_BY_CATEGORY:
        raise AstraError(f"No social metadata strategy is configured for category {category!r}")

    digest = hashlib.sha256(quote.encode("utf-8")).digest()
    caption_options = SOCIAL_CAPTION_OPTIONS[category]
    short_caption = caption_options[digest[0] % len(caption_options)]
    word_count = len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", short_caption))
    if word_count not in {2, 3}:
        raise AstraError("Generated social caption must contain 2 or 3 words")

    quote_words = set(re.findall(r"[a-z]+", quote.lower()))
    hashtags: list[str] = []
    seen: set[str] = set()

    def add_hashtag(hashtag: str) -> None:
        normalized = hashtag.lower()
        if normalized not in seen and len(hashtags) < config["instagram_hashtag_count"]:
            hashtags.append(hashtag)
            seen.add(normalized)

    for hashtag in SOCIAL_HASHTAGS_BY_CATEGORY[category]:
        add_hashtag(hashtag)
    for hashtag, signal_words in SOCIAL_HASHTAG_SIGNALS:
        if quote_words.intersection(signal_words):
            add_hashtag(hashtag)
    general_offset = digest[1] % len(SOCIAL_GENERAL_HASHTAGS)
    for index in range(len(SOCIAL_GENERAL_HASHTAGS)):
        add_hashtag(SOCIAL_GENERAL_HASHTAGS[(general_offset + index) % len(SOCIAL_GENERAL_HASHTAGS)])
        if len(hashtags) == config["instagram_hashtag_count"]:
            break

    if len(hashtags) < 6:
        raise AstraError("Generated social metadata contains fewer than 6 hashtags")

    instagram_caption = f"{short_caption}\n\n{' '.join(hashtags)}"
    if len(instagram_caption) > 2200:
        raise AstraError("Generated Instagram caption exceeds Instagram's 2200-character limit")
    return SocialMetadata(
        short_caption=short_caption,
        hashtags=tuple(hashtags),
        instagram_caption=instagram_caption,
    )


def wrap_text(
    text: str, font: ImageFont.FreeTypeFont, available_width: float, max_line_characters: int = 42
) -> list[str]:
    """Choose deterministic, measured breakpoints that preserve the quote text.

    Every possible word-boundary layout is evaluated with dynamic programming.
    The score combines rendered-width balance, a natural target line count,
    punctuation and phrase boundaries, and orphan-word penalties. Nonbreaking
    spaces keep an end accent attached. An empty result asks the renderer to try
    a smaller font when even an individual word cannot fit.
    """
    awkward_endings = {
        "a", "an", "the", "to", "of", "in", "for", "with", "without", "into", "from",
        "your", "my", "our", "and", "but", "when", "while", "that", "because", "same", "another",
    }
    phrase_starts = {
        "and", "but", "when", "while", "because", "then", "that", "especially", "without", "instead",
    }
    phrase_continuations = {
        "person", "people", "thing", "things", "time", "times", "way", "reason", "moment", "moments",
        "place", "feeling", "feelings", "thought", "thoughts", "promise", "promises", "version", "part",
        "side", "truth", "love", "life",
    }
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        words = re.findall(r"[^ \t\r\n]+", paragraph)
        count = len(words)
        if not count:
            continue

        # Build only physically valid word-boundary lines. Character count is a
        # soft guardrail; rendered width is the actual boundary condition.
        candidates: list[list[tuple[int, str, float]]] = [[] for _ in range(count)]
        for start in range(count):
            for end in range(start + 1, count + 1):
                line = " ".join(words[start:end])
                width = font.getlength(line)
                if width > available_width:
                    break
                candidates[start].append((end, line, width))

        # Find the fewest physically possible lines. This also gives the layout
        # a lower bound when a long quote cannot fit in the preferred count.
        minimum_lines = [count + 1] * (count + 1)
        minimum_lines[count] = 0
        for start in range(count - 1, -1, -1):
            if candidates[start]:
                minimum_lines[start] = 1 + min(minimum_lines[end] for end, _, _ in candidates[start])
        if minimum_lines[0] > count:
            return []

        total_width = font.getlength(" ".join(words))
        total_characters = len(" ".join(words))
        width_target = max(1.0, available_width * 0.78)
        estimated_by_width = max(1, round(total_width / width_target + 0.45))
        estimated_by_characters = max(
            1,
            (total_characters + max_line_characters - 1) // max_line_characters,
        )
        preferred_lines = max(minimum_lines[0], estimated_by_width, estimated_by_characters)
        preferred_lines = min(count, preferred_lines)
        target_line_width = min(available_width * 0.82, total_width / max(1, preferred_lines))

        def line_penalty(start: int, end: int, line: str, width: float) -> float:
            word_count = end - start
            is_last = end == count
            fullness = width / max(1.0, available_width)
            balance = ((width - target_line_width) / max(1.0, available_width)) ** 2 * 8.0
            character_overage = max(0, len(line) - max_line_characters)
            penalty = balance + character_overage / max(1.0, max_line_characters) * 0.45
            if not is_last and fullness < 0.36:
                penalty += (0.36 - fullness) * 3.0
            if word_count == 1 and count > 1:
                penalty += 4.0 if not is_last else 2.5
            if end < count:
                last_word = words[end - 1].lower().rstrip('"”’')
                next_word = words[end].lower()
                if last_word.endswith((",", ";", ":", ".", "!", "?", "—")):
                    penalty += 0.0
                elif next_word in phrase_starts:
                    penalty += 0.0
                else:
                    penalty += 0.05
                if next_word in phrase_continuations:
                    penalty += 1.1
                if last_word in awkward_endings:
                    penalty += 1.8
            elif word_count == 1 and start > 0:
                penalty += 2.0
            return penalty

        # dp[start][line_count] stores the least-cost layout for the remaining
        # words with exactly line_count lines. The final selection adds a small
        # preference for the natural line count without hardcoding word counts.
        dp = [[float("inf")] * (count + 1) for _ in range(count + 1)]
        choices: dict[tuple[int, int], int] = {}
        dp[count][0] = 0.0
        for start in range(count - 1, -1, -1):
            for end, line, width in candidates[start]:
                for remaining_lines in range(count - end + 1):
                    remainder = dp[end][remaining_lines]
                    if remainder == float("inf"):
                        continue
                    line_count = remaining_lines + 1
                    total = line_penalty(start, end, line, width) + remainder
                    if total < dp[start][line_count]:
                        dp[start][line_count] = total
                        choices[(start, line_count)] = end

        available_layouts = [
            (dp[0][line_count] + abs(line_count - preferred_lines) * 1.15, line_count)
            for line_count in range(1, count + 1)
            if dp[0][line_count] != float("inf")
        ]
        if not available_layouts:
            return []
        _, line_count = min(available_layouts)
        start = 0
        while line_count and start < count:
            end = choices[(start, line_count)]
            lines.append(" ".join(words[start:end]))
            start = end
            line_count -= 1
    return lines


def text_layout(
    quote: str,
    width: int,
    height: int,
    config: dict[str, Any],
    font_path: Path,
    left_percent: float,
    top_percent: float | None,
) -> dict[str, Any] | None:
    """Return a safe measured layout for one candidate position."""
    base_font_size = max(1, round(float(config["font_size"]) * width / 1080.0))
    x = round(width * left_percent / 100.0)
    available_width = width * (1.0 - (left_percent + config["right_margin_percent"]) / 100.0)
    safe_top = round(height * float(config["vertical_safe_margin_percent"]) / 100.0)
    safe_bottom = round(height * (1.0 - float(config["vertical_safe_margin_percent"]) / 100.0))
    minimum_font_size = min(base_font_size, max(12, round(base_font_size * 0.65)))
    selected_font_size = base_font_size
    while selected_font_size >= minimum_font_size:
        font = load_font(font_path, selected_font_size, config["font_weight"])
        lines = wrap_text(quote, font, available_width, config["max_line_characters"])
        line_height = max(1, round(selected_font_size * float(config["line_spacing"])))
        text_height = line_height * len(lines)
        if top_percent is None:
            y = safe_top + max(0, (safe_bottom - safe_top - text_height) // 2)
        else:
            y = max(safe_top, round(height * top_percent / 100.0))
        if lines and all(font.getlength(line) <= available_width for line in lines) and y + text_height <= safe_bottom:
            text_width = max(font.getlength(line) for line in lines)
            return {
                "font": font,
                "font_size": selected_font_size,
                "lines": lines,
                "line_height": line_height,
                "text_width": text_width,
                "text_height": text_height,
                "x": x,
                "y": y,
                "left_percent": left_percent,
                "top_percent": y * 100.0 / height,
            }
        selected_font_size -= 1
    return None


def extract_analysis_frames(
    source: Path,
    ffmpeg: str,
    destination: Path,
    duration: float,
    sample_count: int,
) -> list[Image.Image]:
    """Extract small evenly-spaced frames for readability analysis."""
    destination.mkdir(parents=True, exist_ok=True)
    fps = max(0.2, min(2.0, sample_count / max(duration, 1.0)))
    pattern = destination / "analysis-%03d.jpg"
    result = run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            f"fps={fps:.8f},scale=180:-2",
            "-frames:v",
            str(sample_count),
            "-q:v",
            "4",
            str(pattern),
        ]
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown FFmpeg analysis error"
        raise AstraError(f"Could not sample {source.name} for quote placement: {detail}")
    frames: list[Image.Image] = []
    for frame_path in sorted(destination.glob("analysis-*.jpg")):
        try:
            with Image.open(frame_path) as image:
                frames.append(image.convert("RGB"))
        except OSError as exc:
            LOGGER.warning("Could not read analysis frame %s: %s", frame_path.name, exc)
    if not frames:
        raise AstraError(f"Could not sample any frames from {source.name} for quote placement")
    return frames


def frame_readability_score(
    frame: Image.Image,
    layout: dict[str, Any],
    source_width: int,
    source_height: int,
    text_luminance: float,
) -> float:
    """Score a text rectangle for contrast, consistency, and low background texture."""
    left = round(layout["x"] * frame.width / source_width)
    top = round(layout["y"] * frame.height / source_height)
    right = round((layout["x"] + layout["text_width"]) * frame.width / source_width)
    bottom = round((layout["y"] + layout["text_height"]) * frame.height / source_height)
    crop = frame.crop((left, top, max(left + 2, right), max(top + 2, bottom))).convert("L")
    pixels = list(crop.getdata())
    if not pixels:
        return -1.0
    ordered = sorted(pixels)
    lower_quartile = ordered[len(ordered) // 4]
    upper_quartile = ordered[(len(ordered) * 3) // 4]
    average = sum(pixels) / len(pixels)
    variance = sum((pixel - average) ** 2 for pixel in pixels) / len(pixels)
    deviation = variance**0.5
    if text_luminance >= 128:
        contrast = (255.0 - upper_quartile) / 255.0
    else:
        contrast = lower_quartile / 255.0
    consistency = max(0.0, 1.0 - deviation / 100.0)
    row_width, row_height = crop.size
    edge_total = 0
    edge_count = 0
    for row in range(row_height):
        for column in range(row_width - 1):
            edge_total += abs(pixels[row * row_width + column] - pixels[row * row_width + column + 1])
            edge_count += 1
    for row in range(row_height - 1):
        for column in range(row_width):
            edge_total += abs(pixels[row * row_width + column] - pixels[(row + 1) * row_width + column])
            edge_count += 1
    texture = max(0.0, 1.0 - (edge_total / max(1, edge_count)) / 45.0)
    return 0.65 * max(0.0, contrast) + 0.2 * consistency + 0.15 * texture


def candidate_positions(config: dict[str, Any]) -> list[tuple[float, float]]:
    """Build a safe, visually balanced grid without choosing extreme positions."""
    left = float(config["left_margin_percent"])
    top = float(config["top_position_percent"])
    right = float(config["right_margin_percent"])
    horizontal = {left}
    for offset in (8, 16, 24, 32):
        candidate = left + offset
        if candidate + right + 8 < 100:
            horizontal.add(candidate)
    # Keep the quote in the middle visual band: away from the top UI area and
    # away from the bottom where captions, controls, or foreground detail tend
    # to compete with it. The configured top position remains a candidate.
    vertical = {max(24.0, min(68.0, top))}
    for candidate in range(24, 69, 6):
        vertical.add(float(candidate))
    return [(x, y) for y in sorted(vertical) for x in sorted(horizontal)]


def choose_text_layout(
    source: Path,
    ffmpeg: str,
    metadata: dict[str, Any],
    quote: str,
    config: dict[str, Any],
    font_path: Path,
    temporary: Path,
) -> dict[str, Any]:
    """Inspect the video and select the safest readable quote position."""
    width, height = video_dimensions(metadata)
    fallback = text_layout(
        quote,
        width,
        height,
        config,
        font_path,
        float(config["left_margin_percent"]),
        None,
    )
    if fallback is None:
        raise AstraError("Quote could not fit inside the configured safe margins")
    if not config["adaptive_position"]:
        return fallback
    try:
        frames = extract_analysis_frames(
            source,
            ffmpeg,
            temporary / "placement-frames",
            duration_seconds(metadata),
            config["position_analysis_samples"],
        )
    except AstraError as exc:
        LOGGER.warning("%s; using configured quote position", exc)
        return fallback
    text_color = config["text_color"]
    text_luminance = sum(
        channel * weight
        for channel, weight in zip(
            (int(text_color[1:3], 16), int(text_color[3:5], 16), int(text_color[5:7], 16)),
            (0.2126, 0.7152, 0.0722),
        )
    )
    best_layout = fallback
    best_score = float("-inf")
    for left_percent, top_percent in candidate_positions(config):
        layout = text_layout(quote, width, height, config, font_path, left_percent, top_percent)
        if layout is None:
            continue
        scores = [frame_readability_score(frame, layout, width, height, text_luminance) for frame in frames]
        readability = 0.7 * min(scores) + 0.3 * (sum(scores) / len(scores))
        middle_preference = max(0.0, 1.0 - abs(top_percent - 45.0) / 24.0)
        score = 0.82 * readability + 0.18 * middle_preference
        if score > best_score:
            best_score = score
            best_layout = layout
    LOGGER.info(
        "Adaptive quote position: %.1f%% from left, %.1f%% from top (readability %.2f)",
        best_layout["left_percent"],
        best_layout["top_percent"],
        best_score,
    )
    return best_layout


def unique_output_path(output_dir: Path, stem: str) -> Path:
    base = output_dir / f"{stem}_quote.mp4"
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = output_dir / f"{stem}_quote_{index}.mp4"
        if not candidate.exists():
            return candidate
        index += 1


def render_video(
    source: Path,
    destination: Path,
    quote: str,
    metadata: dict[str, Any],
    config: dict[str, Any],
    font_path: Path,
    ffmpeg: str,
) -> None:
    width, height = video_dimensions(metadata)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="astra-") as temporary:
        layout = choose_text_layout(source, ffmpeg, metadata, quote, config, font_path, Path(temporary))
        # A transparent RGBA layer changes only the requested pixels; no
        # background, crop, transition, or generated footage is introduced.
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        color = tuple(int(config["text_color"][index : index + 2], 16) for index in (1, 3, 5)) + (255,)
        draw.multiline_text(
            (layout["x"], layout["y"]),
            "\n".join(layout["lines"]),
            font=layout["font"],
            fill=color,
            anchor="la",
            spacing=max(0, layout["line_height"] - layout["font_size"]),
            align="left",
        )
        overlay_path = Path(temporary) / "quote-overlay.png"
        overlay.save(overlay_path, "PNG", optimize=True)
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-i",
            str(overlay_path),
            "-filter_complex",
            "[0:v:0][1:v:0]overlay=0:0:format=auto[v]",
            "-map",
            "[v]",
            "-map",
            "0:a?",
            "-c:v",
            config["output_video_codec"],
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
        ]
        if has_audio(metadata):
            audio_stream = next(stream for stream in metadata["streams"] if stream.get("codec_type") == "audio")
            if audio_stream.get("codec_name") == "aac":
                command.extend(["-c:a", "copy"])
            else:
                command.extend(["-c:a", config["output_audio_codec"], "-b:a", "192k"])
        command.extend(["-movflags", "+faststart", str(destination)])
        result = run_command(command)
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown ffmpeg error"
            raise AstraError(f"FFmpeg failed for {source.name}: {detail}")


def verify_output(source_metadata: dict[str, Any], destination: Path, ffprobe: str) -> dict[str, Any]:
    if not destination.is_file() or destination.stat().st_size == 0:
        raise AstraError(f"Output was not created: {destination}")
    output_metadata = probe(destination, ffprobe)
    source_width, source_height = video_dimensions(source_metadata)
    output_width, output_height = video_dimensions(output_metadata)
    if (source_width, source_height) != (output_width, output_height):
        raise AstraError(
            f"Output resolution changed from {source_width}x{source_height} to {output_width}x{output_height}"
        )
    source_duration = duration_seconds(source_metadata)
    output_duration = duration_seconds(output_metadata)
    if abs(source_duration - output_duration) > 0.15:
        raise AstraError(f"Output duration changed from {source_duration:.3f}s to {output_duration:.3f}s")
    if has_audio(source_metadata) != has_audio(output_metadata):
        raise AstraError("Output audio presence does not match the source")
    return output_metadata


def _redact_secrets(message: str, secrets: list[str] | tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            message = message.replace(secret, "<redacted>")
    return message[:500]


def _response_error_detail(raw: bytes, status: int, secrets: list[str] | tuple[str, ...]) -> str:
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("error_user_msg") or error.get("type")
            if message:
                return _redact_secrets(str(message), secrets)
        if isinstance(error, str):
            return _redact_secrets(error, secrets)
        if payload.get("message"):
            return _redact_secrets(str(payload["message"]), secrets)
    return f"HTTP {status} from remote API"


def _request_json(
    request: urllib.request.Request,
    *,
    label: str,
    secrets: list[str] | tuple[str, ...],
    timeout: int = 120,
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        raise PublishError(f"{label} failed: {_response_error_detail(raw, exc.code, secrets)}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PublishTransportError(f"{label} failed: {_redact_secrets(str(exc), secrets)}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishTransportError(f"{label} returned invalid JSON (HTTP {status})") from exc
    if not isinstance(payload, dict):
        raise PublishError(f"{label} returned an unexpected response")
    if payload.get("error"):
        raise PublishError(f"{label} failed: {_response_error_detail(raw, status, secrets)}")
    return payload


def _signature(parameters: dict[str, str], api_secret: str) -> str:
    serialized = "&".join(
        f"{key}={value}"
        for key, value in sorted(parameters.items())
        if value is not None and value != ""
    )
    return hashlib.sha1((serialized + api_secret).encode("utf-8")).hexdigest()


def _multipart_body(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----ASTRA{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode("ascii"))
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        "Content-Type: video/mp4\r\n\r\n".encode("utf-8")
    )
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("ascii"))
    return bytes(body), boundary


def publishing_credentials(config: dict[str, Any]) -> dict[str, str]:
    """Read publishing credentials only when the explicit publish workflow is used."""
    names = {
        "instagram_token": "INSTAGRAM_TOKEN",
        "instagram_account_id": "INSTAGRAM_ACCOUNT_ID",
        "cloudinary_cloud_name": "CLOUDINARY_CLOUD_NAME",
        "cloudinary_api_key": "CLOUDINARY_API_KEY",
        "cloudinary_api_secret": "CLOUDINARY_API_SECRET",
        "cloudinary_upload_preset": "CLOUDINARY_UPLOAD_PRESET",
    }
    values = {key: os.environ.get(name, "").strip() for key, name in names.items()}
    required = ["instagram_token", "instagram_account_id", "cloudinary_cloud_name"]
    if config["cloudinary_unsigned_upload"]:
        required.append("cloudinary_upload_preset")
    required.extend(["cloudinary_api_key", "cloudinary_api_secret"])
    missing = [names[key] for key in required if not values[key]]
    if missing:
        raise PublishError(
            "Publishing requires environment variable(s): " + ", ".join(missing)
        )
    return values


def validate_public_video_url(url: str, secrets: list[str] | tuple[str, ...]) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path:
        raise PublishError("Cloudinary did not return a valid HTTPS delivery URL")
    if not parsed.hostname.endswith("cloudinary.com"):
        raise PublishError("Cloudinary returned an unexpected delivery host")
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "astra-reels/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            if not 200 <= status < 400:
                raise PublishError(f"Cloudinary delivery URL returned HTTP {status}")
    except urllib.error.HTTPError as exc:
        if exc.code != 405:
            raise PublishError(f"Cloudinary delivery URL check failed with HTTP {exc.code}") from exc
        range_request = urllib.request.Request(
            url,
            method="GET",
            headers={"Range": "bytes=0-1", "User-Agent": "astra-reels/1.0"},
        )
        try:
            with urllib.request.urlopen(range_request, timeout=30) as response:
                if not 200 <= getattr(response, "status", 200) < 400:
                    raise PublishError("Cloudinary delivery URL is not accessible")
                response.read(2)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as range_exc:
            raise PublishError(f"Cloudinary delivery URL check failed: {_redact_secrets(str(range_exc), secrets)}") from range_exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PublishError(f"Cloudinary delivery URL check failed: {_redact_secrets(str(exc), secrets)}") from exc
    return url


def cloudinary_upload(
    video_path: Path,
    job: dict[str, Any],
    config: dict[str, Any],
    credentials: dict[str, str],
) -> dict[str, Any]:
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise PublishError(f"Generated video is missing or empty: {video_path.name}")
    timestamp = str(int(time.time()))
    # An optional GitHub Actions secret may be present but empty. Treat an
    # empty override as unset so the validated config default still applies.
    folder = (os.environ.get("CLOUDINARY_FOLDER") or config["cloudinary_folder"]).strip().strip("/")
    if not folder:
        raise PublishError("CLOUDINARY_FOLDER or cloudinary_folder must be non-empty")
    fields = {
        "timestamp": timestamp,
        "folder": folder,
        "public_id": job["cloudinary_public_id"],
        "unique_filename": "false",
        "overwrite": "false",
    }
    preset = credentials["cloudinary_upload_preset"]
    if preset:
        fields["upload_preset"] = preset
    if config["cloudinary_unsigned_upload"]:
        fields.pop("unique_filename", None)
        fields.pop("overwrite", None)
    else:
        fields["api_key"] = credentials["cloudinary_api_key"]
        fields["signature"] = _signature(
            {key: value for key, value in fields.items() if key not in {"api_key", "signature"}},
            credentials["cloudinary_api_secret"],
        )
    body, boundary = _multipart_body(fields, video_path)
    url = f"https://api.cloudinary.com/v1_1/{urllib.parse.quote(credentials['cloudinary_cloud_name'], safe='')}/video/upload"
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "User-Agent": "astra-reels/1.0",
        },
        method="POST",
    )
    secrets = [credentials["cloudinary_api_secret"], credentials["instagram_token"]]
    return _request_json(request, label="Cloudinary upload", secrets=secrets, timeout=300)


def cloudinary_delete(public_id: str, config: dict[str, Any], credentials: dict[str, str]) -> str:
    timestamp = str(int(time.time()))
    fields = {
        "public_id": public_id,
        "timestamp": timestamp,
        "invalidate": "true",
        "type": "upload",
        "api_key": credentials["cloudinary_api_key"],
    }
    fields["signature"] = _signature(
        {key: value for key, value in fields.items() if key not in {"api_key", "signature"}},
        credentials["cloudinary_api_secret"],
    )
    data = urllib.parse.urlencode(fields).encode("utf-8")
    url = f"https://api.cloudinary.com/v1_1/{urllib.parse.quote(credentials['cloudinary_cloud_name'], safe='')}/video/destroy"
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "astra-reels/1.0",
        },
        method="POST",
    )
    response = _request_json(
        request,
        label="Cloudinary deletion",
        secrets=[credentials["cloudinary_api_secret"], credentials["instagram_token"]],
    )
    result = str(response.get("result", "")).lower()
    if result not in {"ok", "not found"}:
        raise PublishError("Cloudinary did not confirm deletion of the uploaded video")
    return result


def resolve_instagram_api_host(token: str, config: dict[str, Any]) -> str:
    """Match the Quotes project: honor an override, otherwise infer the host from the token."""
    configured = str(
        config.get("instagram_api_host") or os.environ.get("INSTAGRAM_API_HOST", "")
    ).strip()
    if not configured:
        configured = "graph.instagram.com" if token.startswith("IG") else "graph.facebook.com"
    configured = configured.removeprefix("https://").removeprefix("http://").rstrip("/")
    if configured not in {"graph.facebook.com", "graph.instagram.com"}:
        raise PublishError(
            "Instagram API host must be graph.facebook.com or graph.instagram.com"
        )
    return configured


def instagram_base_url(config: dict[str, Any], token: str) -> str:
    return f"https://{resolve_instagram_api_host(token, config)}/{config['instagram_api_version']}"


def instagram_request(
    method: str,
    path: str,
    parameters: dict[str, str],
    credentials: dict[str, str],
    config: dict[str, Any],
) -> dict[str, Any]:
    token = credentials["instagram_token"]
    base_url = instagram_base_url(config, token)
    if method == "GET":
        query = urllib.parse.urlencode({**parameters, "access_token": token})
        request = urllib.request.Request(
            f"{base_url}/{path}?{query}",
            headers={"User-Agent": "astra-reels/1.0"},
            method="GET",
        )
    else:
        body = urllib.parse.urlencode({**parameters, "access_token": token}).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/{path}",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "astra-reels/1.0",
            },
            method=method,
        )
    return _request_json(
        request,
        label=f"Instagram {method} {path.split('/')[0]}",
        secrets=[credentials["instagram_token"], credentials["cloudinary_api_secret"]],
    )


def instagram_create_reel(
    video_url: str,
    caption: str,
    credentials: dict[str, str],
    config: dict[str, Any],
) -> str:
    parameters = {
        "media_type": "REELS",
        "video_url": video_url,
        "share_to_feed": "true" if config["instagram_share_to_feed"] else "false",
    }
    if caption.strip():
        parameters["caption"] = caption
    response = instagram_request(
        "POST",
        f"{credentials['instagram_account_id']}/media",
        parameters,
        credentials,
        config,
    )
    container_id = response.get("id")
    if not isinstance(container_id, str) or not container_id:
        raise PublishError("Instagram did not return a Reel media container ID")
    return container_id


def instagram_container_status(
    container_id: str,
    credentials: dict[str, str],
    config: dict[str, Any],
) -> dict[str, Any]:
    return instagram_request(
        "GET",
        container_id,
        {"fields": "id,status_code,status"},
        credentials,
        config,
    )


def wait_for_instagram_container(
    container_id: str,
    credentials: dict[str, str],
    config: dict[str, Any],
) -> dict[str, Any]:
    deadline = time.monotonic() + config["instagram_processing_timeout_seconds"]
    while True:
        status = instagram_container_status(container_id, credentials, config)
        status_code = str(status.get("status_code", status.get("status", ""))).upper()
        if status_code in {"FINISHED", "PUBLISHED"}:
            return status
        if status_code in {"ERROR", "EXPIRED"}:
            raise PublishError(f"Instagram Reel processing ended with status {status_code}")
        if time.monotonic() >= deadline:
            raise PublishError(f"Timed out waiting for Instagram Reel processing (status {status_code or 'unknown'})")
        time.sleep(config["instagram_poll_interval_seconds"])


def instagram_publish_reel(
    container_id: str,
    credentials: dict[str, str],
    config: dict[str, Any],
) -> str:
    try:
        response = instagram_request(
            "POST",
            f"{credentials['instagram_account_id']}/media_publish",
            {"creation_id": container_id},
            credentials,
            config,
        )
    except PublishTransportError as exc:
        raise PublishUncertainError(
            "Instagram publication response was uncertain; the Reel was not retried automatically"
        ) from exc
    media_id = response.get("id")
    if not isinstance(media_id, str) or not media_id:
        raise PublishError("Instagram did not return a published Reel ID")
    return media_id


def verify_instagram_publication(
    media_id: str,
    credentials: dict[str, str],
    config: dict[str, Any],
) -> dict[str, Any]:
    response = instagram_request(
        "GET",
        media_id,
        {"fields": "id,media_type,media_product_type,permalink"},
        credentials,
        config,
    )
    if response.get("id") != media_id:
        raise PublishError("Instagram did not confirm the published media ID")
    product_type = str(response.get("media_product_type", "")).upper()
    media_type = str(response.get("media_type", "")).upper()
    if product_type and product_type != "REELS":
        raise PublishError("Instagram returned a non-Reel media product")
    if media_type and media_type not in {"REELS", "VIDEO"}:
        raise PublishError("Instagram returned an unexpected media type")
    return response


def load_publish_state(state_path: Path) -> list[dict[str, Any]]:
    if not state_path.is_file():
        return []
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"Could not read publishing state {state_path}: {exc}") from exc
    jobs = raw.get("jobs") if isinstance(raw, dict) else None
    if not isinstance(jobs, list) or not all(isinstance(job, dict) and isinstance(job.get("job_id"), str) for job in jobs):
        raise PublishError(f"Invalid publishing state in {state_path}")
    return jobs


def save_publish_state(state_path: Path, jobs: list[dict[str, Any]]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_name(f"{state_path.name}.tmp")
    try:
        temporary_path.write_text(json.dumps({"jobs": jobs[-200:]}, indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(state_path)
    except OSError as exc:
        raise PublishError(f"Could not save publishing state {state_path}: {exc}") from exc


def pending_publish_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [job for job in jobs if job.get("status") != "complete"]


def create_publish_job(
    source: Path,
    input_dir: Path,
    processed: ProcessedVideo,
    config: dict[str, Any],
) -> dict[str, Any]:
    output_path = processed.path
    fingerprint = f"{source_key(source, input_dir)}:{output_path.resolve()}:{output_path.stat().st_size}:{output_path.stat().st_mtime_ns}"
    job_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
    return {
        "job_id": job_id,
        "source": source_key(source, input_dir),
        "output": str(output_path),
        "quote": processed.quote,
        "short_caption": processed.social.short_caption,
        "hashtags": list(processed.social.hashtags),
        "caption": processed.social.instagram_caption,
        "cloudinary_public_id": f"astra_{job_id}",
        "status": "generated",
        "last_error": "",
    }


def publish_video_job(
    job: dict[str, Any],
    jobs: list[dict[str, Any]],
    state_path: Path,
    config: dict[str, Any],
) -> None:
    credentials = publishing_credentials(config)
    secrets = [credentials.get("instagram_token", ""), credentials.get("cloudinary_api_secret", "")]

    def persist() -> None:
        save_publish_state(state_path, jobs)

    try:
        if job.get("status") == "publish_uncertain" and not job.get("media_id"):
            raise PublishUncertainError(
                "Instagram publication outcome is uncertain; verify the account before retrying this job to avoid a duplicate Reel"
            )
        video_path = Path(job["output"])
        if not video_path.is_file() or video_path.stat().st_size == 0:
            raise PublishError(f"Local generated video is missing: {video_path}")

        if not job.get("cloudinary_url"):
            upload = cloudinary_upload(video_path, job, config, credentials)
            public_id = upload.get("public_id")
            secure_url = upload.get("secure_url")
            if not isinstance(public_id, str) or not public_id:
                raise PublishError("Cloudinary did not return a public_id")
            job["cloudinary_public_id"] = public_id
            job["cloudinary_asset_id"] = upload.get("asset_id", "")
            persist()
            if not isinstance(secure_url, str) or not secure_url:
                raise PublishError("Cloudinary did not return a secure_url")
            job["cloudinary_url"] = validate_public_video_url(secure_url, secrets)
            job["status"] = "uploaded"
            job["last_error"] = ""
            persist()
            LOGGER.info("Cloudinary upload completed for %s", video_path.name)
        else:
            job["cloudinary_url"] = validate_public_video_url(job["cloudinary_url"], secrets)

        if not job.get("container_id"):
            job["container_id"] = instagram_create_reel(
                job["cloudinary_url"],
                str(job.get("caption", "")),
                credentials,
                config,
            )
            job["status"] = "container_created"
            job["last_error"] = ""
            persist()
            LOGGER.info("Instagram Reel container created for %s", video_path.name)

        wait_for_instagram_container(job["container_id"], credentials, config)
        job["status"] = "ready_to_publish"
        job["last_error"] = ""
        persist()

        if not job.get("media_id"):
            job["media_id"] = instagram_publish_reel(job["container_id"], credentials, config)
            job["status"] = "published"
            persist()
            LOGGER.info("Instagram confirmed Reel publication for %s", video_path.name)

        publication = verify_instagram_publication(job["media_id"], credentials, config)
        job["permalink"] = publication.get("permalink", "")
        job["status"] = "published"
        persist()

        deletion_result = cloudinary_delete(job["cloudinary_public_id"], config, credentials)
        job["cloudinary_deletion"] = deletion_result
        job["status"] = "complete"
        job["last_error"] = ""
        persist()
        LOGGER.info("Cloudinary cleanup confirmed for %s", video_path.name)
        if job.get("permalink"):
            LOGGER.info("Published Instagram Reel: %s", job["permalink"])
    except PublishUncertainError as exc:
        job["status"] = "publish_uncertain"
        job["last_error"] = _redact_secrets(str(exc), secrets)
        try:
            persist()
        except PublishError as state_exc:
            LOGGER.error("Could not persist publishing state: %s", state_exc)
        raise
    except PublishError as exc:
        job["last_error"] = _redact_secrets(str(exc), secrets)
        if job.get("status") == "complete":
            job["status"] = "published"
        try:
            persist()
        except PublishError as state_exc:
            LOGGER.error("Could not persist publishing state: %s", state_exc)
        raise


def process_one(
    source: Path,
    input_dir: Path,
    output_dir: Path,
    config: dict[str, Any],
    font_path: Path,
    ffmpeg: str,
    ffprobe: str,
    quote_history: list[dict[str, Any]],
    quote_history_path: Path,
) -> ProcessedVideo | None:
    video_config = {
        **config,
        "text_color": text_color_for_source(source, input_dir, config),
    }
    metadata = probe(source, ffprobe)
    selection = generate_quote_selection(source, video_config, quote_history)
    quote = add_quote_end_symbol(selection.text, source, video_config)
    social = generate_social_metadata(quote, selection.category, video_config)
    output_path = unique_output_path(output_dir, source.stem)
    LOGGER.info("Input: %s", source.name)
    LOGGER.info("Quote: %s", quote)
    LOGGER.info("Short caption: %s", social.short_caption)
    LOGGER.info("Hashtags: %s", " ".join(social.hashtags))
    LOGGER.info("Instagram caption preview: %s", social.instagram_caption.replace("\n", " | "))
    LOGGER.info("Text color: %s", video_config["text_color"])
    LOGGER.info("Quote category=%s score=%.2f", selection.category, selection.score)
    if video_config["dry_run"]:
        LOGGER.info("Dry run: would write %s", output_path.name)
        return None
    render_video(source, output_path, quote, metadata, video_config, font_path, ffmpeg)
    verified = verify_output(metadata, output_path, ffprobe)
    quote_history.append({
        "quote": selection.text,
        "category": selection.category,
        "source": source.as_posix(),
    })
    save_quote_history(quote_history_path, quote_history, config["quote_history_limit"])
    LOGGER.info(
        "Success: %s (%dx%d, %.3fs, audio=%s)",
        output_path.name,
        *video_dimensions(verified),
        duration_seconds(verified),
        has_audio(verified),
    )
    return ProcessedVideo(path=output_path, quote=quote, social=social)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--limit", type=int, help="Process at most this many unused inputs in this selection cycle")
    parser.add_argument("--all", action="store_true", help="Process all unused inputs in this selection cycle")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and quote inputs without creating videos")
    parser.add_argument("--publish", action="store_true", help="Publish generated output exclusively as Instagram Reels")
    parser.add_argument("--strict", action="store_true", help="Stop at the first failed input")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    project_root = Path(__file__).resolve().parent
    try:
        load_dotenv(project_root / ".env")
        config = load_config(resolve_path(project_root, args.config))
        if args.publish and args.dry_run:
            raise AstraError("--dry-run never uploads, publishes, or deletes Cloudinary assets; remove --dry-run to publish")
        if args.dry_run:
            config["dry_run"] = True
        if args.strict:
            config["strict"] = True
        ffmpeg, ffprobe = require_dependencies(project_root, config)
        input_dir = resolve_path(project_root, config["input_dir"])
        output_dir = resolve_path(project_root, config["output_dir"])
        selection_state_path = resolve_path(project_root, config["selection_state_file"])
        quote_history_path = resolve_path(project_root, config["quote_history_file"])
        quote_history = load_quote_history(quote_history_path)
        publish_state_path = resolve_path(project_root, config["publish_state_file"])
        publish_jobs = load_publish_state(publish_state_path) if args.publish else []
        if args.publish:
            publishing_credentials(config)
            pending_jobs = pending_publish_jobs(publish_jobs)
            if pending_jobs:
                retry_jobs = pending_jobs if args.all else pending_jobs[:1]
                pending_failures = 0
                for job in retry_jobs:
                    try:
                        publish_video_job(job, publish_jobs, publish_state_path, config)
                    except PublishError as exc:
                        pending_failures += 1
                        LOGGER.error("Publishing incomplete for job %s: %s", job["job_id"], exc)
                        if config["strict"]:
                            break
                if pending_failures:
                    return 1
                LOGGER.info("Completed %d pending publishing job(s); no new video was selected", len(retry_jobs))
                return 0
        output_dir.mkdir(parents=True, exist_ok=True)
        font_path = resolve_font(project_root, config["font_path"])
        sources = scan_inputs(input_dir, config["recursive_scan"])
        if args.limit is not None:
            if args.limit < 1:
                raise AstraError("--limit must be at least 1")
        if not sources:
            raise AstraError(f"No MP4 or MOV files found in {input_dir}")
        discovered_count = len(sources)
        selection_count = None if args.all else (args.limit if args.limit is not None else 1)
        sources, used_sources = select_sources(
            sources,
            input_dir,
            selection_state_path,
            selection_count,
        )
        LOGGER.info("Found %d input video(s); selected %d for this run; using font %s", discovered_count, len(sources), font_path)
        failures = 0
        for source in sources:
            try:
                processed = process_one(
                    source,
                    input_dir,
                    output_dir,
                    config,
                    font_path,
                    ffmpeg,
                    ffprobe,
                    quote_history,
                    quote_history_path,
                )
                if processed is not None:
                    if args.publish:
                        job = create_publish_job(source, input_dir, processed, config)
                        publish_jobs.append(job)
                        save_publish_state(publish_state_path, publish_jobs)
                    used_sources.add(source_key(source, input_dir))
                    save_selection_state(selection_state_path, used_sources)
                    if args.publish:
                        publish_video_job(job, publish_jobs, publish_state_path, config)
            except AstraError as exc:
                failures += 1
                LOGGER.error("Failed: %s (%s)", source.name, exc)
                if config["strict"]:
                    break
        if failures:
            LOGGER.error("Finished with %d failure(s)", failures)
            return 1
        return 0
    except AstraError as exc:
        LOGGER.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
