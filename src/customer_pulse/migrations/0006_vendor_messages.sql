-- Migration 0006: messages from the vendor's own staff are context, not customer evidence.
--
-- Real exports carry the vendor's replies in shared channels and on issues ("can you send a
-- member ID?"). Counting them as evidence would inflate a theme's signals and threads, and a
-- staff message in a channel that names no customer would count as unattributed. They stay
-- stored, because a thread read without its replies loses its meaning, but no fact counts them
-- (decision 0011).

ALTER TABLE signals ADD COLUMN author_role TEXT NOT NULL DEFAULT 'customer'
    CHECK (author_role IN ('customer', 'vendor'));

-- Who wrote a signal decides whether any fact counts it, so it is fixed at the first import
-- like the signal's customer (decision 0010).
CREATE TRIGGER signals_author_role_is_fixed BEFORE UPDATE OF author_role ON signals
WHEN NEW.author_role IS NOT OLD.author_role
BEGIN
    SELECT RAISE (ABORT, 'a signal''s author role is fixed at its first import');
END;

DROP VIEW v_run_signals;

-- Evidence that counts for a run: customers' signals first imported by an import in the run's
-- snapshot, with window_start <= occurred_at < cutoff, and never Pulse's own output.
CREATE VIEW v_run_signals AS
SELECT r.run_id, s.signal_id, s.source, s.source_key, s.account_id, s.author_name,
       s.occurred_at, s.thread_key, s.issue_number
FROM runs AS r
JOIN run_imports AS ri ON ri.run_id = r.run_id
JOIN signals AS s ON s.first_import_id = ri.import_id
WHERE r.window_start IS NOT NULL
  AND s.occurred_at >= r.window_start
  AND s.occurred_at < r.cutoff
  AND s.is_pulse_output = 0
  AND s.author_role = 'customer';
