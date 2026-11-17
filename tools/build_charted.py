"""Build Rally Ledger's point-by-point data files from the Match Charting Project.

Usage:  python3 build_charted.py <folder with charting-m-*.csv> <site/data folder> [number of events]

Source: Jeff Sackmann / Match Charting Project (github.com/JeffSackmann/tennis_MatchChartingProject),
licence CC BY-NC-SA 4.0. Writes one data/<event>.js per event and data/index.json.
"""
import csv, json, os, re, sys, unicodedata, collections, zlib

SRC, OUT = sys.argv[1], sys.argv[2]
N_EVENTS = int(sys.argv[3]) if len(sys.argv) > 3 else 30
SKIP = (' CH', 'Juniors', 'NCAA', 'Championships', 'ITF', 'Exhibition', 'UTS', 'Six Kings', 'Qualifiers')
SHOT = set('fbrsvzopuylmhijktq')
ORD = {'RR': 0, 'R128': 1, 'R64': 2, 'R32': 3, 'R16': 4, 'QF': 5, 'BR': 6, 'SF': 6, 'F': 7}

def slug(s):
    s = unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')

def jit(*k):  # small repeatable offset so shots do not land on one spot
    return zlib.crc32(repr(k).encode()) % 9 - 4

def parse(code):
    """-> (is_fault, shots[(letter, dir, depth)], end, errtype); shots[0] is the serve."""
    code = code.replace('c', '').strip()
    if not code or code[0] not in '0456':
        return None
    shots = [['S', code[0], '']]; end = ''; err = ''
    for ch in code[1:]:
        if ch in SHOT: shots.append([ch, '0', ''])
        elif ch in '0123': shots[-1][1] = ch
        elif ch in '789': shots[-1][2] = ch
        elif ch in 'nwdx': err = ch
        elif ch in '*#@': end = ch
        elif ch in 'eg!V' and len(shots) == 1: err = err or 'd'
    fault = len(shots) == 1 and end == '' and err != ''
    return fault, shots, end, err

def path(shots, end, err, srv, deuce, key):
    """Ball positions in court percent: start, then one landing per shot."""
    pts = [5 if srv == 0 else 95, (62 if deuce else 38) if srv == 0 else (38 if deuce else 62)]
    hit = srv
    for i, (letter, d, depth) in enumerate(shots):
        to = 1 - hit; last = i == len(shots) - 1
        if letter == 'S':
            top = (to == 1) == deuce            # receiver's deuce box is the top half on the right side
            y = {'4': 22, '5': 34, '6': 45}.get(d, 34); y = y if top else 100 - y
            x = 69 if to == 1 else 31
        else:
            y = {'1': 72, '3': 28}.get(d, 50); y = y if to == 0 else 100 - y
            x = {'7': 33, '8': 22, '9': 11}.get(depth, 15); x = x if to == 0 else 100 - x
        x += jit(key, i, 'x') // 2; y += jit(key, i, 'y')
        if last and end in '#@' and len(shots) > 1 or (last and letter == 'S' and err and end == ''):
            e = err or 'd'
            if e == 'n': x = 50
            if e in 'wx': y = 97 if y > 50 else 3
            if e in 'dx': x = 99 if to == 1 else 1
        pts += [x, y]
        if last and (end == '*' or (end == '#' and len(shots) == 1)):
            pts += [104 if to == 1 else -4, max(2, min(98, y + jit(key, 'o') * 2))]
        hit = to
    return pts

PV = {'0': 0, '15': 1, '30': 2, '40': 3, 'AD': 4}

