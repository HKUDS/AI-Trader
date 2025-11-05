# Workflow Management System - Complete Guide

## 🎯 Overview

The Workflow Management System provides **robust orchestration** for multi-agent processing with:

✅ **State tracking** - Full visibility into workflow execution
✅ **Step-by-step logging** - Comprehensive logging at each stage
✅ **Task routing** - Conditional routing based on stage outputs
✅ **Error handling** - Automatic retries with exponential backoff
✅ **Performance monitoring** - Duration tracking and metrics
✅ **Visualization** - ASCII progress display
✅ **Persistence** - Save/load workflow state

---

## 📁 Architecture

```
workflows/
├── workflow_state.py           # State management (WorkflowState, StageResult)
├── workflow_executor.py        # Execution engine with routing & retries
├── news_processing_workflow.py # News multi-agent pipeline
└── workflow_monitor.py         # Visualization and monitoring
```

### **Components:**

1. **WorkflowState** - Tracks complete execution state
2. **WorkflowExecutor** - Manages execution with routing
3. **NewsProcessingWorkflow** - Specific news pipeline
4. **WorkflowMonitor** - Visualization and analysis

---

## 🏗️ News Processing Workflow

### **Pipeline Stages:**

```
Event
  ↓
Stage 1: SCREEN (Haiku)
  ├─→ duplicate/spam → SKIP rest of pipeline
  └─→ new/update → Continue
       ↓
Stage 2: FILTER (NewsFilterAgent)
  ├─→ not relevant → SKIP rest
  └─→ relevant → Continue
       ↓
Stage 3: SENTIMENT (NewsSentimentAgent)
  └─→ Extract sentiment + facts → Continue
       ↓
Stage 4: IMPACT (StockImpactAgent)
  └─→ Assess stock-specific impact → Continue
       ↓
Stage 5: DECISION (PortfolioDecisionAgent)
  └─→ Generate trading recommendations
```

### **Conditional Routing:**

- **Screen fails** → Skip all subsequent stages
- **Filter fails** → Skip sentiment/impact/decision
- **No impacts** → Skip decision stage

---

## 🚀 Usage

### **Basic Example:**

```python
from agent.realtime_agent.workflows import NewsProcessingWorkflow
from agent.realtime_agent.event_detector import MarketEvent

# Create workflow
workflow = NewsProcessingWorkflow(
    anthropic_api_key="your_key",
    model="sonnet",
    log_dir="./data/workflows"
)

# Process event
result = await workflow.process_event(
    event=market_event,
    candidate_symbols=["AAPL", "NVDA", "TSLA"],
    current_positions={"CASH": 10000, "AAPL": 10},
    available_cash=8500
)

# Check result
if result.status == WorkflowStatus.COMPLETED:
    recommendations = result.output_data['output']
    for rec in recommendations:
        print(f"{rec.symbol}: {rec.action.value} x {rec.quantity}")
```

### **Monitor Progress:**

```python
from agent.realtime_agent.workflows import WorkflowMonitor

monitor = WorkflowMonitor()

# Print workflow visualization
monitor.print_workflow(result)

# Print summary
monitor.print_summary(result)

# Print metadata
monitor.print_metadata(result)
```

---

## 📊 Example Output

### **Workflow Visualization:**

```
News Processing (news_processing_abc123)
============================================================

✅ screen     [COMPLETED]  1.2s  new
✅ filter     [COMPLETED]  2.3s
✅ sentiment  [COMPLETED]  3.1s
✅ impact     [COMPLETED]  2.8s
✅ decision   [COMPLETED]  4.5s

Status: COMPLETED
Duration: 13.9s
Progress: 100%
```

### **With Conditional Skipping:**

```
News Processing (news_processing_def456)
============================================================

✅ screen     [COMPLETED]  1.1s  duplicate
⏭️  filter     [SKIPPED]    0.0s  Condition not met
⏭️  sentiment  [SKIPPED]    0.0s  Condition not met
⏭️  impact     [SKIPPED]    0.0s  Condition not met
⏭️  decision   [SKIPPED]    0.0s  Condition not met

Status: COMPLETED
Duration: 1.1s
Progress: 100%
```

### **With Error:**

```
News Processing (news_processing_ghi789)
============================================================

✅ screen     [COMPLETED]  1.3s
✅ filter     [COMPLETED]  2.1s
❌ sentiment  [FAILED]     1.5s  API rate limit exceeded
⏸️  impact     [PENDING]    -
⏸️  decision   [PENDING]    -

Status: FAILED
Duration: 4.9s
Progress: 40%

Errors: 1
  - sentiment: API rate limit exceeded...
```

---

## 🔧 Building Custom Workflows

### **Step 1: Create Executor**

```python
from agent.realtime_agent.workflows import WorkflowExecutor

executor = WorkflowExecutor(
    workflow_name="custom_workflow",
    log_dir="./data/workflows",
    max_retries=3,
    retry_delay=1.0
)
```

