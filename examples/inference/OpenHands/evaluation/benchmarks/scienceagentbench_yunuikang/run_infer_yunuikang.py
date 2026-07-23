"""ScienceAgentBench inference harness — P2 isolated port (yunuikang).

Ported from upstream OpenHands @ tag 1.2.1
  evaluation/benchmarks/scienceagentbench/run_infer.py  (280 lines)
with two local adaptations and the ThunderAgent program-id glue grafted in:

  (1) LOCAL_DATASET_PATH -> scratch/sab/benchmark (data shipped out-of-tree)
  (2) offline dataset load from the cached HF parquet (split name is 'verified',
      not upstream's 'validation')
  (3) ThunderAgent glue lifted verbatim from
      evaluation/benchmarks/swe_bench/run_infer.py:618-655,754-758
      (program_id prefix 'swe-' -> 'sab-')

Guardrails: scheduler/router.py and the existing swe_bench/ harness are NOT modified.
This file and its package dir are new and suffixed *_yunuikang.
"""

import asyncio
import hashlib
import json
import os
import urllib.request
from typing import Any

import pandas as pd
from tqdm import tqdm

from evaluation.utils.shared import (
    EvalMetadata,
    EvalOutput,
    codeact_user_response,
    compatibility_for_eval_history_pairs,
    get_default_sandbox_config_for_eval,
    get_metrics,
    get_openhands_config_for_eval,
    make_metadata,
    prepare_dataset,
    reset_logger_for_multiprocessing,
    run_evaluation,
    update_llm_config_for_completions_logging,
)
from openhands.controller.state.state import State
from openhands.core.config import (
    OpenHandsConfig,
    get_evaluation_parser,
    get_llm_config_arg,
)
from openhands.core.logger import openhands_logger as logger
from openhands.core.main import create_runtime, run_controller
from openhands.events.action import CmdRunAction, MessageAction
from openhands.events.observation import CmdOutputObservation
from openhands.runtime.base import Runtime
from openhands.utils.async_utils import call_async_from_sync

AGENT_CLS_TO_FAKE_USER_RESPONSE_FN = {
    'CodeActAgent': codeact_user_response,
}

# (1) local adaptation: benchmark data lives out-of-tree under scratch/
LOCAL_DATASET_PATH = os.environ.get(
    'SAB_BENCHMARK_PATH',
    '/home/yunuikang/yunuikang_work/distserving/scratch/sab/benchmark',
)
# (2) local adaptation: cached HF parquet (split 'verified')
LOCAL_PARQUET_PATH = os.environ.get(
    'SAB_PARQUET_PATH',
    '/home/yunuikang/.cache/huggingface/hub/datasets--osunlp--ScienceAgentBench/'
    'snapshots/9c6e96c9e74572e979b0930ee735041cef528cb7/data/'
    'verified-00000-of-00001.parquet',
)


def load_sab_dataset() -> pd.DataFrame:
    """Offline load of the SAB task table.

    Upstream calls load_dataset('osunlp/ScienceAgentBench', split='validation').
    The locally cached snapshot exposes the split as 'verified', so we read the
    parquet directly to stay offline and reproducible.
    """
    if os.path.exists(LOCAL_PARQUET_PATH):
        df = pd.read_parquet(LOCAL_PARQUET_PATH)
        logger.info(f'Loaded SAB tasks from local parquet: {len(df)} rows')
        return df
    from datasets import load_dataset  # fallback: network

    logger.warning('Local parquet missing; falling back to hub load_dataset')
    return load_dataset('osunlp/ScienceAgentBench', split='validation').to_pandas()


def format_task_dict(example, use_knowledge):
    task = {
        'instance_id': example['instance_id'],
        'task_inst': example['task_inst'],
        'dataset_path': '/benchmark/datasets/'
        + example['dataset_folder_tree'].split('\n')[0][4:],
        'dataset_folder_tree': example['dataset_folder_tree'],
        'dataset_preview': example['dataset_preview'],
        'pred_program_name': 'pred_' + example['gold_program_name'],
    }

    if use_knowledge:
        task['task_inst'] += '\n' + str(example['domain_knowledge'])

    return task


