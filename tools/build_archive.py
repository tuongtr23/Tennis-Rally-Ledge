"""Build Rally Ledger's season files and player facts from the TML ATP database.

Usage:  python3 build_archive.py <folder with the TML csv files> <site/data folder> [players.json]

Writes data/y2010.js ... data/y2026.js (every tour-level main-draw match, with seeds, ranks,
scores, minutes and serve statistics). If a players.json list of {"id","name","born"} is given,
also writes data/players-gen.json with season-end rankings and bios for those players
("soft" lists seasons where the last match was before October, so the rank is less reliable).
"""
import csv, json, os, re, sys, unicodedata, collections

SRC, OUT = sys.argv[1], sys.argv[2]
PLAYERS = json.load(open(sys.argv[3], encoding='utf8')) if len(sys.argv) > 3 else []
ORD = {'RR': 0, 'DC': 0, 'R128': 1, 'R64': 2, 'R32': 3, 'R16': 4, 'QF': 5, 'BR': 6, 'SF': 6, 'F': 7}
ST = ['ace', 'df', 'svpt', '1stIn', '1stWon', '2ndWon', 'bpSaved', 'bpFaced']

def rows(name):
    p = os.path.join(SRC, name)
    return list(csv.DictReader(open(p, encoding='utf8', errors='replace'))) if os.path.exists(p) else []

def toks(s):
    s = unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower()
    return frozenset(re.sub(r'[^a-z ]+', ' ', s).split())

def same(a, b):
    if len(a) < 2 or len(b) < 2: return False
    return a <= b or b <= a

def num(v):
    try: return int(float(v))
    except (ValueError, TypeError): return 0

def iso(d): return d[:4] + '-' + d[4:6] + '-' + d[6:8]

def build_year(y):
    rs = rows('%d.csv' % y)
    if y == 2026: rs += rows('ongoing_tourneys.csv')
    P, pid, T = [], {}, collections.OrderedDict()
    def pl(r, s):
        n = r[s + '_name'].strip()
        if n not in pid: pid[n] = len(P); P.append([n, r[s + '_ioc']])
        return pid[n]
    seen = set()
    for r in rs:
        if not r.get('winner_name') or not r.get('loser_name') or not r['tourney_date'].isdigit(): continue
        key = (r['tourney_id'], r['round'], r['winner_name'], r['loser_name'])
        if key in seen: continue
        seen.add(key)
        t = T.setdefault(r['tourney_id'], [r['tourney_id'], r['tourney_name'], r['tourney_level'], r['surface'], r.get('indoor', ''), num(r['draw_size']), r['tourney_date'], []])
        t[6] = min(t[6], r['tourney_date'])
        st = [num(r['w_' + k]) for k in ST] + [num(r['l_' + k]) for k in ST] if r.get('w_svpt') and r.get('l_svpt') else 0
        t[7].append([r['round'] or ('DC' if r['tourney_level'] == 'D' else 'RR'), pl(r, 'winner'), pl(r, 'loser'), r['score'], num(r['minutes']),
                     r['winner_seed'], r['loser_seed'], r['winner_entry'], r['loser_entry'], num(r['winner_rank']), num(r['loser_rank']), r['tourney_date'], st])
    out = []
    for t in sorted(T.values(), key=lambda t: t[6]):
        t[7].sort(key=lambda m: (m[11], ORD.get(m[0], 0)))
        for m in t[7]: m[11] = iso(m[11]) if m[11] != t[6] or len({x[11] for x in t[7]}) > 1 else ''
        t[6] = iso(t[6]); out.append(t)
    with open(os.path.join(OUT, 'y%d.js' % y), 'w', encoding='utf8') as fh:
        fh.write('RLD("y%d",%s);' % (y, json.dumps({'y': y, 'P': P, 'T': out}, separators=(',', ':'), ensure_ascii=False)))
    return sum(len(t[7]) for t in out), len(out)

def player_facts():
    want = [(p, toks(p['name'])) for p in PLAYERS]
    first, last = collections.defaultdict(dict), collections.defaultdict(dict)   # id -> year -> (date, rank)
    memo = {}
    def who(name):
        if name not in memo:
            t = toks(name); memo[name] = next((p['id'] for p, k in want if k == t), None) or next((p['id'] for p, k in want if same(k, t)), None)
        return memo[name]
    for y in range(1995, 2027):
        for f in ('%d.csv' % y, '%d_challenger.csv' % y):
            for r in rows(f):
                for s in ('winner', 'loser'):
                    i = who(r[s + '_name']); rk = num(r[s + '_rank']); d = r['tourney_date']
                    if not i or not rk or not d.isdigit(): continue
                    if y not in first[i] or d < first[i][y][0]: first[i][y] = (d, rk)
                    if y not in last[i] or d >= last[i][y][0]: last[i][y] = (d, rk)
    ye = {}; soft = {}
    for p, _ in want:
        i = p['id']; yrs = sorted(last[i])
        if not yrs: continue
        arr = []
        for y in range(yrs[0], 2026):
            nxt = first[i].get(y + 1)
            jan = nxt and nxt[0][4:] <= '0125'
            arr.append(nxt[1] if jan else (last[i][y][1] if y in last[i] else None))
            if not jan and y in last[i] and last[i][y][0][4:] < '1001': soft.setdefault(i, []).append(y)
        while arr and arr[-1] is None: arr.pop()
        if arr: ye[i] = [yrs[0]] + arr
    bio = {}
    db = rows('ATP_Database.csv')
    cand = collections.defaultdict(list)
    for r in db:
        i = who(r['player']) or who(r.get('atpname') or '')
        if i: cand[i].append(r)
    for p, k in want:
        c = cand.get(p['id'])
        if not c: continue
        def score(r):
            bd = r['birthdate']; by = int(bd[:4]) if bd[:4].isdigit() and len(bd) == 8 else 0
            return (toks(r['player']) == k, bool(p.get('born')) and abs(by - p['born']) <= 1, bool(r['height']), by)
        r = max(c, key=score); bd = r['birthdate'] if len(r['birthdate']) == 8 and r['birthdate'].isdigit() else ''
        ht, wt, pro = num(r['height']), num(r['weight']), num(r['turnedpro'])
        bh = r['backhand'].lower()
        bio[p['id']] = [ht if 150 <= ht <= 220 else None, r['hand'] if r['hand'] in ('L', 'R') else None,
                        1 if 'one' in bh or bh.startswith('1') else 2 if 'two' in bh or bh.startswith('2') else None,
                        pro if 1960 <= pro <= 2026 else None, wt if 50 <= wt <= 120 else None, iso(bd) if bd else None]
    json.dump({'ye': ye, 'soft': soft, 'bio': bio}, open(os.path.join(OUT, 'players-gen.json'), 'w', encoding='utf8'), separators=(',', ':'))
    print(len(ye), 'ranking histories,', len(bio), 'bios')

os.makedirs(OUT, exist_ok=True)
for y in range(2010, 2027):
    n, e = build_year(y); print(y, n, 'matches,', e, 'events')
if PLAYERS: player_facts()
