# ASTRA raw video quote overlay

This local Python application adds one original, reflective quote to each existing MP4 or MOV in `input/` and writes a new MP4 to `output/`.

It preserves the source footage, resolution, frame timing, duration, and audio presence. The video is necessarily re-encoded to burn in the text. Existing AAC audio is copied; other source audio is converted to AAC only when required for MP4 compatibility. No audio is added to a silent source.

## Styling

- Cormorant Garamond SemiBold (600), bundled under `assets/fonts/`
- folder-based quote color: `White Font` uses `#F2F0EB`, `Yellow Font` uses `#F2D675`
- 34 px at 1080 px wide, scaled proportionally for another source width
- left aligned, 13% from the left and 33% from the top
- 1.2 line spacing
- deterministic intelligent wrapping that measures rendered width, favors punctuation and phrase boundaries, balances line lengths, and avoids orphan words (with 42 characters as a soft guardrail)
- a repeatable accent selected from `quote_end_symbols`: `quote —`, `quote >>`, or `quote :)`
- end symbols stay attached to the last word rather than wrapping onto a line by themselves
- no box, heading, watermark, or visible shadow
- fixed center-left placement: the text stays left aligned and is vertically centered inside a 12% top/bottom safe margin

Adjust `font_size`, `font_weight`, `line_spacing`, `max_line_characters`, and `quote_end_symbols` in `config.json`. The character limit keeps lines compact; measured pixel width keeps the quote inside the left and right margins, and the quote is wrapped only at word boundaries. Use one symbol (for example, `[":)"]`) for a consistent style across all videos, or `[]` to disable accents. The current `adaptive_position: false` setting keeps the composition consistently center-left; the optional frame-scoring code remains available if adaptive placement is enabled later.

These defaults incorporate the requested smaller text, natural line breaks, and simple symbols. A reference image is not included in this project.

## Setup

1. Install Python 3.10+.
2. Install FFmpeg. The `ffmpeg` and `ffprobe` commands must both be on `PATH`.
   - Debian/Ubuntu: `sudo apt-get update && sudo apt-get install ffmpeg`
   - macOS Homebrew: `brew install ffmpeg`
   - Windows: install an FFmpeg build and add its `bin` folder to `PATH`.

   For a temporary self-contained Linux test, the application also detects an
   extracted build at `tools/ffmpeg-*-amd64-static/`. You can instead set
   `ffmpeg_path` and `ffprobe_path` explicitly in `config.json`.
