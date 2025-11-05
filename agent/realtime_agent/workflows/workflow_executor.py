"""
Workflow Executor - Manages workflow execution with routing, logging, and error handling

Features:
- Sequential and parallel stage execution
- Conditional routing based on stage outputs
- Automatic retry with exponential backoff
- Comprehensive logging at each stage
- State persistence
- Error recovery
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Awaitable
from pathlib import Path

from .workflow_state import WorkflowState, WorkflowStatus, StageStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """
    Executes workflows with state management, logging, and error handling

    Example usage:
        executor = WorkflowExecutor(
            workflow_name="news_processing",
            log_dir="./data/workflows"
        )

        executor.add_stage("screen", screen_news_func)
        executor.add_stage("filter", filter_news_func)
        executor.add_stage("sentiment", analyze_sentiment_func)
        executor.add_stage("impact", assess_impact_func)
        executor.add_stage("decision", make_decision_func)

        result = await executor.execute(input_data={"event": event})
    """

    def __init__(
        self,
        workflow_name: str,
        log_dir: str = "./data/workflows",
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize workflow executor

        Args:
            workflow_name: Name of the workflow
            log_dir: Directory for workflow logs
            max_retries: Maximum retries per stage
            retry_delay: Base delay for exponential backoff (seconds)
        """
        self.workflow_name = workflow_name
        self.log_dir = Path(log_dir)
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Workflow definition
        self.stages: List[Dict[str, Any]] = []

        # Routing rules
        self.routing_rules: Dict[str, Callable] = {}

        # Hooks (pre/post stage execution)
        self.pre_stage_hooks: Dict[str, List[Callable]] = {}
        self.post_stage_hooks: Dict[str, List[Callable]] = {}

    def add_stage(
        self,
        name: str,
        handler: Callable[[WorkflowState, Any], Awaitable[Any]],
        condition: Optional[Callable[[WorkflowState], bool]] = None,
        parallel_with: Optional[List[str]] = None
    ):
        """
        Add a stage to the workflow

        Args:
            name: Stage name
            handler: Async function to execute (receives state and input, returns output)
            condition: Optional condition function (if False, stage is skipped)
            parallel_with: List of stage names to execute in parallel with
        """
        self.stages.append({
            'name': name,
            'handler': handler,
            'condition': condition,
            'parallel_with': parallel_with or []
        })

    def add_routing_rule(self, from_stage: str, condition_func: Callable[[Any], str]):
        """
        Add conditional routing rule

        Args:
            from_stage: Stage to route from
            condition_func: Function that takes stage output and returns next stage name
        """
        self.routing_rules[from_stage] = condition_func

    def add_pre_hook(self, stage_name: str, hook: Callable[[WorkflowState], Awaitable[None]]):
        """Add hook to run before stage"""
        if stage_name not in self.pre_stage_hooks:
            self.pre_stage_hooks[stage_name] = []
        self.pre_stage_hooks[stage_name].append(hook)

    def add_post_hook(self, stage_name: str, hook: Callable[[WorkflowState, Any], Awaitable[None]]):
        """Add hook to run after stage"""
        if stage_name not in self.post_stage_hooks:
            self.post_stage_hooks[stage_name] = []
        self.post_stage_hooks[stage_name].append(hook)

    async def _execute_stage(
        self,
        state: WorkflowState,
        stage: Dict[str, Any],
        stage_input: Any
    ) -> Any:
        """
        Execute a single stage with retries and error handling

        Args:
            state: Workflow state
            stage: Stage configuration
            stage_input: Input data for stage

        Returns:
            Stage output
        """
        stage_name = stage['name']
        handler = stage['handler']

        # Check condition
        if stage['condition'] and not stage['condition'](state):
            logger.info(f"⏭️  Skipping stage: {stage_name} (condition not met)")
            state.skip_stage(stage_name, "Condition not met")
            return None

        logger.info(f"🔄 Starting stage: {stage_name}")
        state.start_stage(stage_name)

        # Run pre-hooks
        if stage_name in self.pre_stage_hooks:
            for hook in self.pre_stage_hooks[stage_name]:
                await hook(state)

        # Execute with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                # Execute stage
                output = await handler(state, stage_input)

                # Success! Complete stage first to calculate duration
                state.complete_stage(stage_name, output)
                logger.info(f"✅ Completed stage: {stage_name} ({state.stage_results[stage_name].duration_seconds:.2f}s)")

                # Run post-hooks
                if stage_name in self.post_stage_hooks:
                    for hook in self.post_stage_hooks[stage_name]:
                        await hook(state, output)

                return output

            except Exception as e:
                last_error = str(e)
                logger.error(f"❌ Stage {stage_name} failed (attempt {attempt + 1}/{self.max_retries}): {e}")

                if attempt < self.max_retries - 1:
                    # Retry with exponential backoff
                    delay = self.retry_delay * (2 ** attempt)
                    logger.info(f"⏳ Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    # Final failure
                    state.fail_stage(stage_name, last_error, retry_count=attempt + 1)
                    raise

        return None

    async def _execute_parallel_stages(
        self,
        state: WorkflowState,
        stages: List[Dict[str, Any]],
        stage_input: Any
    ) -> Dict[str, Any]:
        """
        Execute multiple stages in parallel

        Args:
            state: Workflow state
            stages: List of stages to execute in parallel
            stage_input: Input data

        Returns:
            Dictionary of {stage_name: output}
        """
        logger.info(f"🔀 Executing {len(stages)} stages in parallel")

        # Execute all stages concurrently
        tasks = [
            self._execute_stage(state, stage, stage_input)
            for stage in stages
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Package results
        outputs = {}
        for stage, result in zip(stages, results):
            if isinstance(result, Exception):
                logger.error(f"❌ Parallel stage {stage['name']} failed: {result}")
                outputs[stage['name']] = None
            else:
                outputs[stage['name']] = result

        return outputs

    async def execute(
        self,
        input_data: Any,
        workflow_id: Optional[str] = None
    ) -> WorkflowState:
        """
        Execute the complete workflow

        Args:
            input_data: Input data for the workflow
            workflow_id: Optional workflow ID (generated if not provided)

        Returns:
            Final workflow state
        """
        # Create workflow state
        if workflow_id is None:
            workflow_id = f"{self.workflow_name}_{uuid.uuid4().hex[:8]}"

        state = WorkflowState(
            workflow_id=workflow_id,
            workflow_name=self.workflow_name,
            created_at=datetime.now().isoformat(),
            stages=[stage['name'] for stage in self.stages],
            input_data={'input': input_data}
        )

        logger.info(f"\n{'='*70}")
        logger.info(f"🚀 Starting workflow: {self.workflow_name} (ID: {workflow_id})")
        logger.info(f"   Stages: {len(self.stages)}")
        logger.info(f"{'='*70}\n")

        state.start_workflow()

        try:
            # Execute stages
            current_input = input_data
            i = 0

            while i < len(self.stages):
                stage = self.stages[i]

                # Check for parallel execution
                parallel_stages = [stage]
                if stage['parallel_with']:
                    for parallel_name in stage['parallel_with']:
                        parallel_stage = next(
                            (s for s in self.stages if s['name'] == parallel_name),
                            None
                        )
                        if parallel_stage:
                            parallel_stages.append(parallel_stage)

                # Execute (sequential or parallel)
                if len(parallel_stages) > 1:
                    # Parallel execution
                    outputs = await self._execute_parallel_stages(
                        state, parallel_stages, current_input
                    )
                    current_input = outputs
                    i += len(parallel_stages)
                else:
                    # Sequential execution
                    output = await self._execute_stage(state, stage, current_input)
                    current_input = output

                    # Check for conditional routing
                    if stage['name'] in self.routing_rules:
                        next_stage_name = self.routing_rules[stage['name']](output)
                        if next_stage_name:
                            # Find next stage index
                            next_index = next(
                                (idx for idx, s in enumerate(self.stages) if s['name'] == next_stage_name),
                                i + 1
                            )
                            i = next_index
                            logger.info(f"🔀 Routing to stage: {next_stage_name}")
                            continue

                    i += 1

            # Success!
            state.output_data = {'output': current_input}
            state.complete_workflow()

            logger.info(f"\n{'='*70}")
            logger.info(f"✅ Workflow completed: {self.workflow_name}")
            logger.info(f"   Duration: {state.total_duration_seconds:.2f}s")
            logger.info(f"   Stages: {len([r for r in state.stage_results.values() if r.status == StageStatus.COMPLETED])}/{len(self.stages)}")
            logger.info(f"{'='*70}\n")

        except Exception as e:
            logger.error(f"\n{'='*70}")
            logger.error(f"❌ Workflow failed: {self.workflow_name}")
            logger.error(f"   Error: {e}")
            logger.error(f"{'='*70}\n")

            state.fail_workflow(str(e))

        # Save state to file
        self._save_state(state)

        return state

    def _save_state(self, state: WorkflowState):
        """Save workflow state to log file"""
        log_file = self.log_dir / f"{state.workflow_id}.json"

        try:
            state.save(str(log_file))
            logger.info(f"💾 Saved workflow state: {log_file}")
        except Exception as e:
            logger.error(f"❌ Failed to save workflow state: {e}")

    def get_workflow_logs(self, limit: int = 10) -> List[WorkflowState]:
        """
        Get recent workflow logs

        Args:
            limit: Maximum number of logs to return

        Returns:
            List of workflow states
        """
        log_files = sorted(
            self.log_dir.glob(f"{self.workflow_name}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        states = []
        for log_file in log_files[:limit]:
            try:
                state = WorkflowState.load(str(log_file))
                states.append(state)
            except Exception as e:
                logger.error(f"Error loading {log_file}: {e}")

        return states


# Example usage
if __name__ == "__main__":
    async def test_workflow():
        logger.info("Testing Workflow Executor")

        # Define stage handlers
        async def stage1(state: WorkflowState, input_data: Any) -> Any:
            await asyncio.sleep(0.5)
            return {"stage1": "output", "value": input_data.get("value", 0) + 1}

        async def stage2(state: WorkflowState, input_data: Any) -> Any:
            await asyncio.sleep(0.3)
            return {"stage2": "output", "value": input_data.get("value", 0) + 2}

        async def stage3(state: WorkflowState, input_data: Any) -> Any:
            await asyncio.sleep(0.4)
            return {"stage3": "output", "value": input_data.get("value", 0) + 3}

        # Create executor
        executor = WorkflowExecutor(workflow_name="test_workflow")

        # Add stages
        executor.add_stage("stage1", stage1)
        executor.add_stage("stage2", stage2)
        executor.add_stage("stage3", stage3)

        # Execute
        input_data = {"value": 0}
        state = await executor.execute(input_data)

        # Print summary
        print("\n" + "="*70)
        print("WORKFLOW SUMMARY")
        print("="*70)
        print(state.to_json())

    asyncio.run(test_workflow())
