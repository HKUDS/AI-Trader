#!/usr/bin/env python3
"""
MCP Service Startup Script (Python Version)
Start all four MCP services: Math, Search, TradeTools, LocalPrices
"""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class MCPServiceManager:
    def __init__(self):
        self.services = {}
        self.running = True

        # Set default ports
        self.ports = {
            "math": int(os.getenv("MATH_HTTP_PORT", "8000")),
            "search": int(os.getenv("SEARCH_HTTP_PORT", "8001")),
            "trade": int(os.getenv("TRADE_HTTP_PORT", "8002")),
            "price": int(os.getenv("GETPRICE_HTTP_PORT", "8003")),
            "crypto": int(os.getenv("CRYPTO_HTTP_PORT", "8005")),
        }

        # Service configurations
        mcp_server_dir = os.path.dirname(os.path.abspath(__file__))
        self.service_configs = {
            "math": {"script": os.path.join(mcp_server_dir, "tool_math.py"), "name": "Math", "port": self.ports["math"]},
            # "search": {"script": "tool_jina_search.py", "name": "Search", "port": self.ports["search"]},
            "search": {"script": os.path.join(mcp_server_dir, "tool_alphavantage_news.py"), "name": "Search", "port": self.ports["search"]},  
            "trade": {"script": os.path.join(mcp_server_dir, "tool_trade.py"), "name": "TradeTools", "port": self.ports["trade"]},
            "price": {"script": os.path.join(mcp_server_dir, "tool_get_price_local.py"), "name": "LocalPrices", "port": self.ports["price"]},
            "crypto": {"script": os.path.join(mcp_server_dir, "tool_crypto_trade.py"), "name": "CryptoTradeTools", "port": self.ports["crypto"]},
        }

        # Create logs directory
        self.log_dir = Path("../logs")
        self.log_dir.mkdir(exist_ok=True)

        # Set signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle interrupt signals"""
        print("\n🛑 Received stop signal, shutting down all services...")
        self.stop_all_services()
        sys.exit(0)

    def is_port_available(self, port):
        """Check if a port is available"""
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            sock.close()
            return result != 0  # Port is available if connection failed
        except:
            return False

    def check_port_conflicts(self):
        """Check for port conflicts before starting services"""
        conflicts = []
        for service_id, config in self.service_configs.items():
            port = config["port"]
            if not self.is_port_available(port):
                conflicts.append((config["name"], port))

        if conflicts:
            print("⚠️  Port conflicts detected:")
            for name, port in conflicts:
                print(f"   - {name}: Port {port} is already in use")

            import socket

            response = input("\n❓ Do you want to automatically find available ports? (y/n): ")
            if response.lower() == "y":
                for service_id, config in self.service_configs.items():
                    port = config["port"]
                    if not self.is_port_available(port):
                        # Find next available port
                        new_port = port
                        while not self.is_port_available(new_port):
                            new_port += 1
                            if new_port > port + 100:  # Limit search range
                                print(f"❌ Could not find available port for {config['name']}")
                                return False
                        print(f"   ✅ {config['name']}: Changed port from {port} to {new_port}")
                        config["port"] = new_port
                        self.ports[service_id] = new_port
                return True
            else:
                print("\n💡 Tip: Stop the conflicting services or change port configuration")
                return False
        return True

    def start_service(self, service_id, config):
        """Start a single service"""
        script_path = config["script"]
        service_name = config["name"]
        port = config["port"]

        if not Path(script_path).exists():
            print(f"❌ Script file not found: {script_path}")
            return False

        try:
            # Start service process
            log_file = self.log_dir / f"{service_id}.log"
            with open(log_file, "w") as f:
                process = subprocess.Popen(
                    [sys.executable, script_path], stdout=f, stderr=subprocess.STDOUT, cwd=os.getcwd()
                )

            self.services[service_id] = {"process": process, "name": service_name, "port": port, "log_file": log_file}

            print(f"✅ {service_name} service started (PID: {process.pid}, Port: {port})")
            return True

        except Exception as e:
            print(f"❌ Failed to start {service_name} service: {e}")
            return False

    def check_service_health(self, service_id):
        """Check service health status"""
        if service_id not in self.services:
            return False

        service = self.services[service_id]
        process = service["process"]
        port = service["port"]

        # Check if process is still running
        if process.poll() is not None:
            return False

        # Check if port is responding (simple check)
        try:
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            sock.close()
            return result == 0
        except:
            return False

    def start_all_services(self):
        """Start all services"""
        print("🚀 Starting MCP services...")
        print("=" * 50)

        # Check for port conflicts
        if not self.check_port_conflicts():
            print("\n❌ Cannot start services due to port conflicts")
            return

        print(f"\n📊 Port configuration:")
        for service_id, config in self.service_configs.items():
            print(f"  - {config['name']}: {config['port']}")

        print("\n🔄 Starting services...")

        # Start all services
        success_count = 0
        for service_id, config in self.service_configs.items():
            if self.start_service(service_id, config):
                success_count += 1

        if success_count == 0:
            print("\n❌ No services started successfully")
            return

        # Wait for services to start
        print("\n⏳ Waiting for services to start...")
        time.sleep(3)

        # Check service status
        print("\n🔍 Checking service status...")
        healthy_count = self.check_all_services()

        if healthy_count > 0:
            print(f"\n🎉 {healthy_count}/{len(self.services)} MCP services running!")
            self.print_service_info()
            # Keep running
            self.keep_alive()
        else:
            print("\n❌ All services failed to start properly")
            self.stop_all_services()

    def check_all_services(self):
        """Check all service status and return count of healthy services"""
        healthy_count = 0
        for service_id, service in self.services.items():
            if self.check_service_health(service_id):
                print(f"✅ {service['name']} service running normally")
                healthy_count += 1
            else:
                print(f"❌ {service['name']} service failed to start")
                print(f"   Please check logs: {service['log_file']}")
        return healthy_count

    def print_service_info(self):
        """Print service information"""
        print("\n📋 Service information:")
        for service_id, service in self.services.items():
            print(f"  - {service['name']}: http://localhost:{service['port']} (PID: {service['process'].pid})")

        print(f"\n📁 Log files location: {self.log_dir.absolute()}")
        print("\n🛑 Press Ctrl+C to stop all services")

    def keep_alive(self):
        """Keep services running"""
        try:
            while self.running:
                time.sleep(5)

                # Check service status
                stopped_services = []
                for service_id, service in self.services.items():
                    if service["process"].poll() is not None:
                        stopped_services.append(service["name"])

                if stopped_services:
                    print(f"\n⚠️  Following service(s) stopped unexpectedly: {', '.join(stopped_services)}")
                    print(f"📋 Active services: {len(self.services) - len(stopped_services)}/{len(self.services)}")

                    # Only stop all if all services have failed
                    if len(stopped_services) == len(self.services):
                        print("❌ All services have stopped, shutting down...")
                        self.running = False
                        break

        except KeyboardInterrupt:
            pass
        finally:
            self.stop_all_services()

    def stop_all_services(self):
        """Stop all services"""
        print("\n🛑 Stopping all services...")

        for service_id, service in self.services.items():
            try:
                service["process"].terminate()
                service["process"].wait(timeout=5)
                print(f"✅ {service['name']} service stopped")
            except subprocess.TimeoutExpired:
                service["process"].kill()
                print(f"🔨 {service['name']} service force stopped")
            except Exception as e:
                print(f"❌ Error stopping {service['name']} service: {e}")

        print("✅ All services stopped")

    def status(self):
        """Display service status"""
        print("📊 MCP Service Status Check")
        print("=" * 30)

        for service_id, config in self.service_configs.items():
            if service_id in self.services:
                service = self.services[service_id]
                if self.check_service_health(service_id):
                    print(f"✅ {config['name']} service running normally (Port: {config['port']})")
                else:
                    print(f"❌ {config['name']} service abnormal (Port: {config['port']})")
            else:
                print(f"❌ {config['name']} service not started (Port: {config['port']})")


def main():
    """Main function"""
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        # Status check mode
        manager = MCPServiceManager()
        manager.status()
    else:
        # Startup mode
        manager = MCPServiceManager()
        manager.start_all_services()


if __name__ == "__main__":
    main()
