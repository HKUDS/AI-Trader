import os
import sys
import asyncio
from datetime import datetime
import json
from pathlib import Path
from dotenv import load_dotenv
import argparse
load_dotenv()

# Import tools and prompts
from tools.general_tools import write_config_value
from prompts.agent_prompt import all_nasdaq_100_symbols


# Agent class mapping table - for dynamic import and instantiation
AGENT_REGISTRY = {
    "BaseAgent": {
        "module": "agent.base_agent.base_agent",
        "class": "BaseAgent"
    },
    "BaseAgent_Hour": {
        "module": "agent.base_agent.base_agent_hour",
        "class": "BaseAgent_Hour"
    },
}


def get_agent_class(agent_type):
    """
    Dynamically import and return the corresponding class based on agent type name
    
    Args:
        agent_type: Agent type name (e.g., "BaseAgent")
        
    Returns:
        Agent class
        
    Raises:
        ValueError: If agent type is not supported
        ImportError: If unable to import agent module
    """
    if agent_type not in AGENT_REGISTRY:
        supported_types = ", ".join(AGENT_REGISTRY.keys())
        raise ValueError(
            f"❌ Unsupported agent type: {agent_type}\n"
            f"   Supported types: {supported_types}"
        )
    
    agent_info = AGENT_REGISTRY[agent_type]
    module_path = agent_info["module"]
    class_name = agent_info["class"]
    
    try:
        # Dynamic import module
        import importlib
        module = importlib.import_module(module_path)
        agent_class = getattr(module, class_name)
        print(f"✅ Successfully loaded Agent class: {agent_type} (from {module_path})")
        return agent_class
    except ImportError as e:
        raise ImportError(f"❌ Unable to import agent module {module_path}: {e}")
    except AttributeError as e:
        raise AttributeError(f"❌ Class {class_name} not found in module {module_path}: {e}")


def load_config(config_path=None):
    """
    Load configuration file from configs directory
    
    Args:
        config_path: Configuration file path, if None use default config
        
    Returns:
        dict: Configuration dictionary
    """
    if config_path is None:
        # Default configuration file path
        config_path = Path(__file__).parent / "configs" / "default_config.json"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        print(f"❌ Configuration file does not exist: {config_path}")
        exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"✅ Successfully loaded configuration file: {config_path}")
        return config
    except json.JSONDecodeError as e:
        print(f"❌ Configuration file JSON format error: {e}")
        exit(1)
    except Exception as e:
        print(f"❌ Failed to load configuration file: {e}")
        exit(1)


async def _run_model_in_current_process(AgentClass, model_config, INIT_DATE, END_DATE, agent_config, log_config):
    model_name = model_config.get("name", "unknown")
    basemodel = model_config.get("basemodel")
    signature = model_config.get("signature")
    openai_base_url = model_config.get("openai_base_url", None)
    openai_api_key = model_config.get("openai_api_key", None)

    if not basemodel:
        print(f"❌ Model {model_name} missing basemodel field")
        return
    if not signature:
        print(f"❌ Model {model_name} missing signature field")
        return

    print("=" * 60)
    print(f"🤖 Processing model: {model_name}")
    print(f"📝 Signature: {signature}")
    print(f"🔧 BaseModel: {basemodel}")

    project_root = Path(__file__).resolve().parent
    runtime_env_dir = project_root / "data" / "agent_data" / signature
    runtime_env_dir.mkdir(parents=True, exist_ok=True)
    runtime_env_path = runtime_env_dir / ".runtime_env.json"
    os.environ["RUNTIME_ENV_PATH"] = str(runtime_env_path)
    os.environ["SIGNATURE"] = signature
    write_config_value("TODAY_DATE", END_DATE)
    write_config_value("IF_TRADE", False)

    max_steps = agent_config.get("max_steps", 10)
    max_retries = agent_config.get("max_retries", 3)
    base_delay = agent_config.get("base_delay", 0.5)
    initial_cash = agent_config.get("initial_cash", 10000.0)

    log_path = log_config.get("log_path", "./data/agent_data")

    try:
        agent = AgentClass(
            signature=signature,
            basemodel=basemodel,
            stock_symbols=all_nasdaq_100_symbols,
            log_path=log_path,
            openai_base_url=openai_base_url,
            openai_api_key=openai_api_key,
            max_steps=max_steps,
            max_retries=max_retries,
            base_delay=base_delay,
            initial_cash=initial_cash,
            init_date=INIT_DATE
        )

        print(f"✅ {AgentClass.__name__} instance created successfully: {agent}")
        await agent.initialize()
        print("✅ Initialization successful")
        await agent.run_date_range(INIT_DATE, END_DATE)

        summary = agent.get_position_summary()
        print(f"📊 Final position summary:")
        print(f"   - Latest date: {summary.get('latest_date')}")
        print(f"   - Total records: {summary.get('total_records')}")
        print(f"   - Cash balance: ${summary.get('positions', {}).get('CASH', 0):.2f}")

    except Exception as e:
        print(f"❌ Error processing model {model_name} ({signature}): {str(e)}")
        print(f"📋 Error details: {e}")
        raise

    print("=" * 60)
    print(f"✅ Model {model_name} ({signature}) processing completed")
    print("=" * 60)