def main():
    ms = list(csv.DictReader(open(os.path.join(SRC, 'charting-m-matches.csv'), encoding='utf8', errors='replace')))
    ev = collections.OrderedDict()
    for r in ms:
        d = r['Date']
        if not d.isdigit() or r['Round'].startswith('Q') or any(k in r['Tournament'] for k in SKIP):
            continue
        ev.setdefault((d[:4], r['Tournament']), []).append(r)
    picked = sorted((k for k, v in ev.items() if len(v) >= 3), key=lambda k: max(x['Date'] for x in ev[k]), reverse=True)[:N_EVENTS]
    want = {r['match_id']: r for k in picked for r in ev[k]}
    pts = collections.defaultdict(list)
    for f in sorted(os.listdir(SRC)):
        if f.startswith('charting-m-points-') and f >= 'charting-m-points-2020s':
            for r in csv.DictReader(open(os.path.join(SRC, f), encoding='utf8', errors='replace')):
                if r['match_id'] in want:
                    pts[r['match_id']].append(r)
    os.makedirs(OUT, exist_ok=True); index = []; total = 0
    for k in picked:
        out = []
        for r in sorted(ev[k], key=lambda x: (-ORD.get(x['Round'], 0), x['Date']), ):
            rows = sorted(pts.get(r['match_id'], []), key=lambda x: int(x['Pt']) if x['Pt'].isdigit() else 0)
            if len(rows) < 20: continue
            P = []; sets = []; prev = None; bad = False
            for i, q in enumerate(rows):
                try:
                    s = int(q['Svr']) - 1; w = int(q['PtWinner']) - 1
                    st = (int(q['Set1']), int(q['Set2'])); g = (int(q['Gm1']), int(q['Gm2']))
                except ValueError:
                    bad = True; break
                if w not in (0, 1) or s not in (0, 1): bad = True; break
                if prev and st != prev[0]:
                    sets.append(close(prev))
                a, b = (q['Pts'].split('-') + ['0', '0'])[:2]
                if s == 1: a, b = b, a
                tb = g == (6, 6) or a not in PV or b not in PV
                deuce = ((int(a) + int(b)) if tb and a.isdigit() and b.isdigit() else PV.get(a, 0) + PV.get(b, 0)) % 2 == 0
                c1 = parse(q['1st']); c2 = parse(q['2nd']) if q['2nd'] else None
                f1 = 1 if c1 and not c1[0] else 0
                use = c1 if f1 else c2
                e = ''; stroke = ''; pa = []
                if c1 and c1[0] and (c2 is None or c2[0]):
                    e = 'd'
                    if c2: pa = path(c2[1], c2[2], c2[3], s, deuce, (r['match_id'], i))
                elif use:
                    _, sh, en, er = use
                    e = {'*': 'a' if len(sh) == 1 else 'w', '#': 's' if len(sh) == 1 else 'f', '@': 'u'}.get(en, '')
                    stroke = sh[-1][0] if len(sh) > 1 else ''
                    pa = path(sh, en, er, s, deuce, (r['match_id'], i))
                P.append([s, len(sets), g[0], g[1], a + '-' + b, w, f1, e, stroke, pa])
                prev = (st, g, a, b, w, tb)
            if bad or not prev: continue
            last = close(prev); ret = not valid(last)
            if not ret: sets.append(last)
            elif prev[1] != (0, 0): sets.append([prev[1][0], prev[1][1], None])
            sw = [sum(1 for x in sets if x[0] > x[1]), sum(1 for x in sets if x[1] > x[0])]
            out.append({'a': r['Player 1'], 'b': r['Player 2'], 'ha': r['Pl 1 hand'], 'hb': r['Pl 2 hand'], 'r': r['Round'], 'd': r['Date'],
                        'bo': r['Best of'], 'sets': sets, 'w': (0 if sw[0] > sw[1] else 1) if not ret else None, 'ret': ret, 'p': P})
        if len(out) < 3: continue
        eid = k[0] + '-' + slug(k[1]); total += len(out)
        with open(os.path.join(OUT, eid + '.js'), 'w', encoding='utf8') as fh:
            fh.write('RLD(%s,%s);' % (json.dumps(eid), json.dumps({'ms': out}, separators=(',', ':'), ensure_ascii=False)))
        fin = next((m for m in out if m['r'] == 'F' and m['w'] is not None), None)
        index.append({'id': eid, 'n': k[1], 'y': int(k[0]), 'd0': min(m['d'] for m in out), 'd1': max(m['d'] for m in out),
                      'sf': ev[k][0]['Surface'], 'c': len(out), 'f': '%s d. %s' % ((fin['a'], fin['b']) if fin['w'] == 0 else (fin['b'], fin['a'])) if fin else ''})
    json.dump(index, open(os.path.join(OUT, 'index.json'), 'w', encoding='utf8'), separators=(',', ':'), ensure_ascii=False)
    print(len(index), 'events,', total, 'matches')

def close(prev):
    st, g, a, b, w, tb = prev
    s = [g[0], g[1], None]; s[w] += 1
    if tb and a.isdigit() and b.isdigit():
        s[2] = min(int(a) + (1 if w == 0 else 0), int(b) + (1 if w == 1 else 0))
    return s

def valid(s):
    hi, lo = max(s[0], s[1]), min(s[0], s[1])
    return (hi >= 6 and hi - lo >= 2) or hi == 7 or (hi == 1 and lo == 0 and s[2] is not None)

main()
