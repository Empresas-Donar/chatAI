"""
main.py
-------
CLI entrypoint for the AppSheet → PostgreSQL migration generator.

Usage:
    # Generate SQL only (schema + load statements)
    python main.py --app contratistas_isla_maipo

    # Generate SQL and also load data via psycopg2 (client-side)
    python main.py --app contratistas_isla_maipo --load

    # Use a custom config file
    python main.py --app contratistas_isla_maipo --config /path/to/config.yaml
"""

import argparse
import sys
from pathlib import Path

# Make sure imports resolve when running from any directory
sys.path.insert(0, str(Path(__file__).parent))

import schema_generator
import data_loader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AppSheet → PostgreSQL schema generator and data loader.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --app contratistas_isla_maipo
  python main.py --app medicion_pozos --load
  python main.py --app contratistas_isla_maipo --config custom_config.yaml
        """,
    )
    parser.add_argument(
        "--app",
        required=True,
        help="App name. Must match a subfolder in raw_csv/ and an entry in config.yaml.",
    )
    parser.add_argument(
        "--load",
        action="store_true",
        default=False,
        help="After generating SQL, also load data into PostgreSQL via psycopg2.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml in the generator/ directory).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve config path relative to this script
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).parent / config_path

    if not config_path.exists():
        print(f"ERROR: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print(f"  AppSheet → PostgreSQL Generator")
    print(f"  App: {args.app}")
    print("=" * 60)
    print()

    # Step 1: Generate SQL files
    print("--- Step 1: Generating SQL ---")
    schema_generator.run(args.app, config_path=str(config_path))

    # Step 2 (optional): Load data via psycopg2
    if args.load:
        print()
        print("--- Step 2: Loading data into PostgreSQL ---")
        data_loader.run(args.app, config_path=str(config_path))

    print()
    print("=" * 60)
    print("  All done.")
    print("=" * 60)


if __name__ == "__main__":
    main()