def get_config(
    metadata: EvalMetadata,
    instance_id: str,
) -> OpenHandsConfig:
    sandbox_config = get_default_sandbox_config_for_eval()
    sandbox_config.base_container_image = (
        'docker.io/xingyaoww/openhands-eval-scienceagentbench'
    )
    config = get_openhands_config_for_eval(
        metadata=metadata,
        runtime=os.environ.get('RUNTIME', 'docker'),
        sandbox_config=sandbox_config,
    )
    config.set_llm_config(
        update_llm_config_for_completions_logging(
            metadata.llm_config,
            metadata.eval_output_dir,
            instance_id,
        )
    )
    return config


def initialize_runtime(
    runtime: Runtime,
    instance: pd.Series,
):
    """Initialize the runtime for the agent (workspace dirs + dataset copy)."""
    logger.info(f'{"-" * 50} BEGIN Runtime Initialization Fn {"-" * 50}')
    obs: CmdOutputObservation

    action = CmdRunAction(command='mkdir -p /workspace/pred_programs')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    assert obs.exit_code == 0

    action = CmdRunAction(command='mkdir -p /workspace/pred_results')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    assert obs.exit_code == 0

    dataset_name = instance['dataset_folder_tree'].split('\n')[0][4:].rstrip('/')

    dataset_dir = os.path.join(LOCAL_DATASET_PATH, 'datasets', dataset_name)
    runtime.copy_to(dataset_dir, '/workspace/benchmark/datasets', recursive=True)

    action = CmdRunAction(command='cd /workspace/benchmark/datasets && ls')
    obs = runtime.run_action(action)
    logger.info(obs, extra={'msg_type': 'OBSERVATION'})
    assert obs.exit_code == 0
    assert dataset_name in obs.content

    logger.info(f'{"-" * 50} END Runtime Initialization Fn {"-" * 50}')


def complete_runtime(
    runtime: Runtime,
    instance: pd.Series,
) -> dict[str, Any]:
    """Recover the predicted program from the sandbox after the agent finishes."""
    logger.info(f'{"-" * 50} BEGIN Runtime Completion Fn {"-" * 50}')
    obs: CmdOutputObservation

    action = CmdRunAction(command='cd /workspace')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    assert obs.exit_code == 0

    action = CmdRunAction(command=f'cat pred_programs/{instance.pred_program_name}')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)

    if obs.exit_code == 0:
        test_result = {'program': obs.content}
    else:
        test_result = {'program': 'ERROR'}

    logger.info(f'{"-" * 50} END Runtime Completion Fn {"-" * 50}')
    return test_result


