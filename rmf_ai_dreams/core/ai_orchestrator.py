"""
AI Orchestrator - دمج متعدد نماذج الذكاء الاصطناعي
يدير GPT, Claude, Gemini, Mistral ويختار الأنسب لكل مهمة
"""
import os
import json
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass
import asyncio
from enum import Enum


class AIProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    MISTRAL = "mistral"


@dataclass
class ModelCapability:
    """قدرات نموذج معين"""
    provider: AIProvider
    model_name: str
    strengths: List[str]
    weaknesses: List[str]
    cost_per_1k_tokens: float
    speed_rating: int  # 1-10
    quality_rating: int  # 1-10
    context_window: int
    supports_streaming: bool
    supports_functions: bool


@dataclass
class AIRequest:
    """طلب للذكاء الاصطناعي"""
    task_type: str
    prompt: str
    context: Optional[Dict] = None
    max_tokens: int = 4000
    temperature: float = 0.7
    preferred_provider: Optional[AIProvider] = None
    require_streaming: bool = False
    require_functions: bool = False


@dataclass
class AIResponse:
    """استجابة من الذكاء الاصطناعي"""
    provider: AIProvider
    model: str
    content: str
    tokens_used: int
    cost: float
    latency_seconds: float
    confidence: float
    metadata: Dict[str, Any]


