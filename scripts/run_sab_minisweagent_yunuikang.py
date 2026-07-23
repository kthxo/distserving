#!/usr/bin/env python3
"""ScienceAgentBench batch runner on mini-swe-agent (P2 / yunuikang, isolated).

WHY mini-swe-agent and not OpenHands: the paper's Science point uses the OpenHands
CodeAct scaffold, but the OpenHands runtime-image build on this host is blocked by an
upstream poetry/uv mismatch (see P2 log C-4 issue 3). mini-swe-agent is the scaffold
already proven on this server for the P1 SWE recording.

METHODOLOGICAL FRAMING (recorded honestly in the P2 log): unifying the scaffold with
the SWE point isolates the *workload* effect on the fit x d regime map; it is NOT a
faithful reproduction of the paper's OpenHands-on-Science configuration.

Modeled on minisweagent/run/extra/swebench.py but written as a standalone script —
the mini-swe-agent package itself is NOT modified.

Dataset access: SAB data is bind-mounted read-only into the sandbox at /benchmark
(upstream OpenHands copies it in instead; a read-only mount is equivalent for the
agent and avoids a multi-GB copy per task).
"""

import concurrent.futures
import json
import os
import threading
import time
import traceback
from pathlib import Path

import pandas as pd
import typer
import yaml
from rich.live import Live

from minisweagent.agents.default import DefaultAgent
from minisweagent.environments import get_environment
from minisweagent.models import get_model
from minisweagent.run.extra.swebench import release_router_program
from minisweagent.run.extra.utils.batch_progress import RunBatchProgressManager
from minisweagent.run.utils.save import save_traj
from minisweagent.utils.log import add_file_handler, logger

app = typer.Typer(rich_markup_mode="rich", add_completion=False)

DEFAULT_PARQUET = (
    "/home/yunuikang/.cache/huggingface/hub/datasets--osunlp--ScienceAgentBench/"
    "snapshots/9c6e96c9e74572e979b0930ee735041cef528cb7/data/"
    "verified-00000-of-00001.parquet"
)
DEFAULT_BENCHMARK = "/home/yunuikang/yunuikang_work/distserving/scratch/sab/benchmark"
SAB_IMAGE = "docker.io/xingyaoww/openhands-eval-scienceagentbench"

_OUTPUT_FILE_LOCK = threading.Lock()


