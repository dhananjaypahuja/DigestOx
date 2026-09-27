-- Customer Pulse schema, migration 0001. DESIGN.md section 4 explains each table and view.
--
-- Conventions
--   * Timestamps are UTC text in one fixed-width form, YYYY-MM-DDTHH:MM:SS.ffffffZ, written by
--     customer_pulse.timewin.to_db. Text order is time order, so the views below compare
--     timestamps as plain text. The GLOB checks enforce the shape.
--   * Evidence counts for a run when window_start <= occurred_at < cutoff (half-open).
--   * Booleans are INTEGER 0 or 1. JSON columns must hold valid JSON.
--   * Human-facing IDs: accounts acct_<name>, themes th_NNNN, digests dg_NNNN.
--   * History tables are append-only, enforced by triggers.

------------------------------------------------------------------------------------------------
-- Customers and imports
------------------------------------------------------------------------------------------------

CREATE TABLE accounts (
    account_id          TEXT PRIMARY KEY CHECK (account_id GLOB 'acct_?*'),
    name                TEXT NOT NULL CHECK (name <> ''),
    slack_channel_id    TEXT UNIQUE,
    slack_channel_name  TEXT UNIQUE,
    created_at          TEXT NOT NULL CHECK (created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;

-- Email domains that attribute CSV tickets to a customer.
CREATE TABLE account_domains (
    domain      TEXT PRIMARY KEY CHECK (domain = lower(domain) AND domain GLOB '?*.?*'
                                        AND domain NOT GLOB '*@*'),
    account_id  TEXT NOT NULL REFERENCES accounts (account_id)
) STRICT;

-- Approved CSV mappings, reusable when a later export has the same header fingerprint.
CREATE TABLE mappings (
    mapping_id          INTEGER PRIMARY KEY,
    header_fingerprint  TEXT NOT NULL UNIQUE CHECK (length(header_fingerprint) = 64),
    mapping_json        TEXT NOT NULL CHECK (json_valid(mapping_json)),
    approved_at         TEXT NOT NULL CHECK (approved_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;

-- One row per import batch. A file's content hash identifies the batch, not the evidence in it.
CREATE TABLE imports (
    import_id        INTEGER PRIMARY KEY,
    source           TEXT NOT NULL CHECK (source IN ('slack', 'github', 'csv')),
    file_name        TEXT NOT NULL,
    content_sha256   TEXT NOT NULL CHECK (length(content_sha256) = 64),
    imported_at      TEXT NOT NULL CHECK (imported_at GLOB '????-??-??T??:??:??.??????Z'),
    mapping_id       INTEGER REFERENCES mappings (mapping_id),
    new_count        INTEGER NOT NULL DEFAULT 0 CHECK (new_count >= 0),
    updated_count    INTEGER NOT NULL DEFAULT 0 CHECK (updated_count >= 0),
    unchanged_count  INTEGER NOT NULL DEFAULT 0 CHECK (unchanged_count >= 0),
    UNIQUE (source, content_sha256),
    CHECK (mapping_id IS NULL OR source = 'csv')
) STRICT;

------------------------------------------------------------------------------------------------
-- Evidence
------------------------------------------------------------------------------------------------

CREATE TABLE issues (
    issue_number     INTEGER PRIMARY KEY CHECK (issue_number > 0),
    title            TEXT NOT NULL,
    body_redacted    TEXT NOT NULL,
    url              TEXT NOT NULL,
    author_login     TEXT,
    created_at       TEXT NOT NULL CHECK (created_at GLOB '????-??-??T??:??:??.??????Z'),
    first_import_id  INTEGER NOT NULL REFERENCES imports (import_id),
    last_import_id   INTEGER NOT NULL REFERENCES imports (import_id)
) STRICT;

-- Issue state as each import saw it. State history is kept, never overwritten.
CREATE TABLE issue_observations (
    issue_number  INTEGER NOT NULL REFERENCES issues (issue_number),
    import_id     INTEGER NOT NULL REFERENCES imports (import_id),
    state         TEXT NOT NULL CHECK (state IN ('OPEN', 'CLOSED')),
    state_reason  TEXT,
    closed_at     TEXT CHECK (closed_at GLOB '????-??-??T??:??:??.??????Z'),
    labels_json   TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(labels_json)),
    observed_at   TEXT NOT NULL CHECK (observed_at GLOB '????-??-??T??:??:??.??????Z'),
    PRIMARY KEY (issue_number, import_id),
    CHECK ((state = 'CLOSED') = (closed_at IS NOT NULL))
) STRICT;

-- One row per Slack message, GitHub issue comment, or support ticket, keyed by its source
-- identity. Only redacted text is stored; raw_sha256 detects later edits to the record.
CREATE TABLE signals (
    signal_id        INTEGER PRIMARY KEY,
    source           TEXT NOT NULL CHECK (source IN ('slack', 'github', 'csv')),
    source_key       TEXT NOT NULL CHECK (source_key <> ''),
    account_id       TEXT REFERENCES accounts (account_id),  -- NULL means unattributed
    author_name      TEXT,
    occurred_at      TEXT NOT NULL CHECK (occurred_at GLOB '????-??-??T??:??:??.??????Z'),
    text_redacted    TEXT NOT NULL,
    raw_sha256       TEXT NOT NULL CHECK (length(raw_sha256) = 64),
    url              TEXT,
    thread_key       TEXT,
    issue_number     INTEGER REFERENCES issues (issue_number),  -- the issue a comment is on
    is_pulse_output  INTEGER NOT NULL DEFAULT 0 CHECK (is_pulse_output IN (0, 1)),
    first_import_id  INTEGER NOT NULL REFERENCES imports (import_id),
    last_import_id   INTEGER NOT NULL REFERENCES imports (import_id),
    UNIQUE (source, source_key),
    CHECK (issue_number IS NULL OR source = 'github')
) STRICT;

CREATE INDEX signals_by_time ON signals (occurred_at);
CREATE INDEX signals_by_thread ON signals (thread_key, occurred_at);
CREATE INDEX signals_by_account ON signals (account_id);

-- Deliberate record of a change to an existing signal, seen in a later import.
CREATE TABLE signal_revisions (
    revision_id        INTEGER PRIMARY KEY,
    signal_id          INTEGER NOT NULL REFERENCES signals (signal_id),
    import_id          INTEGER NOT NULL REFERENCES imports (import_id),
    old_raw_sha256     TEXT NOT NULL CHECK (length(old_raw_sha256) = 64),
    new_raw_sha256     TEXT NOT NULL CHECK (length(new_raw_sha256) = 64),
    old_text_redacted  TEXT NOT NULL,
    seen_at            TEXT NOT NULL CHECK (seen_at GLOB '????-??-??T??:??:??.??????Z'),
    CHECK (old_raw_sha256 <> new_raw_sha256)
) STRICT;

------------------------------------------------------------------------------------------------
-- Runs, themes, and review
------------------------------------------------------------------------------------------------

-- One row per pipeline run. A run with a window has all four window columns, and its cutoff
-- sits inside the window: window_start < cutoff <= window_end.
CREATE TABLE runs (
    run_id          INTEGER PRIMARY KEY,
    kind            TEXT NOT NULL CHECK (kind IN ('group', 'digest', 'reconcile', 'eval')),
    mode            TEXT NOT NULL CHECK (mode IN ('live', 'replay', 'offline')),
    window_start    TEXT CHECK (window_start GLOB '????-??-??T??:??:??.??????Z'),
    window_end      TEXT CHECK (window_end GLOB '????-??-??T??:??:??.??????Z'),
    cutoff          TEXT CHECK (cutoff GLOB '????-??-??T??:??:??.??????Z'),
    timezone        TEXT,
    model           TEXT,
    effort          TEXT,
    prompt_version  TEXT,
    input_tokens    INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens   INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    cost_usd        REAL NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    started_at      TEXT NOT NULL CHECK (started_at GLOB '????-??-??T??:??:??.??????Z'),
    finished_at     TEXT CHECK (finished_at GLOB '????-??-??T??:??:??.??????Z'),
    status          TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    CHECK ((window_start IS NULL) = (window_end IS NULL)
           AND (window_start IS NULL) = (cutoff IS NULL)
           AND (window_start IS NULL) = (timezone IS NULL)),
    CHECK (window_start IS NULL OR (window_start < cutoff AND cutoff <= window_end))
) STRICT;

-- Themes keep stable IDs. A merged theme points at the theme that absorbed it; a theme split
-- off another records where it came from.
CREATE TABLE themes (
    theme_id        TEXT PRIMARY KEY CHECK (theme_id GLOB 'th_[0-9][0-9][0-9][0-9]*'
                                            AND substr(theme_id, 4) NOT GLOB '*[^0-9]*'),
    title           TEXT NOT NULL CHECK (title <> ''),
    summary         TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'merged', 'retired')),
    merged_into     TEXT REFERENCES themes (theme_id),
    split_from      TEXT REFERENCES themes (theme_id),
    title_pinned    INTEGER NOT NULL DEFAULT 0 CHECK (title_pinned IN (0, 1)),
    created_run_id  INTEGER REFERENCES runs (run_id),
    created_at      TEXT NOT NULL CHECK (created_at GLOB '????-??-??T??:??:??.??????Z'),
    CHECK ((status = 'merged') = (merged_into IS NOT NULL)),
    CHECK (merged_into IS NULL OR merged_into <> theme_id),
    CHECK (split_from IS NULL OR split_from <> theme_id)
) STRICT;

-- The vendor repo's code areas and the path prefixes that belong to each.
CREATE TABLE code_areas (
    area_key     TEXT PRIMARY KEY CHECK (area_key GLOB '[a-z]*'
                                         AND area_key NOT GLOB '*[^a-z0-9_]*'),
    description  TEXT NOT NULL DEFAULT ''
) STRICT;

CREATE TABLE code_area_paths (
    area_key     TEXT NOT NULL REFERENCES code_areas (area_key),
    path_prefix  TEXT NOT NULL CHECK (path_prefix <> '' AND path_prefix NOT GLOB '/*'),
    PRIMARY KEY (area_key, path_prefix)
) STRICT;

CREATE TABLE theme_code_areas (
    theme_id  TEXT NOT NULL REFERENCES themes (theme_id),
    area_key  TEXT NOT NULL REFERENCES code_areas (area_key),
    set_by    TEXT NOT NULL CHECK (set_by IN ('model', 'person')),
    PRIMARY KEY (theme_id, area_key)
) STRICT;

-- One row per digest version. Approval belongs to one content version: an approved digest's
-- content can't change (see the trigger below), so any edit makes a new draft.
CREATE TABLE digests (
    digest_id           TEXT PRIMARY KEY CHECK (digest_id GLOB 'dg_[0-9][0-9][0-9][0-9]*'
                                                AND substr(digest_id, 4) NOT GLOB '*[^0-9]*'),
    run_id              INTEGER NOT NULL REFERENCES runs (run_id),
    previous_digest_id  TEXT REFERENCES digests (digest_id),
    content_md          TEXT NOT NULL,
    content_sha256      TEXT NOT NULL CHECK (length(content_sha256) = 64),
    status              TEXT NOT NULL
                             CHECK (status IN ('draft', 'approved', 'published', 'superseded')),
    approved_sha256     TEXT CHECK (approved_sha256 IS NULL OR approved_sha256 = content_sha256),
    approved_at         TEXT CHECK (approved_at GLOB '????-??-??T??:??:??.??????Z'),
    created_at          TEXT NOT NULL CHECK (created_at GLOB '????-??-??T??:??:??.??????Z'),
    CHECK (status NOT IN ('approved', 'published') OR approved_sha256 IS NOT NULL),
    CHECK ((approved_sha256 IS NULL) = (approved_at IS NULL)),
    CHECK (previous_digest_id IS NULL OR previous_digest_id <> digest_id)
) STRICT;

CREATE TRIGGER digests_approved_content_is_frozen
BEFORE UPDATE OF content_md, content_sha256 ON digests
WHEN OLD.approved_sha256 IS NOT NULL
BEGIN
    SELECT RAISE (ABORT, 'approved digest content cannot change; create a new draft');
END;

-- Append-only log of review commands and their arguments, replayed onto regenerated drafts.
CREATE TABLE corrections (
    correction_id  INTEGER PRIMARY KEY,
    created_at     TEXT NOT NULL CHECK (created_at GLOB '????-??-??T??:??:??.??????Z'),
    command        TEXT NOT NULL CHECK (command <> ''),
    args_json      TEXT NOT NULL CHECK (json_valid(args_json)),
    digest_id      TEXT REFERENCES digests (digest_id),
    note           TEXT
) STRICT;

CREATE TRIGGER corrections_are_append_only_update BEFORE UPDATE ON corrections
BEGIN
    SELECT RAISE (ABORT, 'corrections are append-only');
END;

CREATE TRIGGER corrections_are_append_only_delete BEFORE DELETE ON corrections
BEGIN
    SELECT RAISE (ABORT, 'corrections are append-only');
END;

-- Assignment history. The model assigns within a run; a person assigns through a logged
-- correction, and a person's latest assignment always wins (v_effective_assignment).
CREATE TABLE assignments (
    assignment_id  INTEGER PRIMARY KEY,
    signal_id      INTEGER NOT NULL REFERENCES signals (signal_id),
    theme_id       TEXT NOT NULL REFERENCES themes (theme_id),
    set_by         TEXT NOT NULL CHECK (set_by IN ('model', 'person')),
    confidence     REAL CHECK (confidence BETWEEN 0 AND 1),
    rationale      TEXT,
    run_id         INTEGER REFERENCES runs (run_id),
    correction_id  INTEGER REFERENCES corrections (correction_id),
    created_at     TEXT NOT NULL CHECK (created_at GLOB '????-??-??T??:??:??.??????Z'),
    CHECK (set_by <> 'model' OR (run_id IS NOT NULL AND correction_id IS NULL)),
    CHECK (set_by <> 'person' OR correction_id IS NOT NULL)
) STRICT;

CREATE INDEX assignments_by_signal ON assignments (signal_id, assignment_id);

CREATE TRIGGER assignments_are_append_only_update BEFORE UPDATE ON assignments
BEGIN
    SELECT RAISE (ABORT, 'assignments are history; add a new assignment instead');
END;

CREATE TRIGGER assignments_are_append_only_delete BEFORE DELETE ON assignments
BEGIN
    SELECT RAISE (ABORT, 'assignments are history; add a new assignment instead');
END;

-- Signal-to-issue relationships. A mention ("references") is a fact found by code and never
-- supports a claim about the issue. A report ("reports") is proposed by the model or added by
-- a person, and counts only once a person confirms it. issue_number has no foreign key because
-- a message can mention an issue that is missing from the export.
CREATE TABLE links (
    link_id        INTEGER PRIMARY KEY,
    signal_id      INTEGER NOT NULL REFERENCES signals (signal_id),
    issue_number   INTEGER NOT NULL CHECK (issue_number > 0),
    relation       TEXT NOT NULL CHECK (relation IN ('references', 'reports')),
    found_by       TEXT NOT NULL CHECK (found_by IN ('code', 'model', 'person')),
    confidence     REAL CHECK (confidence BETWEEN 0 AND 1),
    review_status  TEXT NOT NULL
                        CHECK (review_status IN ('observed', 'proposed', 'confirmed', 'rejected')),
    run_id         INTEGER REFERENCES runs (run_id),
    correction_id  INTEGER REFERENCES corrections (correction_id),
    created_at     TEXT NOT NULL CHECK (created_at GLOB '????-??-??T??:??:??.??????Z'),
    UNIQUE (signal_id, issue_number, relation),
    CHECK (relation <> 'references' OR (found_by = 'code' AND review_status = 'observed')),
    CHECK (relation <> 'reports' OR (found_by IN ('model', 'person')
                                     AND review_status <> 'observed')),
    CHECK (review_status NOT IN ('confirmed', 'rejected') OR correction_id IS NOT NULL)
) STRICT;

CREATE INDEX links_by_issue ON links (issue_number, relation, review_status);

------------------------------------------------------------------------------------------------
-- Engineering attention and publishing
------------------------------------------------------------------------------------------------

-- ox sessions from the vendor repo, reconciled by pulling ox's session history.
CREATE TABLE sessions (
    session_name           TEXT PRIMARY KEY CHECK (session_name <> ''),
    repo_id                TEXT NOT NULL CHECK (repo_id GLOB 'repo_?*'),
    agent_id               TEXT,
    url                    TEXT,
    started_at             TEXT CHECK (started_at GLOB '????-??-??T??:??:??.??????Z'),
    stopped_at             TEXT CHECK (stopped_at GLOB '????-??-??T??:??:??.??????Z'),
    produced_commits_json  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(produced_commits_json)),
    reconciled_at          TEXT NOT NULL CHECK (reconciled_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;

-- Files a session touched. Verified: a commit the session produced changed the file.
-- Reported: the transcript shows a write or edit with no linked commit. No row: unknown.
CREATE TABLE session_evidence (
    evidence_id   INTEGER PRIMARY KEY,
    session_name  TEXT NOT NULL REFERENCES sessions (session_name),
    path          TEXT NOT NULL CHECK (path <> '' AND path NOT GLOB '/*'),
    level         TEXT NOT NULL CHECK (level IN ('verified', 'reported')),
    commit_sha    TEXT CHECK (length(commit_sha) = 40 AND commit_sha NOT GLOB '*[^0-9a-f]*'),
    committed_at  TEXT CHECK (committed_at GLOB '????-??-??T??:??:??.??????Z'),
    observed_at   TEXT NOT NULL CHECK (observed_at GLOB '????-??-??T??:??:??.??????Z'),
    CHECK ((level = 'verified') = (commit_sha IS NOT NULL AND committed_at IS NOT NULL))
) STRICT;

CREATE UNIQUE INDEX session_evidence_unique
    ON session_evidence (session_name, path, level, coalesce(commit_sha, ''));

-- One row per digest and publishing step, so a retry resumes where it stopped and a partial
-- success is visible. Every step acts on the digest's approved content hash (triggers below).
CREATE TABLE publish_steps (
    digest_id        TEXT NOT NULL REFERENCES digests (digest_id),
    step             TEXT NOT NULL
                          CHECK (step IN ('doc_written', 'doc_pushed', 'doc_listed', 'archived')),
    status           TEXT NOT NULL CHECK (status IN ('done', 'failed', 'blocked')),
    approved_sha256  TEXT NOT NULL CHECK (length(approved_sha256) = 64),
    doc_sha256       TEXT CHECK (length(doc_sha256) = 64),
    team_commit      TEXT CHECK (length(team_commit) = 40 AND team_commit NOT GLOB '*[^0-9a-f]*'),
    detail_json      TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(detail_json)),
    attempts         INTEGER NOT NULL DEFAULT 1 CHECK (attempts >= 1),
    updated_at       TEXT NOT NULL CHECK (updated_at GLOB '????-??-??T??:??:??.??????Z'),
    PRIMARY KEY (digest_id, step)
) STRICT;

CREATE TRIGGER publish_steps_insert_need_the_approved_hash BEFORE INSERT ON publish_steps
WHEN NEW.approved_sha256 IS NOT
     (SELECT approved_sha256 FROM digests WHERE digest_id = NEW.digest_id)
BEGIN
    SELECT RAISE (ABORT, 'publish steps must act on the digest''s approved content hash');
END;

CREATE TRIGGER publish_steps_update_need_the_approved_hash BEFORE UPDATE ON publish_steps
WHEN NEW.approved_sha256 IS NOT
     (SELECT approved_sha256 FROM digests WHERE digest_id = NEW.digest_id)
BEGIN
    SELECT RAISE (ABORT, 'publish steps must act on the digest''s approved content hash');
END;

-- Validated model responses keyed by a hash of the complete request, for replay mode.
-- request_json holds the request as sent, which contains only redacted text.
CREATE TABLE llm_cache (
    request_sha256  TEXT PRIMARY KEY CHECK (length(request_sha256) = 64),
    task            TEXT NOT NULL,
    model           TEXT NOT NULL,
    effort          TEXT,
    prompt_version  TEXT NOT NULL,
    schema_version  TEXT NOT NULL,
    request_json    TEXT NOT NULL CHECK (json_valid(request_json)),
    response_json   TEXT NOT NULL CHECK (json_valid(response_json)),
    input_tokens    INTEGER CHECK (input_tokens >= 0),
    output_tokens   INTEGER CHECK (output_tokens >= 0),
    created_at      TEXT NOT NULL CHECK (created_at GLOB '????-??-??T??:??:??.??????Z')
) STRICT;

------------------------------------------------------------------------------------------------
-- Views: the facts code computes. Window-dependent views join through runs, because SQLite
-- views can't take parameters.
------------------------------------------------------------------------------------------------

-- Each theme mapped to the theme that survives it after merges (itself if never merged).
CREATE VIEW v_theme_resolution AS
WITH RECURSIVE chain (theme_id, final_theme_id, depth) AS (
    SELECT theme_id, theme_id, 0 FROM themes WHERE merged_into IS NULL
    UNION ALL
    SELECT t.theme_id, chain.final_theme_id, chain.depth + 1
    FROM themes AS t
    JOIN chain ON t.merged_into = chain.theme_id
    WHERE chain.depth < 64
)
SELECT theme_id, final_theme_id FROM chain;

-- The assignment that counts for each signal: a person's latest if there is one, otherwise
-- the model's latest. Merged themes resolve to the theme that absorbed them.
CREATE VIEW v_effective_assignment AS
WITH ranked AS (
    SELECT a.*,
           row_number() OVER (
               PARTITION BY a.signal_id
               ORDER BY CASE a.set_by WHEN 'person' THEN 0 ELSE 1 END, a.assignment_id DESC
           ) AS pick
    FROM assignments AS a
)
SELECT r.signal_id,
       res.final_theme_id AS theme_id,
       r.theme_id AS assigned_theme_id,
       r.set_by,
       r.confidence,
       r.assignment_id,
       r.run_id,
       r.correction_id
FROM ranked AS r
JOIN v_theme_resolution AS res ON res.theme_id = r.theme_id
WHERE r.pick = 1;

-- Each issue as the most recent import saw it.
CREATE VIEW v_issue_latest AS
SELECT o.issue_number, o.state, o.state_reason, o.closed_at, o.labels_json, o.import_id,
       o.observed_at
FROM issue_observations AS o
WHERE o.import_id = (SELECT max(o2.import_id)
                     FROM issue_observations AS o2
                     WHERE o2.issue_number = o.issue_number);

-- The evidence that counts for a run: window_start <= occurred_at < cutoff, and never Pulse's
-- own output.
CREATE VIEW v_run_signals AS
SELECT r.run_id, s.signal_id, s.source, s.source_key, s.account_id, s.author_name,
       s.occurred_at, s.thread_key, s.issue_number
FROM runs AS r
JOIN signals AS s ON s.occurred_at >= r.window_start AND s.occurred_at < r.cutoff
WHERE r.window_start IS NOT NULL
  AND s.is_pulse_output = 0;

-- Facts per run and theme. Affected customers count only attributed evidence; the rest is
-- counted as unattributed, never guessed. Confirmed versus proposed shows how much of each
-- count rests on a person's review.
CREATE VIEW v_run_theme_facts AS
SELECT rs.run_id,
       ea.theme_id,
       count(*) AS signal_count,
       count(DISTINCT coalesce(rs.thread_key, rs.source || ':' || rs.source_key)) AS thread_count,
       count(DISTINCT rs.account_id) AS affected_customer_count,
       sum(rs.account_id IS NULL) AS unattributed_count,
       sum(ea.set_by = 'person') AS confirmed_assignment_count,
       sum(ea.set_by = 'model') AS proposed_assignment_count,
       min(rs.occurred_at) AS first_seen,
       max(rs.occurred_at) AS last_seen
FROM v_run_signals AS rs
JOIN v_effective_assignment AS ea ON ea.signal_id = rs.signal_id
GROUP BY rs.run_id, ea.theme_id;

-- Which customers each theme affects in a run.
CREATE VIEW v_run_theme_customers AS
SELECT DISTINCT rs.run_id, ea.theme_id, rs.account_id, a.name AS account_name
FROM v_run_signals AS rs
JOIN v_effective_assignment AS ea ON ea.signal_id = rs.signal_id
JOIN accounts AS a ON a.account_id = rs.account_id;

-- Each digest's themes against the previous digest. Both windows use today's theme structure,
-- so merges and splits compare like with like. Themes that went quiet are included.
CREATE VIEW v_digest_theme_trend AS
SELECT d.digest_id,
       cur.theme_id,
       cur.signal_count,
       coalesce(prev.signal_count, 0) AS previous_signal_count,
       cur.affected_customer_count,
       coalesce(prev.affected_customer_count, 0) AS previous_affected_customer_count,
       CASE
           WHEN d.previous_digest_id IS NULL THEN 'no_previous'
           WHEN prev.theme_id IS NULL THEN 'new'
           WHEN cur.signal_count > prev.signal_count THEN 'growing'
           WHEN cur.signal_count < prev.signal_count THEN 'shrinking'
           ELSE 'steady'
       END AS trend
FROM digests AS d
JOIN v_run_theme_facts AS cur ON cur.run_id = d.run_id
LEFT JOIN digests AS pd ON pd.digest_id = d.previous_digest_id
LEFT JOIN v_run_theme_facts AS prev ON prev.run_id = pd.run_id AND prev.theme_id = cur.theme_id
UNION ALL
SELECT d.digest_id, prev.theme_id, 0, prev.signal_count, 0, prev.affected_customer_count,
       'quiet'
FROM digests AS d
JOIN digests AS pd ON pd.digest_id = d.previous_digest_id
JOIN v_run_theme_facts AS prev ON prev.run_id = pd.run_id
WHERE NOT EXISTS (SELECT 1
                  FROM v_run_theme_facts AS cur
                  WHERE cur.run_id = d.run_id AND cur.theme_id = prev.theme_id);

-- Reported after issue closure: a report inside the run's evidence range, tied to an issue by a
-- confirmed "reports" link, dated after the issue closed. The closure may fall before the
-- window; only the report has to be inside it. Never labelled a regression.
CREATE VIEW v_run_reported_after_closure AS
SELECT rs.run_id, rs.signal_id, l.issue_number, rs.occurred_at AS reported_at, il.closed_at,
       il.state_reason
FROM v_run_signals AS rs
JOIN links AS l ON l.signal_id = rs.signal_id
               AND l.relation = 'reports'
               AND l.review_status = 'confirmed'
JOIN v_issue_latest AS il ON il.issue_number = l.issue_number
WHERE il.closed_at IS NOT NULL
  AND il.closed_at < rs.occurred_at;

-- Possibly related engineering activity: sessions that stopped inside a run's evidence range
-- and changed (verified) or edited (reported) files in a theme's code areas. It never marks a
-- theme resolved.
CREATE VIEW v_run_theme_attention AS
SELECT r.run_id,
       res.final_theme_id AS theme_id,
       s.session_name,
       CASE max(CASE se.level WHEN 'verified' THEN 2 ELSE 1 END)
           WHEN 2 THEN 'verified' ELSE 'reported'
       END AS level
FROM runs AS r
JOIN sessions AS s ON s.stopped_at >= r.window_start AND s.stopped_at < r.cutoff
JOIN session_evidence AS se ON se.session_name = s.session_name
                           AND (se.committed_at IS NULL OR se.committed_at < r.cutoff)
JOIN code_area_paths AS cap ON substr(se.path, 1, length(cap.path_prefix)) = cap.path_prefix
JOIN theme_code_areas AS tca ON tca.area_key = cap.area_key
JOIN v_theme_resolution AS res ON res.theme_id = tca.theme_id
WHERE r.window_start IS NOT NULL
GROUP BY r.run_id, res.final_theme_id, s.session_name;

-- What Pulse last pushed to the team doc, for the ownership check before the next publish.
CREATE VIEW v_last_published_doc AS
SELECT ps.digest_id, ps.doc_sha256, ps.team_commit, ps.updated_at
FROM publish_steps AS ps
WHERE ps.step = 'doc_pushed' AND ps.status = 'done'
ORDER BY ps.updated_at DESC, ps.digest_id DESC
LIMIT 1;
