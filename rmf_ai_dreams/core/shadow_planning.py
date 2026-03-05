"""
Shadow Planning System - نظام التخطيط الخفي
يعمل في الخلفية لتجهيز خطط بديلة وتوقع المشاكل قبل حدوثها
"""
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum


class PlanStatus(Enum):
    SHADOW = "shadow"  # خطة خفية جاهزة
    ACTIVE = "active"  # خطة قيد التنفيذ
    FALLBACK = "fallback"  # خطة بديلة
    ARCHIVED = "archived"  # خطة منتهية


@dataclass
class RiskAssessment:
    """تقييم المخاطر"""
    risk_type: str
    probability: float  # 0-1
    impact: str  # low, medium, high, critical
    mitigation: str
    auto_trigger: bool  # هل ينفذ تلقائياً عند المشكلة


@dataclass
class ShadowPlan:
    """خطة خفية"""
    plan_id: str
    parent_task: str
    plan_type: str  # primary, fallback, optimization, preventive
    status: PlanStatus
    steps: List[Dict[str, Any]]
    risks: List[RiskAssessment]
    triggers: List[str]  # متى تتحول من shadow إلى active
    confidence: float
    created_at: str
    activated_at: Optional[str] = None
    reasoning: str = ""


@dataclass
class CognitiveState:
    """الحالة المعرفية للنظام"""
    active_plans: int
    shadow_plans: int
    detected_patterns: List[str]
    predicted_bottlenecks: List[str]
    recommended_optimizations: List[str]
    system_confidence: float
    last_learning: str