### **Step 2: Define Stage Handlers**

```python
async def stage1_handler(state: WorkflowState, input_data: Any) -> Any:
    # Your processing logic
    result = process_data(input_data)

    # Optional: Add metadata
    state.metadata['stage1_info'] = "some info"

    return result
```

### **Step 3: Add Stages**

```python
# Add sequential stages
executor.add_stage("stage1", stage1_handler)
executor.add_stage("stage2", stage2_handler)

# Add conditional stage
executor.add_stage(
    "stage3",
    stage3_handler,
    condition=lambda state: state.get_stage_output("stage1")['should_continue']
)

# Add parallel stages
executor.add_stage(
    "stage4a",
    stage4a_handler,
    parallel_with=["stage4b", "stage4c"]
)
```

### **Step 4: Add Routing**

```python
def routing_logic(stage_output: Any) -> str:
    if stage_output['type'] == 'A':
        return "path_a_stage"
    else:
        return "path_b_stage"

executor.add_routing_rule("stage1", routing_logic)
```

### **Step 5: Execute**

```python
state = await executor.execute(input_data={"key": "value"})
```

---

## 📈 State Management

### **WorkflowState Fields:**

```python
state.workflow_id           # Unique ID
state.workflow_name         # Workflow name
state.status                # PENDING/RUNNING/COMPLETED/FAILED
state.current_stage         # Currently executing stage
state.stages                # List of all stages
state.stage_results         # Results from each stage
state.input_data            # Initial input
state.output_data           # Final output
state.intermediate_data     # Data passed between stages
state.errors                # List of errors
state.metadata              # Custom metadata
```

### **Query State:**

```python
# Get stage output
output = state.get_stage_output("stage_name")

# Get progress
progress = state.get_progress()  # 0.0 to 1.0

# Get summary
summary = state.get_summary()

# Save to file
state.save("./data/workflows/workflow_123.json")

# Load from file
state = WorkflowState.load("./data/workflows/workflow_123.json")
```

---

## 🔍 Monitoring & Analysis

### **Print Workflow:**

```python
monitor = WorkflowMonitor()
monitor.print_workflow(state)
```

### **Analyze Logs:**

```python
# Analyze recent workflows
monitor.print_analysis("./data/workflows", workflow_name="news_processing")
```

**Output:**
```
============================================================
WORKFLOW ANALYSIS
============================================================
Total workflows: 50
Completed: 47
Failed: 3
Success rate: 94.0%
Avg duration: 12.4s

Avg Stage Durations:
  screen: 1.2s
  filter: 2.1s
  sentiment: 3.0s
  impact: 2.8s
  decision: 4.3s

Stage Failures:
  sentiment: 2
  impact: 1
```

### **Stage Details:**

```python
monitor.print_stage_details(state, "sentiment")
```

---

## 🎯 Advanced Features

### **1. Pre/Post Hooks**

```python
async def before_sentiment(state: WorkflowState):
    logger.info("About to analyze sentiment...")

async def after_sentiment(state: WorkflowState, output: Any):
    logger.info(f"Sentiment: {output.sentiment}")
    state.metadata['sentiment_value'] = output.sentiment

executor.add_pre_hook("sentiment", before_sentiment)
executor.add_post_hook("sentiment", after_sentiment)
```

### **2. Parallel Execution**

```python
# These stages run in parallel
executor.add_stage("fetch_news", fetch_news_handler)
executor.add_stage("fetch_prices", fetch_prices_handler, parallel_with=["fetch_news"])
```

### **3. Conditional Routing**

```python
def route_by_priority(output: Any) -> str:
    if output['priority'] == 'HIGH':
        return "fast_track_stage"
    else:
        return "normal_stage"

executor.add_routing_rule("screen", route_by_priority)
```

### **4. Retry Configuration**

```python
executor = WorkflowExecutor(
    workflow_name="my_workflow",
    max_retries=5,        # Retry up to 5 times
    retry_delay=2.0       # Start with 2s delay (exponential backoff)
)

# Retry delays: 2s, 4s, 8s, 16s, 32s
```

---

## 📁 Log Files

### **Location:**
```
data/workflows/
├── news_processing_abc123.json
├── news_processing_def456.json
└── news_processing_ghi789.json
```

### **Format:**

```json
{
  "workflow_id": "news_processing_abc123",
  "workflow_name": "news_processing",
  "status": "completed",
  "total_duration_seconds": 13.9,
  "stage_results": {
    "screen": {
      "stage_name": "screen",
      "status": "completed",
      "duration_seconds": 1.2,
      "metadata": {"category": "new"}
    },
    "filter": {
      "stage_name": "filter",
      "status": "completed",
      "duration_seconds": 2.3
    }
  },
  "metadata": {
    "screening_decision": "new",
    "relevance_score": 0.95,
    "sentiment": "bullish",
    "stocks_impacted": 2,
    "recommendations_count": 2
  },
  "summary": {
    "progress": "100%",
    "stages_completed": 5,
    "stages_failed": 0
  }
}
```

