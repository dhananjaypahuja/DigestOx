"""The `pulse` command line. Every command supports --json so an agent can drive it too."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

from customer_pulse import __version__, db, state
from customer_pulse.clock import clock_from_env
from customer_pulse.config import Config, load_config
from customer_pulse.errors import PulseError

app = typer.Typer(
    name="pulse",
    help="Customer Pulse: turn customer feedback into an evidence-backed friction digest.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)

JsonFlag = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]

Result = dict[str, Any]


@dataclass(frozen=True)
class _Options:
    config_path: Path | None


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"pulse {__version__}")
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            envvar="PULSE_CONFIG",
            dir_okay=False,
            help="Path to pulse.toml. Defaults to ./pulse.toml when it exists.",
        ),
    ] = None,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", callback=_show_version, is_eager=True, help="Show the version and exit."
        ),
    ] = None,
) -> None:
    ctx.obj = _Options(config_path=config)


def _run(
    ctx: typer.Context,
    as_json: bool,
    action: Callable[[Config], Result],
    render: Callable[[Result], None],
) -> None:
    """Load the config, run ``action``, and print its result as JSON or for people."""
    try:
        config = load_config(ctx.obj.config_path, Path.cwd())
        result = action(config)
    except PulseError as err:
        _fail(err, as_json)
    except (OSError, sqlite3.Error) as exc:
        # Expected operational failures get a stable code too. Anything else is a bug and is
        # left to raise, so it can't hide behind a tidy error message.
        _fail(operational_error(exc), as_json, cause=exc)
    if as_json:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
    else:
        render(result)


def _fail(err: PulseError, as_json: bool, cause: BaseException | None = None) -> None:
    if as_json:
        typer.echo(json.dumps({"error": err.to_dict()}, indent=2, sort_keys=True))
    else:
        typer.echo(f"error: {err.message}", err=True)
        if err.hint:
            typer.echo(f"hint: {err.hint}", err=True)
    raise typer.Exit(code=1) from (cause or err)


def operational_error(exc: OSError | sqlite3.Error) -> PulseError:
    """Translate a filesystem or SQLite failure into a stable, actionable error."""
    if isinstance(exc, sqlite3.Error):
        text = str(exc)
        lowered = text.lower()
        if "locked" in lowered or "busy" in lowered:
            return PulseError(
                "database_locked",
                "the database is locked by another process",
                hint="wait for the other pulse command to finish, then try again",
            )
        if "unable to open" in lowered:
            return PulseError(
                "database_unavailable",
                f"the database can't be opened: {text}",
                hint="check that the state directory exists and that you can write to it",
            )
        if "readonly" in lowered or "read-only" in lowered:
            return PulseError(
                "permission_denied",
                f"the database is read-only: {text}",
                hint="check the permissions of the state directory and the database",
            )
        if isinstance(exc, sqlite3.DatabaseError) and not isinstance(exc, sqlite3.OperationalError):
            return PulseError(
                "database_unreadable",
                f"the database can't be read: {text}",
                hint="if it's corrupt or not a Customer Pulse database, move it aside and run "
                "`pulse init`",
            )
        return PulseError("database_error", f"database error: {text}")
    where = f": {exc.filename}" if exc.filename else ""
    if isinstance(exc, FileExistsError | NotADirectoryError):
        return PulseError(
            "state_path_not_a_directory",
            f"a file is in the way of the state directory{where}",
            hint="move it aside, or set pulse.state_dir to another path",
        )
    if isinstance(exc, PermissionError):
        return PulseError(
            "permission_denied",
            f"permission denied{where}",
            hint="check the permissions of the state directory and its files",
        )
    return PulseError("filesystem_error", f"{exc.strerror or exc}{where}")


def _display_path(text: str) -> str:
    path = Path(text)
    try:
        return str(path.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


# pulse init


@app.command()
def init(ctx: typer.Context, as_json: JsonFlag = False) -> None:
    """Create the local database, or bring it up to the latest schema."""
    _run(ctx, as_json, _init, _render_init)


def _init(config: Config) -> Result:
    clock = clock_from_env(os.environ)
    db.check_sqlite_version()
    # The database holds customer evidence: create it private, and refuse existing state that
    # other users can read rather than silently changing its permissions.
    created = state.prepare(config)
    with closing(db.connect(config.db_path)) as conn:
        applied = db.migrate(conn, clock)
        version = db.schema_version(conn)
    return {
        "applied_migrations": applied,
        "config_file": str(config.file) if config.file else None,
        "created": created,
        "database": str(config.db_path),
        "schema_version": version,
        "timezone": config.timezone.key,
    }


def _render_init(result: Result) -> None:
    where = _display_path(result["database"])
    if result["applied_migrations"]:
        verb = "Created" if result["created"] else "Updated"
        typer.echo(
            f"{verb} {where}: applied {db.describe_migrations(result['applied_migrations'])}, "
            f"now at schema {result['schema_version']}."
        )
    else:
        typer.echo(f"{where} is up to date at schema {result['schema_version']}.")
    typer.echo(f"Digest windows use the {result['timezone']} timezone.")


# pulse status


@app.command()
def status(ctx: typer.Context, as_json: JsonFlag = False) -> None:
    """Show the configuration, the database, and what it holds. Changes nothing."""
    _run(ctx, as_json, _status, _render_status)


def _status(config: Config) -> Result:
    database = db.inspect(config.db_path)
    return {
        "config": {
            "file": str(config.file) if config.file else None,
            "state_dir": str(config.state_dir),
            "timezone": config.timezone.key,
        },
        "counts": database["counts"],
        "database": {
            **{
                key: database[key]
                for key in (
                    "initialized",
                    "latest_schema_version",
                    "migrations_modified",
                    "migrations_pending",
                    "path",
                    "schema_version",
                )
            },
            "privacy_problems": state.privacy_problems(config),
        },
        "last_digest": database["last_digest"],
        "pulse_version": __version__,
    }


def _render_status(result: Result) -> None:
    config, database, counts = result["config"], result["database"], result["counts"]
    typer.echo(f"Customer Pulse {result['pulse_version']}")
    source = _display_path(config["file"]) if config["file"] else "no pulse.toml, using defaults"
    typer.echo(f"  config    {source}; timezone {config['timezone']}")
    where = _display_path(database["path"])
    for problem in database["privacy_problems"]:
        typer.echo(f"  warning   local state isn't private: {problem}")
    if not database["initialized"]:
        typer.echo(f"  database  {where} is not initialized. Run `pulse init`.")
        return
    schema = f"schema {database['schema_version']} of {database['latest_schema_version']}"
    if database["migrations_pending"]:
        pending = db.describe_migrations(database["migrations_pending"])
        schema += f"; run `pulse init` to apply {pending}"
    if database["migrations_modified"]:
        schema += (
            f"; warning: {db.describe_migrations(database['migrations_modified'])} changed "
            "after being applied"
        )
    typer.echo(f"  database  {where}, {schema}")
    typer.echo(
        f"  evidence  {counts['signals']} signals, {counts['issues']} issues, "
        f"{counts['accounts']} accounts, {counts['imports']} imports"
    )
    last = result["last_digest"]
    last_text = f"{last['digest_id']} ({last['status']})" if last else "none yet"
    typer.echo(
        f"  review    {counts['themes']} themes, {counts['digests']} digests; "
        f"last digest {last_text}"
    )
    typer.echo(f"  sessions  {counts['sessions']} engineering sessions reconciled")