3. Optional Python environment:

   ```bash
   python -m venv .venv
   # macOS/Linux
   . .venv/bin/activate
   # Windows PowerShell: .venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

Pillow is used to measure the bundled font and create a transparent text-only overlay layer. The local quote mode does not need an API key.

The bundled Cormorant Garamond font is distributed under the SIL Open Font License; see `assets/fonts/OFL.txt`.

## Usage

Put source videos in `input/` or its subfolders. Originals are never overwritten. The output directory is created automatically.

Each normal run processes exactly one unused video. The selected video is recorded in
`.video_selection_state.json`, so the next run selects another video instead of
repeating it. After every discovered video has been used once, the selection cycle
starts over. The state file is updated only after a video renders and verifies
successfully. Use `--all` to process every unused video in the current cycle, or
`--limit N` to process up to N unused videos.

Run the next one-video selection:

```bash
python main.py
```

Inspect the next selected video without rendering it:

```bash
python main.py --dry-run
```

Process all unused MP4/MOV inputs in the current cycle:

```bash
python main.py --all
```

By default, a failed file is logged and the next selected input continues. Use
`--strict` to stop after the first failure. Recursive scanning is enabled by
default so videos in the `White Font` and `Yellow Font` subfolders are included.

## Instagram Reel publishing

Publishing is opt-in. A normal generation run never contacts Cloudinary or
Instagram. Copy `.env.example` to `.env` and fill in the publishing variables:

```env
INSTAGRAM_TOKEN=your-token
INSTAGRAM_ACCOUNT_ID=your-instagram-professional-account-id
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
CLOUDINARY_UPLOAD_PRESET=your-preset
CLOUDINARY_FOLDER=glimpse-of-thoughts/reels
```

Cloudinary uploads are signed by default. Set
`"cloudinary_unsigned_upload": true` only when deliberately using an unsigned
preset; the API key and secret are still required for post-publication cleanup.
The environment `CLOUDINARY_FOLDER` overrides the same-named config default.

The Instagram API host follows the same behavior as the Quotes project. Set
`instagram_api_host` in `config.json` or `INSTAGRAM_API_HOST` in `.env` to
explicitly choose `graph.instagram.com` or `graph.facebook.com`. If neither is
set, tokens beginning with `IG` use `graph.instagram.com`; other tokens use
`graph.facebook.com`.
For every selected quote, ASTRA also creates a 2–3 word emoji caption and
6–7 related hashtags. The final Instagram caption contains only the generated
short caption followed by the hashtags; the quote is shown in the video but is
not repeated in the Instagram caption. Set `instagram_share_to_feed` to `true`
to place future Reels in both the Instagram Feed/profile grid and the Reels tab.

Generate one selected video and publish it exclusively as an Instagram Reel:

```bash
python main.py --publish --limit 1
```

The workflow validates the generated output, uploads it to Cloudinary, confirms
the HTTPS delivery URL, creates an Instagram `REELS` container, waits for the
container to finish processing, publishes it, verifies the published media, and
only then deletes the matching Cloudinary asset. Local output files are never
deleted.

Use dry-run to preview generation without uploading, publishing, or deleting:

```bash
python main.py --dry-run --limit 1
```

Dry-run prints the generated short caption, hashtags, and complete Instagram
caption preview. It does not render a video, upload to Cloudinary, publish to
Instagram, delete any Cloudinary asset, or update selection state.

If a publish or cleanup step fails, `.instagram_publish_state.json` records the
job and Cloudinary asset ID so the next `--publish` run retries the pending step
instead of creating a duplicate Reel. A pending job is retried before a new
video is selected. Cleanup failures are safely retryable after publication. If
the Instagram publish request itself has an uncertain response, ASTRA marks the
job `publish_uncertain` and refuses an automatic retry until the account is
checked, preventing a possible duplicate Reel. Use `--publish --all` to retry
all safe pending jobs or process all unused videos in the current selection
cycle.

## GitHub Actions schedule

`.github/workflows/instagram-reel-publisher.yml` publishes one Reel at 11:00,
15:00, and 20:00 every day in `Asia/Kolkata` time. It also supports manual
execution with **Run workflow** in GitHub Actions.

Add these repository secrets before enabling the schedule:

- `GROQ_API_KEY` (optional; local quote fallback is used when absent)
- `INSTAGRAM_TOKEN`
- `INSTAGRAM_ACCOUNT_ID`
- `INSTAGRAM_API_HOST` (optional; leave unset for token-based host detection)
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- `CLOUDINARY_UPLOAD_PRESET`
- `CLOUDINARY_FOLDER` (optional; defaults to `glimpse-of-thoughts/reels`)

The workflow installs FFmpeg on the runner, publishes one input video per run,
and commits the selection, quote, and publishing state files so later scheduled
runs continue through the input cycle instead of selecting the same video every
time. The `.env` file, virtual environment, generated output videos, and local
FFmpeg bundle are not committed.

Instagram publishing requires an eligible Instagram Professional account and a
valid Graph API access token with content-publishing permissions. No real
publishing is performed by the project's tests.

## Groq quote generation

Quotes are generated with Groq's OpenAI-compatible API using
`openai/gpt-oss-120b` by default. Keep the API key outside source control:

```bash
cp .env.example .env
# Add your key to .env:
# GROQ_API_KEY=your-key
python main.py --limit 1
```

The active settings are `"quote_provider": "groq"` and
`"quote_model": "openai/gpt-oss-120b"` in `config.json`. You can change the
model there if needed. If the API key is missing or the request fails, the
application safely uses its local original-candidate fallback. Keys are never
logged. Set `quote_provider` to `local` to disable API calls.

### Quote strategy

Each generated reel selects one configured emotional category, then creates four
candidate quotes and scores them locally for emotional impact, relatability,
originality, mobile clarity, shareability, and category fit. The highest-scoring
candidate above `quote_min_score` is selected. The category distribution,
candidate count, word range, minimum score, and similarity threshold are all
configurable in `config.json`.

Successful quotes are stored in `.quote_history.json` after the output passes
video verification. Recent history is used to reject near-duplicate wording and
to avoid repeating the same category in consecutive runs. The history file is
local and ignored by Git. If a provider response is malformed or unavailable,
ASTRA logs the reason and uses the same validation and scoring process with its
bundled original candidates.

## Troubleshooting

- **Missing FFmpeg/ffprobe:** install FFmpeg and confirm `ffmpeg -version` and `ffprobe -version` work in the same terminal.
- **Missing font:** restore `assets/fonts/CormorantGaramond-Variable.ttf`, or install Cormorant Garamond, Libre Baskerville, or Georgia. The application reports the fallback it selected.
- **No inputs:** supported extensions are `.mp4` and `.mov`; check that the files are inside `input/`.
- **Output verification failure:** the incomplete output is left available for inspection, while the source remains untouched. Check the FFmpeg error and the source file's health with `ffprobe`.

## Project files

- `main.py` — configuration, scanning, probing, quoting, safe FFmpeg invocation, rendering, and output verification.
- `config.json` — safe defaults matching the specification.
- `assets/fonts/` — locally bundled font and license.
- `input/` — place raw videos here.
- `output/` — finished quote videos are saved here.