---

## 🎓 News Processing Workflow Details

### **Stage 1: Screen (Haiku)**

**Purpose:** Fast, cheap initial filtering

**Cost:** $0.001 per event

**Output:**
```python
{
    'event': MarketEvent,
    'screening_decision': ScreeningDecision(
        should_process=True,
        category="new",
        confidence=0.9
    )
}
```

**Routing:**
- `should_process=False` → Skip all remaining stages
- `should_process=True` → Continue to filter

---

### **Stage 2: Filter (Sonnet)**

**Purpose:** Deep relevance analysis

**Cost:** $0.015 per event

**Output:**
```python
{
    'filtered': FilteredNews(
        is_relevant=True,
        relevance_score=0.95,
        reason="Major product announcement"
    )
}
```

**Routing:**
- `is_relevant=False` → Skip sentiment/impact/decision
- `is_relevant=True` → Continue to sentiment

---

### **Stage 3: Sentiment**

**Purpose:** Extract sentiment and key facts

**Output:**
```python
{
    'sentiment': SentimentAnalysis(
        sentiment=Sentiment.BULLISH,
        confidence=0.88,
        key_facts=[...],
        reasoning="..."
    )
}
```

---

### **Stage 4: Impact**

**Purpose:** Assess stock-specific impact

**Output:**
```python
{
    'impacts': [
        StockImpactAssessment(
            symbol="NVDA",
            sentiment=Sentiment.BULLISH,
            impact=Impact.HIGH,
            confidence=0.85
        ),
        ...
    ]
}
```

**Routing:**
- `impacts=[]` → Skip decision
- `impacts=[...]` → Continue to decision

---

### **Stage 5: Decision**

**Purpose:** Generate trading recommendations

**Output:**
```python
[
    TradingRecommendation(
        symbol="NVDA",
        action=TradeAction.BUY,
        quantity=15,
        confidence=0.82,
        reasoning="..."
    ),
    ...
]
```

---

## 📊 Performance Metrics

### **Typical News Processing:**

| Stage | Avg Duration | Cost | Skip Rate |
|-------|--------------|------|-----------|
| Screen | 1.2s | $0.001 | 30% |
| Filter | 2.1s | $0.015 | 15% |
| Sentiment | 3.0s | $0.015 | 0% |
| Impact | 2.8s | $0.015 | 5% |
| Decision | 4.3s | $0.015 | 0% |
| **Total** | **13.4s** | **$0.061** | - |

**With screening:**
- 30% filtered at stage 1 → Cost: $0.001
- 70% continue → Average cost: ~$0.043/event

---

## 🐛 Debugging

### **Enable Debug Logging:**

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### **Inspect State:**

```python
# Print all stage results
for stage_name, result in state.stage_results.items():
    print(f"{stage_name}: {result.status.value}")
    if result.error:
        print(f"  Error: {result.error}")
```

### **Check Intermediate Data:**

```python
# Get data passed to each stage
for stage_name in state.stages:
    data = state.intermediate_data.get(stage_name)
    print(f"{stage_name} output: {data}")
```

---

## 🎯 Best Practices

### **1. Use Conditional Stages**

Don't process if earlier stages indicate it's not valuable:

```python
executor.add_stage(
    "expensive_stage",
    handler,
    condition=lambda state: state.get_stage_output("screen")['should_process']
)
```

### **2. Add Metadata**

Track important information:

```python
async def my_handler(state: WorkflowState, input_data: Any):
    result = process(input_data)

    # Add metadata for monitoring
    state.metadata['processing_time'] = result.duration
    state.metadata['items_processed'] = len(result.items)

    return result
```

### **3. Use Hooks for Logging**

```python
async def log_before(state: WorkflowState):
    logger.info(f"Starting {state.current_stage}")

async def log_after(state: WorkflowState, output: Any):
    logger.info(f"Completed {state.current_stage}: {output}")

executor.add_pre_hook("stage_name", log_before)
executor.add_post_hook("stage_name", log_after)
```

### **4. Monitor Performance**

Regularly analyze logs to identify bottlenecks:

```python
monitor.print_analysis("./data/workflows")
```

---

## 📞 Summary

The Workflow Management System provides:

✅ **Complete state tracking** - Know exactly what happened
✅ **Automatic routing** - Skip unnecessary stages
✅ **Error recovery** - Retry failed stages
✅ **Performance monitoring** - Identify bottlenecks
✅ **Visualization** - See progress in real-time
✅ **Persistence** - Save/load for debugging

**Key benefit:** Transform complex multi-agent pipelines into manageable, debuggable, monitorable workflows!

---

**Files:**
- `workflow_state.py` - State management
- `workflow_executor.py` - Execution engine
- `news_processing_workflow.py` - News pipeline
- `workflow_monitor.py` - Visualization

**Next:** See `REALTIME_AGENT_GUIDE.md` for complete system documentation.
