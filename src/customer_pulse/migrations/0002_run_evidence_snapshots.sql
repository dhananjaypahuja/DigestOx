-- Migration 0002: bind every run to an evidence snapshot, and derive issue state at the cutoff.
--
-- Review finding R2 (Codex, 95fc080): a run's facts changed when a later import arrived,
-- because v_run_reported_after_closure read each issue's latest observation globally. A run
-- now records exactly which imports and engineering sessions it used, and every run-scoped
-- view reads only that snapshot. Later imports and sessions feed later runs, including valid
-- earlier facts they reveal, but they can't change a run that already exists. The evidence a
-- snapshot relies on is fixed so the snapshot stays meaningful.

------------------------------------------------------------------------------------------------
-- Snapshots
------------------------------------------------------------------------------------------------

CREATE TABLE run_imports (
    run_id     INTEGER NOT NULL REFERENCES runs (run_id),
    import_id  INTEGER NOT NULL REFERENCES imports (import_id),
    PRIMARY KEY (run_id, import_id)
) STRICT;

CREATE TABLE run_sessions (
    run_id        INTEGER NOT NULL REFERENCES runs (run_id),
    session_name  TEXT NOT NULL REFERENCES sessions (session_name),
    PRIMARY KEY (run_id, session_name)
) STRICT;

CREATE INDEX run_sessions_by_session ON run_sessions (session_name);

-- A snapshot is recorded while its run is running and never changes afterwards.
CREATE TRIGGER run_imports_only_while_running BEFORE INSERT ON run_imports
WHEN (SELECT status FROM runs WHERE run_id = NEW.run_id) IS NOT 'running'
BEGIN
    SELECT RAISE (ABORT, 'a run''s evidence snapshot is recorded only while the run is running');
END;

CREATE TRIGGER run_sessions_only_while_running BEFORE INSERT ON run_sessions
WHEN (SELECT status FROM runs WHERE run_id = NEW.run_id) IS NOT 'running'
BEGIN
    SELECT RAISE (ABORT, 'a run''s evidence snapshot is recorded only while the run is running');
END;

CREATE TRIGGER run_imports_are_fixed_update BEFORE UPDATE ON run_imports
BEGIN
    SELECT RAISE (ABORT, 'a run''s evidence snapshot is fixed');
END;

CREATE TRIGGER run_imports_are_fixed_delete BEFORE DELETE ON run_imports
BEGIN
    SELECT RAISE (ABORT, 'a run''s evidence snapshot is fixed');
END;

CREATE TRIGGER run_sessions_are_fixed_update BEFORE UPDATE ON run_sessions
BEGIN
    SELECT RAISE (ABORT, 'a run''s evidence snapshot is fixed');
END;

CREATE TRIGGER run_sessions_are_fixed_delete BEFORE DELETE ON run_sessions
BEGIN
    SELECT RAISE (ABORT, 'a run''s evidence snapshot is fixed');
END;

-- A run's window can't move, and a finished run stays finished.
CREATE TRIGGER runs_window_is_fixed
BEFORE UPDATE OF window_start, window_end, cutoff, timezone ON runs
WHEN NEW.window_start IS NOT OLD.window_start
  OR NEW.window_end IS NOT OLD.window_end
  OR NEW.cutoff IS NOT OLD.cutoff
  OR NEW.timezone IS NOT OLD.timezone
BEGIN
    SELECT RAISE (ABORT, 'a run''s window and cutoff are fixed');
END;

CREATE TRIGGER runs_finish_once BEFORE UPDATE OF status ON runs
WHEN OLD.status <> 'running' AND NEW.status IS NOT OLD.status
BEGIN
    SELECT RAISE (ABORT, 'a finished run can''t change status');
END;

------------------------------------------------------------------------------------------------
-- Evidence a snapshot relies on
------------------------------------------------------------------------------------------------

-- Issue observations are history: each records what one import saw.
CREATE TRIGGER issue_observations_are_history_update BEFORE UPDATE ON issue_observations
BEGIN
    SELECT RAISE (ABORT, 'issue observations are history; import a new observation instead');
END;

CREATE TRIGGER issue_observations_are_history_delete BEFORE DELETE ON issue_observations
BEGIN
    SELECT RAISE (ABORT, 'issue observations are history; import a new observation instead');
END;

