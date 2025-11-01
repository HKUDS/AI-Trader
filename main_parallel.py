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
}


def get_agent_class(agent_type):
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
        import importlib
        
        # Import with timeout to detect blocking imports
        # Note: langchain imports can take 60+ seconds, especially with multiple processes
        try:
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Module import timed out after 120 seconds: {module_path}")
            
            # Set timeout for import (120 seconds - langchain imports can be very slow)
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(120)
            
            try:
                module = importlib.import_module(module_path)
            finally:
                signal.alarm(0)  # Cancel alarm
            
        except TimeoutError as e:
            print(f"❌ {e}")
            raise
        except:
            # If signal not available (Windows), just import normally
            module = importlib.import_module(module_path)
        
        agent_class = getattr(module, class_name)
        print(f"✅ Successfully loaded Agent class: {agent_type} (from {module_path})")
        return agent_class
    except ImportError as e:
        raise ImportError(f"❌ Unable to import agent module {module_path}: {e}")
    except AttributeError as e:
        raise AttributeError(f"❌ Class {class_name} not found in module {module_path}: {e}")


def load_config(config_path=None):
    if config_path is None:
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

        print(f"✅ {AgentClass.__name__} instance created successfully")
        
        # Add timeout to initialization
        try:
            await asyncio.wait_for(agent.initialize(), timeout=120.0)  # 2 minute timeout
        except asyncio.TimeoutError:
            print(f"❌ Initialization timed out after 120 seconds")
            print(f"   This usually means MCP services are not responding")
            raise RuntimeError("Agent initialization timed out - MCP services may not be accessible")
        
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
    
    # Ensure unbuffered output for subprocesses
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    # Stagger subprocess launches to avoid import lock contention
    # When multiple processes import the same module simultaneously, 
    # Python's import lock can cause deadlocks.
    # Use longer delays to allow each process to complete imports before starting the next
    for idx, model in enumerate(enabled_models):
        signature = model.get("signature")
        if not signature:
            continue
        cmd = [python_exec, "-u", this_file]  # -u flag for unbuffered output
        if config_path:
            cmd.append(str(config_path))
        cmd.extend(["--signature", signature])
        print(f"🧩 Spawning subprocess for signature='{signature}': {' '.join(cmd)}")
        sys.stdout.flush()
        
        # Stagger launches by 5 seconds to avoid import lock contention
        # langchain imports can be very slow, give each process more time
        if idx > 0:
            print(f"⏳ Waiting 5 seconds before starting next subprocess to avoid import conflicts...")
            await asyncio.sleep(5)
        
        # Create subprocess with explicit stdout/stderr handling
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        # Create tasks to read output
        async def read_output(proc, signature):
            """Read and print subprocess output in real-time"""
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                print(f"[{signature}] {line.decode().rstrip()}")
                sys.stdout.flush()
            
            # Read stderr
            stderr_data = await proc.stderr.read()
            if stderr_data:
                print(f"[{signature}] STDERR: {stderr_data.decode()}")
                sys.stdout.flush()
            
            return await proc.wait()
        
        tasks.append(read_output(proc, signature))
    
    if not tasks:
        return
    await asyncio.gather(*tasks)


async def main(config_path=None, only_signature: str | None = None):
    config = load_config(config_path)
    agent_type = config.get("agent_type", "BaseAgent")
    
    try:
        AgentClass = get_agent_class(agent_type)
    except (ValueError, ImportError, AttributeError) as e:
        print(str(e))
        exit(1)

    INIT_DATE = config["date_range"]["init_date"]
    END_DATE = config["date_range"]["end_date"]

    if os.getenv("INIT_DATE"):
        INIT_DATE = os.getenv("INIT_DATE")
        print(f"⚠️  Using environment variable to override INIT_DATE: {INIT_DATE}")
    if os.getenv("END_DATE"):
        END_DATE = os.getenv("END_DATE")
        print(f"⚠️  Using environment variable to override END_DATE: {END_DATE}")

    INIT_DATE_obj = datetime.strptime(INIT_DATE, "%Y-%m-%d").date()
    END_DATE_obj = datetime.strptime(END_DATE, "%Y-%m-%d").date()
    if INIT_DATE_obj > END_DATE_obj:
        print("❌ INIT_DATE is greater than END_DATE")
        exit(1)

    enabled_models = [m for m in config["models"] if m.get("enabled", True)]
    
    if only_signature:
        enabled_models = [m for m in enabled_models if m.get("signature") == only_signature]

    agent_config = config.get("agent_config", {})
    log_config = config.get("log_config", {})

    model_names = [m.get("name", m.get("signature")) for m in enabled_models]
    print("🚀 Starting trading experiment (parallel runner)")
    print(f"🤖 Agent type: {agent_type}")
    print(f"📅 Date range: {INIT_DATE} to {END_DATE}")
    print(f"🤖 Model list: {model_names}")

    # When --signature is specified, always run in current process (single model mode)
    if only_signature:
        if len(enabled_models) == 0:
            print(f"❌ Model with signature {only_signature} not found or not enabled")
            return
        model_config = enabled_models[0]
        await _run_model_in_current_process(AgentClass, model_config, INIT_DATE, END_DATE, agent_config, log_config)
        print("🎉 Model processing completed!")
    elif len(enabled_models) <= 1:
        # Single model without --signature flag
        for model_config in enabled_models:
            await _run_model_in_current_process(AgentClass, model_config, INIT_DATE, END_DATE, agent_config, log_config)
        print("🎉 All models processing completed!")
    else:
        # Multiple models - spawn subprocesses
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


