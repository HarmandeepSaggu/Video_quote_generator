# ASTRA.md — Raw Video Quote Overlay Project

## 1. Project Objective

Build a local Python application that takes my existing raw video files from the `input/` folder, adds a meaningful quote overlay matching my provided reference image, and exports finished videos to an output folder.

**Only add a quote to my existing videos.** Do not generate videos from scratch, replace footage, generate images, add music, or perform unnecessary video editing.

## 2. Input and Output Folders

Use this default folder structure:

```text
project/
├── ASTRA.md
├── main.py
├── config.json
├── requirements.txt
├── input/
│   └── raw videos go here
└── output/
    └── finished quote videos go here
```

- Read source videos from `input/`.
- Write finished videos to `output/`.
- Create `output/` automatically if it does not exist.
- Support MP4 and MOV files when supported by FFmpeg.
- Scan `input/` for supported video files; optionally support recursive scanning through configuration.
- Process one or multiple videos.
- A normal CLI run selects one unused video and records it in the selection state file. It does not select that video again until every discovered video has been used once, then the cycle starts over.
- Never overwrite or modify original videos.
- Provide a one-video test mode before batch processing.
- Ignore files already inside `output/` so they are not processed again.

## 3. Quote Generation

Generate one original quote suitable for the video's mood and visual content.

Use a configurable distribution across these categories: feeling misunderstood,
overthinking and late-night thoughts, loneliness, letting go and changing
relationships, self-respect and boundaries, healing and quiet resilience, and
hard truths about human behaviour. For each output, generate 3–5 candidates,
score them from 1–10 for emotional impact, relatability, originality, mobile
clarity, shareability, and category fit, then select the strongest candidate.
Keep a lightweight local history to reject exact and near-duplicate wording and
to reduce consecutive category repetition.

Preferred themes:
- Overthinking and inner peace.
- Appreciating the present moment.
- Patience, healing, and personal growth.
- Letting go and acceptance.
- Life lessons, change, and self-respect.

Quotes must feel natural, reflective, emotional, and meaningful—not generic motivational slogans.

Aim for approximately 6–22 words, adjusted to fit the available screen space and the video's duration. Use an optional configurable AI API to generate quotes. Keep API credentials in environment variables or a local `.env` file excluded from version control. Include a local fallback option so the project can be tested without an API key.

Do not attribute generated quotes to famous people unless their attribution has been verified.

## 4. Mandatory Quote Styling

Apply the same typography and placement consistently to every video.

- Primary font: Cormorant Garamond.
- Fallback fonts: Libre Baskerville, then Georgia.
- Font weight: SemiBold (600).
- Text color: `#F2F0EB` for `White Font` inputs and `#F2D675` for `Yellow Font` inputs, with `text_color` as the fallback.
- Starting font size: 34 px for a 1080 × 1920 output.
- Alignment: Left.
- Left margin: approximately 13% of frame width.
- Top position: approximately 33% of frame height.
- Line spacing: 1.2–1.3 times the font size.
- Text shadow: None or extremely subtle.
- Background box: None.
- Use deterministic intelligent breakpoints based on measured rendered width, punctuation, phrase boundaries, line balance, and orphan-word avoidance. Treat 42 characters as a soft guardrail, never as a fixed words-per-line rule.
- Add a simple configured text accent at the quote's end: `quote —`, `quote >>`, or `quote :)`. Keep the symbol attached to the final word.
- No emoji graphics, headings, decorative effects, or watermarks.
- Keep the quote in a consistent center-left position: left aligned, vertically centered, and inside safe margins on every side.

Use the supplied reference image as the visual authority. Keep font size, margins, line spacing, and positioning configurable. Bundle the chosen font locally when licensing permits. If the reference image/video is not available for inspection, use the values above and do not claim a pixel-perfect match.

## 5. Video Processing Rules

- Preserve the original video footage.
- Preserve the original audio and existing music.
- Do not add, replace, remix, or normalize music.
- Do not change playback speed.
- Do not trim the source video by default.
- Preserve the source video's original duration unless a different duration is explicitly configured.
- Add the quote as a text overlay.
- Match the reference's text animation when the reference can be inspected. Otherwise, use static text or a subtle fade-in.
- Keep the complete quote visible and readable without cropping.
- Do not add transitions, filters, effects, or generated footage.
- If a video has no audio, do not add an audio track.

When the explicit `--publish` option is used, upload the verified local output
to Cloudinary, create and publish it only as an Instagram Reel, verify the
published media, and delete the matching Cloudinary asset only after successful
publication. Keep the local output. If any publishing or cleanup step is
uncertain, retain the Cloudinary asset and persist a retryable publishing job.

## 6. Export Format

Default export settings:

- Container: MP4.
- Video codec: H.264.
- Audio codec: AAC when audio is present.
- Resolution: Preserve the source resolution by default.
- Frame rate: Preserve the source frame rate when practical.
- Duration: Preserve the original duration.
- Aspect ratio: Preserve the original aspect ratio by default.

If a vertical 9:16 export at 1080 × 1920 is required, make it configurable. Never stretch or distort the original footage. Use a configurable crop or fit strategy only when necessary to meet explicitly selected output dimensions.

Rendering text normally requires video re-encoding. Use sensible quality settings and preserve the original audio stream where possible; if the audio must be re-encoded for container compatibility, document that clearly.

## 7. Processing Pipeline

