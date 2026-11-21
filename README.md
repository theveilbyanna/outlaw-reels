# outlaw-reels

Anna's daily reel machine. Every morning a scheduled Claude run:

1. picks today's brand (FrickFake → UAOM → The Veil → Outlaw Built Media → Veil Academy → Pocket Built, one a day),
2. writes a fresh reel script (a small JSON file) from `BRANDS.md`,
3. renders it to a 1080×1920 MP4 with music using the engine in `engine/`,
4. hosts the video on the public `videos` branch of this repo, so Metricool can fetch it,
5. schedules it on **Facebook (Reel) + TikTok** in Metricool (blog 7933639), set to publish automatically,
6. updates the **Outlaw Daily Reels** page (captions with Copy buttons, video, status):
   https://claude.ai/artifact/EQMNyJfwpUky7ydjpnyP9L

The full run book the scheduled task follows is **`DAILY.md`**. Change that file to change what the daily run does.

## Folders

| Path | What it is |
|---|---|
| `engine/make_reel.py` | JSON script → finished reel (`<slug>.mp4` + `<slug>.jpg` cover) |
| `engine/lib.py`, `engine/audio.py` | drawing helpers and the synth music / sound effects |
| `fonts/` | open-licence fonts the engine uses |
| `assets/veil/` | The Veil art (backgrounds, logo, the 78 tarot cards in `web/`) |
| `specs/` | example scripts, one per brand |
| `tools/reelq.py` | the queue: hosts reels on the `videos` branch, tracks what is scheduled |
| `tools/page.py` | builds the Daily Reels page |
| `BRANDS.md` | facts, links, angles and hashtags per brand. The only claims a reel may make |
| `DAILY.md` | the daily run book |

The `videos` branch holds the reel files, their covers and `queue.json` (every reel, its captions
and where it is scheduled). It is rewritten as a single commit on every update so the repo stays
small. Files older than 60 days are removed; their records stay.

Public video URL pattern: `https://raw.githubusercontent.com/Theveilbyanna/outlaw-reels/videos/<file>.mp4`

## Make a reel by hand

```bash
bash setup.sh                                   # deps + videos branch checkout
python3 engine/make_reel.py specs/uaom.json out --stills   # contact sheet of every scene
python3 engine/make_reel.py specs/uaom.json out            # full render → out/<slug>.mp4
```

## Script format

```json
{"theme": "uaom", "slug": "uaom-after-hours", "title": "UAOM after-hours calls", "angle": "after-hours calls",
 "scenes": [ {...}, {...} ]}
```

`theme`: `frickfake`, `uaom`, `veil`, `academy`, `outlaw`, `pocket` (colours, fonts, background, music).
4–6 scenes, 15–30 seconds. Each scene's length comes from its word count (2.6–7.5 s); add `"dur": 4.0` to force one.
Any scene can take `"bg": "<file in assets/veil>"` on the veil/academy themes.

| type | fields | notes |
|---|---|---|
| `hook` | `kicker`, `lines` [...], `sub` | 1–3 short lines (≤ 16 characters each reads best). Prefix one line with `*` to colour it. Scene 1 is always a hook. |
| `statement` | `text`, `sub` | one bold sentence |
| `bullets` | `title`, `items` [[title, sub], ...], `numbered`, `foot` | up to 4 items |
| `big` | `kicker`, `big`, `sub`, `checks` [...] | one big number or word (e.g. `$95`) and up to 4 check lines |
| `chat` | `title`, `messages` [["them"\|"me", text], ...] | up to 6 bubbles |
| `xlist` | `title`, `items` [...], `after` | crossed-out list ("not this"), up to 6 |
| `card` | `kicker`, `name`, `card` (`web/<file>.webp`), `words` [3], `sub` | tarot card with 3 anchor words (veil/academy) |
| `cta` | `logo`, `kicker`, `headline`, `url`, `button`, `foot` | always the last scene. `logo`: veil, academy, frickfake, uaom, outlaw, pocket |

Environment variables (all optional): `REELS_OUT` (default `./out`), `VEIL_DIR` (default `assets/veil`),
`REEL_WORKERS` (default 4), `OR_VIDEOS` (videos branch checkout, default `/home/claude/or-videos`).
