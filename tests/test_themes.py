"""Theme merge and split rules (migration 0004, review finding R3).

Stable theme IDs are the core of "what changed since the last digest", so merges can never
form a cycle, and resolution never drops a theme or its evidence silently.
"""

import sqlite3
from itertools import pairwise

import pytest

from customer_pulse import db

START, END = "2026-10-05T07:00:00Z", "2026-10-12T07:00:00Z"


def resolution(conn):
    rows = conn.execute("SELECT theme_id, final_theme_id FROM v_theme_resolution").fetchall()
    return {row["theme_id"]: row["final_theme_id"] for row in rows}


def unresolved(conn):
    return [row[0] for row in conn.execute("SELECT theme_id FROM v_theme_unresolved")]


def test_codex_reproduction_two_node_cycle_is_refused_and_facts_survive(build):
    build.theme("th_0001")
    build.theme("th_0002")
    signal = build.signal("C1:1", "2026-10-06T00:00:00Z")
    run = build.run(START, END)
    build.assign(signal, "th_0001", run=run)

    build.merge("th_0001", "th_0002")
    with pytest.raises(sqlite3.IntegrityError, match="merge only into an active theme"):
        build.merge("th_0002", "th_0001")

    assert resolution(build.conn) == {"th_0001": "th_0002", "th_0002": "th_0002"}
    facts = build.conn.execute(
        "SELECT theme_id, signal_count FROM v_run_theme_facts WHERE run_id = ?", (run,)
    ).fetchall()
    assert [tuple(row) for row in facts] == [("th_0002", 1)]
    assert unresolved(build.conn) == []


def test_a_longer_cycle_is_refused(build):
    for theme in ("th_0001", "th_0002", "th_0003"):
        build.theme(theme)
    build.merge("th_0001", "th_0002")
    build.merge("th_0002", "th_0003")
    with pytest.raises(sqlite3.IntegrityError, match="merge only into an active theme"):
        build.merge("th_0003", "th_0001")
    assert unresolved(build.conn) == []


def test_a_long_chain_resolves_past_the_old_depth_limit(build):
    themes = [f"th_{n:04d}" for n in range(1, 82)]  # 81 themes, a chain 80 merges deep
    for theme in themes:
        build.theme(theme)
    for merged, survivor in pairwise(themes):
        build.merge(merged, survivor)
    signal = build.signal("C1:1", "2026-10-06T00:00:00Z")
    run = build.run(START, END)
    build.assign(signal, themes[0], run=run)

    assert set(resolution(build.conn).values()) == {"th_0081"}
    assert len(resolution(build.conn)) == 81
    effective = build.conn.execute("SELECT theme_id FROM v_effective_assignment").fetchone()[0]
    assert effective == "th_0081"
    assert unresolved(build.conn) == []


def test_only_active_themes_merge_or_absorb_merges(build):
    for theme in ("th_0001", "th_0002", "th_0003"):
        build.theme(theme)
    build.conn.execute("UPDATE themes SET status = 'retired' WHERE theme_id = 'th_0003'")
    with pytest.raises(sqlite3.IntegrityError, match="merge only into an active theme"):
        build.merge("th_0001", "th_0003")  # into a retired theme
    with pytest.raises(sqlite3.IntegrityError, match="only an active theme can be merged"):
        build.merge("th_0003", "th_0002")  # a retired theme can't merge
    with pytest.raises(sqlite3.IntegrityError, match="merge only into an active theme"):
        build.theme("th_0004", merged_into="th_0003")


def test_a_merge_is_final(build):
    for theme in ("th_0001", "th_0002", "th_0003"):
        build.theme(theme)
    build.merge("th_0001", "th_0002")
    with pytest.raises(sqlite3.IntegrityError, match="merge is final"):
        build.conn.execute("UPDATE themes SET merged_into = 'th_0003' WHERE theme_id = 'th_0001'")
    with pytest.raises(sqlite3.IntegrityError, match="merge is final"):
        build.conn.execute(
            "UPDATE themes SET status = 'active', merged_into = NULL WHERE theme_id = 'th_0001'"
        )


def test_split_lineage_comes_from_an_active_theme_and_is_fixed(build):
    build.theme("th_0001")
    build.insert(
        "themes", theme_id="th_0002", title="Split off", split_from="th_0001", created_at=build.now
    )
    with pytest.raises(sqlite3.IntegrityError, match="split lineage is fixed"):
        build.conn.execute("UPDATE themes SET split_from = NULL WHERE theme_id = 'th_0002'")
    build.merge("th_0001", "th_0002")
    with pytest.raises(sqlite3.IntegrityError, match="split only from an active theme"):
        build.insert(
            "themes", theme_id="th_0003", title="Late split", split_from="th_0001",
            created_at=build.now,
        )  # fmt: skip


def test_themes_are_kept(build):
    build.theme("th_0001")
    with pytest.raises(sqlite3.IntegrityError, match="themes are kept"):
        build.conn.execute("DELETE FROM themes")


def test_a_database_that_already_holds_a_cycle_stops_the_migration(db_path, clock, monkeypatch):
    shipped = db.available_migrations()
    conn = db.connect(db_path)
    monkeypatch.setattr(db, "available_migrations", lambda: shipped[:3])
    db.migrate(conn, clock)
    now = "2026-10-12T17:00:00.000000Z"
    conn.executemany(
        "INSERT INTO themes (theme_id, title, created_at) VALUES (?, ?, ?)",
        [("th_0001", "A", now), ("th_0002", "B", now)],
    )
    conn.execute(
        "UPDATE themes SET status = 'merged', merged_into = 'th_0002' WHERE theme_id = 'th_0001'"
    )
    conn.execute(
        "UPDATE themes SET status = 'merged', merged_into = 'th_0001' WHERE theme_id = 'th_0002'"
    )
    monkeypatch.setattr(db, "available_migrations", lambda: shipped)
    with pytest.raises(sqlite3.IntegrityError, match="themes_must_have_no_merge_cycles"):
        db.migrate(conn, clock)
    assert db.schema_version(conn) == 3
    conn.close()
