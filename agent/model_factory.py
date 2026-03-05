"""
Model factory - creates the appropriate LangChain chat model based on provider.

Supports:
- Anthropic (Claude): uses langchain-anthropic ChatAnthropic
- DeepSeek: uses custom DeepSeekChatOpenAI wrapper
- OpenAI and others: uses langchain-openai ChatOpenAI
"""

import json
import os
from typing import Optional

from langchain_openai import ChatOpenAI


class DeepSeekChatOpenAI(ChatOpenAI):
    """Custom ChatOpenAI wrapper for DeepSeek API compatibility."""

    def _create_message_dicts(self, messages: list, stop: Optional[list] = None) -> list:
        message_dicts = super()._create_message_dicts(messages, stop)
        for message_dict in message_dicts:
            if "tool_calls" in message_dict:
                for tool_call in message_dict["tool_calls"]:
                    if "function" in tool_call and "arguments" in tool_call["function"]:
                        args = tool_call["function"]["arguments"]
                        if isinstance(args, str):
                            try:
                                tool_call["function"]["arguments"] = json.loads(args)
                            except json.JSONDecodeError:
                                pass
        return message_dicts

    def _generate(self, messages: list, stop: Optional[list] = None, **kwargs):
        result = super()._generate(messages, stop, **kwargs)
        for generation in result.generations:
            for gen in generation:
                if hasattr(gen, "message") and hasattr(gen.message, "additional_kwargs"):
                    tool_calls = gen.message.additional_kwargs.get("tool_calls")
                    if tool_calls:
                        for tool_call in tool_calls:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                args = tool_call["function"]["arguments"]
                                if isinstance(args, str):
                                    try:
                                        tool_call["function"]["arguments"] = json.loads(args)
                                    except json.JSONDecodeError:
                                        pass
        return result

    async def _agenerate(self, messages: list, stop: Optional[list] = None, **kwargs):
        result = await super()._agenerate(messages, stop, **kwargs)
        for generation in result.generations:
            for gen in generation:
                if hasattr(gen, "message") and hasattr(gen.message, "additional_kwargs"):
                    tool_calls = gen.message.additional_kwargs.get("tool_calls")
                    if tool_calls:
                        for tool_call in tool_calls:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                args = tool_call["function"]["arguments"]
                                if isinstance(args, str):
                                    try:
                                        tool_call["function"]["arguments"] = json.loads(args)
                                    except json.JSONDecodeError:
                                        pass
        return result


def is_anthropic_model(basemodel: str) -> bool:
    """Check if the model string refers to an Anthropic Claude model."""
    lower = basemodel.lower()
    return "anthropic/" in lower or "claude" in lower


def create_llm_model(
    basemodel: str,
    openai_base_url: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    max_retries: int = 3,
    timeout: int = 60,
):
    """
    Create the appropriate LangChain chat model based on the basemodel string.

    For Anthropic models (basemodel contains 'anthropic/' or 'claude'):
      - Uses ChatAnthropic from langchain-anthropic
      - API key from ANTHROPIC_API_KEY env var or openai_api_key param

    For DeepSeek models:
      - Uses custom DeepSeekChatOpenAI wrapper

    For all others (OpenAI, Qwen, Gemini via OpenAI-compatible endpoints):
      - Uses standard ChatOpenAI
    """
    if is_anthropic_model(basemodel):
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "langchain-anthropic is required for Anthropic models. "
                "Install it with: pip install langchain-anthropic"
            )

        # Extract the model name (strip 'anthropic/' prefix if present)
        model_name = basemodel
        if model_name.lower().startswith("anthropic/"):
            model_name = model_name[len("anthropic/"):]

        # API key: prefer explicit param, then env var
        api_key = openai_api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Anthropic API key not set. "
                "Set ANTHROPIC_API_KEY in your .env file or pass it in the config."
            )

        print(f"  Using Anthropic ChatAnthropic for model: {model_name}")
        return ChatAnthropic(
            model=model_name,
            anthropic_api_key=api_key,
            max_retries=max_retries,
            default_request_timeout=timeout,
        )

    elif "deepseek" in basemodel.lower():
        print(f"  Using DeepSeek-compatible ChatOpenAI for model: {basemodel}")
        return DeepSeekChatOpenAI(
            model=basemodel,
            base_url=openai_base_url,
            api_key=openai_api_key,
            max_retries=max_retries,
            timeout=timeout,
        )

    else:
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "API key not set. Set OPENAI_API_KEY in your .env file or pass it in the config."
            )
        print(f"  Using ChatOpenAI for model: {basemodel}")
        return ChatOpenAI(
            model=basemodel,
            base_url=openai_base_url,
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout,
        )
