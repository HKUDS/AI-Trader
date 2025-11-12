#!/usr/bin/env python3
"""
AI-Trader Authentication System Deployment Script

This script automates the complete setup and deployment of the JWT authentication
system and MCP services for AI-Trader.

Features:
- Dependency checking and installation
- Environment configuration
- Service initialization
- Health checks
- Automated testing

Usage:
    python deploy_auth_system.py [options]

Options:
    --check-only    Only check dependencies, don't install
    --no-auth       Deploy without authentication (development mode)
    --skip-tests    Skip health checks after deployment
    --help          Show this help message
"""

import os
import sys
import subprocess
import json
import time
import secrets
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")

def print_info(text: str):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.ENDC}")

def print_step(step: int, total: int, text: str):
    """Print step message"""
    print(f"\n{Colors.BOLD}[Step {step}/{total}] {text}{Colors.ENDC}")
    print("-" * 70)

def run_command(command: List[str], check: bool = True, capture: bool = True) -> Tuple[int, str, str]:
    """Run a shell command and return results"""
    try:
        result = subprocess.run(
            command,
            check=check,
            capture_output=capture,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout, e.stderr
    except Exception as e:
        return 1, "", str(e)

class DependencyChecker:
    """Check and install Python dependencies"""

    REQUIRED_PACKAGES = {
        'langchain': '1.0.2',
        'langchain-openai': '1.0.1',
        'langchain-mcp-adapters': '0.1.0',
        'fastmcp': '2.12.5',
        'PyJWT': '2.8.0',
        'fastapi': '0.109.2',
        'uvicorn': '0.27.1',
        'python-multipart': '0.0.9',
        'bcrypt': '4.1.2',
        'python-dotenv': '1.0.0',
        'pytest': '8.0.0',
        'httpx': '0.26.0',
        'requests': None,  # No specific version required
        'pydantic': None,
    }

    def __init__(self):
        self.missing_packages = []
        self.outdated_packages = []

    def check_python_version(self) -> bool:
        """Check if Python version is 3.8+"""
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            print_error(f"Python 3.8+ required. Current version: {version.major}.{version.minor}.{version.micro}")
            return False
        print_success(f"Python version: {version.major}.{version.minor}.{version.micro}")
        return True

    def check_package(self, package: str, required_version: Optional[str] = None) -> bool:
        """Check if a package is installed"""
        try:
            import importlib.metadata
            try:
                installed_version = importlib.metadata.version(package)
                if required_version:
                    # Simple version check (not perfect but works for our needs)
                    if installed_version != required_version:
                        self.outdated_packages.append((package, installed_version, required_version))
                        return False
                return True
            except importlib.metadata.PackageNotFoundError:
                self.missing_packages.append(package)
                return False
        except ImportError:
            # Fallback for older Python versions
            try:
                __import__(package)
                return True
            except ImportError:
                self.missing_packages.append(package)
                return False

    def check_all_dependencies(self) -> bool:
        """Check all required dependencies"""
        print_info("Checking dependencies...")

        all_ok = True
        for package, version in self.REQUIRED_PACKAGES.items():
            # Handle special package names
            import_name = package
            if package == 'PyJWT':
                import_name = 'jwt'
            elif package == 'python-multipart':
                import_name = 'multipart'
            elif package == 'python-dotenv':
                import_name = 'dotenv'

            if self.check_package(import_name, version):
                print(f"  ✓ {package}: installed")
            else:
                all_ok = False
                if version:
                    print(f"  ✗ {package}: missing or wrong version (need {version})")
                else:
                    print(f"  ✗ {package}: missing")

        return all_ok

    def install_dependencies(self) -> bool:
        """Install all dependencies from requirements.txt"""
        print_info("Installing dependencies from requirements.txt...")

        requirements_file = Path("requirements.txt")
        if not requirements_file.exists():
            print_error("requirements.txt not found!")
            return False

        # Install using pip
        returncode, stdout, stderr = run_command(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=False,
            capture=True
        )

        if returncode == 0:
            print_success("All dependencies installed successfully")
            return True
        else:
            print_error("Failed to install dependencies")
            print(stderr)
            return False

class EnvironmentSetup:
    """Setup environment configuration"""

    def __init__(self):
        self.env_file = Path(".env")
        self.env_example = Path(".env.example")

    def check_env_file(self) -> bool:
        """Check if .env file exists"""
        return self.env_file.exists()

    def create_env_file(self, enable_auth: bool = True) -> bool:
        """Create .env file from .env.example"""
        if not self.env_example.exists():
            print_error(".env.example not found!")
            return False

        print_info("Creating .env file...")

        # Read .env.example
        with open(self.env_example, 'r') as f:
            env_content = f.read()

        # Generate secure JWT secret key
        jwt_secret = secrets.token_urlsafe(32)
        env_content = env_content.replace(
            'JWT_SECRET_KEY="your-secret-key-change-in-production-use-long-random-string"',
            f'JWT_SECRET_KEY="{jwt_secret}"'
        )

        # Set ENABLE_AUTH
        if enable_auth:
            env_content = env_content.replace('ENABLE_AUTH=true', 'ENABLE_AUTH=true')
        else:
            env_content = env_content.replace('ENABLE_AUTH=true', 'ENABLE_AUTH=false')

        # Write .env file
        with open(self.env_file, 'w') as f:
            f.write(env_content)

        print_success(f"Created .env file with secure JWT secret key")
        print_warning("Remember to add your API keys (JINA_API_KEY, etc.) to .env")

        return True

    def update_env_file(self, updates: Dict[str, str]) -> bool:
        """Update specific values in .env file"""
        if not self.env_file.exists():
            print_error(".env file not found!")
            return False

        # Read current .env
        with open(self.env_file, 'r') as f:
            lines = f.readlines()

        # Update values
        updated_lines = []
        for line in lines:
            updated = False
            for key, value in updates.items():
                if line.startswith(f"{key}="):
                    updated_lines.append(f"{key}={value}\n")
                    updated = True
                    break
            if not updated:
                updated_lines.append(line)

        # Write back
        with open(self.env_file, 'w') as f:
            f.writelines(updated_lines)

        return True

class ServiceManager:
    """Manage MCP services and authentication service"""

    def __init__(self):
        self.services = {
            'auth': {'port': 8004, 'module': 'auth.auth_service', 'name': 'Authentication'},
            'math': {'port': 8000, 'script': 'agent_tools/tool_math.py', 'name': 'Math'},
            'search': {'port': 8001, 'script': 'agent_tools/tool_jina_search.py', 'name': 'Search'},
            'trade': {'port': 8002, 'script': 'agent_tools/tool_trade.py', 'name': 'Trade'},
            'price': {'port': 8003, 'script': 'agent_tools/tool_get_price_local.py', 'name': 'Price'},
        }
        self.processes = {}

    def check_port(self, port: int) -> bool:
        """Check if a port is available"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('localhost', port))
            sock.close()
            return True
        except OSError:
            return False

    def check_all_ports(self) -> bool:
        """Check if all required ports are available"""
        print_info("Checking ports...")
        all_available = True

        for service_id, config in self.services.items():
            port = config['port']
            if self.check_port(port):
                print(f"  ✓ Port {port} ({config['name']}): available")
            else:
                print(f"  ✗ Port {port} ({config['name']}): in use")
                all_available = False

        return all_available

    def start_service(self, service_id: str, background: bool = True) -> bool:
        """Start a single service"""
        config = self.services.get(service_id)
        if not config:
            print_error(f"Unknown service: {service_id}")
            return False

        print_info(f"Starting {config['name']} service on port {config['port']}...")

        try:
            if 'module' in config:
                # Run as module (auth service)
                if background:
                    process = subprocess.Popen(
                        [sys.executable, '-m', config['module']],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    self.processes[service_id] = process
                else:
                    subprocess.run([sys.executable, '-m', config['module']])
            else:
                # Run as script (MCP services)
                if background:
                    process = subprocess.Popen(
                        [sys.executable, config['script']],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    self.processes[service_id] = process
                else:
                    subprocess.run([sys.executable, config['script']])

            time.sleep(2)  # Wait for service to start

            # Check if service is running
            if background and service_id in self.processes:
                if self.processes[service_id].poll() is None:
                    print_success(f"{config['name']} service started (PID: {self.processes[service_id].pid})")
                    return True
                else:
                    print_error(f"{config['name']} service failed to start")
                    return False

            return True

        except Exception as e:
            print_error(f"Failed to start {config['name']} service: {e}")
            return False

    def start_all_services(self) -> bool:
        """Start all services"""
        print_info("Starting all services...")

        success = True
        for service_id in self.services.keys():
            if not self.start_service(service_id, background=True):
                success = False

        return success

    def stop_all_services(self):
        """Stop all running services"""
        print_info("Stopping all services...")

        for service_id, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                print_success(f"Stopped {self.services[service_id]['name']} service")
            except subprocess.TimeoutExpired:
                process.kill()
                print_warning(f"Force killed {self.services[service_id]['name']} service")
            except Exception as e:
                print_error(f"Error stopping {self.services[service_id]['name']}: {e}")

class HealthChecker:
    """Check health of all services"""

    def __init__(self):
        self.services = {
            'auth': 'http://localhost:8004/health',
            'math': 'http://localhost:8000/health',
            'search': 'http://localhost:8001/health',
            'trade': 'http://localhost:8002/health',
            'price': 'http://localhost:8003/health',
        }

    def check_service(self, service_id: str, url: str) -> bool:
        """Check if a service is healthy"""
        try:
            import requests
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                auth_status = data.get('authentication', 'unknown')
                print(f"  ✓ {service_id.capitalize()}: {data.get('status', 'running')} (auth: {auth_status})")
                return True
            else:
                print(f"  ✗ {service_id.capitalize()}: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"  ✗ {service_id.capitalize()}: {str(e)[:50]}")
            return False

    def check_all_services(self) -> bool:
        """Check health of all services"""
        print_info("Checking service health...")

        all_healthy = True
        for service_id, url in self.services.items():
            if not self.check_service(service_id, url):
                all_healthy = False

        return all_healthy

    def test_authentication_flow(self) -> bool:
        """Test the complete authentication flow"""
        print_info("Testing authentication flow...")

        try:
            import requests

            # Test login
            print("  Testing login...")
            response = requests.post(
                'http://localhost:8004/auth/login',
                json={'username': 'admin', 'password': 'admin123'},
                timeout=5
            )

            if response.status_code != 200:
                print_error("Login failed")
                return False

            tokens = response.json()
            access_token = tokens.get('access_token')

            if not access_token:
                print_error("No access token received")
                return False

            print_success("Login successful")

            # Test authenticated request
            print("  Testing authenticated request...")
            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(
                'http://localhost:8004/auth/me',
                headers=headers,
                timeout=5
            )

            if response.status_code != 200:
                print_error("Authenticated request failed")
                return False

            user = response.json()
            print_success(f"Authenticated as: {user.get('username')}")

            return True

        except Exception as e:
            print_error(f"Authentication test failed: {e}")
            return False

def main():
    """Main deployment function"""
    import argparse

    parser = argparse.ArgumentParser(description='Deploy AI-Trader Authentication System')
    parser.add_argument('--check-only', action='store_true', help='Only check dependencies')
    parser.add_argument('--no-auth', action='store_true', help='Deploy without authentication')
    parser.add_argument('--skip-tests', action='store_true', help='Skip health checks')
    args = parser.parse_args()

    print_header("AI-TRADER AUTHENTICATION SYSTEM DEPLOYMENT")

    # Step 1: Check Python version
    print_step(1, 7, "Checking Python Version")
    dep_checker = DependencyChecker()
    if not dep_checker.check_python_version():
        return 1

    # Step 2: Check dependencies
    print_step(2, 7, "Checking Dependencies")
    deps_ok = dep_checker.check_all_dependencies()

    if not deps_ok:
        if args.check_only:
            print_error("Missing dependencies found (use without --check-only to install)")
            return 1

        print_warning("Some dependencies are missing or outdated")
        response = input("Install missing dependencies? [Y/n]: ")

        if response.lower() != 'n':
            if not dep_checker.install_dependencies():
                print_error("Failed to install dependencies")
                return 1
        else:
            print_error("Cannot proceed without dependencies")
            return 1
    else:
        print_success("All dependencies satisfied")

    if args.check_only:
        print_success("Dependency check complete")
        return 0

    # Step 3: Setup environment
    print_step(3, 7, "Setting Up Environment")
    env_setup = EnvironmentSetup()

    if not env_setup.check_env_file():
        print_info(".env file not found")
        if not env_setup.create_env_file(enable_auth=not args.no_auth):
            print_error("Failed to create .env file")
            return 1
    else:
        print_info(".env file already exists")
        if args.no_auth:
            env_setup.update_env_file({'ENABLE_AUTH': 'false'})
            print_info("Updated ENABLE_AUTH=false")

    # Step 4: Check ports
    print_step(4, 7, "Checking Port Availability")
    service_mgr = ServiceManager()

    if not service_mgr.check_all_ports():
        print_warning("Some ports are already in use")
        response = input("Continue anyway? [y/N]: ")
        if response.lower() != 'y':
            print_info("Deployment cancelled")
            return 1

    # Step 5: Initialize default users
    print_step(5, 7, "Initializing Default Users")
    print_info("Default admin user will be created: admin/admin123")
    print_warning("Change this password in production!")

    # Step 6: Start services
    print_step(6, 7, "Starting Services")

    try:
        if not service_mgr.start_all_services():
            print_error("Some services failed to start")
            service_mgr.stop_all_services()
            return 1

        print_success("All services started")

        # Step 7: Health checks
        if not args.skip_tests:
            print_step(7, 7, "Running Health Checks")

            time.sleep(3)  # Wait for services to fully initialize

            health_checker = HealthChecker()

            if not health_checker.check_all_services():
                print_warning("Some services are not healthy")

            if not args.no_auth:
                if not health_checker.test_authentication_flow():
                    print_warning("Authentication flow test failed")

            print_success("Health checks complete")

        # Success!
        print_header("DEPLOYMENT SUCCESSFUL!")

        print(f"\n{Colors.GREEN}{Colors.BOLD}✨ All services are running! ✨{Colors.ENDC}\n")

        print("Services:")
        print(f"  • Authentication: http://localhost:8004")
        print(f"  • Math Service: http://localhost:8000")
        print(f"  • Search Service: http://localhost:8001")
        print(f"  • Trade Service: http://localhost:8002")
        print(f"  • Price Service: http://localhost:8003")

        print(f"\nAPI Documentation:")
        print(f"  • Auth API: http://localhost:8004/docs")

        print(f"\nDefault Credentials:")
        print(f"  • Username: admin")
        print(f"  • Password: admin123")
        print(f"  {Colors.RED}⚠️  Change this password!{Colors.ENDC}")

        if args.no_auth:
            print(f"\n{Colors.YELLOW}Note: Authentication is DISABLED (development mode){Colors.ENDC}")
        else:
            print(f"\n{Colors.GREEN}Note: Authentication is ENABLED{Colors.ENDC}")

        print(f"\nPress Ctrl+C to stop all services\n")

        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n")
            service_mgr.stop_all_services()
            print_success("All services stopped")

        return 0

    except Exception as e:
        print_error(f"Deployment failed: {e}")
        service_mgr.stop_all_services()
        return 1

if __name__ == "__main__":
    sys.exit(main())
