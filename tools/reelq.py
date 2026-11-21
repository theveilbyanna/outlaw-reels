#!/usr/bin/env python3
"""Reel queue: hosts finished reels on the `videos` branch and keeps queue.json there.

The `videos` branch is public, so every reel gets a plain URL that Metricool can fetch:
  https://raw.githubusercontent.com/Theveilbyanna/outlaw-reels/videos/<file>

Commands (run from the repo root):
  python3 tools/reelq.py sync                      clone or refresh the videos branch
  python3 tools/reelq.py today                     today's brand, recent hooks for it, posts waiting
  python3 tools/reelq.py add --spec S --video V --cover C --captions CAP.json [--target 2026-11-23T12:30]
  python3 tools/reelq.py pending                   reels not yet scheduled in Metricool
  python3 tools/reelq.py mark ID NETWORK --when 2026-11-23T12:30 [--planner URL]
  python3 tools/reelq.py fail ID NETWORK --note "why"
  python3 tools/reelq.py meta --metricool connected|missing [--note "..."]
  python3 tools/reelq.py show ID
  python3 tools/reelq.py plan [--slots 11:30,14:30,18:30] [--skip tiktok]   what to schedule now, with exact times
"""
import argparse, datetime as dt, json, os, re, shutil, subprocess, sys
from zoneinfo import ZoneInfo

REPO_URL = 'https://github.com/Theveilbyanna/outlaw-reels'
RAW = 'https://raw.githubusercontent.com/Theveilbyanna/outlaw-reels/videos/'
VID_DIR = os.environ.get('OR_VIDEOS', '/home/claude/or-videos')
TZ = ZoneInfo('America/Los_Angeles')
KEEP_DAYS = 60          # video files older than this are removed from the branch (the record stays)

# One reel a day, rotating through the brands. Day 0 of the rotation is Mon 2026-11-23.
ROTATION = ['frickfake', 'uaom', 'veil', 'outlaw', 'academy', 'pocket']
ANCHOR = dt.date(2026, 11, 23)
SKIP_DAYS = {'2026-11-21', '2026-11-22'}   # covered by the weekend batch
BRAND_NAMES = {'frickfake': 'FrickFake', 'uaom': 'UAOM', 'veil': 'The Veil', 'outlaw': 'Outlaw Built Media',
               'academy': 'Veil Academy', 'pocket': 'Pocket Built'}
NETWORKS = ('facebook', 'tiktok')


def now():
    return dt.datetime.now(TZ)


def git(*a, check=True, cwd=None):
    return subprocess.run(['git', '-C', cwd or VID_DIR] + list(a), check=check, capture_output=True, text=True)


def sync():
    if os.path.isdir(os.path.join(VID_DIR, '.git')):
        git('fetch', '--depth', '1', 'origin', 'videos')
        git('reset', '--hard', 'origin/videos')
    else:
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', 'videos', REPO_URL, VID_DIR], check=True)
    git('config', 'user.name', 'Outlaw Reels')
    git('config', 'user.email', 'noreply@anthropic.com')


def load():
    p = os.path.join(VID_DIR, 'queue.json')
    if os.path.exists(p):
        return json.load(open(p))
    return {'meta': {}, 'reels': []}


def save(q):
    q['reels'].sort(key=lambda r: (r.get('target') or r['date'], r['id']))
    with open(os.path.join(VID_DIR, 'queue.json'), 'w') as fh:
        json.dump(q, fh, ensure_ascii=False, indent=1)


def publish(msg):
    """Commit the branch as ONE fresh commit and force-push, so old videos never pile up in history."""
    git('add', '-A')
    git('checkout', '--orphan', 'tmp-videos')
    git('commit', '-qm', msg + '\n\nCo-Authored-By: Claude <noreply@anthropic.com>')
    r = git('push', '-f', 'origin', 'tmp-videos:videos', check=False)
    if r.returncode != 0:
        sys.exit('push failed: ' + r.stderr[-500:])
    git('branch', '-M', 'videos')


