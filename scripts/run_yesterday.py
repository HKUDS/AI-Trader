#!/usr/bin/env python3
"""
Daily automated trading data update script
- Starts all MCP services
- Checks if yesterday was a trading day
- Runs main_parallel.py with production_config.json if it's a trading day
- Stops all MCP services when done
"""

import os
import sys
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import json
from dotenv import load_dotenv


def compute_yesterday(date_format: str = "%Y-%m-%d") -> str:
    """Compute yesterday's date"""
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    return yesterday.strftime(date_format)


def load_trading_calendar(calendar_path: Path) -> set:
    """Load trading days from calendar file"""
    try:
        with open(calendar_path, "r", encoding="utf-8") as f:
            calendar = json.load(f)
        trading_days = set(calendar.get("trading_days", []))
        return trading_days
    except Exception as e:
        print(f"❌ Failed to load trading calendar: {e}")
        raise


def is_trading_day(date_str: str, trading_days: set) -> bool:
    """Check if a date is a trading day"""
    return date_str in trading_days


def wait_for_service_ready(port: int, max_attempts: int = 60, delay: float = 2.0) -> bool:
    """Wait for a service to be ready by checking if port is open and responding"""
    import socket
    import urllib.request
    
    for attempt in range(max_attempts):
        try:
            # First check if port is open
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            
            if result == 0:
                # Port is open, try to check if HTTP endpoint responds
                try:
                    # Try to connect to /mcp endpoint
                    req = urllib.request.Request(f'http://localhost:{port}/mcp')
                    req.add_header('Content-Type', 'application/json')
                    urllib.request.urlopen(req, timeout=2)
                    return True
                except:
                    # Port is open but endpoint might not be ready yet, keep waiting
                    pass
        except Exception:
            pass
        
        if attempt < max_attempts - 1:
            time.sleep(delay)
    
    return False


def start_mcp_services(agent_tools_path: Path) -> object:
    """
    Start all MCP services using MCPServiceManager
    Returns the manager instance
    """
    sys.path.insert(0, str(agent_tools_path))
    from start_mcp_services import MCPServiceManager
    
    print("\n" + "=" * 60)
    print("🚀 Starting MCP services...")
    print("=" * 60)
    
    # Change to agent_tools directory to start services
    original_cwd = os.getcwd()
    try:
        os.chdir(agent_tools_path)
        mcp_manager = MCPServiceManager()
        
        # Start all services
        print(f"\n📊 Port configuration:")
        for service_id, config in mcp_manager.service_configs.items():
            print(f"  - {config['name']}: {config['port']}")
        
        print("\n🔄 Starting services...")
        for service_id, config in mcp_manager.service_configs.items():
            success = mcp_manager.start_service(service_id, config)
            if not success:
                print(f"⚠️  Warning: Failed to start {config['name']} service")
        
        # Initial wait for services to start
        print("\n⏳ Waiting for services to initialize (5 seconds)...")
        time.sleep(5)
        
        # Wait and verify services are ready
        print("\n⏳ Verifying services are ready...")
        all_ready = True
        service_status = {}
        for service_id, service in mcp_manager.services.items():
            service_name = service['name']
            port = service['port']
            print(f"  Checking {service_name} on port {port}...", end=" ", flush=True)
            if wait_for_service_ready(port, max_attempts=30, delay=2.0):
                print("✅ Ready")
                service_status[service_id] = True
            else:
                print("❌ Not ready after 60 seconds")
                service_status[service_id] = False
                all_ready = False
        
        if not all_ready:
            print("\n⚠️  Warning: Some services are not ready:")
            for service_id, service in mcp_manager.services.items():
                if not service_status.get(service_id, False):
                    print(f"   - {service['name']} (port {service['port']}) not responding")
            print("\n   Checking process status...")
            for service_id, service in mcp_manager.services.items():
                if not service_status.get(service_id, False):
                    process = service['process']
                    if process.poll() is not None:
                        print(f"   - {service['name']} process has exited (exit code: {process.returncode})")
                        print(f"     Check log: {service['log_file']}")
                    else:
                        print(f"   - {service['name']} process is running (PID: {process.pid}) but not responding")
            print("\n   Continuing anyway, but initialization may fail...")
        
        # Check service status
        print("\n🔍 Final service status check...")
        mcp_manager.check_all_services()
        
        print("\n✅ MCP services startup completed!")
        mcp_manager.print_service_info()
        
        return mcp_manager
        
    finally:
        os.chdir(original_cwd)