-- A snapshot includes a signal through the import that first brought it in, so what the facts
-- depend on is fixed at that import: identity, time, customer, thread, and issue. A later import
-- may revise only the text, and signal_revisions records every such change.
CREATE TRIGGER signals_evidence_is_fixed
BEFORE UPDATE OF source, source_key, account_id, occurred_at, thread_key, issue_number,
                 is_pulse_output, first_import_id ON signals
WHEN NEW.source IS NOT OLD.source
  OR NEW.source_key IS NOT OLD.source_key
  OR NEW.account_id IS NOT OLD.account_id
  OR NEW.occurred_at IS NOT OLD.occurred_at
  OR NEW.thread_key IS NOT OLD.thread_key
  OR NEW.issue_number IS NOT OLD.issue_number
  OR NEW.is_pulse_output IS NOT OLD.is_pulse_output
  OR NEW.first_import_id IS NOT OLD.first_import_id
BEGIN
    SELECT RAISE (ABORT, 'a signal''s identity, time, customer, thread, and issue are fixed '
                         || 'at its first import; only its text can be revised');
END;

-- A session's evidence is fixed once any run has used the session.
CREATE TRIGGER session_evidence_is_fixed_once_used BEFORE INSERT ON session_evidence
WHEN EXISTS (SELECT 1 FROM run_sessions WHERE session_name = NEW.session_name)
BEGIN
    SELECT RAISE (ABORT, 'a session''s evidence is fixed once a run has used it');
END;

CREATE TRIGGER session_evidence_is_history_update BEFORE UPDATE ON session_evidence
BEGIN
    SELECT RAISE (ABORT, 'session evidence is history');
END;

CREATE TRIGGER session_evidence_is_history_delete BEFORE DELETE ON session_evidence
BEGIN
    SELECT RAISE (ABORT, 'session evidence is history');
END;

CREATE TRIGGER sessions_times_are_fixed_once_used
BEFORE UPDATE OF started_at, stopped_at, repo_id ON sessions
WHEN EXISTS (SELECT 1 FROM run_sessions WHERE session_name = OLD.session_name)
 AND (NEW.started_at IS NOT OLD.started_at
      OR NEW.stopped_at IS NOT OLD.stopped_at
      OR NEW.repo_id IS NOT OLD.repo_id)
BEGIN
    SELECT RAISE (ABORT, 'a session''s times are fixed once a run has used it');
END;

------------------------------------------------------------------------------------------------
-- Run-scoped views read only the run's snapshot. v_issue_latest stays as a live view for
-- present-state display; no run-scoped fact may use it.
------------------------------------------------------------------------------------------------

DROP VIEW v_run_signals;

-- Evidence that counts for a run: signals first imported by an import in the run's snapshot,
-- with window_start <= occurred_at < cutoff, and never Pulse's own output.
CREATE VIEW v_run_signals AS
SELECT r.run_id, s.signal_id, s.source, s.source_key, s.account_id, s.author_name,
       s.occurred_at, s.thread_key, s.issue_number
FROM runs AS r
JOIN run_imports AS ri ON ri.run_id = r.run_id
JOIN signals AS s ON s.first_import_id = ri.import_id
WHERE r.window_start IS NOT NULL
  AND s.occurred_at >= r.window_start
  AND s.occurred_at < r.cutoff
  AND s.is_pulse_output = 0;

-- The issue observations in a run's snapshot.
CREATE VIEW v_run_issue_observations AS
SELECT ri.run_id, o.issue_number, o.import_id, o.state, o.state_reason, o.closed_at,
       o.labels_json, o.observed_at
FROM run_imports AS ri
JOIN issue_observations AS o ON o.import_id = ri.import_id;

-- Every closure a run's snapshot has seen, with the reason first recorded for it. A later
-- observation showing the issue reopened doesn't erase a closure that happened.
CREATE VIEW v_run_issue_closures AS
SELECT o.run_id,
       o.issue_number,
       o.closed_at,
       (SELECT o2.state_reason
        FROM v_run_issue_observations AS o2
        WHERE o2.run_id = o.run_id
          AND o2.issue_number = o.issue_number
          AND o2.closed_at = o.closed_at
        ORDER BY o2.import_id
        LIMIT 1) AS state_reason
FROM v_run_issue_observations AS o
WHERE o.closed_at IS NOT NULL
GROUP BY o.run_id, o.issue_number, o.closed_at;

