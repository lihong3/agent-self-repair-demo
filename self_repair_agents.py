from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GOAL = (
    "Build a customer lead management module that supports creating leads, "
    "updating lead status, listing leads, and summarizing the pipeline."
)


def rough_tokens(text: str) -> int:
    """A small deterministic approximation for audit reports."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass
class AgentEvent:
    name: str
    role: str
    input_text: str
    output_text: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def input_tokens(self) -> int:
        return rough_tokens(self.input_text)

    @property
    def output_tokens(self) -> int:
        return rough_tokens(self.output_text)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "started_at": self.started_at,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "output": self.output_text,
        }


class AgentMemory:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def record(self, name: str, role: str, input_text: str, output: Any) -> Any:
        output_text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        self.events.append(AgentEvent(name, role, input_text, output_text))
        return output

    def as_dict(self) -> dict[str, Any]:
        events = [event.as_dict() for event in self.events]
        return {
            "events": events,
            "total_input_tokens": sum(event["input_tokens"] for event in events),
            "total_output_tokens": sum(event["output_tokens"] for event in events),
            "total_tokens": sum(event["total_tokens"] for event in events),
        }


class OptionalOpenAIClient:
    def __init__(self, enabled: bool, model: str) -> None:
        self.enabled = enabled
        self.model = model
        self.client = None
        if enabled:
            try:
                from openai import OpenAI

                self.client = OpenAI()
            except Exception as exc:  # pragma: no cover - depends on local SDK setup.
                print(f"OpenAI SDK unavailable, falling back to deterministic agents: {exc}")
                self.enabled = False

    def complete_json(self, system: str, prompt: str) -> dict[str, Any] | None:
        if not self.enabled or self.client is None:
            return None
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                text={"format": {"type": "json_object"}},
            )
            return json.loads(response.output_text)
        except Exception as exc:  # pragma: no cover - network/API dependent.
            print(f"OpenAI request failed, falling back to deterministic agents: {exc}")
            return None


class RequirementAgent:
    name = "Requirement Agent"
    role = "Turn a natural language goal into testable requirements."

    def run(self, goal: str, llm: OptionalOpenAIClient) -> dict[str, Any]:
        system = "Return concise JSON requirements for a small Python module."
        prompt = f"Goal: {goal}"
        generated = llm.complete_json(system, prompt)
        if generated:
            return generated
        return {
            "goal": goal,
            "entities": [
                {
                    "name": "Lead",
                    "fields": ["id", "name", "email", "status", "notes"],
                }
            ],
            "statuses": ["new", "contacted", "qualified", "lost"],
            "capabilities": [
                "create a lead",
                "update lead status",
                "list leads by optional status",
                "summarize counts by status",
            ],
            "acceptance_criteria": [
                "each lead gets a stable sequential id",
                "invalid status values are rejected",
                "status summary always includes all configured statuses",
            ],
        }


class ArchitectureAgent:
    name = "Architecture Agent"
    role = "Design the smallest runnable module shape."

    def run(self, requirements: dict[str, Any], llm: OptionalOpenAIClient) -> dict[str, Any]:
        system = "Return concise JSON architecture for a small Python module."
        prompt = json.dumps(requirements, ensure_ascii=False)
        generated = llm.complete_json(system, prompt)
        if generated:
            return generated
        return {
            "language": "Python 3.10+",
            "module": "app.py",
            "tests": "test_app.py",
            "public_api": [
                "LeadStore.create_lead(name, email, notes='')",
                "LeadStore.update_status(lead_id, status)",
                "LeadStore.list_leads(status=None)",
                "LeadStore.summary()",
            ],
            "storage": "in-memory dictionary",
            "quality_gate": "python -m unittest discover",
        }


class TestDesignAgent:
    name = "Test Design Agent"
    role = "Create executable unit tests from requirements."

    def run(self, requirements: dict[str, Any], architecture: dict[str, Any]) -> str:
        statuses = requirements["statuses"]
        return f'''import unittest

from app import LeadStore


class LeadStoreTest(unittest.TestCase):
    def test_create_and_list_leads(self):
        store = LeadStore()
        lead = store.create_lead("Ada", "ada@example.com", notes="first contact")

        self.assertEqual(lead["id"], 1)
        self.assertEqual(lead["name"], "Ada")
        self.assertEqual(store.list_leads(), [lead])
        self.assertEqual(store.list_leads(status="new"), [lead])

    def test_update_status(self):
        store = LeadStore()
        lead = store.create_lead("Lin", "lin@example.com")

        updated = store.update_status(lead["id"], "qualified")

        self.assertEqual(updated["status"], "qualified")
        self.assertEqual(store.list_leads(status="qualified"), [updated])

    def test_rejects_invalid_status(self):
        store = LeadStore()
        lead = store.create_lead("Grace", "grace@example.com")

        with self.assertRaises(ValueError):
            store.update_status(lead["id"], "archived")

    def test_summary_includes_all_statuses(self):
        store = LeadStore()
        first = store.create_lead("Nora", "nora@example.com")
        second = store.create_lead("Kai", "kai@example.com")
        store.update_status(first["id"], "contacted")
        store.update_status(second["id"], "lost")

        self.assertEqual(
            store.summary(),
            {dict.fromkeys(statuses, 0) | {"contacted": 1, "lost": 1}},
        )


if __name__ == "__main__":
    unittest.main()
'''


class CodeAgent:
    name = "Code Agent"
    role = "Generate the application module."

    def run(self, seed_bug: bool) -> str:
        status_assignment = '"state": "new",' if seed_bug else '"status": "new",'
        return f'''class LeadStore:
    STATUSES = ("new", "contacted", "qualified", "lost")

    def __init__(self):
        self._next_id = 1
        self._leads = {{}}

    def create_lead(self, name, email, notes=""):
        if not name:
            raise ValueError("name is required")
        if not email:
            raise ValueError("email is required")
        lead = {{
            "id": self._next_id,
            "name": name,
            "email": email,
            {status_assignment}
            "notes": notes,
        }}
        self._leads[self._next_id] = lead
        self._next_id += 1
        return dict(lead)

    def update_status(self, lead_id, status):
        if status not in self.STATUSES:
            raise ValueError(f"invalid status: {{status}}")
        if lead_id not in self._leads:
            raise KeyError(f"unknown lead id: {{lead_id}}")
        self._leads[lead_id]["status"] = status
        return dict(self._leads[lead_id])

    def list_leads(self, status=None):
        if status is not None and status not in self.STATUSES:
            raise ValueError(f"invalid status: {{status}}")
        leads = [dict(lead) for lead in self._leads.values()]
        if status is None:
            return leads
        return [lead for lead in leads if lead["status"] == status]

    def summary(self):
        counts = {{status: 0 for status in self.STATUSES}}
        for lead in self._leads.values():
            counts[lead["status"]] += 1
        return counts
'''


class EvaluationAgent:
    name = "Evaluation Agent"
    role = "Run tests and capture pass/fail evidence."

    def run(self, build_dir: Path) -> dict[str, Any]:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover"],
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        output = "\n".join(part for part in [result.stdout, result.stderr] if part)
        return {
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "command": f"{sys.executable} -m unittest discover",
            "output": output,
        }


class RepairAgent:
    name = "Repair Agent"
    role = "Patch the generated code based on failing test evidence."

    def run(self, app_path: Path, eval_result: dict[str, Any]) -> dict[str, Any]:
        source = app_path.read_text(encoding="utf-8")
        patches: list[str] = []
        if '"state": "new"' in source and "KeyError: 'status'" in eval_result["output"]:
            source = source.replace('"state": "new"', '"status": "new"')
            patches.append("Renamed lead field from state to status.")
        if not patches:
            patches.append("No deterministic patch matched the failure output.")
        app_path.write_text(source, encoding="utf-8")
        return {"patches": patches, "app_path": str(app_path)}


def build_summary(report: dict[str, Any]) -> str:
    final_eval = report["evaluations"][-1]
    status = "PASSED" if final_eval["passed"] else "FAILED"
    repair_count = len(report["repairs"])
    if repair_count:
        outcome = (
            "This run created a customer lead management module, executed unit tests, "
            "detected a seeded field-name defect, repaired it, and produced an "
            "auditable report of the full loop."
        )
    else:
        outcome = (
            "This run created a customer lead management module, executed unit tests, "
            "passed the quality gate without repair, and produced an auditable report "
            "of the full loop."
        )
    events = report["memory"]["events"]
    agent_lines = "\n".join(
        f"- {event['name']}: {event['total_tokens']} rough tokens" for event in events
    )
    return f"""# Agent Build Summary