def process_instance(
    instance: pd.Series,
    metadata: EvalMetadata,
    reset_logger: bool = True,
) -> EvalOutput:
    # ---- ThunderAgent glue (from swe_bench/run_infer.py:618-655) ----
    def _make_thunderagent_program_id(instance_id: str) -> str:
        digest = hashlib.sha1(f'{instance_id}:{os.getpid()}'.encode('utf-8')).hexdigest()
        return f'sab-{digest[:16]}'

    def _release_thunderagent_program(base_url: str | None, program_id: str) -> None:
        if not base_url:
            return
        url = base_url.rstrip('/')
        if url.endswith('/v1'):
            url = url[:-3]
        release_url = f'{url}/programs/release'
        try:
            req = urllib.request.Request(
                release_url,
                data=json.dumps({'program_id': program_id}).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as exc:
            logger.warning(
                f'ThunderAgent program release failed for {program_id}: {exc}'
            )

    program_id = _make_thunderagent_program_id(str(instance.instance_id))
    prev_program_id = os.environ.get('OPENHANDS_PROGRAM_ID')
    os.environ['OPENHANDS_PROGRAM_ID'] = program_id
    # ---------------------------------------------------------------

    try:
        instance_id = instance.instance_id.replace('/', '__')
        config = get_config(metadata, instance_id)

        if reset_logger:
            log_dir = os.path.join(metadata.eval_output_dir, 'infer_logs')
            reset_logger_for_multiprocessing(logger, instance_id, log_dir)
        else:
            logger.info(f'Starting evaluation for instance {instance_id}.')

        instruction = f"""You are an expert Python programming assistant that helps scientist users to write high-quality code to solve their tasks.
Given a user request, you are expected to write a complete program that accomplishes the requested task and save any outputs to `/workspace/pred_results/` in the correct format.

Here's the user request you need to work on:
{instance.task_inst}

You can access the dataset at `{instance.dataset_path}`. Here is the directory structure of the dataset:
```
{instance.dataset_folder_tree}
```
Here are some helpful previews for the dataset file(s):
{instance.dataset_preview}

Please save your program as `/workspace/pred_programs/{instance.pred_program_name}`.
Then, please run the program to check and fix any errors.
Please do NOT run the program in the background.
If the program uses some packages that are incompatible, please figure out alternative implementations and do NOT restart the environment.

"""

        runtime = create_runtime(config)
        call_async_from_sync(runtime.connect)
        initialize_runtime(runtime, instance)

        state: State | None = asyncio.run(
            run_controller(
                config=config,
                initial_user_action=MessageAction(content=instruction),
                runtime=runtime,
                fake_user_response_fn=AGENT_CLS_TO_FAKE_USER_RESPONSE_FN.get(
                    metadata.agent_class
                ),
            )
        )

        test_result = complete_runtime(runtime, instance)

        if state is None:
            raise ValueError('State should not be None.')
        metrics = get_metrics(state)
        histories = compatibility_for_eval_history_pairs(state.history)

        output = EvalOutput(
            instance_id=instance.instance_id,
            instruction=instruction,
            metadata=metadata,
            history=histories,
            metrics=metrics,
            error=state.last_error if state and state.last_error else None,
            test_result=test_result,
        )
        return output
    finally:
        # ---- ThunderAgent glue (from swe_bench/run_infer.py:754-758) ----
        _release_thunderagent_program(metadata.llm_config.base_url, program_id)
        if prev_program_id is None:
            os.environ.pop('OPENHANDS_PROGRAM_ID', None)
        else:
            os.environ['OPENHANDS_PROGRAM_ID'] = prev_program_id


if __name__ == '__main__':
    parser = get_evaluation_parser()
    parser.add_argument(
        '--use-knowledge',
        type=str,
        default='false',
        choices=['true', 'false'],
        help='use expert-provided knowledge or not',
    )
    args, _ = parser.parse_known_args()

    sab_dataset = load_sab_dataset()

    dataset_processed = []
    for _, example in tqdm(sab_dataset.iterrows(), total=len(sab_dataset)):
        dataset_processed.append(format_task_dict(example, args.use_knowledge == 'true'))

    dataset = pd.DataFrame(dataset_processed)

    llm_config = None
    if args.llm_config:
        # (4) local fix: upstream drops args.config_file here, so --config-file was
        # silently ignored and the lookup returned None. swe_bench/run_infer.py:849
        # passes it; match that.
        llm_config = get_llm_config_arg(args.llm_config, args.config_file)
        # modify_params must be False for evaluation purpose (reproducibility)
        llm_config.modify_params = False
    if llm_config is None:
        raise ValueError(f'Could not find LLM config: --llm_config {args.llm_config}')

    metadata = make_metadata(
        llm_config,
        'ScienceAgentBench',
        args.agent_cls,
        args.max_iterations,
        args.eval_note,
        args.eval_output_dir,
    )
    output_file = os.path.join(metadata.eval_output_dir, 'output.jsonl')
    dataset['instance_id'] = dataset['instance_id'].apply(str)
    instances = prepare_dataset(dataset, output_file, args.eval_n_limit)

    run_evaluation(
        instances, metadata, output_file, args.eval_num_workers, process_instance
    )
