import argparse
import json
import logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LLM YouTube landscape tracker",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init-db", help="Create the SQLite schema")
    subparsers.add_parser("ingest", help="Fetch channel metadata and new videos")
    subparsers.add_parser("transcript", help="Fetch or generate transcripts")
    subparsers.add_parser("analyse", help="Summarise and classify transcripts")
    subparsers.add_parser("export-dashboard", help="Write the static dashboard snapshot")
    subparsers.add_parser("run", help="Run the full pipeline once")

    serve = subparsers.add_parser("serve-api", help="Run the FastAPI backend")
    serve.add_argument("--host", default=None, help="Host to bind")
    serve.add_argument("--port", default=None, type=int, help="Port to bind")
    serve.add_argument("--reload", action="store_true", help="Enable hot reload")

    return parser


def main() -> int:
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s",
        level=logging.INFO,
    )

    parser = build_parser()
    args = parser.parse_args()

    command = args.command or "run"

    if command == "init-db":
        from tracker.db import initialise_database
        initialise_database()
        logging.getLogger().info("Database initialised.")
        return 0

    if command == "ingest":
        from tracker.pipeline import run_ingestion
        result = run_ingestion()
        logging.getLogger().info(json.dumps(result, indent=2, ensure_ascii=True))
        return 0

    if command == "transcript":
        from tracker.pipeline import run_transcripts
        result = run_transcripts()
        logging.getLogger().info(json.dumps(result, indent=2, ensure_ascii=True))
        return 0

    if command == "analyse":
        from tracker.pipeline import run_analyses
        result = run_analyses()
        logging.getLogger().info(json.dumps(result, indent=2, ensure_ascii=True))
        return 0

    if command == "export-dashboard":
        from tracker.pipeline import export_dashboard_snapshot
        path = export_dashboard_snapshot()
        logging.getLogger().info(f"Dashboard snapshot written to {path}")
        return 0

    if command == "serve-api":
        import uvicorn

        from tracker.config import get_settings

        settings = get_settings()
        if args.reload:
            uvicorn.run(
                "tracker.api:app",
                host=args.host or settings.api_host,
                port=args.port or settings.api_port,
                reload=True,
            )
        else:
            from tracker.api import create_app
            uvicorn.run(
                create_app(),
                host=args.host or settings.api_host,
                port=args.port or settings.api_port,
                reload=False,
            )
        return 0

    if command == "run":
        from tracker.pipeline import run_all
        result = run_all()
        logging.getLogger().info(json.dumps(result, indent=2, ensure_ascii=True))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
