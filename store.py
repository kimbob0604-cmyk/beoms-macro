"""macro.db: 지표 값(series)과 지표 설명·신선도(meta)."""
import sqlite3
from datetime import datetime

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS series (key TEXT NOT NULL, date TEXT NOT NULL, value REAL, PRIMARY KEY (key, date)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY, name TEXT, grp TEXT, unit TEXT, source TEXT, freq TEXT,
    use TEXT,            -- 용도: 흐름·타이밍·비중·섹터 (쉼표로 여러 개)
    diff INTEGER,        -- 1 이면 변화를 %가 아니라 차이(포인트)로 보여 준다 (금리·변동성 등)
    dec INTEGER, note TEXT, asof TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS runlog (at TEXT, job TEXT, ok INTEGER, msg TEXT);
"""
FIELDS = ['name', 'grp', 'unit', 'source', 'freq', 'use', 'diff', 'dec', 'note']


def connect():
    config.DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(config.DB, timeout=60)
    c.executescript(SCHEMA)
    return c


def put(c, key, rows, **meta):
    """rows: [(date 'YYYY-MM-DD', value)] — 같은 날짜는 덮어쓴다. meta: name, grp, unit, source, freq, use, diff, dec, note"""
    rows = [(key, d, float(v)) for d, v in rows if v is not None and v == v]
    if rows:
        c.executemany('INSERT OR REPLACE INTO series VALUES (?,?,?)', rows)
    asof = c.execute('SELECT max(date) FROM series WHERE key=?', (key,)).fetchone()[0]
    old = c.execute('SELECT name,grp,unit,source,freq,use,diff,dec,note,fetched_at FROM meta WHERE key=?', (key,)).fetchone() or (None,) * 10
    vals = [meta.get(k, o) for k, o in zip(FIELDS, old)]
    fetched = datetime.now().strftime('%Y-%m-%d %H:%M') if rows else old[9]
    c.execute('INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (key, *vals, asof, fetched))
    return len(rows)


def get(c, key, start='1900-01-01'):
    return c.execute('SELECT date, value FROM series WHERE key=? AND date>=? ORDER BY date', (key, start)).fetchall()


def log(c, job, ok, msg=''):
    c.execute('INSERT INTO runlog VALUES (?,?,?,?)', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), job, int(ok), str(msg)[:300]))
    c.commit()
