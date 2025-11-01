import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import json
from dotenv import load_dotenv


def compute_yesterday(date_format: str = "%Y-%m-%d") -> str:
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    return yesterday.strftime(date_format)


def main():
    # Optional args:
    #   1) config path (default: project configs/production_config.json)
    #   2) date (YYYY-MM-DD). If omitted, use yesterday.
    project_root = Path(__file__).resolve().parents[1]
    default_config = project_root / "configs" / "production_config.json"

    # Load environment variables from .env file (or .env.example as fallback)
    env_file = project_root / ".env"
    env_example_file = project_root / ".env.example"
    
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Loaded environment variables from: {env_file}")
    elif env_example_file.exists():
        load_dotenv(env_example_file)
        print(f"⚠️  Loaded environment variables from .env.example (consider creating .env file): {env_example_file}")
    else:
        print(f"⚠️  No .env or .env.example file found in {project_root}")

    config_path = sys.argv[1] if len(sys.argv) > 1 else str(default_config)
    run_date = sys.argv[2] if len(sys.argv) > 2 else compute_yesterday()

    # Ensure absolute config path for clarity
    config_path = str(Path(config_path).resolve())

    # Optional trading calendar check
    # Set FORCE_RUN_NON_TRADING=1 to bypass skipping on non-trading days
    calendar_path = project_root / "data" / "trading_calendar" / "us_trading_days_2025Q4.json"
    if calendar_path.exists():
        try:
            with open(calendar_path, "r", encoding="utf-8") as f:
                calendar = json.load(f)
            trading_days = set(calendar.get("trading_days", []))
            if os.getenv("FORCE_RUN_NON_TRADING", "0") not in ("1", "true", "True"):
                if run_date not in trading_days:
                    print(f"Skip: {run_date} is not in trading calendar {calendar_path}")
                    return
        except Exception as e:
            print(f"Warning: failed to read trading calendar {calendar_path}: {e}")

    # Export date overrides for main.py to pick up
    os.environ["INIT_DATE"] = run_date
    os.environ["END_DATE"] = run_date

    # Initialize MCP Service Manager
    sys.path.insert(0, str(project_root))
    agent_tools_path = project_root / "agent_tools"
    sys.path.insert(0, str(agent_tools_path))
    
    from start_mcp_services import MCPServiceManager
    
    # Create MCP service manager instance
    mcp_manager = None
    
    try:
        # Change to agent_tools directory to start services (they expect to run from there)
        original_cwd = os.getcwd()
        os.chdir(agent_tools_path)
        
        # Initialize and start MCP services
        print("\n" + "=" * 60)
        print("🚀 Starting MCP services...")
        print("=" * 60)
        mcp_manager = MCPServiceManager()
        
        # Start all services manually (without keep_alive)
        print(f"📊 Port configuration:")
        for service_id, config in mcp_manager.service_configs.items():
            print(f"  - {config['name']}: {config['port']}")
        
        print("\n🔄 Starting services...")
        for service_id, config in mcp_manager.service_configs.items():
            mcp_manager.start_service(service_id, config)
        
        # Wait for services to start
        print("\n⏳ Waiting for services to start...")
        time.sleep(3)
        
        # Check service status
        print("\n🔍 Checking service status...")
        mcp_manager.check_all_services()
        
        print("\n✅ All MCP services started!")
        mcp_manager.print_service_info()
        
        # Restore original working directory
        os.chdir(original_cwd)
        
        # Import and run the project main
        import asyncio
        import main_parallel as project_main

        print("\n" + "=" * 60)
        print(f"📅 Running for date: {run_date}")
        print(f"📄 Using config: {config_path}")
        print("=" * 60 + "\n")
        asyncio.run(project_main.main(config_path))
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        raise
    finally:
        # Always stop MCP services
        if mcp_manager and mcp_manager.services:
            print("\n" + "=" * 60)
            print("🛑 Stopping MCP services...")
            print("=" * 60)
            try:
                mcp_manager.stop_all_services()
            except Exception as e:
                print(f"⚠️  Error stopping MCP services: {e}")


if __name__ == "__main__":
    main()