1. Load and validate `config.json`.
2. Scan `input/` for supported videos.
3. Inspect video dimensions, duration, frame rate, and audio streams with `ffprobe`.
4. Choose a configured emotional category and generate 3–5 quote candidates.
5. Score candidates, reject malformed or near-duplicate wording, and validate the selected quote's length, line wrapping, and safe margins.
6. Render the quote overlay with the required typography.
7. Preserve the existing audio and music.
8. Export the finished video to `output/` with a unique filename.
9. Verify that the output exists and check playback metadata, dimensions, duration, and audio presence.
10. Log the input filename, quote, output filename, and processing status.
11. Continue to the next input if one file fails, unless strict mode is enabled.
12. When `--publish` is explicitly selected, upload the verified output to Cloudinary, publish it through the Instagram `REELS` container workflow, verify publication, and delete the temporary Cloudinary asset only after confirmation.

Use FFmpeg/ffprobe and Python where appropriate. Escape text safely; do not build shell commands directly from quote text or filenames.

## 8. Suggested Configuration

Create a `config.json` with settings equivalent to:

```json
{
  "input_dir": "input",
  "output_dir": "output",
  "recursive_scan": true,
  "quote_provider": "groq",
  "quote_model": "openai/gpt-oss-120b",
  "quote_category_distribution": {
    "misunderstood": 0.20,
    "overthinking": 0.16,
    "loneliness": 0.14,
    "letting_go": 0.14,
    "self_respect": 0.14,
    "healing": 0.12,
    "hard_truths": 0.10
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
    "Yellow Font": "#F2D675"
  },
  "text_alignment": "left",
  "left_margin_percent": 13,
  "top_position_percent": 33,
  "line_spacing": 1.2,
  "max_line_characters": 42,
  "adaptive_position": false,
  "position_analysis_samples": 8,
  "vertical_safe_margin_percent": 12,
  "quote_end_symbols": ["—", ">>", ":)"],
  "text_shadow": false,
  "text_animation": "reference",
  "preserve_source_audio": true,
  "preserve_source_duration": true,
  "preserve_source_resolution": true,
  "output_container": "mp4",
  "output_video_codec": "libx264",
  "output_audio_codec": "aac",
  "selection_state_file": ".video_selection_state.json",
  "publish_state_file": ".instagram_publish_state.json",
  "cloudinary_folder": "glimpse-of-thoughts/reels",
  "cloudinary_unsigned_upload": false,
  "instagram_api_version": "v21.0",
  "instagram_caption": "",
  "instagram_processing_timeout_seconds": 600,
  "instagram_poll_interval_seconds": 10,
  "dry_run": false
}
```

These are safe starter defaults. Validate configuration and give helpful errors for invalid values, missing paths, or missing dependencies. Never place real API keys in `config.json`; use environment variables or `.env`.

## 9. Suggested Technology

Prefer a simple, maintainable local Python implementation.

- Python for orchestration and quote validation.
- FFmpeg/ffprobe for video inspection, rendering, encoding, and audio preservation.
- Pillow or another suitable text-rendering method for text measurement and layout.
- An optional compatible LLM API for quote generation.

Avoid adding a database, web server, frontend, Docker, cloud storage, or paid media API unless genuinely necessary. Include `requirements.txt`, `.gitignore`, and setup instructions. Check that FFmpeg and ffprobe are installed and explain how to install them if missing.

## 10. Command-Line Usage

Provide commands such as:

```bash
python main.py --dry-run
python main.py --limit 1
python main.py --all
python main.py --publish --limit 1
```

Adapt command options to the actual implementation and document them accurately. The one-video test mode should select one file from `input/` without changing the source file. `--publish` is explicit and always uses the Instagram `REELS` workflow; `--dry-run` never publishes or deletes remote assets.

## 11. Testing and Acceptance Criteria

Test the following before claiming completion:

- A video with existing music: quote is overlaid and original audio remains.
- A video without audio: quote is overlaid and no music is added.
- Long quote: wraps cleanly and remains within safe margins.
- Short quote: remains visually balanced.
- Light and dark backgrounds: text remains readable while preserving the reference style.
- Missing font, FFmpeg, API key, or invalid input folder: helpful error is shown.
- Failed quote generation: configured fallback or safe failure works.
- Multiple inputs: one failed video does not corrupt other outputs.
- Output verification: file plays and duration/resolution/audio are checked.
- Original files remain unchanged.
- No secrets are logged or committed.

Do not claim tests passed unless they were actually run.

## 12. Deliverables

Create or update:

- `ASTRA.md` — this specification.
- `main.py` and any supporting Python modules.
- `config.json` — safe defaults.
- `requirements.txt`.
- `.gitignore` — exclude `.env`, secrets, temporary files, and generated output if appropriate.
- `README.md` — installation, setup, usage, and troubleshooting.

At completion, report which files were created, how to install dependencies, how to put videos in `input/`, how to run a one-video test, and where finished videos are saved.

## 13. Non-Negotiable Requirements

- **Input videos are read from the `input/` folder.**
- **Finished videos are saved to the `output/` folder.**
- **Only overlay a quote on the existing video.**
- **Do not add music. Preserve the source video's audio.**
- **Do not replace, regenerate, or unnecessarily alter footage.**
- **Preserve the original duration and resolution by default.**
- **Use the specified warm-ivory serif typography and reference placement.**
- **Keep source videos untouched and API keys secure.**