async def _spawn_model_subprocesses(config_path, enabled_models):
    tasks = []
    python_exec = sys.executable
    this_file = str(Path(__file__).resolve())
    for model in enabled_models:
        signature = model.get("signature")
        if not signature:
            continue
        cmd = [python_exec, this_file]
        if config_path:
            cmd.append(str(config_path))
        cmd.extend(["--signature", signature])
        print(f"🧩 Spawning subprocess for signature='{signature}': {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(*cmd)
        tasks.append(proc.wait())
    if not tasks:
        return
    await asyncio.gather(*tasks)


async def main(config_path=None, only_signature: str | None = None):
    """Run trading experiment using Agent class (parallel runner)
    
    Args:
        config_path: Configuration file path, if None use default config
        only_signature: If provided, run only this model signature
    """
    # Load configuration file
    config = load_config(config_path)
    
    # Get Agent type
    agent_type = config.get("agent_type", "BaseAgent")
    try:
        AgentClass = get_agent_class(agent_type)
    except (ValueError, ImportError, AttributeError) as e:
        print(str(e))
        exit(1)

    INIT_DATE = config["date_range"]["init_date"]
    END_DATE = config["date_range"]["end_date"]

    # Environment variables can override dates in configuration file
    if os.getenv("INIT_DATE"):
        INIT_DATE = os.getenv("INIT_DATE")
        print(f"⚠️  Using environment variable to override INIT_DATE: {INIT_DATE}")
    if os.getenv("END_DATE"):
        END_DATE = os.getenv("END_DATE")
        print(f"⚠️  Using environment variable to override END_DATE: {END_DATE}")

    # Validate date range
    # Support both YYYY-MM-DD and YYYY-MM-DD HH:MM:SS formats
    if ' ' in INIT_DATE:
        INIT_DATE_obj = datetime.strptime(INIT_DATE, "%Y-%m-%d %H:%M:%S")
    else:
        INIT_DATE_obj = datetime.strptime(INIT_DATE, "%Y-%m-%d")
    
    if ' ' in END_DATE:
        END_DATE_obj = datetime.strptime(END_DATE, "%Y-%m-%d %H:%M:%S")
    else:
        END_DATE_obj = datetime.strptime(END_DATE, "%Y-%m-%d")
    
    if INIT_DATE_obj > END_DATE_obj:
        print("❌ INIT_DATE is greater than END_DATE")
        exit(1)

    # Get model list from configuration file (only select enabled models)
    enabled_models = [
        model for model in config["models"] 
        if model.get("enabled", True)
    ]
    if only_signature:
        enabled_models = [m for m in enabled_models if m.get("signature") == only_signature]

    # Get agent configuration
    agent_config = config.get("agent_config", {})
    log_config = config.get("log_config", {})

    # Display enabled model information
    model_names = [m.get("name", m.get("signature")) for m in enabled_models]
    print("🚀 Starting trading experiment (parallel runner)")
    print(f"🤖 Agent type: {agent_type}")
    print(f"📅 Date range: {INIT_DATE} to {END_DATE}")
    print(f"🤖 Model list: {model_names}")

    if len(enabled_models) <= 1:
        for model_config in enabled_models:
            await _run_model_in_current_process(AgentClass, model_config, INIT_DATE, END_DATE, agent_config, log_config)
        print("🎉 All models processing completed!")
    else:
        print("⚡ Multiple models enabled; running them in parallel using subprocesses...")
        await _spawn_model_subprocesses(config_path, enabled_models)
        print("🎉 All model subprocesses completed!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI-Trader parallel runner")
    parser.add_argument("config_path", nargs="?", default=None, help="Path to config JSON")
    parser.add_argument("--signature", dest="signature", default=None, help="Run only this model signature")
    args = parser.parse_args()

    if args.config_path:
        print(f"📄 Using specified configuration file: {args.config_path}")
    else:
        print(f"📄 Using default configuration file: configs/default_config.json")
    if args.signature:
        print(f"🎯 Filtering to single signature: {args.signature}")

    asyncio.run(main(args.config_path, args.signature))