-- Each issue's state at a run's cutoff, from the run's snapshot, taking observations in import
-- order (imports are assumed to arrive in the order they were exported).
--   closed:  the last observation showing a closure before the cutoff isn't followed by one
--            showing the issue open or closed at a different time.
--   unknown: it is, so the issue reopened at a time the data can't place relative to the cutoff.
--   open:    no closure before the cutoff was seen. Reopen history before that is unknowable
--            from exports, as DESIGN.md section 5 states.
CREATE VIEW v_run_issue_state AS
WITH issues_at_cutoff AS (
    SELECT DISTINCT o.run_id, o.issue_number, i.title, i.created_at
    FROM v_run_issue_observations AS o
    JOIN issues AS i ON i.issue_number = o.issue_number
    JOIN runs AS r ON r.run_id = o.run_id
    WHERE i.created_at < r.cutoff
),
last_closure AS (
    SELECT o.run_id, o.issue_number, max(o.import_id) AS import_id
    FROM v_run_issue_observations AS o
    JOIN runs AS r ON r.run_id = o.run_id
    WHERE o.closed_at IS NOT NULL AND o.closed_at < r.cutoff
    GROUP BY o.run_id, o.issue_number
)
SELECT i.run_id,
       i.issue_number,
       i.title,
       i.created_at,
       CASE
           WHEN lc.import_id IS NULL THEN 'open'
           WHEN EXISTS (SELECT 1
                        FROM v_run_issue_observations AS later
                        WHERE later.run_id = lc.run_id
                          AND later.issue_number = lc.issue_number
                          AND later.import_id > lc.import_id
                          AND later.closed_at IS NOT lco.closed_at) THEN 'unknown'
           ELSE 'closed'
       END AS state_at_cutoff,
       lco.closed_at AS last_closed_before_cutoff,
       lco.state_reason
FROM issues_at_cutoff AS i
LEFT JOIN last_closure AS lc
       ON lc.run_id = i.run_id AND lc.issue_number = i.issue_number
LEFT JOIN v_run_issue_observations AS lco
       ON lco.run_id = lc.run_id AND lco.issue_number = lc.issue_number
      AND lco.import_id = lc.import_id;

DROP VIEW v_run_reported_after_closure;

-- Reported after issue closure: a report in the run's evidence, tied to an issue by a confirmed
-- "reports" link, dated after a closure the run's snapshot has seen. The closure may fall before
-- the window. The flag names the latest such closure. Never labelled a regression.
CREATE VIEW v_run_reported_after_closure AS
SELECT rs.run_id,
       rs.signal_id,
       l.issue_number,
       rs.occurred_at AS reported_at,
       c.closed_at,
       c.state_reason
FROM v_run_signals AS rs
JOIN links AS l ON l.signal_id = rs.signal_id
               AND l.relation = 'reports'
               AND l.review_status = 'confirmed'
JOIN v_run_issue_closures AS c ON c.run_id = rs.run_id AND c.issue_number = l.issue_number
WHERE c.closed_at = (SELECT max(c2.closed_at)
                     FROM v_run_issue_closures AS c2
                     WHERE c2.run_id = rs.run_id
                       AND c2.issue_number = l.issue_number
                       AND c2.closed_at < rs.occurred_at);

DROP VIEW v_run_theme_attention;

-- Possibly related engineering activity: sessions in the run's snapshot that stopped inside its
-- evidence range and changed (verified) or edited (reported) files in a theme's code areas. It
-- never marks a theme resolved.
CREATE VIEW v_run_theme_attention AS
SELECT r.run_id,
       res.final_theme_id AS theme_id,
       s.session_name,
       CASE max(CASE se.level WHEN 'verified' THEN 2 ELSE 1 END)
           WHEN 2 THEN 'verified' ELSE 'reported'
       END AS level
FROM runs AS r
JOIN run_sessions AS rsn ON rsn.run_id = r.run_id
JOIN sessions AS s ON s.session_name = rsn.session_name
                  AND s.stopped_at >= r.window_start
                  AND s.stopped_at < r.cutoff
JOIN session_evidence AS se ON se.session_name = s.session_name
                           AND (se.committed_at IS NULL OR se.committed_at < r.cutoff)
JOIN code_area_paths AS cap ON substr(se.path, 1, length(cap.path_prefix)) = cap.path_prefix
JOIN theme_code_areas AS tca ON tca.area_key = cap.area_key
JOIN v_theme_resolution AS res ON res.theme_id = tca.theme_id
WHERE r.window_start IS NOT NULL
GROUP BY r.run_id, res.final_theme_id, s.session_name;
