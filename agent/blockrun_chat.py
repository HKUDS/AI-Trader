"""
BlockRun.AI LangChain Integration
=================================

LangChain-compatible ChatOpenAI wrapper that uses BlockRun.AI for LLM access.
Pay-per-request via x402 micropayments on Base chain.

SECURITY: Your private key NEVER leaves your machine.
It's only used for local EIP-712 signing - only signatures are sent.

Usage:
    from agent.blockrun_chat import BlockRunChat

    model = BlockRunChat(
        model="openai/gpt-4o",  # or anthropic/claude-sonnet-4, google/gemini-2.5-pro
        blockrun_wallet_key="0x...",  # or set BLOCKRUN_WALLET_KEY env var
    )

Available Models:
    - openai/gpt-4o, openai/gpt-4o-mini, openai/o1, openai/o3-mini
    - anthropic/claude-sonnet-4, anthropic/claude-3-5-sonnet
    - google/gemini-2.5-pro, google/gemini-2.5-flash
    - deepseek/deepseek-chat, deepseek/deepseek-reasoner
    - x-ai/grok-3

Docs: https://blockrun.ai/docs
"""

import os
from typing import Any, Dict, List, Optional, Iterator, AsyncIterator

from langchain_core.callbacks import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class BlockRunChat(BaseChatModel):
    """
    LangChain ChatModel that uses BlockRun.AI gateway.

    BlockRun provides pay-per-request access to multiple LLM providers
    (OpenAI, Anthropic, Google, DeepSeek) via x402 micropayments on Base chain.

    Attributes:
        model: Model identifier (e.g., "openai/gpt-4o", "anthropic/claude-sonnet-4")
        blockrun_wallet_key: Base chain wallet private key for payments
        max_tokens: Maximum tokens to generate (this determines the price)
        temperature: Sampling temperature
    """

    model: str = "openai/gpt-4o"
    blockrun_wallet_key: Optional[str] = None
    blockrun_api_url: str = "https://blockrun.ai/api"
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 120.0

    _client: Any = None  # BlockRun SDK client

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_client()

    def _init_client(self):
        """Initialize the BlockRun SDK client."""
        try:
            from blockrun_llm import LLMClient
        except ImportError:
            raise ImportError(
                "blockrun-llm package not installed. "
                "Install with: pip install blockrun-llm"
            )

        # Get wallet key from param or environment
        wallet_key = self.blockrun_wallet_key or os.environ.get("BLOCKRUN_WALLET_KEY")
        if not wallet_key:
            raise ValueError(
                "BlockRun requires a wallet private key. "
                "Set BLOCKRUN_WALLET_KEY in .env or pass blockrun_wallet_key parameter. "
                "NOTE: Your key never leaves your machine - only signatures are sent."
            )

        self._client = LLMClient(
            private_key=wallet_key,
            api_url=self.blockrun_api_url,
            timeout=self.timeout,
        )

    @property
    def _llm_type(self) -> str:
        return "blockrun"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

    def _convert_messages(self, messages: List[BaseMessage]) -> List[Dict[str, str]]:
        """Convert LangChain messages to BlockRun format."""
        result = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})
            else:
                # Default to user for unknown message types
                result.append({"role": "user", "content": str(msg.content)})
        return result

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a response using BlockRun."""
        # Convert messages
        msg_list = self._convert_messages(messages)

        # Call BlockRun SDK
        response = self._client.chat_completion(
            model=self.model,
            messages=msg_list,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
        )

        # Extract response content
        content = response.choices[0].message.content

        # Handle tool calls if present
        additional_kwargs = {}
        if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
            additional_kwargs["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in response.choices[0].message.tool_calls
            ]

        # Create AIMessage
        message = AIMessage(
            content=content,
            additional_kwargs=additional_kwargs,
        )

        # Build generation
        generation = ChatGeneration(
            message=message,
            generation_info={
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                } if response.usage else {},
            },
        )

        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generate - falls back to sync for now."""
        # BlockRun SDK sync client used in async context
        # TODO: Use AsyncLLMClient when needed
        return self._generate(messages, stop, None, **kwargs)

    def get_wallet_address(self) -> str:
        """Get the wallet address being used for payments."""
        return self._client.get_wallet_address()

    def bind_tools(self, tools: List[Any], **kwargs) -> "BlockRunChat":
        """Bind tools to the model for function calling."""
        # For now, return self - tool handling is done at the agent level
        # BlockRun passes through tool calls from underlying models
        return self
