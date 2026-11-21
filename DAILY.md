# Daily run book

You are making today's reel for Anna and handing it to Metricool. Nobody is watching: work on your
own, take the most reasonable choice when something is unclear, and do not message Anna except the
one-line summary at the end. Times are America/Los_Angeles.

Key ids
- Metricool blogId: `7933639` (posts go to **Facebook as a Reel** and **TikTok**; Clapper Anna posts herself)
- Daily Reels page (artifact): slug `6c8977da-59c2-495f-adef-615aba219c6b`, url https://claude.ai/artifact/EQMNyJfwpUky7ydjpnyP9L
- Outlaw Pulse (artifact with a database): slug `c467e07f-51d1-42d3-9320-1b9166a8abed`

## 1. Set up
```bash
cd /home/claude/outlaw-reels && bash setup.sh
python3 tools/reelq.py today
```
`today` prints today's brand, the recent hooks for that brand, `skip_new_reel`, and reels waiting
to be scheduled. If `skip_new_reel` is true, go straight to step 4.

## 2. Write today's reel
Read `BRANDS.md` (facts, links, angles, hashtags) and look at the example script for the brand in
`specs/<brand>.json` (`veil.json`, `academy.json`, `frickfake.json`, `uaom.json`, `outlaw.json`, `pocket.json`).
The script format is in `README.md`.

- Pick an angle from the brand's list (or a new one that stays inside the facts) that is **not** in
  `recent_for_brand`. Never reuse a hook, even reworded.
- Scene 1 is a `hook` that stops the scroll in one second: a bold claim, a question or a pain point.
- 4–6 scenes, about 15–30 seconds. Short lines; the text carries the whole message (no voice).
- Last scene is a `cta` with the brand's logo, the on-screen link from BRANDS.md and a clear action.
- Set `"slug"` (lowercase-hyphenated keywords, e.g. `uaom-missed-call-missed-job`), `"title"` and `"angle"`.
- Academy days: a card of the day (`card` scene) with a card not used recently.

Save it as `out/<slug>.json`, then check every scene before the full render:
```bash
python3 engine/make_reel.py out/<slug>.json out --stills
```
Open `out/stills_<slug>.jpg` with the Read tool. Check: all text inside the frame, nothing
overlapping, nothing cut off, readable contrast, correct spelling and link. Fix the script and
check again until it is right (at most 3 tries).

## 3. Render, caption, queue
```bash
python3 engine/make_reel.py out/<slug>.json out
```
It prints `{"video", "cover", "seconds"}`. Grab one frame near the end and look at it:
`ffmpeg -v error -sseof -1.5 -i out/<slug>.mp4 -frames:v 1 out/end.jpg`, then Read `out/end.jpg`.

Write `out/<slug>.captions.json` following "Caption rules" in BRANDS.md (facebook, tiktok, clapper,
optional comment, link, isAigc from the brand's entry).

Pick the post time: call Metricool `getBestTimeToPostByNetwork` (brandId 7933639, facebook, today
10:00–20:00, timezone America/Los_Angeles). Use the best hour that is at least 2 hours from now;
if there is no data, use 12:30. Then queue it:
```bash
python3 tools/reelq.py add --spec out/<slug>.json --video out/<slug>.mp4 --cover out/<slug>.jpg \
  --captions out/<slug>.captions.json --target <YYYY-MM-DD>T<HH:MM>
```
This puts the video on the public `videos` branch and prints its `video_url`.

## 4. Schedule in Metricool
Call `getBrandSettings`.
- If it errors or shows no Facebook and no TikTok connected:
  `python3 tools/reelq.py meta --metricool missing` and go to step 5.
- If the connected TikTok account is **@flynndabest**, that account is not Anna's: do not post to
  TikTok. Use `--skip tiktok` in the plan below and
  `python3 tools/reelq.py meta --metricool connected --note "The TikTok connected in Metricool is @flynndabest, not yours. Reconnect your TikTok in Metricool."`
- Otherwise: `python3 tools/reelq.py meta --metricool connected` (add `--skip` for any network
  that is not connected, e.g. `--skip tiktok`).

```bash
python3 tools/reelq.py plan [--skip tiktok]
```
`plan` lists every post to create now (today's reel and anything still waiting, at most 3 per
network per day, within 2 days), each with its exact time. For each entry call
`createScheduledPost` with blogId `7933639`, `date` = the entry's `date_param`, and `info`:

Facebook:
```json
{"autoPublish": true, "draft": false, "descendants": [], "firstCommentText": "<comment or empty>",
 "hasNotReadNotes": false, "media": ["<media>"], "mediaAltText": [], "providers": [{"network": "facebook"}],
 "publicationDate": <publicationDate>, "shortener": false, "smartLinkData": {"ids": []},
 "text": "<text>", "facebookData": {"type": "REEL"}}
```
TikTok:
```json
{"autoPublish": true, "draft": false, "descendants": [], "firstCommentText": "",
 "hasNotReadNotes": false, "media": ["<media>"], "mediaAltText": [], "providers": [{"network": "tiktok"}],
 "publicationDate": <publicationDate>, "shortener": false, "smartLinkData": {"ids": []},
 "text": "<text>", "tiktokData": {"privacyOption": "PUBLIC_TO_EVERYONE", "disableComment": false,
 "disableDuet": false, "disableStitch": false, "commercialContentThirdParty": false,
 "commercialContentOwnBrand": true, "autoAddMusic": false, "isAigc": <isAigc>}}
```
After each success: `python3 tools/reelq.py mark <id> <network> --when <when> --planner "<plannerUrl>"`.
After a failure: retry once if the error looks temporary; otherwise
`python3 tools/reelq.py fail <id> <network> --note "<short reason>"` and carry on with the rest.
Never send the same entry twice: if a call's result is unclear, check `getScheduledPosts` for that
day before retrying.

## 5. Log to Outlaw Pulse
For each post you scheduled in step 4, add it to Pulse with ONE `db_write` call (slug
`c467e07f-51d1-42d3-9320-1b9166a8abed`), op `set`, path `posts/or-<id>-<network>`, data:
```json
{"id": "or-<id>-<network>", "title": "<title>", "brand": "<FrickFake|UAOM|The Veil|Veil Academy|Outlaw Built Media|Pocket Built>",
 "platform": "<Facebook|TikTok>", "type": "Reel / video", "status": "posted", "postedAt": "<when as UTC ISO>",
 "hook": "<hook>", "cta": "<cta headline>", "link": "<link>", "notes": "Auto-scheduled in Metricool by the daily reel run",
 "m": {"lengthSec": <seconds>}, "created": "<now UTC ISO>", "updated": "<now UTC ISO>"}
```
(`python3 tools/reelq.py show <id>` prints a reel's details.) If the write is refused, skip this step.

## 6. Update the Daily Reels page
```bash
python3 tools/page.py --new <ids added today, comma separated, or nothing>
```
It prints `files` and `remove`. Call `get_artifact` on slug `6c8977da-59c2-495f-adef-615aba219c6b`
for the version (and `list_files` if you have it), then `publish_files` with that slug,
`base_version`, `mode: "patch"`, the printed `files` and `remove`.

## 7. Finish
One line only, for example:
`Today's reel: UAOM — "It's 9 PM. Your phone rings." Facebook + TikTok at 12:30 PM.`
If Metricool is not connected: `… Ready on your Daily Reels page, waiting for Facebook + TikTok to be connected in Metricool.`
If something failed, say plainly what in the same line.
