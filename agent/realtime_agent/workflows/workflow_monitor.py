"""
Workflow Monitor - Visualization and monitoring for workflow execution

Features:
- ASCII visualization of workflow progress
- Real-time status updates
- Performance metrics
- Error tracking
- Historical analysis
"""

from typing import List, Dict, Optional
from pathlib import Path
import json

from .workflow_state import WorkflowState, WorkflowStatus, StageStatus


class WorkflowMonitor:
    """
    Monitor and visualize workflow execution

    Usage:
        monitor = WorkflowMonitor()
        monitor.print_workflow(state)
        monitor.print_summary(state)
        monitor.analyze_workflow_logs("./data/workflows")
    """

    @staticmethod
    def print_workflow(state: WorkflowState):
        """
        Print ASCII visualization of workflow

        Example output:
            News Processing Workflow (news_processing_abc123)
            ════════════════════════════════════════════════

            ✅ screen     [COMPLETED]  1.2s  duplicate
            ⏭️ filter     [SKIPPED]    0.0s  Condition not met
            ⏭️ sentiment  [SKIPPED]    0.0s  Condition not met
            ⏭️ impact     [SKIPPED]    0.0s  Condition not met
            ⏭️ decision   [SKIPPED]    0.0s  Condition not met

            Status: COMPLETED
            Duration: 1.2s
            Progress: 100%
        """
        print(f"\n{state.workflow_name.title()} ({state.workflow_id})")
        print("=" * 60)

        # Print each stage
        for stage_name in state.stages:
            if stage_name not in state.stage_results:
                # Not started yet
                icon = "⏸️"
                status_str = "[PENDING]"
                duration_str = "-"
                extra = ""
            else:
                result = state.stage_results[stage_name]

                # Status icon
                if result.status == StageStatus.COMPLETED:
                    icon = "✅"
                elif result.status == StageStatus.FAILED:
                    icon = "❌"
                elif result.status == StageStatus.SKIPPED:
                    icon = "⏭️"
                elif result.status == StageStatus.RUNNING:
                    icon = "🔄"
                else:
                    icon = "⏸️"

                status_str = f"[{result.status.value.upper()}]"
                duration_str = f"{result.duration_seconds:.1f}s" if result.duration_seconds else "-"

                # Extra info
                extra = ""
                if result.status == StageStatus.FAILED:
                    extra = f"  {result.error[:40]}..."
                elif result.status == StageStatus.SKIPPED:
                    extra = f"  {result.metadata.get('skip_reason', '')[:40]}"
                elif state.metadata.get(f'{stage_name}_info'):
                    extra = f"  {state.metadata[f'{stage_name}_info']}"

            print(f"{icon} {stage_name:12s} {status_str:12s}  {duration_str:6s} {extra}")

        print()
        print(f"Status: {state.status.value.upper()}")
        print(f"Duration: {state.total_duration_seconds:.1f}s" if state.total_duration_seconds else "Duration: -")
        print(f"Progress: {state.get_progress() * 100:.0f}%")

        if state.errors:
            print(f"\nErrors: {len(state.errors)}")
            for error in state.errors:
                print(f"  - {error[:60]}...")

    @staticmethod
    def print_summary(state: WorkflowState):
        """Print workflow summary"""
        summary = state.get_summary()

        print(f"\n{'='*60}")
        print("WORKFLOW SUMMARY")
        print(f"{'='*60}")

        for key, value in summary.items():
            if isinstance(value, list):
                print(f"{key}:")
                for item in value:
                    print(f"  - {item}")
            else:
                print(f"{key}: {value}")

    @staticmethod
    def print_metadata(state: WorkflowState):
        """Print workflow metadata"""
        if not state.metadata:
            return

        print(f"\n{'='*60}")
        print("WORKFLOW METADATA")
        print(f"{'='*60}")

        for key, value in state.metadata.items():
            print(f"{key}: {value}")

    @staticmethod
    def print_stage_details(state: WorkflowState, stage_name: str):
        """Print detailed information about a specific stage"""
        if stage_name not in state.stage_results:
            print(f"Stage '{stage_name}' not found")
            return

        result = state.stage_results[stage_name]

        print(f"\n{'='*60}")
        print(f"STAGE: {stage_name}")
        print(f"{'='*60}")
        print(f"Status: {result.status.value}")
        print(f"Started: {result.started_at}")
        print(f"Completed: {result.completed_at}")
        print(f"Duration: {result.duration_seconds:.2f}s" if result.duration_seconds else "Duration: -")
        print(f"Retries: {result.retry_count}")

        if result.error:
            print(f"\nError: {result.error}")

        if result.metadata:
            print(f"\nMetadata:")
            for key, value in result.metadata.items():
                print(f"  {key}: {value}")

    @staticmethod
    def analyze_workflow_logs(
        log_dir: str,
        workflow_name: Optional[str] = None,
        limit: int = 10
    ) -> Dict:
        """
        Analyze workflow logs for performance metrics

        Args:
            log_dir: Directory containing workflow logs
            workflow_name: Optional filter by workflow name
            limit: Number of recent workflows to analyze

        Returns:
            Analysis dictionary
        """
        log_path = Path(log_dir)

        # Find log files
        if workflow_name:
            pattern = f"{workflow_name}_*.json"
        else:
            pattern = "*.json"

        log_files = sorted(
            log_path.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]

        if not log_files:
            return {"error": "No workflow logs found"}

        # Analyze workflows
        total = len(log_files)
        completed = 0
        failed = 0
        total_duration = 0
        stage_durations = {}
        stage_failures = {}

        for log_file in log_files:
            try:
                state = WorkflowState.load(str(log_file))

                if state.status == WorkflowStatus.COMPLETED:
                    completed += 1
                elif state.status == WorkflowStatus.FAILED:
                    failed += 1

                if state.total_duration_seconds:
                    total_duration += state.total_duration_seconds

                # Stage analysis
                for stage_name, result in state.stage_results.items():
                    if stage_name not in stage_durations:
                        stage_durations[stage_name] = []
                        stage_failures[stage_name] = 0

                    if result.duration_seconds:
                        stage_durations[stage_name].append(result.duration_seconds)

                    if result.status == StageStatus.FAILED:
                        stage_failures[stage_name] += 1

            except Exception as e:
                print(f"Error loading {log_file}: {e}")

        # Calculate averages
        avg_stage_durations = {
            stage: sum(durations) / len(durations)
            for stage, durations in stage_durations.items()
            if durations
        }

        return {
            "total_workflows": total,
            "completed": completed,
            "failed": failed,
            "success_rate": f"{(completed / total * 100):.1f}%" if total > 0 else "0%",
            "avg_duration": total_duration / total if total > 0 else 0,
            "avg_stage_durations": avg_stage_durations,
            "stage_failure_counts": stage_failures
        }

    @staticmethod
    def print_analysis(log_dir: str, workflow_name: Optional[str] = None):
        """Print workflow analysis"""
        analysis = WorkflowMonitor.analyze_workflow_logs(log_dir, workflow_name)

        print(f"\n{'='*60}")
        print("WORKFLOW ANALYSIS")
        print(f"{'='*60}")

        if "error" in analysis:
            print(analysis["error"])
            return

        print(f"Total workflows: {analysis['total_workflows']}")
        print(f"Completed: {analysis['completed']}")
        print(f"Failed: {analysis['failed']}")
        print(f"Success rate: {analysis['success_rate']}")
        print(f"Avg duration: {analysis['avg_duration']:.2f}s")

        print(f"\nAvg Stage Durations:")
        for stage, duration in analysis['avg_stage_durations'].items():
            print(f"  {stage}: {duration:.2f}s")

        if any(analysis['stage_failure_counts'].values()):
            print(f"\nStage Failures:")
            for stage, count in analysis['stage_failure_counts'].items():
                if count > 0:
                    print(f"  {stage}: {count}")


# Example usage
if __name__ == "__main__":
    import sys
    import os

    # Add project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, project_root)

    from agent.realtime_agent.workflows.workflow_state import WorkflowState, WorkflowStatus

    # Create example state
    state = WorkflowState(
        workflow_id="example_123",
        workflow_name="news_processing",
        created_at="2025-11-05T10:00:00",
        stages=["screen", "filter", "sentiment", "impact", "decision"]
    )

    state.start_workflow()
    state.start_stage("screen")
    state.complete_stage("screen", {"decision": "process"}, {"category": "new"})
    state.skip_stage("filter", "Screened out as duplicate")
    state.skip_stage("sentiment", "Condition not met")
    state.skip_stage("impact", "Condition not met")
    state.skip_stage("decision", "Condition not met")
    state.complete_workflow()

    # Print visualization
    monitor = WorkflowMonitor()
    monitor.print_workflow(state)
    monitor.print_summary(state)
