"""
Simple main script for AI-Trader without MCP tools
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from agent.simple_agent.simple_agent import SimpleAgent
from prompts.agent_prompt import all_nasdaq_100_symbols


async def main(config_path: str):
    """Main function"""
    
    # Load configuration
    print(f"📄 Loading configuration from: {config_path}")
    with open(config_path, "r") as f:
        config = json.load(f)
    
    print(f"✅ Configuration loaded successfully")
    
    # Extract configuration
    agent_type = config.get("agent_type", "SimpleAgent")
    market = config.get("market", "us")
    date_range = config.get("date_range", {})
    models = config.get("models", [])
    agent_config = config.get("agent_config", {})
    log_config = config.get("log_config", {})
    
    INIT_DATE = date_range.get("init_date")
    END_DATE = date_range.get("end_date")
    
    # Agent configuration
    max_steps = agent_config.get("max_steps", 1)
    max_retries = agent_config.get("max_retries", 3)
    base_delay = agent_config.get("base_delay", 1.0)
    initial_cash = agent_config.get("initial_cash", 10000.0)
    
    # Log configuration
    log_path = log_config.get("log_path", "./data/agent_data")
    
    print(f"\n{'='*60}")
    print(f"🚀 Starting AI-Trader (Simple Mode - No MCP)")
    print(f"{'='*60}")
    print(f"📅 Date range: {INIT_DATE} to {END_DATE}")
    print(f"🌍 Market: {market}")
    print(f"💰 Initial cash: ${initial_cash:,.2f}")
    print(f"📊 Max steps per day: {max_steps}")
    print(f"🔄 Max retries: {max_retries}")
    
    # Get enabled models
    enabled_models = [m for m in models if m.get("enabled", False)]
    
    if not enabled_models:
        print("❌ No enabled models found in configuration!")
        return
    
    print(f"🤖 Models to run: {[m['name'] for m in enabled_models]}")
    
    # Stock symbols
    stock_symbols = all_nasdaq_100_symbols
    print(f"📈 Tracking {len(stock_symbols)} stocks")
    
    # Process each model
    for model_config in enabled_models:
        model_name = model_config.get("name", "unknown")
        basemodel = model_config.get("basemodel")
        signature = model_config.get("signature")
        openai_base_url = model_config.get("openai_base_url")
        openai_api_key = model_config.get("openai_api_key")
        
        if not basemodel or not signature:
            print(f"❌ Model {model_name} missing required fields")
            continue
        
        print(f"\n{'='*60}")
        print(f"🤖 Processing model: {model_name}")
        print(f"📝 Signature: {signature}")
        print(f"🔧 BaseModel: {basemodel}")
        print(f"{'='*60}")
        
        try:
            # Create agent
            agent = SimpleAgent(
                signature=signature,
                basemodel=basemodel,
                stock_symbols=stock_symbols,
                log_path=log_path,
                max_steps=max_steps,
                max_retries=max_retries,
                base_delay=base_delay,
                initial_cash=initial_cash,
                market=market,
                openai_base_url=openai_base_url,
                openai_api_key=openai_api_key,
            )
            
            print(f"✅ Agent created successfully")
            
            # Run trading
            await agent.run_date_range(INIT_DATE, END_DATE)
            
            print(f"✅ {model_name} ({signature}) completed successfully")
        
        except Exception as e:
            print(f"❌ Error processing {model_name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n{'='*60}")
    print(f"✅ All models processed")
    print(f"{'='*60}")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/default_config.json"
    
    if not os.path.exists(config_path):
        print(f"❌ Configuration file not found: {config_path}")
        sys.exit(1)
    
    asyncio.run(main(config_path))
