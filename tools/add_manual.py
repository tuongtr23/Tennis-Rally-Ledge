"""Merge hand-entered matches into Rally Ledger's season files.

Usage:  python3 add_manual.py manual_matches.json <site/data folder>

Run it after build_archive.py. Matches already in the season file (same event, round,
winner and loser) are skipped, so it is safe to run more than once. Once the TML database
includes these matches, delete them from manual_matches.json.
"""
import json, os, sys
SRC, OUT = sys.argv[1], sys.argv[2]
ORD = {'RR': 0, 'R128': 1, 'R64': 2, 'R32': 3, 'R16': 4, 'QF': 5, 'SF': 6, 'F': 7}
by_year = {}
for ev in json.load(open(SRC, encoding='utf8'))['events']:
    by_year.setdefault(int(ev['date'][:4]), []).append(ev)
for y, evs in by_year.items():
    path = os.path.join(OUT, 'y%d.js' % y)
    s = open(path, encoding='utf8').read()
    d = json.loads(s[s.index(',') + 1:-2])
    P, T = d['P'], d['T']
    idx = {p[0]: i for i, p in enumerate(P)}
    def pid(n, ioc):
        if n not in idx: idx[n] = len(P); P.append([n, ioc])
        return idx[n]
    added = 0
    for ev in evs:
        t = next((t for t in T if t[0] == ev['id']), None)
        if t is None:
            t = [ev['id'], ev['name'], ev['lv'], ev['sf'], ev['indoor'], ev['draw'], ev['date'], []]; T.append(t)
        have = {(m[0], m[1], m[2]) for m in t[7]}
        for r, wn, wc, ln, lc, sc, mins, ws, ls, wr, lr, dt in ev['matches']:
            w, l = pid(wn, wc), pid(ln, lc)
            if (r, w, l) in have: continue
            t[7].append([r, w, l, sc, mins, ws, ls, '', '', wr, lr, dt, 0]); added += 1
        t[7].sort(key=lambda m: (m[11] or t[6], ORD.get(m[0], 0)))
    T.sort(key=lambda t: t[6])
    with open(path, 'w', encoding='utf8') as fh:
        fh.write('RLD("y%d",%s);' % (y, json.dumps({'y': y, 'P': P, 'T': T}, separators=(',', ':'), ensure_ascii=False)))
    print('y%d: %d matches added' % (y, added))
