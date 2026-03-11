"""
Automatic Environment Detection

Detects: local, codespaces, vps, docker
Auto-configures based on environment
"""

import os
import platform
from pathlib import Path
from typing import Dict, Optional


def detect_environment() -> str:
    """
    Detect current runtime environment
    
    Returns:
        Environment name: local, codespaces, vps, docker, unknown
    """
    
    # Check GitHub Codespaces
    if os.getenv("CODESPACES") == "true":
        return "codespaces"
    
    # Check if running in Docker
    if os.path.exists("/.dockerenv"):
        return "docker"
    
    # Check if VPS (common indicators)
    if os.path.exists("/proc/vz"):  # OpenVZ
        return "vps"
    
    if os.path.exists("/proc/xen"):  # Xen
        return "vps"
    
    # Check for cloud providers
    try:
        with open("/sys/class/dmi/id/product_name", "r") as f:
            product = f.read().strip().lower()
            if any(cloud in product for cloud in ["google", "amazon", "azure", "oracle", "digitalocean"]):
                return "vps"
    except:
        pass
    
    # Check hostname patterns
    hostname = platform.node().lower()
    if any(pattern in hostname for pattern in ["vps", "server", "cloud", "vm"]):
        return "vps"
    
    # Default to local
    return "local"


def get_environment_config(env: Optional[str] = None) -> Dict[str, any]:
    """
    Get configuration for detected environment
    
    Args:
        env: Environment name (auto-detect if None)
        
    Returns:
        Configuration dictionary
    """
    if env is None:
        env = detect_environment()
    
    configs = {
        "local": {
            "testnet": True,
            "log_level": "DEBUG",
            "data_path": "./data/crypto",
            "cache_enabled": True,
            "max_parallel": 1,
            "recommended_interval": "1m",
            "recommended_api": "github_models"
        },
        "codespaces": {
            "testnet": False,
            "log_level": "INFO",
            "data_path": "/workspace/data/crypto",
            "cache_enabled": True,
            "max_parallel": 2,
            "recommended_interval": "1m",
            "recommended_api": "github_models"
        },
        "vps": {
            "testnet": False,
            "log_level": "INFO",
            "data_path": "/var/ai-trader/data/crypto",
            "cache_enabled": True,
            "max_parallel": 4,
            "recommended_interval": "30s",
            "recommended_api": "openai"
        },
        "docker": {
            "testnet": True,
            "log_level": "INFO",
            "data_path": "/app/data/crypto",
            "cache_enabled": True,
            "max_parallel": 2,
            "recommended_interval": "1m",
            "recommended_api": "anthropic"
        }
    }
    
    return configs.get(env, configs["local"])


def print_environment_info():
    """Print detected environment information"""
    env = detect_environment()
    config = get_environment_config(env)
    
    print("=" * 60)
    print("🌐 ENVIRONMENT DETECTION")
    print("=" * 60)
    print(f"Environment: {env.upper()}")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {platform.python_version()}")
    print(f"Hostname: {platform.node()}")
    print("\n📋 Recommended Configuration:")
    for key, value in config.items():
        print(f"   - {key}: {value}")
    print("=" * 60)
    
    return env, config


def setup_environment():
    """
    Setup environment variables based on detection
    
    Returns:
        Environment name
    """
    env, config = print_environment_info()
    
    # Set environment variables if not already set
    if not os.getenv("RUNTIME_ENV"):
        os.environ["RUNTIME_ENV"] = env
    
    if not os.getenv("TESTNET_MODE"):
        os.environ["TESTNET_MODE"] = str(config["testnet"])
    
    # Create data directory if needed
    data_path = Path(config["data_path"])
    data_path.mkdir(parents=True, exist_ok=True)
    
    print(f"\n✅ Environment configured: {env}")
    
    return env


if __name__ == "__main__":
    setup_environment()