def prune(q):
    cut = (now().date() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for r in q['reels']:
        if r['date'] < cut and not r.get('expired'):
            for f in (r['file'], r['cover_file']):
                p = os.path.join(VID_DIR, f)
                if os.path.exists(p):
                    os.remove(p)
            r['expired'] = True


def find(q, rid):
    for r in q['reels']:
        if r['id'] == rid:
            return r
    sys.exit('no reel with id ' + rid)


def brand_for(day):
    return ROTATION[(day - ANCHOR).days % len(ROTATION)]


def cmd_today(a):
    sync(); q = load()
    d = now().date()
    brand = brand_for(d)
    mine = [r for r in q['reels'] if r['brand'] == brand][-15:]
    out = {
        'date': d.isoformat(), 'now': now().strftime('%Y-%m-%dT%H:%M'),
        'brand': brand, 'brand_name': BRAND_NAMES[brand],
        'skip_new_reel': d.isoformat() in SKIP_DAYS or any(r['date'] == d.isoformat() and r.get('daily') for r in q['reels']),
        'recent_for_brand': [{'date': r['date'], 'title': r['title'], 'hook': r['hook'], 'angle': r.get('angle', '')} for r in mine],
        'pending': [summary(r) for r in pending(q)],
        'metricool': q.get('meta', {}).get('metricool', 'unknown'),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


def summary(r):
    return {k: r.get(k) for k in ('id', 'brand', 'title', 'target', 'video_url', 'cover_url', 'isAigc', 'scheduled', 'status')}


def pending(q):
    out = []
    for r in q['reels']:
        if r['status'] in ('ready', 'partly') and r.get('expires') and now().strftime('%Y-%m-%dT%H:%M') > r['expires']:
            r['status'] = 'missed'
        if r['status'] in ('ready', 'partly') and not r.get('expired'):
            out.append(r)
    return out


def cmd_add(a):
    if not a.no_sync:
        sync()
    q = load()
    spec = json.load(open(a.spec)) if a.spec else {'title': a.title, 'slug': a.slug, 'scenes': [{'text': a.hook or a.title}], 'theme': a.brand}
    cap = json.load(open(a.captions))
    for k in ('facebook', 'tiktok', 'clapper', 'link'):
        if not cap.get(k):
            sys.exit('captions file is missing ' + k)
    d = a.date or now().date().isoformat()
    slug = spec.get('slug') or re.sub(r'[^a-z0-9]+', '-', spec.get('title', 'reel').lower()).strip('-')
    rid = f'{d}-{slug}'[:80]
    if any(r['id'] == rid for r in q['reels']) and not a.replace:
        sys.exit(f'{rid} is already in the queue (use --replace to overwrite it)')
    q['reels'] = [r for r in q['reels'] if r['id'] != rid]
    vf, cf = rid + '.mp4', rid + '.jpg'
    shutil.copy(a.video, os.path.join(VID_DIR, vf))
    from PIL import Image
    Image.open(a.cover).convert('RGB').resize((540, 960), Image.LANCZOS).save(os.path.join(VID_DIR, cf), quality=84)
    first = spec['scenes'][0]
    hook = a.hook or ' '.join(x.lstrip('*') for x in first.get('lines', [])) or first.get('text', '') or spec.get('title', '')
    secs = None
    try:
        secs = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', a.video],
                                    capture_output=True, text=True).stdout.strip())
    except Exception:
        pass
    rec = {
        'id': rid, 'date': d, 'brand': a.brand or spec['theme'], 'title': spec.get('title', slug), 'hook': hook,
        'angle': a.angle or spec.get('angle', ''), 'seconds': round(secs, 1) if secs else None,
        'file': vf, 'cover_file': cf, 'video_url': RAW + vf, 'cover_url': RAW + cf,
        'captions': {k: cap[k] for k in ('facebook', 'tiktok', 'clapper') }, 'comment': cap.get('comment', ''),
        'link': cap['link'], 'isAigc': bool(cap.get('isAigc', False)),
        'target': a.target, 'status': 'ready', 'scheduled': {}, 'daily': not a.batch,
        'created': now().isoformat(timespec='minutes'),
    }
    if a.spec and a.spec_copy:
        os.makedirs(os.path.join(VID_DIR, 'specs'), exist_ok=True)
        shutil.copy(a.spec, os.path.join(VID_DIR, 'specs', rid + '.json'))
    q['reels'].append(rec)
    prune(q); save(q)
    if not a.no_push:
        publish(f'Add reel {rid}')
    print(json.dumps(summary(rec), ensure_ascii=False, indent=1))


def cmd_pending(a):
    sync(); q = load()
    print(json.dumps([summary(r) for r in pending(q)], ensure_ascii=False, indent=1))


def settle(r):
    done = [n for n in NETWORKS if r['scheduled'].get(n, {}).get('when')]
    skipped = [n for n in NETWORKS if r['scheduled'].get(n, {}).get('skip')]
    if len(done) + len(skipped) == len(NETWORKS) and done:
        r['status'] = 'scheduled'
    elif done:
        r['status'] = 'partly'


def cmd_mark(a):
    sync(); q = load(); r = find(q, a.id)
    r['scheduled'][a.network] = {'when': a.when, 'planner': a.planner or ''}
    settle(r); save(q); publish(f'Scheduled {a.id} on {a.network}')
    print(json.dumps(summary(r), ensure_ascii=False, indent=1))


def cmd_fail(a):
    sync(); q = load(); r = find(q, a.id)
    r['scheduled'][a.network] = {'error': a.note, 'at': now().isoformat(timespec='minutes')}
    if a.skip:
        r['scheduled'][a.network]['skip'] = True
    settle(r); save(q); publish(f'Note on {a.id} {a.network}')
    print(json.dumps(summary(r), ensure_ascii=False, indent=1))