class AIOrchestrator:
    """
    منسق الذكاء الاصطناعي - يختار أفضل نموذج لكل مهمة
    """

    def __init__(self):
        self.models = self._register_models()
        self.usage_stats: Dict[str, Any] = {
            'total_requests': 0,
            'total_cost': 0.0,
            'by_provider': {}
        }

    def _register_models(self) -> List[ModelCapability]:
        """تسجيل النماذج المتاحة"""
        return [
            # OpenAI GPT-4
            ModelCapability(
                provider=AIProvider.OPENAI,
                model_name="gpt-4-turbo-preview",
                strengths=["reasoning", "coding", "analysis", "creative_writing"],
                weaknesses=["cost"],
                cost_per_1k_tokens=0.03,
                speed_rating=7,
                quality_rating=10,
                context_window=128000,
                supports_streaming=True,
                supports_functions=True
            ),
            # OpenAI GPT-3.5
            ModelCapability(
                provider=AIProvider.OPENAI,
                model_name="gpt-3.5-turbo",
                strengths=["speed", "cost_effective", "general_tasks"],
                weaknesses=["complex_reasoning"],
                cost_per_1k_tokens=0.002,
                speed_rating=10,
                quality_rating=7,
                context_window=16000,
                supports_streaming=True,
                supports_functions=True
            ),
            # Anthropic Claude
            ModelCapability(
                provider=AIProvider.ANTHROPIC,
                model_name="claude-3-opus-20240229",
                strengths=["reasoning", "long_context", "nuanced_understanding", "safety"],
                weaknesses=["cost", "speed"],
                cost_per_1k_tokens=0.015,
                speed_rating=6,
                quality_rating=10,
                context_window=200000,
                supports_streaming=True,
                supports_functions=True
            ),
            # Anthropic Claude Sonnet
            ModelCapability(
                provider=AIProvider.ANTHROPIC,
                model_name="claude-3-sonnet-20240229",
                strengths=["balanced", "coding", "analysis"],
                weaknesses=[],
                cost_per_1k_tokens=0.003,
                speed_rating=8,
                quality_rating=8,
                context_window=200000,
                supports_streaming=True,
                supports_functions=True
            ),
            # Google Gemini
            ModelCapability(
                provider=AIProvider.GOOGLE,
                model_name="gemini-pro",
                strengths=["multimodal", "reasoning", "free_tier"],
                weaknesses=["availability"],
                cost_per_1k_tokens=0.00025,
                speed_rating=9,
                quality_rating=8,
                context_window=32000,
                supports_streaming=True,
                supports_functions=True
            ),
            # Mistral
            ModelCapability(
                provider=AIProvider.MISTRAL,
                model_name="mistral-large-latest",
                strengths=["reasoning", "coding", "cost_effective", "privacy"],
                weaknesses=["availability"],
                cost_per_1k_tokens=0.008,
                speed_rating=8,
                quality_rating=8,
                context_window=32000,
                supports_streaming=True,
                supports_functions=True
            )
        ]

    def select_model(self, request: AIRequest) -> ModelCapability:
        """
        اختيار أفضل نموذج بناءً على المهمة

        Args:
            request: طلب الذكاء الاصطناعي

        Returns:
            النموذج الأنسب
        """
        # إذا حدد المستخدم provider معين
        if request.preferred_provider:
            candidates = [
                m for m in self.models
                if m.provider == request.preferred_provider
            ]
        else:
            candidates = self.models

        # فلترة بناءً على المتطلبات
        if request.require_streaming:
            candidates = [m for m in candidates if m.supports_streaming]

        if request.require_functions:
            candidates = [m for m in candidates if m.supports_functions]

        # فلترة بناءً على context window
        if request.context:
            estimated_tokens = len(str(request.context)) // 4  # تقريبي
            candidates = [
                m for m in candidates
                if m.context_window >= estimated_tokens + request.max_tokens
            ]

        if not candidates:
            # fallback
            return self.models[0]

        # تسجيل نقاط لكل نموذج
        scored = []
        for model in candidates:
            score = self._calculate_model_score(model, request)
            scored.append((score, model))

        # اختيار الأعلى
        scored.sort(reverse=True, key=lambda x: x[0])
        return scored[0][1]

    def _calculate_model_score(
        self,
        model: ModelCapability,
        request: AIRequest
    ) -> float:
        """حساب نقاط النموذج للمهمة"""
        score = 0.0

        # مطابقة القوة مع نوع المهمة
        task_type = request.task_type

        strength_match = {
            'code_generation': ['coding', 'reasoning'],
            'text_analysis': ['analysis', 'reasoning'],
            'creative_writing': ['creative_writing'],
            'data_extraction': ['reasoning', 'analysis'],
            'planning': ['reasoning', 'long_context'],
            'quick_task': ['speed', 'cost_effective']
        }

        required_strengths = strength_match.get(task_type, [])

        for strength in required_strengths:
            if strength in model.strengths:
                score += 30

        # السرعة
        score += model.speed_rating * 2

        # الجودة
        score += model.quality_rating * 3

        # التكلفة (أقل = أفضل)
        cost_score = 10 - (model.cost_per_1k_tokens * 100)
        score += max(0, cost_score)

        return score

    async def execute(self, request: AIRequest) -> AIResponse:
        """
        تنفيذ طلب ذكاء اصطناعي

        Args:
            request: الطلب

        Returns:
            الاستجابة
        """
        # اختيار النموذج
        model = self.select_model(request)

        # تنفيذ
        start_time = asyncio.get_event_loop().time()

        try:
            if model.provider == AIProvider.OPENAI:
                response = await self._call_openai(model, request)
            elif model.provider == AIProvider.ANTHROPIC:
                response = await self._call_anthropic(model, request)
            elif model.provider == AIProvider.GOOGLE:
                response = await self._call_google(model, request)
            elif model.provider == AIProvider.MISTRAL:
                response = await self._call_mistral(model, request)
            else:
                raise ValueError(f"Unsupported provider: {model.provider}")

            latency = asyncio.get_event_loop().time() - start_time

            # حساب التكلفة
            cost = (response['tokens_used'] / 1000) * model.cost_per_1k_tokens

            # تحديث الإحصائيات
            self._update_stats(model.provider, cost)

            return AIResponse(
                provider=model.provider,
                model=model.model_name,
                content=response['content'],
                tokens_used=response['tokens_used'],
                cost=cost,
                latency_seconds=round(latency, 2),
                confidence=response.get('confidence', 0.85),
                metadata=response.get('metadata', {})
            )

        except Exception as e:
            # fallback لنموذج آخر
            print(f"Error with {model.provider}: {e}")
            # محاولة نموذج بديل
            if len(self.models) > 1:
                # اختيار التالي
                next_model = self.models[1]
                request.preferred_provider = next_model.provider
                return await self.execute(request)
            else:
                raise

    async def _call_openai(
        self,
        model: ModelCapability,
        request: AIRequest
    ) -> Dict[str, Any]:
        """استدعاء OpenAI API"""
        try:
            import openai

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return {
                    'content': "[تنبيه: OPENAI_API_KEY غير موجود - محاكاة الاستجابة]",
                    'tokens_used': 100,
                    'confidence': 0.5
                }

            client = openai.AsyncOpenAI(api_key=api_key)

            messages = [
                {"role": "system", "content": "أنت مساعد ذكي للنظام RMF AI Dreams."},
                {"role": "user", "content": request.prompt}
            ]

            if request.context:
                messages.insert(1, {
                    "role": "system",
                    "content": f"السياق: {json.dumps(request.context, ensure_ascii=False)}"
                })

            response = await client.chat.completions.create(
                model=model.model_name,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                stream=request.require_streaming
            )

            if request.require_streaming:
                # معالجة streaming
                content = ""
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        content += chunk.choices[0].delta.content
                tokens_used = len(content.split())  # تقريبي
            else:
                content = response.choices[0].message.content
                tokens_used = response.usage.total_tokens

            return {
                'content': content,
                'tokens_used': tokens_used,
                'confidence': 0.9
            }

        except Exception as e:
            return {
                'content': f"[خطأ في OpenAI: {e}]",
                'tokens_used': 0,
                'confidence': 0.0
            }

    async def _call_anthropic(
        self,
        model: ModelCapability,
        request: AIRequest
    ) -> Dict[str, Any]:
        """استدعاء Anthropic Claude API"""
        try:
            import anthropic

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                return {
                    'content': "[تنبيه: ANTHROPIC_API_KEY غير موجود - محاكاة الاستجابة]",
                    'tokens_used': 100,
                    'confidence': 0.5
                }

            client = anthropic.AsyncAnthropic(api_key=api_key)

            system_prompt = "أنت مساعد ذكي للنظام RMF AI Dreams."
            if request.context:
                system_prompt += f"\n\nالسياق: {json.dumps(request.context, ensure_ascii=False)}"

            response = await client.messages.create(
                model=model.model_name,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": request.prompt}
                ]
            )

            return {
                'content': response.content[0].text,
                'tokens_used': response.usage.input_tokens + response.usage.output_tokens,
                'confidence': 0.92
            }

        except Exception as e:
            return {
                'content': f"[خطأ في Anthropic: {e}]",
                'tokens_used': 0,
                'confidence': 0.0
            }

    async def _call_google(
        self,
        model: ModelCapability,
        request: AIRequest
    ) -> Dict[str, Any]:
        """استدعاء Google Gemini API"""
        try:
            import google.generativeai as genai

            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return {
                    'content': "[تنبيه: GOOGLE_API_KEY غير موجود - محاكاة الاستجابة]",
                    'tokens_used': 100,
                    'confidence': 0.5
                }

            genai.configure(api_key=api_key)
            model_instance = genai.GenerativeModel(model.model_name)

            full_prompt = request.prompt
            if request.context:
                full_prompt = f"السياق: {json.dumps(request.context, ensure_ascii=False)}\n\n{request.prompt}"

            response = await model_instance.generate_content_async(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=request.max_tokens,
                    temperature=request.temperature
                )
            )

            return {
                'content': response.text,
                'tokens_used': len(response.text.split()),  # تقريبي
                'confidence': 0.87
            }

        except Exception as e:
            return {
                'content': f"[خطأ في Google: {e}]",
                'tokens_used': 0,
                'confidence': 0.0
            }

    async def _call_mistral(
        self,
        model: ModelCapability,
        request: AIRequest
    ) -> Dict[str, Any]:
        """استدعاء Mistral API"""
        try:
            from mistralai.async_client import MistralAsyncClient
            from mistralai.models.chat_completion import ChatMessage

            api_key = os.getenv("MISTRAL_API_KEY")
            if not api_key:
                return {
                    'content': "[تنبيه: MISTRAL_API_KEY غير موجود - محاكاة الاستجابة]",
                    'tokens_used': 100,
                    'confidence': 0.5
                }

            client = MistralAsyncClient(api_key=api_key)

            messages = [
                ChatMessage(role="system", content="أنت مساعد ذكي للنظام RMF AI Dreams."),
                ChatMessage(role="user", content=request.prompt)
            ]

            if request.context:
                messages.insert(1, ChatMessage(
                    role="system",
                    content=f"السياق: {json.dumps(request.context, ensure_ascii=False)}"
                ))

            response = await client.chat(
                model=model.model_name,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )

            return {
                'content': response.choices[0].message.content,
                'tokens_used': response.usage.total_tokens,
                'confidence': 0.88
            }

        except Exception as e:
            return {
                'content': f"[خطأ في Mistral: {e}]",
                'tokens_used': 0,
                'confidence': 0.0
            }

    def _update_stats(self, provider: AIProvider, cost: float):
        """تحديث إحصائيات الاستخدام"""
        self.usage_stats['total_requests'] += 1
        self.usage_stats['total_cost'] += cost

        provider_name = provider.value
        if provider_name not in self.usage_stats['by_provider']:
            self.usage_stats['by_provider'][provider_name] = {
                'requests': 0,
                'cost': 0.0
            }

        self.usage_stats['by_provider'][provider_name]['requests'] += 1
        self.usage_stats['by_provider'][provider_name]['cost'] += cost

    def get_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات الاستخدام"""
        return self.usage_stats

    async def parallel_execute(
        self,
        requests: List[AIRequest]
    ) -> List[AIResponse]:
        """
        تنفيذ متوازي لعدة طلبات

        Args:
            requests: قائمة الطلبات

        Returns:
            قائمة الاستجابات بنفس الترتيب
        """
        tasks = [self.execute(req) for req in requests]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # معالجة الأخطاء
        results = []
        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                results.append(AIResponse(
                    provider=AIProvider.OPENAI,
                    model="error",
                    content=f"خطأ: {resp}",
                    tokens_used=0,
                    cost=0.0,
                    latency_seconds=0.0,
                    confidence=0.0,
                    metadata={}
                ))
            else:
                results.append(resp)

        return results
