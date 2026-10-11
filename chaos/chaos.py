"""Command-line controller for the local Docker chaos scenarios."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import random
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


CHAOS_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = CHAOS_DIR / "scenarios"
STATE_FILE = CHAOS_DIR / ".chaos_state.json"


def load_scenarios(directory: Path = SCENARIOS_DIR) -> dict[str, ModuleType]:
    """Load each scenario module and verify its public entry points."""
    scenarios: dict[str, ModuleType] = {}
    for scenario_path in sorted(directory.glob("*.py")):
        if scenario_path.name == "__init__.py" or scenario_path.name.startswith("_"):
            continue

        name = scenario_path.stem
        spec = importlib.util.spec_from_file_location(
            f"_chaos_scenario_{name}", scenario_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load chaos scenario: {scenario_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for function_name in ("inject", "revert", "get_hint"):
            if not callable(getattr(module, function_name, None)):
                raise ImportError(
                    f"Scenario {scenario_path.name} must define "
                    f"{function_name}()"
                )
        scenarios[name] = module

    if not scenarios:
        raise RuntimeError(f"No chaos scenarios found in {directory}")
    return scenarios


def save_state(scenario: str, status: str) -> None:
    temporary_file = STATE_FILE.with_suffix(".json.tmp")
    temporary_file.write_text(
        json.dumps({"scenario": scenario, "status": status}, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_file.replace(STATE_FILE)


def read_state() -> dict[str, str]:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError("No active chaos scenario to revert or hint.") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Chaos state file is invalid: {STATE_FILE}") from error

    if (
        not isinstance(state, dict)
        or not isinstance(state.get("scenario"), str)
        or not isinstance(state.get("status"), str)
    ):
        raise RuntimeError(f"Chaos state file has an unsupported format: {STATE_FILE}")
    return state


def create_docker_client() -> Any:
    try:
        docker = importlib.import_module("docker")
    except ModuleNotFoundError as error:
        if error.name != "docker":
            raise
        raise RuntimeError(
            "Docker SDK is missing. Install it with "
            "'python -m pip install -r chaos/requirements.txt'."
        ) from error
    return docker.from_env()


def trigger(scenarios: dict[str, ModuleType]) -> None:
    if STATE_FILE.exists():
        state = read_state()
        raise RuntimeError(
            f"Scenario '{state['scenario']}' is {state['status']}; "
            "revert it before triggering another."
        )

    name = random.choice(list(scenarios))
    scenario = scenarios[name]
    client = create_docker_client()
    save_state(name, "injecting")
    scenario.inject(client)
    save_state(name, "active")
    print(f"Chaos scenario '{name}' triggered. Check Grafana for impact.")


def revert(scenarios: dict[str, ModuleType]) -> None:
    state = read_state()
    name = state["scenario"]
    scenario = scenarios.get(name)
    if scenario is None:
        raise RuntimeError(
            f"Active scenario '{name}' is not present in {SCENARIOS_DIR}."
        )

    client = create_docker_client()
    scenario.revert(client)
    STATE_FILE.unlink()
    print(f"Chaos scenario '{name}' reverted.")


def hint(scenarios: dict[str, ModuleType]) -> None:
    state = read_state()
    scenario = scenarios.get(state["scenario"])
    if scenario is None:
        raise RuntimeError(
            f"Active scenario '{state['scenario']}' is not present "
            f"in {SCENARIOS_DIR}."
        )
    print(scenario.get_hint())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("trigger", "revert", "hint"))
    arguments = parser.parse_args(argv)

    try:
        scenarios = load_scenarios()
        if arguments.command == "trigger":
            trigger(scenarios)
        elif arguments.command == "revert":
            revert(scenarios)
        else:
            hint(scenarios)
    except (OSError, RuntimeError, ImportError) as error:
        print(f"chaos: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())