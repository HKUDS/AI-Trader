"""
Idea-to-Execution Compiler - مترجم الأفكار للتنفيذ
يحول أي فكرة غامضة إلى نتائج ملموسة فوراً
"""
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from .intent_reconstruction import IntentReconstructor, ReconstructedIntent
from .shadow_planning import ShadowPlanner, ShadowPlan
from .ai_orchestrator import AIOrchestrator, AIRequest


@dataclass
class CompiledIdea:
    """فكرة مترجمة إلى تنفيذ"""
    original_idea: str
    reconstructed_intent: ReconstructedIntent
    execution_plan: Dict[str, Any]
    shadow_plans: List[ShadowPlan]
    generated_assets: Dict[str, Any]  # اسم، domain، كود، إلخ
    next_actions: List[Dict[str, str]]
    compilation_confidence: float
    estimated_completion: str
    compiled_at: str


class IdeaCompiler:
    """
    مترجم الأفكار - من فكرة مبهمة إلى نتائج ملموسة
    """

    def __init__(self):
        self.intent_reconstructor = IntentReconstructor()
        self.shadow_planner = ShadowPlanner()
        self.ai_orchestrator = AIOrchestrator()

    async def compile(
        self,
        idea: str,
        context: Optional[Dict[str, Any]] = None
    ) -> CompiledIdea:
        """
        ترجمة فكرة كاملة

        Args:
            idea: الفكرة (يمكن أن تكون غامضة جداً)
            context: سياق إضافي

        Returns:
            CompiledIdea - فكرة مترجمة بالكامل
        """
        # المرحلة 1: إعادة بناء النية
        reconstructed = self.intent_reconstructor.reconstruct(idea, context)

        # المرحلة 2: توليد خطة التنفيذ
        execution_plan = self.intent_reconstructor.to_execution_plan(reconstructed)

        # المرحلة 3: إنشاء خطط خفية
        shadow_plans = self.shadow_planner.create_shadow_plans(
            primary_task=reconstructed.primary_goal,
            primary_plan=execution_plan,
            context=context or {}
        )

        # المرحلة 4: توليد الأصول (اسم، domain، كود أولي، إلخ)
        generated_assets = await self._generate_assets(
            reconstructed,
            execution_plan,
            context
        )

        # المرحلة 5: تحديد الخطوات التالية
        next_actions = self._determine_next_actions(
            reconstructed,
            execution_plan,
            generated_assets
        )

        # المرحلة 6: حساب الثقة الإجمالية
        confidence = self._calculate_compilation_confidence(
            reconstructed,
            execution_plan,
            generated_assets
        )

        # المرحلة 7: تقدير وقت الإنجاز
        estimated = self._estimate_completion(execution_plan)

        return CompiledIdea(
            original_idea=idea,
            reconstructed_intent=reconstructed,
            execution_plan=execution_plan,
            shadow_plans=shadow_plans,
            generated_assets=generated_assets,
            next_actions=next_actions,
            compilation_confidence=confidence,
            estimated_completion=estimated,
            compiled_at=datetime.now().isoformat()
        )

    async def _generate_assets(
        self,
        intent: ReconstructedIntent,
        plan: Dict[str, Any],
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        توليد الأصول الأولية

        Returns:
            {
                'project_name': str,
                'tagline': str,
                'domain_suggestions': List[str],
                'tech_stack': List[str],
                'initial_code': str,
                'file_structure': Dict,
                'branding': Dict
            }
        """
        assets = {}

        # توليد اسم المشروع
        if self._needs_project_name(intent):
            assets['project_name'] = await self._generate_project_name(intent)

        # توليد tagline
        if assets.get('project_name'):
            assets['tagline'] = await self._generate_tagline(
                assets['project_name'],
                intent
            )

        # توليد اقتراحات domains
        if assets.get('project_name'):
            assets['domain_suggestions'] = await self._suggest_domains(
                assets['project_name']
            )

        # تحديد tech stack
        assets['tech_stack'] = self._recommend_tech_stack(intent, plan)

        # توليد كود أولي
        if self._needs_code(intent):
            assets['initial_code'] = await self._generate_initial_code(
                intent,
                assets.get('tech_stack', [])
            )

        # بنية الملفات
        if assets.get('initial_code'):
            assets['file_structure'] = self._generate_file_structure(
                assets['tech_stack'],
                intent
            )

        # branding أولي
        if assets.get('project_name'):
            assets['branding'] = await self._generate_branding(
                assets['project_name'],
                intent
            )

        return assets

    def _needs_project_name(self, intent: ReconstructedIntent) -> bool:
        """هل تحتاج الفكرة لاسم مشروع؟"""
        keywords = ['منتج', 'تطبيق', 'موقع', 'نظام', 'مشروع', 'أداة']
        return any(kw in intent.primary_goal for kw in keywords)

    async def _generate_project_name(self, intent: ReconstructedIntent) -> str:
        """توليد اسم للمشروع"""
        request = AIRequest(
            task_type='creative_writing',
            prompt=f"""
اقترح 5 أسماء إبداعية لمشروع التالي:

الهدف: {intent.primary_goal}
الأهداف الفرعية: {', '.join(intent.sub_goals[:3])}

الأسماء يجب أن تكون:
- قصيرة (كلمة أو كلمتين)
- سهلة النطق
- مميزة
- ذات علاقة بالهدف

أعطني فقط الأسماء، كل اسم في سطر.
""",
            max_tokens=200,
            temperature=0.9
        )

        response = await self.ai_orchestrator.execute(request)

        # استخراج الاسم الأول
        names = [line.strip() for line in response.content.strip().split('\n') if line.strip()]
        if names:
            # إزالة الترقيم
            first_name = names[0].lstrip('1234567890.-) ')
            return first_name
        return "MyProject"

    async def _generate_tagline(self, project_name: str, intent: ReconstructedIntent) -> str:
        """توليد شعار للمشروع"""
        request = AIRequest(
            task_type='creative_writing',
            prompt=f"""
اكتب شعار (tagline) قصير لمشروع اسمه "{project_name}"

الهدف من المشروع: {intent.primary_goal}

الشعار يجب أن يكون:
- جملة واحدة قصيرة (5-10 كلمات)
- واضح ومباشر
- يوضح القيمة الأساسية

أعطني الشعار فقط، بدون شرح.
""",
            max_tokens=100,
            temperature=0.8
        )

        response = await self.ai_orchestrator.execute(request)
        return response.content.strip().strip('"').strip("'")

    async def _suggest_domains(self, project_name: str) -> List[str]:
        """اقتراح أسماء domains"""
        # تحويل الاسم لـ domain-friendly
        base = project_name.lower().replace(' ', '').replace('-', '')

        suggestions = [
            f"{base}.com",
            f"{base}.io",
            f"{base}.app",
            f"get{base}.com",
            f"try{base}.com"
        ]

        return suggestions[:3]

    def _recommend_tech_stack(
        self,
        intent: ReconstructedIntent,
        plan: Dict[str, Any]
    ) -> List[str]:
        """توصية بـ tech stack"""
        stack = []

        # بناءً على نوع المشروع
        if any(kw in intent.primary_goal for kw in ['موقع', 'تطبيق ويب', 'web']):
            stack.extend(['React', 'Next.js', 'TailwindCSS'])

        if any(kw in intent.primary_goal for kw in ['api', 'backend', 'خادم']):
            stack.extend(['FastAPI', 'PostgreSQL'])

        if any(kw in intent.primary_goal for kw in ['ذكاء', 'ai', 'تعلم']):
            stack.extend(['Python', 'LangChain', 'OpenAI'])

        if any(kw in intent.primary_goal for kw in ['تحليل', 'بيانات', 'data']):
            stack.extend(['Python', 'Pandas', 'Plotly'])

        # افتراضي
        if not stack:
            stack = ['Python', 'Streamlit']

        return list(set(stack))  # إزالة المكرر

    def _needs_code(self, intent: ReconstructedIntent) -> bool:
        """هل تحتاج الفكرة لكود؟"""
        code_keywords = [
            'تطبيق', 'موقع', 'نظام', 'أداة', 'script',
            'أتمتة', 'api', 'برنامج'
        ]
        return any(kw in intent.primary_goal.lower() for kw in code_keywords)

    async def _generate_initial_code(
        self,
        intent: ReconstructedIntent,
        tech_stack: List[str]
    ) -> str:
        """توليد كود أولي"""
        request = AIRequest(
            task_type='code_generation',
            prompt=f"""
اكتب كود أولي (MVP skeleton) لمشروع:

الهدف: {intent.primary_goal}
Tech Stack: {', '.join(tech_stack)}

الكود يجب أن يتضمن:
- البنية الأساسية
- الملف الرئيسي
- تعليقات توضيحية

اكتب كود كامل جاهز للتشغيل.
""",
            max_tokens=2000,
            temperature=0.3
        )

        response = await self.ai_orchestrator.execute(request)
        return response.content

    def _generate_file_structure(
        self,
        tech_stack: List[str],
        intent: ReconstructedIntent
    ) -> Dict[str, Any]:
        """توليد بنية ملفات المشروع"""
        structure = {
            'root': {
                'README.md': 'وصف المشروع',
                'requirements.txt': 'المكتبات المطلوبة',
                '.env.example': 'متغيرات البيئة'
            }
        }

        if 'Python' in tech_stack:
            structure['root']['main.py'] = 'الملف الرئيسي'
            structure['root']['config.py'] = 'الإعدادات'

        if 'React' in tech_stack or 'Next.js' in tech_stack:
            structure['src'] = {
                'components/': 'المكونات',
                'pages/': 'الصفحات',
                'styles/': 'التصاميم'
            }

        if 'FastAPI' in tech_stack:
            structure['app'] = {
                'main.py': 'FastAPI app',
                'routes/': 'المسارات',
                'models/': 'النماذج'
            }

        return structure

    async def _generate_branding(
        self,
        project_name: str,
        intent: ReconstructedIntent
    ) -> Dict[str, Any]:
        """توليد branding أولي"""
        request = AIRequest(
            task_type='creative_writing',
            prompt=f"""
اقترح branding لمشروع "{project_name}"

الهدف: {intent.primary_goal}

اقترح:
1. الألوان الأساسية (3 ألوان hex)
2. نوع الشعار (أيقونة، نص، مجموعة)
3. الأسلوب العام (minimalist, modern, playful, professional)

أعطني JSON فقط بهذا الشكل:
{{
  "primary_color": "#hex",
  "secondary_color": "#hex",
  "accent_color": "#hex",
  "logo_type": "...",
  "style": "..."
}}
""",
            max_tokens=300,
            temperature=0.7
        )

        response = await self.ai_orchestrator.execute(request)

        try:
            # محاولة parse JSON
            content = response.content.strip()
            # إزالة markdown code blocks إن وجدت
            if content.startswith('```'):
                content = '\n'.join(content.split('\n')[1:-1])
            branding = json.loads(content)
        except:
            # افتراضي
            branding = {
                'primary_color': '#3B82F6',
                'secondary_color': '#8B5CF6',
                'accent_color': '#10B981',
                'logo_type': 'text+icon',
                'style': 'modern'
            }

        return branding

    def _determine_next_actions(
        self,
        intent: ReconstructedIntent,
        plan: Dict[str, Any],
        assets: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """تحديد الخطوات التالية الفورية"""
        actions = []

        # إذا كان هناك كود، الخطوة التالية: إنشاء ملفات
        if assets.get('initial_code'):
            actions.append({
                'action': 'create_project_files',
                'description': 'إنشاء ملفات المشروع',
                'status': 'ready'
            })

        # إذا كان هناك domain، الخطوة التالية: فحص التوافر
        if assets.get('domain_suggestions'):
            actions.append({
                'action': 'check_domain_availability',
                'description': f"فحص توافر {assets['domain_suggestions'][0]}",
                'status': 'ready'
            })

        # دائماً: مراجعة الخطة
        actions.append({
            'action': 'review_plan',
            'description': 'مراجعة الخطة والموافقة عليها',
            'status': 'awaiting_approval'
        })

        # بناءً على استراتيجية إعادة البناء
        if intent.reconstruction_strategy == 'interactive_clarification':
            actions.insert(0, {
                'action': 'clarify_requirements',
                'description': 'توضيح المتطلبات الغامضة',
                'status': 'needs_input'
            })

        return actions

    def _calculate_compilation_confidence(
        self,
        intent: ReconstructedIntent,
        plan: Dict[str, Any],
        assets: Dict[str, Any]
    ) -> float:
        """حساب ثقة الترجمة"""
        score = 0.0

        # ثقة إعادة بناء النية
        score += (1 - intent.ambiguity_score) * 0.4

        # اكتمال الأصول
        asset_completeness = len(assets) / 7  # 7 أصول محتملة
        score += asset_completeness * 0.3

        # وضوح الخطة
        if plan.get('auto_executable'):
            score += 0.2
        else:
            score += 0.1

        # وجود خطوات واضحة
        total_steps = sum(
            len(phase.get('steps', []))
            for phase in plan.get('phases', [])
        )
        if total_steps > 3:
            score += 0.1

        return min(1.0, score)

    def _estimate_completion(self, plan: Dict[str, Any]) -> str:
        """تقدير وقت الإنجاز (نصي، ليس رقمي)"""
        total_steps = sum(
            len(phase.get('steps', []))
            for phase in plan.get('phases', [])
        )

        complexity = plan.get('complexity', 'medium')

        if complexity == 'high' or total_steps > 10:
            return "مشروع معقد - يحتاج تخطيط مفصل"
        elif total_steps > 5:
            return "مشروع متوسط - قابل للتنفيذ بعد التوضيح"
        else:
            return "مشروع بسيط - جاهز للتنفيذ الفوري"

    def format_output(self, compiled: CompiledIdea) -> str:
        """
        تنسيق النتيجة للعرض

        Returns:
            نص منسق بـ Markdown
        """
        output = f"""
# 🚀 ترجمة الفكرة إلى تنفيذ

## الفكرة الأصلية
> {compiled.original_idea}

## النية المعاد بناؤها

**الهدف الرئيسي:** {compiled.reconstructed_intent.primary_goal}

**الأهداف الفرعية:**
"""

        for i, goal in enumerate(compiled.reconstructed_intent.sub_goals, 1):
            output += f"{i}. {goal}\n"

        output += f"""
**درجة الغموض:** {compiled.reconstructed_intent.ambiguity_score:.0%}
**الاستراتيجية:** {compiled.reconstructed_intent.reconstruction_strategy}

---

## الأصول المولدة
"""

        if compiled.generated_assets.get('project_name'):
            output += f"\n### 📛 اسم المشروع\n**{compiled.generated_assets['project_name']}**\n"

        if compiled.generated_assets.get('tagline'):
            output += f"\n*{compiled.generated_assets['tagline']}*\n"

        if compiled.generated_assets.get('domain_suggestions'):
            output += f"\n### 🌐 Domain Suggestions\n"
            for domain in compiled.generated_assets['domain_suggestions']:
                output += f"- {domain}\n"

        if compiled.generated_assets.get('tech_stack'):
            output += f"\n### 🛠️ Tech Stack\n"
            for tech in compiled.generated_assets['tech_stack']:
                output += f"- {tech}\n"

        if compiled.generated_assets.get('branding'):
            branding = compiled.generated_assets['branding']
            output += f"\n### 🎨 Branding\n"
            output += f"- Primary: {branding.get('primary_color', 'N/A')}\n"
            output += f"- Secondary: {branding.get('secondary_color', 'N/A')}\n"
            output += f"- Style: {branding.get('style', 'N/A')}\n"

        if compiled.generated_assets.get('initial_code'):
            output += f"\n### 💻 كود أولي\n```python\n{compiled.generated_assets['initial_code'][:500]}...\n```\n"

        output += f"""
---

## الخطوات التالية

"""

        for i, action in enumerate(compiled.next_actions, 1):
            status_emoji = {
                'ready': '✅',
                'awaiting_approval': '⏳',
                'needs_input': '❓'
            }.get(action.get('status', 'ready'), '▶️')

            output += f"{i}. {status_emoji} **{action['description']}**\n"

        output += f"""
---

## الخطة التنفيذية

**التعقيد:** {compiled.execution_plan.get('complexity', 'N/A')}
**التقدير:** {compiled.estimated_completion}
**الثقة في الترجمة:** {compiled.compilation_confidence:.0%}

"""

        for phase in compiled.execution_plan.get('phases', []):
            output += f"\n### {phase['name']}\n"
            for step in phase.get('steps', []):
                output += f"- {step}\n"

        output += f"""
---

## نقاط الموافقة المطلوبة

"""

        approval_points = compiled.execution_plan.get('approval_points', [])
        if approval_points:
            for point in approval_points:
                output += f"- ⚠️ {point}\n"
        else:
            output += "لا توجد نقاط موافقة - الخطة قابلة للتنفيذ التلقائي\n"

        return output
