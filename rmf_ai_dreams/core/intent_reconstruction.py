"""
Intent Reconstruction Engine - إعادة بناء النية من النصوص المبهمة
يحول أي فكرة غامضة إلى خطة تنفيذ واضحة
"""
import re
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class IntentLayer:
    """طبقة من طبقات النية"""
    level: int  # 0=literal, 1=implied, 2=strategic, 3=meta
    interpretation: str
    confidence: float
    reasoning: str


@dataclass
class ReconstructedIntent:
    """النية المعاد بناؤها"""
    original_text: str
    primary_goal: str
    sub_goals: List[str]
    intent_layers: List[IntentLayer]
    suggested_actions: List[Dict[str, Any]]
    context_assumptions: List[str]
    ambiguity_score: float  # 0=واضح تماماً, 1=غامض تماماً
    reconstruction_strategy: str


class IntentReconstructor:
    """
    محرك إعادة بناء النية
    يحلل ما وراء الكلمات ليفهم الهدف الحقيقي
    """

    def __init__(self):
        self.intent_patterns = self._load_patterns()
        self.action_templates = self._load_action_templates()

    def _load_patterns(self) -> Dict[str, Any]:
        """أنماط النوايا الشائعة"""
        return {
            'create_product': {
                'keywords': ['منتج', 'مشروع', 'تطبيق', 'موقع', 'نظام', 'أداة'],
                'triggers': ['أعمل', 'أبني', 'أصمم', 'أنشئ', 'عايز'],
                'implied_needs': ['تخطيط', 'تصميم', 'برمجة', 'اختبار', 'نشر']
            },
            'solve_problem': {
                'keywords': ['مشكلة', 'خلل', 'عطل', 'بطء', 'error'],
                'triggers': ['أحل', 'أصلح', 'أحسّن', 'fix'],
                'implied_needs': ['تشخيص', 'تحليل', 'حل', 'اختبار']
            },
            'automate_task': {
                'keywords': ['أتمتة', 'تلقائي', 'automatic', 'script'],
                'triggers': ['يعمل لوحده', 'تلقائي', 'بدون تدخل'],
                'implied_needs': ['تحليل الخطوات', 'برمجة', 'جدولة', 'مراقبة']
            },
            'create_content': {
                'keywords': ['محتوى', 'مقال', 'منشور', 'فيديو', 'تصميم'],
                'triggers': ['أكتب', 'أنشر', 'أنشئ محتوى'],
                'implied_needs': ['بحث', 'كتابة', 'تحسين SEO', 'نشر']
            },
            'analyze_data': {
                'keywords': ['بيانات', 'تحليل', 'إحصائيات', 'أرقام'],
                'triggers': ['أحلل', 'أفهم', 'أستخرج', 'insights'],
                'implied_needs': ['تنظيف البيانات', 'تحليل', 'تصور', 'تقرير']
            },
            'vague_idea': {
                'keywords': ['فكرة', 'نفسي', 'عايز', 'أحلم', 'يا ريت'],
                'triggers': ['مش عارف', 'ممكن', 'شكل', 'حاجة'],
                'implied_needs': ['استكشاف', 'تخطيط', 'تحليل جدوى', 'نموذج أولي']
            }
        }

    def _load_action_templates(self) -> Dict[str, Any]:
        """قوالب الإجراءات"""
        return {
            'create_product': [
                {'action': 'market_research', 'description': 'بحث السوق والمنافسين'},
                {'action': 'define_mvp', 'description': 'تحديد MVP'},
                {'action': 'design_architecture', 'description': 'تصميم البنية التقنية'},
                {'action': 'create_project_plan', 'description': 'خطة تنفيذ مفصلة'},
                {'action': 'setup_development', 'description': 'إعداد بيئة التطوير'}
            ],
            'solve_problem': [
                {'action': 'diagnose', 'description': 'تشخيص المشكلة'},
                {'action': 'root_cause_analysis', 'description': 'تحليل السبب الجذري'},
                {'action': 'propose_solutions', 'description': 'اقتراح حلول'},
                {'action': 'implement_fix', 'description': 'تطبيق الحل'},
                {'action': 'verify', 'description': 'التحقق من الحل'}
            ],
            'automate_task': [
                {'action': 'document_manual_steps', 'description': 'توثيق الخطوات اليدوية'},
                {'action': 'identify_automation_points', 'description': 'تحديد نقاط الأتمتة'},
                {'action': 'design_workflow', 'description': 'تصميم سير العمل'},
                {'action': 'develop_automation', 'description': 'برمجة الأتمتة'},
                {'action': 'schedule_execution', 'description': 'جدولة التنفيذ'}
            ]
        }

    def reconstruct(self, user_input: str, context: Optional[Dict] = None) -> ReconstructedIntent:
        """
        إعادة بناء النية من نص المستخدم

        Args:
            user_input: النص الذي أدخله المستخدم
            context: السياق الإضافي (محادثات سابقة، تفضيلات، إلخ)

        Returns:
            ReconstructedIntent
        """
        # تنظيف النص
        cleaned = self._clean_text(user_input)

        # التعرف على نمط النية
        intent_type = self._identify_intent_type(cleaned)

        # استخراج طبقات النية
        layers = self._extract_intent_layers(cleaned, intent_type, context)

        # تحديد الأهداف
        primary_goal, sub_goals = self._extract_goals(cleaned, intent_type, layers)

        # توليد إجراءات مقترحة
        actions = self._generate_actions(intent_type, primary_goal, sub_goals, context)

        # الافتراضات المستخرجة
        assumptions = self._extract_assumptions(cleaned, context)

        # حساب درجة الغموض
        ambiguity = self._calculate_ambiguity(cleaned, layers)

        # استراتيجية إعادة البناء
        strategy = self._determine_strategy(intent_type, ambiguity)

        return ReconstructedIntent(
            original_text=user_input,
            primary_goal=primary_goal,
            sub_goals=sub_goals,
            intent_layers=layers,
            suggested_actions=actions,
            context_assumptions=assumptions,
            ambiguity_score=ambiguity,
            reconstruction_strategy=strategy
        )

    def _clean_text(self, text: str) -> str:
        """تنظيف النص"""
        # إزالة الأحرف الخاصة الزائدة
        text = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', text)
        # توحيد المسافات
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _identify_intent_type(self, text: str) -> str:
        """التعرف على نوع النية"""
        text_lower = text.lower()

        scores = {}
        for intent_type, pattern in self.intent_patterns.items():
            score = 0

            # فحص الكلمات المفتاحية
            for keyword in pattern['keywords']:
                if keyword in text_lower:
                    score += 2

            # فحص المحفزات
            for trigger in pattern['triggers']:
                if trigger in text_lower:
                    score += 3

            scores[intent_type] = score

        if not scores or max(scores.values()) == 0:
            return 'vague_idea'

        return max(scores, key=scores.get)

    def _extract_intent_layers(
        self,
        text: str,
        intent_type: str,
        context: Optional[Dict]
    ) -> List[IntentLayer]:
        """استخراج طبقات النية"""
        layers = []

        # المستوى 0: الحرفي (ماذا قال بالضبط)
        layers.append(IntentLayer(
            level=0,
            interpretation=text,
            confidence=1.0,
            reasoning="النص الحرفي"
        ))

        # المستوى 1: الضمني (ماذا يقصد)
        implied = self._infer_implied_meaning(text, intent_type)
        layers.append(IntentLayer(
            level=1,
            interpretation=implied['meaning'],
            confidence=implied['confidence'],
            reasoning=implied['reasoning']
        ))

        # المستوى 2: الاستراتيجي (ما الهدف الأكبر)
        strategic = self._infer_strategic_intent(text, intent_type, context)
        layers.append(IntentLayer(
            level=2,
            interpretation=strategic['meaning'],
            confidence=strategic['confidence'],
            reasoning=strategic['reasoning']
        ))

        # المستوى 3: الميتا (لماذا يريد هذا)
        meta = self._infer_meta_intent(text, intent_type, context)
        if meta:
            layers.append(IntentLayer(
                level=3,
                interpretation=meta['meaning'],
                confidence=meta['confidence'],
                reasoning=meta['reasoning']
            ))

        return layers

    def _infer_implied_meaning(self, text: str, intent_type: str) -> Dict:
        """استنتاج المعنى الضمني"""
        implications = {
            'create_product': {
                'meaning': 'يريد بناء منتج رقمي كامل من الصفر',
                'confidence': 0.8,
                'reasoning': 'كلمات تدل على إنشاء شيء جديد'
            },
            'solve_problem': {
                'meaning': 'يواجه مشكلة تقنية تحتاج حل سريع',
                'confidence': 0.85,
                'reasoning': 'كلمات تدل على وجود خلل'
            },
            'automate_task': {
                'meaning': 'يريد توفير الوقت بأتمتة مهمة متكررة',
                'confidence': 0.8,
                'reasoning': 'كلمات تدل على رغبة في الأتمتة'
            },
            'vague_idea': {
                'meaning': 'لديه فكرة غير واضحة المعالم تحتاج استكشاف',
                'confidence': 0.6,
                'reasoning': 'النص يحتوي على غموض كبير'
            }
        }
        return implications.get(intent_type, {
            'meaning': 'نية غير واضحة',
            'confidence': 0.3,
            'reasoning': 'لم يتم التعرف على النمط'
        })

    def _infer_strategic_intent(
        self,
        text: str,
        intent_type: str,
        context: Optional[Dict]
    ) -> Dict:
        """استنتاج النية الاستراتيجية"""
        # افتراضات استراتيجية بناءً على السياق
        if context and context.get('business_context'):
            return {
                'meaning': 'جزء من استراتيجية أعمال أكبر',
                'confidence': 0.7,
                'reasoning': 'السياق يشير لهدف تجاري'
            }

        strategic_map = {
            'create_product': {
                'meaning': 'دخول سوق جديد أو تحسين موقع تنافسي',
                'confidence': 0.65,
                'reasoning': 'المنتجات الجديدة عادة لأهداف تجارية'
            },
            'solve_problem': {
                'meaning': 'تحسين الكفاءة التشغيلية',
                'confidence': 0.7,
                'reasoning': 'حل المشاكل يزيد الإنتاجية'
            }
        }

        return strategic_map.get(intent_type, {
            'meaning': 'تحسين عام في الوضع الحالي',
            'confidence': 0.5,
            'reasoning': 'افتراض عام'
        })

    def _infer_meta_intent(
        self,
        text: str,
        intent_type: str,
        context: Optional[Dict]
    ) -> Optional[Dict]:
        """استنتاج النية على مستوى الميتا (لماذا؟)"""
        # فقط إذا كان هناك سياق كافٍ
        if not context or context.get('user_history_count', 0) < 3:
            return None

        return {
            'meaning': 'بناء نظام مستدام طويل الأمد',
            'confidence': 0.55,
            'reasoning': 'المستخدم لديه تاريخ من المشاريع'
        }

    def _extract_goals(
        self,
        text: str,
        intent_type: str,
        layers: List[IntentLayer]
    ) -> tuple[str, List[str]]:
        """استخراج الأهداف الرئيسية والفرعية"""
        # الهدف الرئيسي من المستوى الضمني
        primary = layers[1].interpretation if len(layers) > 1 else text

        # الأهداف الفرعية
        sub_goals = []

        if intent_type in self.intent_patterns:
            needs = self.intent_patterns[intent_type].get('implied_needs', [])
            sub_goals = [f"{need} للمشروع" for need in needs]

        return primary, sub_goals

    def _generate_actions(
        self,
        intent_type: str,
        primary_goal: str,
        sub_goals: List[str],
        context: Optional[Dict]
    ) -> List[Dict[str, Any]]:
        """توليد إجراءات مقترحة"""
        base_actions = self.action_templates.get(
            intent_type,
            [{'action': 'explore', 'description': 'استكشاف الخيارات'}]
        )

        # إضافة تفاصيل
        actions = []
        for i, action in enumerate(base_actions):
            actions.append({
                'step': i + 1,
                'action_type': action['action'],
                'description': action['description'],
                'estimated_complexity': self._estimate_complexity(action['action']),
                'requires_approval': self._requires_approval(action['action']),
                'auto_executable': not self._requires_approval(action['action'])
            })

        return actions

    def _estimate_complexity(self, action_type: str) -> str:
        """تقدير تعقيد الإجراء"""
        complex_actions = ['design_architecture', 'develop_automation', 'root_cause_analysis']
        if action_type in complex_actions:
            return 'high'
        return 'medium'

    def _requires_approval(self, action_type: str) -> bool:
        """هل يحتاج الإجراء لموافقة؟"""
        approval_needed = [
            'implement_fix',
            'develop_automation',
            'publish',
            'deploy'
        ]
        return action_type in approval_needed

    def _extract_assumptions(self, text: str, context: Optional[Dict]) -> List[str]:
        """استخراج الافتراضات"""
        assumptions = []

        # افتراضات بناءً على النص
        if 'منتج' in text or 'تطبيق' in text:
            assumptions.append('المستخدم لديه معرفة أساسية بالتكنولوجيا')
            assumptions.append('يريد بناء MVP أولاً')

        if 'سريع' in text or 'فوري' in text:
            assumptions.append('الوقت عامل حاسم')

        # افتراضات من السياق
        if context:
            if context.get('has_technical_background'):
                assumptions.append('لديه خلفية تقنية')
            if context.get('budget_limited'):
                assumptions.append('الميزانية محدودة')

        if not assumptions:
            assumptions.append('لا توجد افتراضات خاصة')

        return assumptions

    def _calculate_ambiguity(self, text: str, layers: List[IntentLayer]) -> float:
        """حساب درجة الغموض"""
        score = 0.0

        # قصر النص = غموض أكبر
        word_count = len(text.split())
        if word_count < 5:
            score += 0.3
        elif word_count < 10:
            score += 0.15

        # كلمات غامضة
        vague_words = ['شيء', 'حاجة', 'ممكن', 'نوع', 'شكل', 'نفسي']
        for word in vague_words:
            if word in text:
                score += 0.1

        # ثقة الطبقات
        avg_confidence = sum(l.confidence for l in layers) / len(layers)
        score += (1 - avg_confidence) * 0.3

        return min(1.0, score)

    def _determine_strategy(self, intent_type: str, ambiguity: float) -> str:
        """تحديد استراتيجية التعامل مع النية"""
        if ambiguity > 0.7:
            return 'interactive_clarification'  # اطرح أسئلة توضيحية
        elif ambiguity > 0.4:
            return 'guided_exploration'  # استكشاف موجه
        else:
            return 'direct_execution'  # تنفيذ مباشر

    def to_execution_plan(self, intent: ReconstructedIntent) -> Dict[str, Any]:
        """
        تحويل النية المعاد بناؤها إلى خطة تنفيذ

        Returns:
            خطة تنفيذ قابلة للتشغيل مباشرة
        """
        return {
            'title': intent.primary_goal,
            'complexity': 'high' if intent.ambiguity_score > 0.5 else 'medium',
            'strategy': intent.reconstruction_strategy,
            'phases': [
                {
                    'name': 'Clarification' if intent.ambiguity_score > 0.6 else 'Planning',
                    'steps': [
                        f"توضيح: {goal}" for goal in intent.sub_goals[:2]
                    ] if intent.ambiguity_score > 0.6 else [
                        f"تخطيط: {goal}" for goal in intent.sub_goals
                    ]
                },
                {
                    'name': 'Execution',
                    'steps': [
                        action['description'] for action in intent.suggested_actions
                    ]
                }
            ],
            'assumptions': intent.context_assumptions,
            'approval_points': [
                action['description']
                for action in intent.suggested_actions
                if action.get('requires_approval')
            ],
            'auto_executable': all(
                action.get('auto_executable', False)
                for action in intent.suggested_actions
            )
        }
