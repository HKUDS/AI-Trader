"""
Workflow Management System for Multi-Agent Processing

This package provides a robust workflow orchestration framework for
managing multi-agent pipelines with state tracking, logging, and error handling.
"""

from .workflow_state import WorkflowState, StageResult, WorkflowStatus
from .workflow_executor import WorkflowExecutor
from .news_processing_workflow import NewsProcessingWorkflow

__all__ = [
    'WorkflowState',
    'StageResult',
    'WorkflowStatus',
    'WorkflowExecutor',
    'NewsProcessingWorkflow'
]