def stop_mcp_services(mcp_manager):
    """Stop all MCP services"""
    if mcp_manager and hasattr(mcp_manager, 'services') and mcp_manager.services:
        print("\n" + "=" * 60)
        print("🛑 Stopping MCP services...")
        print("=" * 60)
        try:
            mcp_manager.stop_all_services()
            print("✅ All MCP services stopped")
        except Exception as e:
            print(f"⚠️  Error stopping MCP services: {e}")


def run_trading_update(project_root: Path, config_path: Path, run_date: str):
    """Run main_parallel.py with the specified config"""
    print("\n" + "=" * 60)
    print(f"📅 Running trading update for date: {run_date}")
    print(f"📄 Using config: {config_path}")
    print("=" * 60 + "\n")
    
    # Set date environment variables
    os.environ["INIT_DATE"] = run_date
    os.environ["END_DATE"] = run_date
    
    # Ensure Python output is unbuffered
    os.environ["PYTHONUNBUFFERED"] = "1"
    
    # Import and run main_parallel
    sys.path.insert(0, str(project_root))
    import asyncio
    import main_parallel
    
    # Run with explicit flushing
    import sys as sys_module
    sys_module.stdout.flush()
    sys_module.stderr.flush()
    
    asyncio.run(main_parallel.main(str(config_path)))


def main():
    """Main execution flow"""
    # Get project root directory
    project_root = Path(__file__).resolve().parents[1]
    
    # Load environment variables
    env_file = project_root / ".env"
    env_example_file = project_root / ".env.example"
    
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Loaded environment variables from: {env_file}")
    elif env_example_file.exists():
        load_dotenv(env_example_file)
        print(f"⚠️  Loaded environment variables from .env.example: {env_example_file}")
    else:
        print(f"⚠️  No .env or .env.example file found")
    
    # Compute yesterday's date
    yesterday = compute_yesterday()
    print(f"\n📅 Target date: {yesterday}")
    
    # Paths
    agent_tools_path = project_root / "agent_tools"
    calendar_path = project_root / "data" / "trading_calendar" / "us_trading_days_2025Q4.json"
    config_path = project_root / "configs" / "production_config.json"
    
    # Initialize MCP manager
    mcp_manager = None
    
    try:
        # Step 1: Start all MCP services
        mcp_manager = start_mcp_services(agent_tools_path)
        
        # Step 2: Load trading calendar and check if yesterday is a trading day
        print("\n" + "=" * 60)
        print("📅 Checking trading calendar...")
        print("=" * 60)
        
        if not calendar_path.exists():
            print(f"❌ Trading calendar file not found: {calendar_path}")
            print("⚠️  Continuing anyway (trading day check skipped)")
            is_trading = True  # Continue if calendar doesn't exist
        else:
            trading_days = load_trading_calendar(calendar_path)
            is_trading = is_trading_day(yesterday, trading_days)
            
            if is_trading:
                print(f"✅ {yesterday} is a trading day")
            else:
                print(f"⏭️  {yesterday} is NOT a trading day")
                print("ℹ️  Skipping trading update")
                return
        
        # Step 3: Run trading update if it's a trading day
        if is_trading:
            run_trading_update(project_root, config_path, yesterday)
        
        print("\n✅ Trading update completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        raise
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        # Step 4: Always stop MCP services
        stop_mcp_services(mcp_manager)


if __name__ == "__main__":
    main()