class ProgressTrackingAgent(DefaultAgent):
    """DefaultAgent + progress updates (mirrors swebench.py)."""

    def __init__(self, *args, progress_manager: RunBatchProgressManager, instance_id: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.progress_manager = progress_manager
        self.instance_id = instance_id

    def step(self) -> dict:
        self.progress_manager.update_instance_status(
            self.instance_id, f"Step {self.model.n_calls + 1:3d} (${self.model.cost:.2f})"
        )
        return super().step()


def load_tasks(parquet: str) -> pd.DataFrame:
    df = pd.read_parquet(parquet)
    df["instance_id"] = df["instance_id"].astype(str)
    df["dataset_root"] = df["dataset_folder_tree"].map(lambda t: str(t).split("\n")[0][4:].rstrip("/"))
    df["pred_program_name"] = "pred_" + df["gold_program_name"].astype(str)
    return df


def build_task_text(row: pd.Series, use_knowledge: bool) -> str:
    """SAB instruction, ported from the upstream OpenHands SAB harness template."""
    task_inst = str(row["task_inst"])
    if use_knowledge and pd.notna(row.get("domain_knowledge")):
        task_inst += "\n" + str(row["domain_knowledge"])
    return f"""You are an expert Python programming assistant that helps scientist users to write high-quality code to solve their tasks.
Given a user request, you are expected to write a complete program that accomplishes the requested task and save any outputs to `/workspace/pred_results/` in the correct format.

Here's the user request you need to work on:
{task_inst}

You can access the dataset at `/benchmark/datasets/{row["dataset_root"]}/`. Here is the directory structure of the dataset:
```
{row["dataset_folder_tree"]}
```
Here are some helpful previews for the dataset file(s):
{row["dataset_preview"]}

Please save your program as `/workspace/pred_programs/{row["pred_program_name"]}`.
Then, please run the program to check and fix any errors.
Please do NOT run the program in the background.
If the program uses some packages that are incompatible, please figure out alternative implementations and do NOT restart the environment.
"""


def get_sab_environment(config: dict, benchmark_dir: str):
    """Docker env on the SAB sandbox image with the benchmark bind-mounted read-only."""
    env_config = config.setdefault("environment", {})
    env_config["environment_class"] = env_config.get("environment_class", "docker")
    env_config["image"] = env_config.get("image", SAB_IMAGE)
    run_args = list(env_config.get("run_args", ["--rm"]))
    mount = f"{benchmark_dir}/datasets:/benchmark/datasets:ro"
    if mount not in run_args:
        run_args += ["-v", mount]
    env_config["run_args"] = run_args
    return get_environment(env_config)


def update_preds_file(output_path: Path, instance_id: str, model_name: str, result: str):
    with _OUTPUT_FILE_LOCK:
        data = json.loads(output_path.read_text()) if output_path.exists() else {}
        data[instance_id] = {
            "model_name_or_path": model_name,
            "instance_id": instance_id,
            "model_patch": result,
        }
        output_path.write_text(json.dumps(data, indent=2))


def process_instance(
    row: pd.Series,
    output_dir: Path,
    config: dict,
    progress_manager: RunBatchProgressManager,
    benchmark_dir: str,
    instance_number: int,
    use_knowledge: bool,
) -> None:
    instance_id = str(row["instance_id"])
    instance_dir = output_dir / instance_id
    instance_dir.mkdir(parents=True, exist_ok=True)

    # vLLM/ThunderAgent wiring: job_id -> extra_body.program_id (models/vllm_model.py:131)
    model_config = config.get("model", {}).copy()
    if "vllm" in str(model_config.get("model_class", "")).lower():
        model_config["job_id"] = instance_number
        model_config["step_limit"] = config.get("agent", {}).get("step_limit", 0)
    model = get_model(config=model_config)

    task = build_task_text(row, use_knowledge)

    progress_manager.on_instance_start(instance_id)
    progress_manager.update_instance_status(instance_id, "Starting docker")

    agent = None
    env = None
    extra_info = None
    env_prepare_timing = None
    try:
        t0 = time.time()
        try:
            env = get_sab_environment(config, benchmark_dir)
            # SAB workspace dirs the instruction refers to
            env.execute("mkdir -p /workspace/pred_programs /workspace/pred_results")
        finally:
            env_prepare_timing = {"start_ts": t0, "end_ts": time.time(), "total_s": time.time() - t0}

        agent = ProgressTrackingAgent(
            model, env, progress_manager=progress_manager,
            instance_id=instance_id, **config.get("agent", {}),
        )
        exit_status, result = agent.run(task)
    except Exception as e:
        logger.error(f"Error processing instance {instance_id}: {e}", exc_info=True)
        exit_status, result = type(e).__name__, str(e)
        extra_info = {"traceback": traceback.format_exc()}
    finally:
        try:
            (instance_dir / f"{instance_id}.timings.json").write_text(
                json.dumps(
                    {
                        "instance_id": instance_id,
                        "env_prepare": env_prepare_timing,
                        "steps": getattr(agent, "step_timings", []) if agent else [],
                    },
                    indent=2,
                )
            )
        except Exception as exc:
            logger.warning(f"Failed to write timings for {instance_id}: {exc}")

        save_traj(
            agent, instance_dir / f"{instance_id}.traj.json",
            exit_status=exit_status, result=result, extra_info=extra_info,
            instance_id=instance_id, print_fct=logger.info,
        )
        update_preds_file(output_dir / "preds.json", instance_id, model.config.model_name, result)
        release_router_program(str(instance_number), model)
        if env and hasattr(env, "cleanup"):
            try:
                env.cleanup()
            except Exception as exc:
                logger.warning(f"Cleanup failed for {instance_id}: {exc}")
        progress_manager.on_instance_end(instance_id, exit_status)


@app.command(help="Run mini-swe-agent on ScienceAgentBench tasks.")
def main(
    config_path: str = typer.Option(..., "-c", "--config", help="mini-swe config yaml"),
    output: str = typer.Option(..., "-o", "--output", help="output directory"),
    parquet: str = typer.Option(DEFAULT_PARQUET, "--parquet"),
    benchmark_dir: str = typer.Option(DEFAULT_BENCHMARK, "--benchmark-dir"),
    workers: int = typer.Option(1, "-w", "--workers"),
    limit: int = typer.Option(0, "-n", "--limit", help="0 = all"),
    task_ids: str = typer.Option("", "--task-ids", help="comma-separated instance_ids"),
    use_knowledge: bool = typer.Option(True, "--use-knowledge/--no-use-knowledge"),
) -> None:
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    add_file_handler(output_dir / "run.log")

    config = yaml.safe_load(Path(config_path).read_text())
    df = load_tasks(parquet)
    if task_ids:
        wanted = [t.strip() for t in task_ids.split(",") if t.strip()]
        df = df[df["instance_id"].isin(wanted)]
    if limit > 0:
        df = df.head(limit)

    logger.info(f"Running {len(df)} SAB tasks | workers={workers} | image={SAB_IMAGE}")
    progress_manager = RunBatchProgressManager(len(df), output_dir / f"exit_statuses_{time.time()}.yaml")

    def _run(idx_row):
        i, (_, row) = idx_row
        # instance_number starts at 1 so job_id > 0 (vllm_model.py:131 treats 0 as fallback)
        process_instance(row, output_dir, config, progress_manager, benchmark_dir, i + 1, use_knowledge)

    with Live(progress_manager.render_group, refresh_per_second=4):
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_run, ir) for ir in enumerate(df.iterrows())]
            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    logger.error(f"worker failed: {e}", exc_info=True)


if __name__ == "__main__":
    app()