def cmd_meta(a):
    sync(); q = load()
    q.setdefault('meta', {}).update({'metricool': a.metricool, 'note': a.note or '', 'checked': now().isoformat(timespec='minutes')})
    save(q); publish('Update status')
    print(json.dumps(q['meta']))


def local_dt(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=TZ) if 'T' in s else None


def cmd_plan(a):
    """Work out what to schedule now: one entry per reel x network, with the exact time."""
    sync(); q = load()
    earliest = now() + dt.timedelta(minutes=a.lead)
    slots = [x.strip() for x in a.slots.split(',') if x.strip()]
    horizon = (now().date() + dt.timedelta(days=a.days)).isoformat()
    used = {}
    for r in q['reels']:
        for n, s in r.get('scheduled', {}).items():
            if s.get('when'):
                used.setdefault((n, s['when'][:10]), set()).add(s['when'][11:16])
    nets = [n for n in NETWORKS if n not in (a.skip or '').split(',')]
    out = []
    def fixed(r):
        t = local_dt(r['target']) if r.get('target') else None
        return 0 if (t and t >= earliest) else 1
    for r in sorted(pending(q), key=lambda r: (fixed(r), r.get('target') or r['date'])):
        for n in nets:
            s = r['scheduled'].get(n, {})
            if s.get('when') or s.get('skip'):
                continue
            when = None
            t = local_dt(r['target']) if r.get('target') else None
            if t and t >= earliest:
                when = t
            else:
                day = max(now().date(), dt.date.fromisoformat(r['date']))
                for k in range(0, 10):
                    dd = day + dt.timedelta(days=k)
                    taken = used.get((n, dd.isoformat()), set())
                    if len(taken) >= a.per_day:
                        continue
                    for sl in slots:
                        cand = dt.datetime.fromisoformat(f'{dd.isoformat()}T{sl}').replace(tzinfo=TZ)
                        if cand >= earliest and sl not in taken:
                            when = cand; break
                    if when:
                        break
            if not when or when.date().isoformat() > horizon:
                continue
            if r.get('expires') and when.strftime('%Y-%m-%dT%H:%M') > r['expires']:
                continue
            key = when.strftime('%Y-%m-%dT%H:%M')
            used.setdefault((n, key[:10]), set()).add(key[11:16])
            out.append({'id': r['id'], 'network': n, 'when': key,
                        'date_param': when.isoformat(timespec='seconds'),
                        'publicationDate': {'dateTime': when.strftime('%Y-%m-%dT%H:%M:00'), 'timezone': 'America/Los_Angeles'},
                        'media': r['video_url'], 'text': r['captions']['facebook' if n == 'facebook' else 'tiktok'],
                        'comment': r.get('comment', ''), 'isAigc': r.get('isAigc', False), 'title': r['title']})
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_show(a):
    sync(); q = load()
    print(json.dumps(find(q, a.id), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest='cmd', required=True)
    s.add_parser('sync')
    s.add_parser('today')
    s.add_parser('pending')
    x = s.add_parser('add')
    x.add_argument('--spec'); x.add_argument('--title'); x.add_argument('--slug'); x.add_argument('--hook')
    x.add_argument('--video', required=True); x.add_argument('--cover', required=True)
    x.add_argument('--captions', required=True); x.add_argument('--target'); x.add_argument('--date'); x.add_argument('--brand')
    x.add_argument('--angle'); x.add_argument('--batch', action='store_true'); x.add_argument('--replace', action='store_true')
    x.add_argument('--no-push', action='store_true'); x.add_argument('--no-sync', action='store_true'); x.add_argument('--spec-copy', action='store_true', default=True)
    x = s.add_parser('mark'); x.add_argument('id'); x.add_argument('network', choices=NETWORKS)
    x.add_argument('--when', required=True); x.add_argument('--planner')
    x = s.add_parser('fail'); x.add_argument('id'); x.add_argument('network', choices=NETWORKS)
    x.add_argument('--note', required=True); x.add_argument('--skip', action='store_true')
    x = s.add_parser('meta'); x.add_argument('--metricool', required=True); x.add_argument('--note')
    x = s.add_parser('show'); x.add_argument('id')
    x = s.add_parser('plan'); x.add_argument('--slots', default='11:30,14:30,18:30')
    x.add_argument('--per-day', type=int, default=3); x.add_argument('--days', type=int, default=2)
    x.add_argument('--lead', type=int, default=60); x.add_argument('--skip', default='')
    a = p.parse_args()
    if a.cmd == 'sync':
        sync(); print(VID_DIR)
    else:
        globals()['cmd_' + a.cmd](a)
