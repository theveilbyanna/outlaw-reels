#!/usr/bin/env python3
"""Build the "Outlaw Daily Reels" page (captions with Copy buttons + video + status) from queue.json.

  python3 tools/page.py [--new ID,ID | --new all] [--out /home/claude/daily-page]

Prints JSON: {"files": [{"as": ..., "path": ...}], "remove": [...]} ready for the Artifact
publish_files tool (mode "patch") on the Daily Reels artifact. index.html is always included;
posters and videos only for the reels named in --new. Videos stay on the page for the newest
VIDEO_WINDOW reels; older ones are listed in "remove" and link to their public URL instead.
"""
import argparse, datetime as dt, html, json, os, shutil, sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reelq

VIDEO_WINDOW = 8
SHOW_DAYS = 45
METRICOOL_CONNECT = 'https://app.metricool.com/brands/connections?blogId=7933639'
METRICOOL_PLANNER = 'https://app.metricool.com/planner?blogId=7933639'
COLORS = {'frickfake': '#e5322b', 'uaom': '#f2a33a', 'veil': '#d6a64b', 'academy': '#b9a2ff',
          'outlaw': '#e8352a', 'pocket': '#c9ccd1'}

PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Outlaw Daily Reels</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0f0d0c;--card:#191615;--line:#2c2725;--txt:#f3ece0;--mut:#a79d90;--red:#e8352a;--gold:#d9a441;--ok:#4cc38a}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--txt);font-family:'Space Grotesk',system-ui,sans-serif;font-size:16px;line-height:1.45}
main{max-width:640px;margin:0 auto;padding:22px 16px 80px}
h1{font-family:Anton,Impact,sans-serif;font-weight:400;font-size:44px;line-height:1;margin:0 0 6px;letter-spacing:.5px}
h1 span{color:var(--red)}
.lead{color:var(--mut);margin:0 0 16px}
.banner{border:1px solid var(--line);border-radius:16px;padding:14px 16px;margin:0 0 18px;background:#1d1715}
.banner.warn{border-color:#6b3a14;background:#241a10}
.banner b{display:block;margin-bottom:4px}
.banner a{color:var(--gold);font-weight:700}
h2{font-family:Anton,Impact,sans-serif;font-weight:400;font-size:26px;margin:28px 0 12px;color:var(--gold);letter-spacing:.5px}
section.reel{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:16px;margin:0 0 18px}
.top{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.pill{font-size:13px;font-weight:700;padding:4px 10px;border-radius:99px;color:#111}
.when{color:var(--mut);font-size:14px}
.st{margin-left:auto;font-size:13px;font-weight:700;padding:4px 10px;border-radius:99px;border:1px solid var(--line)}
.st.ok{color:var(--ok);border-color:#24553f}.st.wait{color:var(--gold);border-color:#5b4520}.st.bad{color:#ff8a80;border-color:#5c2a26}
h3{margin:2px 0 12px;font-size:20px;line-height:1.25}
.media{display:flex;justify-content:center;margin:0 0 12px}
video,.cover{width:min(100%,300px);aspect-ratio:9/16;border-radius:16px;background:#000;border:1px solid var(--line);object-fit:cover;display:block}
.links{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}
.links a{flex:1 1 auto;text-align:center;text-decoration:none;font-weight:700;font-size:14px;padding:11px 12px;border-radius:12px;border:1px solid var(--line);color:var(--txt);background:#221e1c}
.sched{font-size:14px;color:var(--mut);margin:0 0 12px}
.sched div{margin:2px 0}
.cap{border-top:1px solid var(--line);padding-top:12px;margin-top:12px}
.caphead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}
.caphead b{font-size:15px}
button.copy{font:inherit;font-weight:700;font-size:15px;border:0;border-radius:12px;padding:11px 18px;background:var(--red);color:#fff;min-width:108px}
button.copy.done{background:var(--ok);color:#06140d}
pre{white-space:pre-wrap;word-wrap:break-word;font-family:inherit;font-size:14px;background:#120f0e;border:1px solid var(--line);border-radius:12px;padding:12px;margin:0;max-height:180px;overflow:auto;user-select:text;-webkit-user-select:text}
.empty{color:var(--mut)}
footer{color:var(--mut);font-size:13px;margin-top:30px}
</style></head><body><main>
<h1>OUTLAW <span>DAILY REELS</span></h1>
<p class="lead">A new reel every day. Facebook and TikTok post on their own through Metricool. For Clapper, save the video and tap Copy.</p>
<div id="banner"></div>
<div id="list"></div>
<footer id="foot"></footer>
</main>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
function el(tag, attrs, kids){ const e = document.createElement(tag); for (const k in (attrs||{})){ if (k === 'text') e.textContent = attrs[k]; else e.setAttribute(k, attrs[k]); } (kids||[]).forEach(c => c && e.appendChild(c)); return e; }
async function copyText(text, btn, box){
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; } catch(e) {}
  if (!ok){ try { const t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.opacity = '0'; document.body.appendChild(t); t.focus(); t.select(); ok = document.execCommand('copy'); t.remove(); } catch(e) {} }
  if (ok){ btn.textContent = 'Copied ✓'; btn.classList.add('done'); setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('done'); }, 1800); }
  else { const r = document.createRange(); r.selectNodeContents(box); const s = getSelection(); s.removeAllRanges(); s.addRange(r); btn.textContent = 'Selected: tap Copy in the menu'; }
}
function capBlock(label, text){
  const box = el('pre', {text});
  const btn = el('button', {class: 'copy', type: 'button', text: 'Copy'});
  btn.addEventListener('click', () => copyText(text, btn, box));
  return el('div', {class: 'cap'}, [el('div', {class: 'caphead'}, [el('b', {text: label}), btn]), box]);
}
function fmtWhen(s){
  if (!s) return '';
  const d = new Date(s.length <= 10 ? s + 'T12:00' : s);
  const day = d.toLocaleDateString('en-US', {weekday: 'short', month: 'short', day: 'numeric'});
  return s.length <= 10 ? day : day + ' · ' + d.toLocaleTimeString('en-US', {hour: 'numeric', minute: '2-digit'});
}
const NET = {facebook: 'Facebook', tiktok: 'TikTok'};
function status(r){
  if (r.status === 'scheduled') return ['Scheduled ✓', 'ok'];
  if (r.status === 'partly') return ['Partly scheduled', 'wait'];
  if (r.status === 'missed') return ['Too late to post', 'bad'];
  const errs = Object.values(r.scheduled || {}).filter(x => x.error);
  if (errs.length) return ['Needs a look', 'bad'];
  return [DATA.meta.metricool === 'connected' ? 'Queued' : 'Waiting for Metricool', 'wait'];
}
function card(r){
  const [stTxt, stCls] = status(r);
  const top = el('div', {class: 'top'}, [
    el('span', {class: 'pill', style: 'background:' + r.color, text: r.brandName}),
    el('span', {class: 'when', text: fmtWhen(r.target || r.date)}),
    el('span', {class: 'st ' + stCls, text: stTxt})]);
  const media = el('div', {class: 'media'});
  if (r.pageVideo) media.appendChild(el('video', {controls: '', playsinline: '', preload: 'none', poster: r.pagePoster, src: r.pageVideo}));
  else media.appendChild(el('img', {class: 'cover', src: r.pagePoster, alt: r.title}));
  const links = el('div', {class: 'links'}, [el('a', {href: r.video_url, text: 'Open video to save it'})]);
  if (r.link && /^https?:/.test(r.link)) links.appendChild(el('a', {href: r.link, text: 'Open the link'}));
  const sched = el('div', {class: 'sched'});
  Object.keys(NET).forEach(n => {
    const s = (r.scheduled || {})[n];
    if (!s) return;
    if (s.when) { const d = el('div'); d.appendChild(document.createTextNode(NET[n] + ': ' + fmtWhen(s.when) + ' ')); if (s.planner) d.appendChild(el('a', {href: s.planner, text: '(open in Metricool)', style: 'color:var(--gold)'})); sched.appendChild(d); }
    else if (s.error) sched.appendChild(el('div', {text: NET[n] + ': ' + s.error}));
  });
  const kids = [top, el('h3', {text: r.title}), media, links];
  if (sched.childNodes.length) kids.push(sched);
  kids.push(capBlock('Facebook caption', r.captions.facebook));
  kids.push(capBlock('TikTok caption', r.captions.tiktok));
  kids.push(capBlock('Clapper caption', r.captions.clapper));
  if (r.comment) kids.push(capBlock('First comment (pin it)', r.comment));
  return el('section', {class: 'reel', id: r.id}, kids);
}
(function render(){
  const b = $('#banner');
  if (DATA.meta.metricool !== 'connected'){
    const d = el('div', {class: 'banner warn'}, [el('b', {text: 'Facebook + TikTok are not connected in Metricool yet'}),
      el('span', {text: 'Until they are, nothing posts on its own. Connect them here: '}), el('a', {href: DATA.connect, text: 'Metricool connections'}),
      el('div', {text: 'Once connected, the next daily run schedules everything waiting below.', style: 'margin-top:6px;color:var(--mut)'})]);
    b.appendChild(d);
  } else {
    b.appendChild(el('div', {class: 'banner'}, [el('b', {text: 'Auto-posting is on'}), el('span', {text: 'Facebook + TikTok publish through Metricool. '}), el('a', {href: DATA.planner, text: 'Open the Metricool planner'})]));
  }
  if (DATA.meta.note) b.appendChild(el('div', {class: 'banner', text: DATA.meta.note}));
  const L = $('#list');
  const today = DATA.today;
  const up = DATA.reels.filter(r => (r.target || r.date).slice(0, 10) >= today);
  const past = DATA.reels.filter(r => (r.target || r.date).slice(0, 10) < today);
  L.appendChild(el('h2', {text: 'Today and coming up'}));
  if (!up.length) L.appendChild(el('p', {class: 'empty', text: 'Nothing waiting. The next reel is made tomorrow morning.'}));
  up.sort((a, b) => (a.target || a.date).localeCompare(b.target || b.date)).forEach(r => L.appendChild(card(r)));
  if (past.length){ L.appendChild(el('h2', {text: 'Earlier'})); past.forEach(r => L.appendChild(card(r))); }
  $('#foot').textContent = 'Updated ' + DATA.updated + ' · ' + DATA.reels.length + ' reels · videos are hosted at github.com/Theveilbyanna/outlaw-reels (videos branch)';
})();
</script></body></html>
"""


def build(new, out):
    reelq.sync() if not os.path.isdir(os.path.join(reelq.VID_DIR, '.git')) else None
    q = reelq.load()
    reelq.pending(q)            # marks time-limited reels that can no longer go out as 'missed'
    today = reelq.now().date()
    cut = (today - dt.timedelta(days=SHOW_DAYS)).isoformat()
    reels = [r for r in q['reels'] if r['date'] >= cut]
    reels.sort(key=lambda r: (r.get('target') or r['date']), reverse=True)
    os.makedirs(os.path.join(out, 'videos'), exist_ok=True)
    os.makedirs(os.path.join(out, 'posters'), exist_ok=True)
    window = {r['id'] for r in reels[:VIDEO_WINDOW] if not r.get('expired')}
    want = {r['id'] for r in reels} if new == ['all'] else set(new)
    files, remove, data = [], [], []
    for r in reels:
        d = {k: r.get(k) for k in ('id', 'date', 'target', 'title', 'hook', 'video_url', 'link', 'captions', 'comment', 'status', 'scheduled')}
        d['brandName'] = reelq.BRAND_NAMES.get(r['brand'], r['brand'])
        d['color'] = COLORS.get(r['brand'], '#d9a441')
        d['pagePoster'] = 'posters/' + r['cover_file']
        if r['id'] in window:
            d['pageVideo'] = 'videos/' + r['file']
        if r['id'] in want:
            src = os.path.join(reelq.VID_DIR, r['cover_file'])
            if os.path.exists(src):
                shutil.copy(src, os.path.join(out, 'posters', r['cover_file']))
                files.append({'as': 'posters/' + r['cover_file'], 'path': os.path.join(out, 'posters', r['cover_file'])})
            if r['id'] in window:
                shutil.copy(os.path.join(reelq.VID_DIR, r['file']), os.path.join(out, 'videos', r['file']))
                files.append({'as': 'videos/' + r['file'], 'path': os.path.join(out, 'videos', r['file'])})
        data.append(d)
    for r in q['reels']:
        if r['id'] not in window:
            remove.append('videos/' + r['file'])
        if r['date'] < cut:
            remove.append('posters/' + r['cover_file'])
    payload = {'meta': q.get('meta', {}), 'reels': data, 'today': today.isoformat(),
               'updated': reelq.now().strftime('%b %-d, %-I:%M %p PT'), 'connect': METRICOOL_CONNECT, 'planner': METRICOOL_PLANNER}
    page = PAGE.replace('__DATA__', json.dumps(payload, ensure_ascii=False).replace('</', '<\\/'))
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as fh:
        fh.write(page)
    files.insert(0, {'as': 'index.html', 'path': os.path.join(out, 'index.html')})
    return {'files': files, 'remove': sorted(set(remove))}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--new', default='')
    p.add_argument('--out', default='/home/claude/daily-page')
    a = p.parse_args()
    new = [x for x in a.new.split(',') if x]
    print(json.dumps(build(new, a.out), indent=1))
