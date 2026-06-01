from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.dashboard import serve_dashboard
from app.main import SwarmApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Multiagent Swarm CLI.")
    parser.add_argument(
        "--config",
        default="configs/agents.yaml",
        help="Path to the agents configuration file, relative to the project root unless absolute.",
    )
    parser.add_argument(
        "--prompt",
        help="Run one non-interactive turn and exit.",
    )
    parser.add_argument(
        "--provider",
        choices=["agents_sdk", "codex_cli"],
        help="Override the default provider for agents that do not set one explicitly.",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Serve the local dashboard instead of running the CLI loop.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard host.")
    parser.add_argument("--port", type=int, default=8765, help="Dashboard port.")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[1]
    args = build_parser().parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path

    if args.dashboard:
        serve_dashboard(project_root, config_path, args.host, args.port)
        return 0

    app = SwarmApp(project_root, config_path, provider_override=args.provider)

    if args.prompt:
        result = await app.run_turn(args.prompt)
        print(result.get("final_answer") or "No final answer returned.")
        return 0

    print("Multiagent Swarm CLI. Type 'exit' to quit.")
    while True:
        try:
            user_input = input("\nYou> ").strip()
        except EOFError:
            print()
            return 0

        if user_input.lower() in {"exit", "quit"}:
            return 0
        if not user_input:
            continue

        try:
            result = await app.run_turn(user_input)
        except Exception as exc:
            print(f"\nError: {exc}")
            continue

        print("\nSwarm>")
        print(result.get("final_answer") or "No final answer returned.")

        artifacts = result.get("artifacts", [])
        if artifacts:
            print("\nArtifacts:")
            for artifact in artifacts:
                print(f"- {artifact.get('agent')}: {artifact.get('artifact_path')}")


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