Final status: **{status}**

Goal:

{report["goal"]}

Agents executed:

{agent_lines}

Generated artifact:

- `.agent_build/app.py`
- `.agent_build/test_app.py`
- `.agent_build/report.json`

Concrete outcome:

{outcome}
"""


def run_pipeline(args: argparse.Namespace) -> int:
    build_dir = Path(args.output)
    if args.clean and build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    memory = AgentMemory()
    llm = OptionalOpenAIClient(args.use_openai, args.model)

    req_agent = RequirementAgent()
    requirements = memory.record(
        req_agent.name,
        req_agent.role,
        args.goal,
        req_agent.run(args.goal, llm),
    )
    write_json(build_dir / "01_requirements.json", requirements)

    arch_agent = ArchitectureAgent()
    architecture = memory.record(
        arch_agent.name,
        arch_agent.role,
        json.dumps(requirements, ensure_ascii=False),
        arch_agent.run(requirements, llm),
    )
    write_json(build_dir / "02_architecture.json", architecture)

    test_agent = TestDesignAgent()
    tests = memory.record(
        test_agent.name,
        test_agent.role,
        json.dumps({"requirements": requirements, "architecture": architecture}, ensure_ascii=False),
        test_agent.run(requirements, architecture),
    )
    (build_dir / "test_app.py").write_text(tests, encoding="utf-8")

    code_agent = CodeAgent()
    code = memory.record(
        code_agent.name,
        code_agent.role,
        json.dumps(architecture, ensure_ascii=False),
        code_agent.run(seed_bug=not args.no_seed_bug),
    )
    app_path = build_dir / "app.py"
    app_path.write_text(code, encoding="utf-8")

    evaluator = EvaluationAgent()
    repairer = RepairAgent()
    evaluations: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []

    for round_index in range(1, args.max_rounds + 1):
        eval_result = memory.record(
            evaluator.name,
            evaluator.role,
            f"round={round_index}",
            evaluator.run(build_dir),
        )
        evaluations.append(eval_result)
        (build_dir / "latest_eval.txt").write_text(eval_result["output"], encoding="utf-8")
        if eval_result["passed"]:
            break
        repair_result = memory.record(
            repairer.name,
            repairer.role,
            eval_result["output"],
            repairer.run(app_path, eval_result),
        )
        repairs.append(repair_result)
        (build_dir / f"repair_round_{round_index}.md").write_text(
            "\n".join(f"- {patch}" for patch in repair_result["patches"]),
            encoding="utf-8",
        )

    report = {
        "goal": args.goal,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "openai_enabled": llm.enabled,
        "build_dir": str(build_dir),
        "evaluations": evaluations,
        "repairs": repairs,
        "memory": memory.as_dict(),
    }
    write_json(build_dir / "report.json", report)
    (build_dir / "summary.md").write_text(build_summary(report), encoding="utf-8")

    print((build_dir / "summary.md").read_text(encoding="utf-8"))
    return 0 if evaluations[-1]["passed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a small evaluation-driven multi-agent self-repair demo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python self_repair_agents.py --clean
              python self_repair_agents.py --clean --no-seed-bug
              python self_repair_agents.py --clean --use-openai --model gpt-5.5
            """
        ),
    )
    parser.add_argument("--goal", default=DEFAULT_GOAL, help="Natural language build goal.")
    parser.add_argument("--output", default=".agent_build", help="Directory for generated artifacts.")
    parser.add_argument("--clean", action="store_true", help="Delete the output directory before running.")
    parser.add_argument("--no-seed-bug", action="store_true", help="Do not inject the first-round demo bug.")
    parser.add_argument("--max-rounds", type=int, default=3, help="Maximum evaluate/repair rounds.")
    parser.add_argument("--use-openai", action="store_true", help="Use OpenAI SDK for planning when available.")
    parser.add_argument("--model", default="gpt-5.5", help="OpenAI model name for --use-openai.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run_pipeline(parse_args()))
