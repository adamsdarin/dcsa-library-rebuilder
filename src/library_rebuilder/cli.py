from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .acquire import acquire, targets_from
from .census import census
from .common import write_json
from .engine import load_config, preflight, protected_overlap, run, verify
from .notice import MAINTENANCE_MODE, NOTICE, banner
from .recipe import build_recipe

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _emit(result: dict) -> None:
    print(json.dumps({**result, "maintenance_mode": MAINTENANCE_MODE, "maintenance_notice": NOTICE}, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="rebuilder", description="Rebuild a DCSA Library into an empty destination, "
                                     "standalone (no Librarian, no Archivist). The result is NOT autonomously maintained.")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "rebuilder.json")
    commands = parser.add_subparsers(dest="command", required=True)

    c = commands.add_parser("census", help="Read-only: classify every document by rebuild route")
    c.add_argument("--library", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)

    a = commands.add_parser("acquire", help="Fetch official HTTPS sources into a run-owned quarantine")
    a.add_argument("--census", type=Path, help="Census report; uses reacquire_from_official_url documents")
    a.add_argument("--urls", type=Path, help="Text file of official URLs, one per line")
    a.add_argument("--collection", action="append", help="Limit census targets to this collection (repeatable)")
    a.add_argument("--limit", type=int)
    a.add_argument("--out", type=Path, required=True)

    r = commands.add_parser("recipe", help="Write recipe.json from a reviewed intake plan and evaluations")
    r.add_argument("--dir", type=Path, required=True)
    r.add_argument("--release-id", required=True)
    r.add_argument("--scope", required=True)
    r.add_argument("--intake-plan", default="intake_plan.json")
    r.add_argument("--evaluations", default="golden_queries.json")

    p = commands.add_parser("preflight", help="Check destination, protection, locks and FTS5 support")
    p.add_argument("--destination", type=Path, required=True)

    b = commands.add_parser("run", help="Build, validate, evaluate and publish into an empty destination")
    b.add_argument("--recipe", type=Path, required=True)
    b.add_argument("--destination", type=Path, required=True)

    v = commands.add_parser("verify", help="Fail-closed approved-release check of a rebuilt destination")
    v.add_argument("--destination", type=Path, required=True)
    v.add_argument("--release-id")

    args = parser.parse_args(argv)
    # Printed before any work, on stderr so stdout stays machine-readable JSON.
    print(banner(), file=sys.stderr)
    try:
        if args.command == "census":
            report = census(args.library)
            write_json(args.out, report)
            _emit({k: report[k] for k in ("source_release_id", "total_documents", "by_route")})
            return 0
        if args.command == "recipe":
            _emit({"ok": True, "recipe": str(build_recipe(args.dir, args.release_id, args.scope, args.intake_plan, args.evaluations))})
            return 0
        if args.command == "verify":
            result = verify(args.destination, args.release_id)
        else:
            config = load_config(args.config, PROJECT_ROOT)
            if args.command == "acquire":
                if not (args.census or args.urls):
                    raise ValueError("acquire needs --census or --urls")
                overlap = protected_overlap(config, args.out)
                if overlap:
                    raise ValueError("; ".join(overlap))
                targets = targets_from(args.census, args.urls, args.collection, args.limit)
                report = acquire(targets, args.out, config.get("acquisition", {}))
                _emit({k: report[k] for k in ("requested", "counts", "complete", "changed_since_recorded")})
                return 0 if report["complete"] else 1
            if args.command == "preflight":
                result = preflight(config, args.destination)
            else:
                result = run(config, args.recipe, args.destination, PROJECT_ROOT / "runs")
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2
    _emit(result)
    if result.get("ok") and args.command in ("run", "verify"):
        print(banner(), file=sys.stderr)  # repeated after a build or verify so it is the last thing seen
    return 0 if result["ok"] else 1