class ShadowPlanner:
    """
    مخطط خفي - يعمل باستمرار في الخلفية
    """

    def __init__(self):
        self.plans: Dict[str, ShadowPlan] = {}
        self.execution_history: List[Dict] = []
        self.pattern_memory: Dict[str, Any] = {}

    def create_shadow_plans(
        self,
        primary_task: str,
        primary_plan: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[ShadowPlan]:
        """
        إنشاء خطط خفية متعددة لمهمة واحدة

        Args:
            primary_task: المهمة الأساسية
            primary_plan: الخطة الأساسية
            context: السياق

        Returns:
            قائمة من الخطط الخفية (primary + fallbacks + optimizations)
        """
        plans = []

        # الخطة الأساسية
        primary = self._create_primary_plan(primary_task, primary_plan, context)
        plans.append(primary)

        # خطط بديلة للمخاطر المحتملة
        fallbacks = self._create_fallback_plans(primary_task, primary_plan, context)
        plans.extend(fallbacks)

        # خطط تحسينية
        optimizations = self._create_optimization_plans(primary_task, primary_plan, context)
        plans.extend(optimizations)

        # خطط وقائية
        preventive = self._create_preventive_plans(primary_task, context)
        plans.extend(preventive)

        # حفظ الخطط
        for plan in plans:
            self.plans[plan.plan_id] = plan

        return plans

    def _create_primary_plan(
        self,
        task: str,
        plan: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ShadowPlan:
        """إنشاء الخطة الأساسية"""
        plan_id = f"primary_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # تحليل المخاطر
        risks = self._analyze_risks(plan, context)

        # استخراج الخطوات
        steps = plan.get('steps', [])

        return ShadowPlan(
            plan_id=plan_id,
            parent_task=task,
            plan_type='primary',
            status=PlanStatus.SHADOW,
            steps=steps,
            risks=risks,
            triggers=['user_approval'],
            confidence=0.85,
            created_at=datetime.now().isoformat(),
            reasoning="الخطة الرئيسية المقترحة بناءً على فهم المهمة"
        )

    def _create_fallback_plans(
        self,
        task: str,
        primary_plan: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[ShadowPlan]:
        """إنشاء خطط بديلة"""
        fallbacks = []

        # تحديد نقاط الفشل المحتملة
        failure_points = self._identify_failure_points(primary_plan)

        for i, failure in enumerate(failure_points):
            plan_id = f"fallback_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # خطة بديلة لكل نقطة فشل
            alternative_steps = self._generate_alternative_approach(
                failure['step'],
                failure['type'],
                context
            )

            fallbacks.append(ShadowPlan(
                plan_id=plan_id,
                parent_task=task,
                plan_type='fallback',
                status=PlanStatus.SHADOW,
                steps=alternative_steps,
                risks=[],
                triggers=[
                    f"failure_at_{failure['step']}",
                    f"error_{failure['type']}"
                ],
                confidence=0.7,
                created_at=datetime.now().isoformat(),
                reasoning=f"خطة بديلة في حالة: {failure['description']}"
            ))

        return fallbacks

    def _create_optimization_plans(
        self,
        task: str,
        primary_plan: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[ShadowPlan]:
        """إنشاء خطط تحسينية"""
        optimizations = []

        # تحديد فرص التحسين
        opportunities = self._identify_optimization_opportunities(primary_plan, context)

        for i, opp in enumerate(opportunities):
            plan_id = f"optimize_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            optimizations.append(ShadowPlan(
                plan_id=plan_id,
                parent_task=task,
                plan_type='optimization',
                status=PlanStatus.SHADOW,
                steps=opp['steps'],
                risks=[],
                triggers=[
                    'performance_degradation',
                    'user_requests_faster'
                ],
                confidence=0.75,
                created_at=datetime.now().isoformat(),
                reasoning=f"تحسين: {opp['description']}"
            ))

        return optimizations

    def _create_preventive_plans(
        self,
        task: str,
        context: Dict[str, Any]
    ) -> List[ShadowPlan]:
        """إنشاء خطط وقائية"""
        preventive = []

        # من التاريخ، ما المشاكل التي تتكرر؟
        common_issues = self._get_common_issues_for_task_type(task)

        for i, issue in enumerate(common_issues):
            plan_id = f"prevent_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            preventive.append(ShadowPlan(
                plan_id=plan_id,
                parent_task=task,
                plan_type='preventive',
                status=PlanStatus.SHADOW,
                steps=issue['prevention_steps'],
                risks=[],
                triggers=['before_execution'],
                confidence=0.8,
                created_at=datetime.now().isoformat(),
                reasoning=f"منع مشكلة متكررة: {issue['description']}"
            ))

        return preventive

    def _analyze_risks(
        self,
        plan: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[RiskAssessment]:
        """تحليل مخاطر الخطة"""
        risks = []

        steps = plan.get('steps', [])

        # فحص كل خطوة
        for step in steps:
            step_risks = self._assess_step_risks(step, context)
            risks.extend(step_risks)

        # مخاطر عامة
        if context.get('requires_external_api'):
            risks.append(RiskAssessment(
                risk_type='api_failure',
                probability=0.15,
                impact='medium',
                mitigation='استخدام retry logic مع exponential backoff',
                auto_trigger=True
            ))

        if context.get('involves_data_modification'):
            risks.append(RiskAssessment(
                risk_type='data_loss',
                probability=0.05,
                impact='critical',
                mitigation='إنشاء backup قبل التعديل',
                auto_trigger=True
            ))

        return risks

    def _assess_step_risks(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[RiskAssessment]:
        """تقييم مخاطر خطوة واحدة"""
        risks = []

        step_type = step.get('type', '')

        risk_profiles = {
            'api_call': {
                'risk_type': 'network_timeout',
                'probability': 0.1,
                'impact': 'medium',
                'mitigation': 'timeout + retry'
            },
            'file_operation': {
                'risk_type': 'permission_denied',
                'probability': 0.08,
                'impact': 'medium',
                'mitigation': 'فحص الصلاحيات مسبقاً'
            },
            'database_query': {
                'risk_type': 'query_timeout',
                'probability': 0.12,
                'impact': 'high',
                'mitigation': 'query optimization + indexing'
            }
        }

        if step_type in risk_profiles:
            profile = risk_profiles[step_type]
            risks.append(RiskAssessment(
                risk_type=profile['risk_type'],
                probability=profile['probability'],
                impact=profile['impact'],
                mitigation=profile['mitigation'],
                auto_trigger=False
            ))

        return risks

    def _identify_failure_points(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """تحديد نقاط الفشل المحتملة"""
        failure_points = []

        steps = plan.get('steps', [])

        for i, step in enumerate(steps):
            # الخطوات التي تعتمد على مصادر خارجية
            if step.get('requires_external_api'):
                failure_points.append({
                    'step': i,
                    'type': 'api_unavailable',
                    'description': 'API غير متاح'
                })

            # خطوات معقدة
            if step.get('complexity') == 'high':
                failure_points.append({
                    'step': i,
                    'type': 'execution_timeout',
                    'description': 'تعقيد عالي قد يؤدي لفشل'
                })

            # خطوات تحتاج موافقة
            if step.get('requires_approval'):
                failure_points.append({
                    'step': i,
                    'type': 'user_rejection',
                    'description': 'احتمال رفض المستخدم'
                })

        return failure_points

    def _generate_alternative_approach(
        self,
        failed_step_index: int,
        failure_type: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """توليد نهج بديل"""
        alternatives = {
            'api_unavailable': [
                {
                    'type': 'fallback_data',
                    'description': 'استخدام بيانات محفوظة مؤقتاً',
                    'action': 'load_cached_data'
                },
                {
                    'type': 'alternative_api',
                    'description': 'استخدام API بديل',
                    'action': 'switch_to_backup_api'
                }
            ],
            'execution_timeout': [
                {
                    'type': 'simplify',
                    'description': 'تبسيط العملية',
                    'action': 'break_into_smaller_chunks'
                }
            ],
            'user_rejection': [
                {
                    'type': 'request_clarification',
                    'description': 'طلب توضيح من المستخدم',
                    'action': 'ask_for_modification'
                }
            ]
        }

        return alternatives.get(failure_type, [])

    def _identify_optimization_opportunities(
        self,
        plan: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """تحديد فرص التحسين"""
        opportunities = []

        steps = plan.get('steps', [])

        # البحث عن خطوات قابلة للتنفيذ المتوازي
        parallelizable = [
            i for i, step in enumerate(steps)
            if step.get('independent', False)
        ]

        if len(parallelizable) > 1:
            opportunities.append({
                'type': 'parallelization',
                'description': 'تنفيذ خطوات متعددة بالتوازي',
                'steps': [
                    {
                        'action': 'run_parallel',
                        'step_indices': parallelizable
                    }
                ]
            })

        # البحث عن خطوات قابلة للتخزين المؤقت
        cacheable = [
            i for i, step in enumerate(steps)
            if step.get('cacheable', False)
        ]

        if cacheable:
            opportunities.append({
                'type': 'caching',
                'description': 'تخزين النتائج مؤقتاً لتسريع التنفيذ',
                'steps': [
                    {
                        'action': 'enable_cache',
                        'step_indices': cacheable
                    }
                ]
            })

        return opportunities

    def _get_common_issues_for_task_type(self, task: str) -> List[Dict[str, Any]]:
        """الحصول على المشاكل الشائعة لنوع المهمة"""
        # من الذاكرة أو قاعدة بيانات
        common = []

        if 'api' in task.lower():
            common.append({
                'description': 'rate limiting',
                'prevention_steps': [
                    {
                        'action': 'implement_rate_limiter',
                        'description': 'تطبيق rate limiting'
                    }
                ]
            })

        if 'database' in task.lower():
            common.append({
                'description': 'connection pool exhaustion',
                'prevention_steps': [
                    {
                        'action': 'configure_connection_pool',
                        'description': 'ضبط connection pool'
                    }
                ]
            })

        return common

    def activate_plan(self, plan_id: str) -> bool:
        """تفعيل خطة خفية"""
        if plan_id not in self.plans:
            return False

        plan = self.plans[plan_id]
        plan.status = PlanStatus.ACTIVE
        plan.activated_at = datetime.now().isoformat()

        return True

    def check_triggers(self, event: str, context: Dict[str, Any]) -> List[str]:
        """
        فحص المحفزات - هل حدث شيء يجب أن يفعّل خطة خفية؟

        Returns:
            قائمة بـ plan_ids التي يجب تفعيلها
        """
        activated = []

        for plan_id, plan in self.plans.items():
            if plan.status != PlanStatus.SHADOW:
                continue

            # فحص المحفزات
            for trigger in plan.triggers:
                if self._trigger_matches(trigger, event, context):
                    activated.append(plan_id)
                    break

        return activated

    def _trigger_matches(self, trigger: str, event: str, context: Dict[str, Any]) -> bool:
        """فحص تطابق المحفز"""
        # مطابقة نصية بسيطة
        if trigger.lower() in event.lower():
            return True

        # مطابقة على السياق
        if trigger in context:
            return True

        return False

    def get_cognitive_briefing(self) -> CognitiveState:
        """
        ملخص معرفي يومي - ماذا يفكر النظام؟
        """
        active = sum(1 for p in self.plans.values() if p.status == PlanStatus.ACTIVE)
        shadow = sum(1 for p in self.plans.values() if p.status == PlanStatus.SHADOW)

        # الأنماط المكتشفة
        patterns = self._detect_patterns()

        # الاختناقات المتوقعة
        bottlenecks = self._predict_bottlenecks()

        # تحسينات مقترحة
        optimizations = self._suggest_optimizations()

        # ثقة النظام
        confidence = self._calculate_system_confidence()

        return CognitiveState(
            active_plans=active,
            shadow_plans=shadow,
            detected_patterns=patterns,
            predicted_bottlenecks=bottlenecks,
            recommended_optimizations=optimizations,
            system_confidence=confidence,
            last_learning=datetime.now().isoformat()
        )

    def _detect_patterns(self) -> List[str]:
        """كشف الأنماط في التنفيذ"""
        patterns = []

        # تحليل بسيط
        if len(self.execution_history) > 10:
            patterns.append("المستخدم يفضل التنفيذ السريع على الدقة")

        return patterns

    def _predict_bottlenecks(self) -> List[str]:
        """التنبؤ بالاختناقات"""
        bottlenecks = []

        # تحليل الخطط النشطة
        for plan in self.plans.values():
            if plan.status == PlanStatus.ACTIVE:
                for risk in plan.risks:
                    if risk.probability > 0.5 and risk.impact in ['high', 'critical']:
                        bottlenecks.append(
                            f"{plan.plan_type}: احتمال {risk.risk_type}"
                        )

        return bottlenecks

    def _suggest_optimizations(self) -> List[str]:
        """اقتراح تحسينات"""
        suggestions = []

        optimization_plans = [
            p for p in self.plans.values()
            if p.plan_type == 'optimization' and p.confidence > 0.7
        ]

        for plan in optimization_plans:
            suggestions.append(plan.reasoning)

        return suggestions

    def _calculate_system_confidence(self) -> float:
        """حساب ثقة النظام الإجمالية"""
        if not self.plans:
            return 0.5

        avg_confidence = sum(p.confidence for p in self.plans.values()) / len(self.plans)
        return round(avg_confidence, 2)

    def export_plans(self) -> Dict[str, Any]:
        """تصدير جميع الخطط"""
        return {
            'plans': {
                plan_id: {
                    **asdict(plan),
                    'status': plan.status.value
                }
                for plan_id, plan in self.plans.items()
            },
            'stats': {
                'total': len(self.plans),
                'active': sum(1 for p in self.plans.values() if p.status == PlanStatus.ACTIVE),
                'shadow': sum(1 for p in self.plans.values() if p.status == PlanStatus.SHADOW),
            }
        }
