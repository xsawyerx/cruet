"""CLI entry point: python -m cruet run [options]"""
import argparse
import importlib
import sys


def main():
    parser = argparse.ArgumentParser(prog="cruet")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the WSGI server")
    run_parser.add_argument("app", help="WSGI application (module:app)")
    run_parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    run_parser.add_argument("--port", type=int, default=8000, help="Bind port")
    run_parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    run_parser.add_argument("--unix-socket", default=None,
                            help="UNIX socket path (overrides host/port)")
    run_parser.add_argument("--no-async", action="store_true",
                            help="Force sync server fallback")

    args = parser.parse_args()

    if args.command == "run":
        # Import the WSGI app
        if ":" in args.app:
            module_path, app_name = args.app.rsplit(":", 1)
        else:
            module_path = args.app
            app_name = "app"

        module = importlib.import_module(module_path)
        app = getattr(module, app_name)

        from cruet.serving import run
        run(app, host=args.host, port=args.port, workers=args.workers,
            unix_socket=args.unix_socket, use_async=not args.no_async)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
