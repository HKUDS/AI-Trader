"""
Workflow State Management

Tracks the state of workflow execution including:
- Current stage
- Stage results
- Errors and retries
- Timing information
- Data passed between stages
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import json


class WorkflowStatus(Enum):
    """Status of workflow execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(Enum):
    """Status of individual stage"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Result from a single workflow stage"""
    stage_name: str
    status: StageStatus
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'stage_name': self.stage_name,
            'status': self.status.value,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'duration_seconds': self.duration_seconds,
            'output': str(self.output)[:200] if self.output else None,  # Truncate for logging
            'error': self.error,
            'retry_count': self.retry_count,
            'metadata': self.metadata
        }


@dataclass
class WorkflowState:
    """
    Complete state of workflow execution

    Tracks:
    - Workflow metadata (ID, name, created time)
    - Current status and stage
    - Results from each stage
    - Data passed between stages
    - Error tracking
    - Performance metrics
    """
    workflow_id: str
    workflow_name: str
    created_at: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_stage: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_duration_seconds: Optional[float] = None

    # Stage tracking
    stages: List[str] = field(default_factory=list)
    stage_results: Dict[str, StageResult] = field(default_factory=dict)
    current_stage_index: int = 0

    # Data flow
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    intermediate_data: Dict[str, Any] = field(default_factory=dict)

    # Error tracking
    errors: List[str] = field(default_factory=list)
    total_retries: int = 0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def start_workflow(self):
        """Mark workflow as started"""
        self.status = WorkflowStatus.RUNNING
        self.started_at = datetime.now().isoformat()

    def complete_workflow(self):
        """Mark workflow as completed"""
        self.status = WorkflowStatus.COMPLETED
        self.completed_at = datetime.now().isoformat()

        if self.started_at:
            start_time = datetime.fromisoformat(self.started_at)
            end_time = datetime.fromisoformat(self.completed_at)
            self.total_duration_seconds = (end_time - start_time).total_seconds()

    def fail_workflow(self, error: str):
        """Mark workflow as failed"""
        self.status = WorkflowStatus.FAILED
        self.completed_at = datetime.now().isoformat()
        self.errors.append(error)

        if self.started_at:
            start_time = datetime.fromisoformat(self.started_at)
            end_time = datetime.fromisoformat(self.completed_at)
            self.total_duration_seconds = (end_time - start_time).total_seconds()

    def start_stage(self, stage_name: str):
        """Start a new stage"""
        self.current_stage = stage_name
        self.current_stage_index = self.stages.index(stage_name) if stage_name in self.stages else len(self.stages)

        result = StageResult(
            stage_name=stage_name,
            status=StageStatus.RUNNING,
            started_at=datetime.now().isoformat()
        )

        self.stage_results[stage_name] = result

    def complete_stage(self, stage_name: str, output: Any, metadata: Optional[Dict] = None):
        """Complete a stage successfully"""
        if stage_name not in self.stage_results:
            raise ValueError(f"Stage {stage_name} not started")

        result = self.stage_results[stage_name]
        result.status = StageStatus.COMPLETED
        result.completed_at = datetime.now().isoformat()
        result.output = output

        if metadata:
            result.metadata.update(metadata)

        # Calculate duration
        start_time = datetime.fromisoformat(result.started_at)
        end_time = datetime.fromisoformat(result.completed_at)
        result.duration_seconds = (end_time - start_time).total_seconds()

        # Store output in intermediate data
        self.intermediate_data[stage_name] = output

    def fail_stage(self, stage_name: str, error: str, retry_count: int = 0):
        """Fail a stage"""
        if stage_name not in self.stage_results:
            raise ValueError(f"Stage {stage_name} not started")

        result = self.stage_results[stage_name]
        result.status = StageStatus.FAILED
        result.completed_at = datetime.now().isoformat()
        result.error = error
        result.retry_count = retry_count

        # Calculate duration
        start_time = datetime.fromisoformat(result.started_at)
        end_time = datetime.fromisoformat(result.completed_at)
        result.duration_seconds = (end_time - start_time).total_seconds()

        self.errors.append(f"{stage_name}: {error}")
        self.total_retries += retry_count

    def skip_stage(self, stage_name: str, reason: str):
        """Skip a stage"""
        result = StageResult(
            stage_name=stage_name,
            status=StageStatus.SKIPPED,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
            duration_seconds=0.0,
            metadata={'skip_reason': reason}
        )

        self.stage_results[stage_name] = result

    def get_stage_output(self, stage_name: str) -> Optional[Any]:
        """Get output from a specific stage"""
        return self.intermediate_data.get(stage_name)

    def get_progress(self) -> float:
        """Get workflow progress (0.0 to 1.0)"""
        if not self.stages:
            return 0.0

        completed = sum(
            1 for result in self.stage_results.values()
            if result.status in [StageStatus.COMPLETED, StageStatus.SKIPPED]
        )

        return completed / len(self.stages)

    def get_summary(self) -> Dict:
        """Get workflow summary"""
        return {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'status': self.status.value,
            'progress': f"{self.get_progress() * 100:.0f}%",
            'current_stage': self.current_stage,
            'total_duration': self.total_duration_seconds,
            'stages_completed': sum(
                1 for r in self.stage_results.values()
                if r.status == StageStatus.COMPLETED
            ),
            'stages_failed': sum(
                1 for r in self.stage_results.values()
                if r.status == StageStatus.FAILED
            ),
            'total_retries': self.total_retries,
            'errors': self.errors
        }

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'created_at': self.created_at,
            'status': self.status.value,
            'current_stage': self.current_stage,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'total_duration_seconds': self.total_duration_seconds,
            'stages': self.stages,
            'stage_results': {
                name: result.to_dict()
                for name, result in self.stage_results.items()
            },
            'errors': self.errors,
            'total_retries': self.total_retries,
            'metadata': self.metadata,
            'summary': self.get_summary()
        }

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    def save(self, filepath: str):
        """Save state to file"""
        with open(filepath, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, filepath: str) -> 'WorkflowState':
        """Load state from file"""
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Reconstruct state
        state = cls(
            workflow_id=data['workflow_id'],
            workflow_name=data['workflow_name'],
            created_at=data['created_at']
        )

        state.status = WorkflowStatus(data['status'])
        state.current_stage = data.get('current_stage')
        state.started_at = data.get('started_at')
        state.completed_at = data.get('completed_at')
        state.total_duration_seconds = data.get('total_duration_seconds')
        state.stages = data.get('stages', [])
        state.errors = data.get('errors', [])
        state.total_retries = data.get('total_retries', 0)
        state.metadata = data.get('metadata', {})

        # Reconstruct stage results
        for stage_name, result_data in data.get('stage_results', {}).items():
            result = StageResult(
                stage_name=result_data['stage_name'],
                status=StageStatus(result_data['status']),
                started_at=result_data['started_at'],
                completed_at=result_data.get('completed_at'),
                duration_seconds=result_data.get('duration_seconds'),
                error=result_data.get('error'),
                retry_count=result_data.get('retry_count', 0),
                metadata=result_data.get('metadata', {})
            )
            state.stage_results[stage_name] = result

        return state
