"""
RMF AI Dreams v2.0 - Next-Gen Execution Intelligence
Owner: REEM_RMF_2026

نظام تنفيذ ذكي يتعلم، يخطط، ويتكيف مع قرارات المالك
"""
import streamlit as st
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd
import plotly.graph_objects as go

# استيراد الوحدات الذكية
import sys
sys.path.insert(0, str(Path(__file__).parent))

from core.execution_dna import ExecutionDNA
from core.intent_reconstruction import IntentReconstructor
from core.shadow_planning import ShadowPlanner
from core.ai_orchestrator import AIOrchestrator
from core.idea_compiler import IdeaCompiler

# الإعدادات
st.set_page_config(
    page_title="RMF AI Dreams v2.0 🧬",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تحميل CSS
def load_css():
    css_path = Path(__file__).parent / "theme.css"
    if css_path.exists():
        with open(css_path) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

    # إضافة CSS للمكونات الجديدة
    st.markdown("""
    <style>
        .cognitive-header {
            background: linear-gradient(135deg, #FF00AA 0%, #AA00FF 50%, #00FFFF 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 42px;
            font-weight: 900;
            text-align: center;
            margin: 20px 0;
            text-shadow: 0 0 30px rgba(170, 0, 255, 0.8);
        }

        .dna-card {
            background: rgba(10, 0, 30, 0.7);
            border: 2px solid #AA00FF;
            border-radius: 15px;
            padding: 20px;
            margin: 15px 0;
            backdrop-filter: blur(15px);
            box-shadow: 0 0 20px rgba(170, 0, 255, 0.3);
        }

        .intent-layer {
            background: linear-gradient(90deg, rgba(255, 0, 170, 0.1), rgba(0, 255, 255, 0.1));
            border-left: 3px solid #00FFFF;
            padding: 10px 15px;
            margin: 8px 0;
            border-radius: 5px;
        }

        .shadow-plan {
            background: rgba(0, 0, 0, 0.5);
            border: 1px dashed #FF00AA;
            padding: 15px;
            margin: 10px 0;
            border-radius: 8px;
        }

        .confidence-meter {
            height: 10px;
            background: linear-gradient(90deg, #FF0000, #FFAA00, #00FF00);
            border-radius: 5px;
            margin: 5px 0;
        }

        .owner-code {
            color: #FF00AA;
            font-weight: 900;
            font-size: 14px;
            letter-spacing: 2px;
            text-shadow: 0 0 10px #FF00AA;
        }
    </style>
    """, unsafe_allow_html=True)

load_css()

# إنشاء المجلدات
Path("data").mkdir(exist_ok=True)

# تهيئة الأنظمة الذكية
@st.cache_resource
def init_intelligence():
    """تهيئة الذكاء"""
    return {
        'dna': ExecutionDNA(db_path="data/execution_dna.db"),
        'intent': IntentReconstructor(),
        'shadow': ShadowPlanner(),
        'ai': AIOrchestrator(),
        'compiler': IdeaCompiler()
    }

intelligence = init_intelligence()

# Session State
if 'owner_authenticated' not in st.session_state:
    st.session_state.owner_authenticated = False
if 'execution_history' not in st.session_state:
    st.session_state.execution_history = []
if 'current_task' not in st.session_state:
    st.session_state.current_task = None
if 'cognitive_state' not in st.session_state:
    st.session_state.cognitive_state = None

# التحقق من الهوية
def authenticate_owner():
    """التحقق من هوية المالك"""
    st.markdown('<h1 class="cognitive-header">🧬 RMF AI Dreams v2.0</h1>', unsafe_allow_html=True)
    st.markdown('<p class="owner-code">OWNER CODE REQUIRED</p>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        owner_code = st.text_input(
            "أدخل Owner Code",
            type="password",
            key="owner_code_input"
        )

        if st.button("🔓 Authenticate", use_container_width=True):
            if owner_code == "REEM_RMF_2026":
                st.session_state.owner_authenticated = True
                st.success("✅ تم التحقق - مرحباً Reem")
                st.rerun()
            else:
                st.error("❌ كود خاطئ")

if not st.session_state.owner_authenticated:
    authenticate_owner()
    st.stop()

# الواجهة الرئيسية
st.markdown('<h1 class="cognitive-header">🧠 RMF AI Dreams v2.0</h1>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### 🎛️ لوحة التحكم")

    # إحصائيات DNA
    dna_stats = intelligence['dna'].get_stats()
    st.metric("قرارات متعلمة", dna_stats['total_decisions'])
    st.metric("معدل النجاح", f"{dna_stats['execution_success_rate']:.0%}")
    st.metric("تفضيلات مكتشفة", dna_stats['learned_preferences'])

    st.markdown("---")

    # الحالة المعرفية
    if st.button("📊 Cognitive Briefing"):
        st.session_state.cognitive_state = intelligence['shadow'].get_cognitive_briefing()

    st.markdown("---")

    # تسجيل خروج
    if st.button("🚪 تسجيل خروج"):
        st.session_state.owner_authenticated = False
        st.rerun()

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🚀 Idea Compiler",
    "🧬 Execution DNA",
    "🎯 Intent Layers",
    "👁️ Shadow Plans",
    "💬 Cognitive Chat"
])

# Tab 1: Idea Compiler
with tab1:
    st.markdown("## 💡 Idea-to-Execution Compiler")
    st.markdown("*اكتب أي فكرة غامضة، وسأحولها لمشروع كامل*")

    idea_input = st.text_area(
        "الفكرة",
        placeholder="مثال: نفسي أعمل منتج يربط الناس بالإبداع",
        height=100
    )

    col1, col2 = st.columns([3, 1])

    with col1:
        include_code = st.checkbox("توليد كود أولي", value=True)
        include_branding = st.checkbox("توليد branding", value=True)

    with col2:
        if st.button("⚡ Compile", use_container_width=True, type="primary"):
            if idea_input:
                with st.spinner("🧠 جاري ترجمة الفكرة..."):
                    try:
                        # تنفيذ async
                        compiled = asyncio.run(
                            intelligence['compiler'].compile(
                                idea_input,
                                context={
                                    'include_code': include_code,
                                    'include_branding': include_branding
                                }
                            )
                        )

                        st.session_state.current_task = compiled

                        # عرض النتيجة
                        formatted = intelligence['compiler'].format_output(compiled)
                        st.markdown(formatted)

                        # عرض الأصول
                        if compiled.generated_assets:
                            st.markdown("### 📦 الأصول المولدة")

                            assets_cols = st.columns(3)

                            with assets_cols[0]:
                                if 'project_name' in compiled.generated_assets:
                                    st.info(f"**اسم المشروع:** {compiled.generated_assets['project_name']}")

                            with assets_cols[1]:
                                if 'domain_suggestions' in compiled.generated_assets:
                                    st.success(f"**Domain:** {compiled.generated_assets['domain_suggestions'][0]}")

                            with assets_cols[2]:
                                if 'tech_stack' in compiled.generated_assets:
                                    st.warning(f"**Tech:** {', '.join(compiled.generated_assets['tech_stack'][:3])}")

                        # أزرار الإجراءات
                        st.markdown("### ⚡ الإجراءات")

                        action_cols = st.columns(len(compiled.next_actions))

                        for i, action in enumerate(compiled.next_actions):
                            with action_cols[i]:
                                if st.button(
                                    action['description'],
                                    key=f"action_{i}",
                                    use_container_width=True
                                ):
                                    st.info(f"تنفيذ: {action['action']}")

                    except Exception as e:
                        st.error(f"خطأ: {e}")
            else:
                st.warning("أدخل فكرة أولاً")

# Tab 2: Execution DNA
with tab2:
    st.markdown("## 🧬 Execution DNA")
    st.markdown("*الحمض النووي التنفيذي - تعلم أنماط قراراتك*")

    # إحصائيات مفصلة
    dna_stats = intelligence['dna'].get_stats()

    stat_cols = st.columns(4)

    with stat_cols[0]:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{dna_stats["total_decisions"]}</div>', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">قرارات</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with stat_cols[1]:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{dna_stats["execution_success_rate"]:.0%}</div>', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">نجاح</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with stat_cols[2]:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{dna_stats["avg_approval_confidence"]:.2f}</div>', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">ثقة</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with stat_cols[3]:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{dna_stats["learned_preferences"]}</div>', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">تفضيلات</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # توزيع القرارات
    if dna_stats['decision_breakdown']:
        st.markdown("### 📊 توزيع القرارات")

        df = pd.DataFrame([
            {'نوع القرار': k, 'العدد': v}
            for k, v in dna_stats['decision_breakdown'].items()
        ])

        fig = go.Figure(data=[
            go.Bar(
                x=df['نوع القرار'],
                y=df['العدد'],
                marker_color=['#FF00AA', '#AA00FF', '#00FFFF']
            )
        ])

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#FFFFFF'
        )

        st.plotly_chart(fig, use_container_width=True)

    # التفضيلات المتعلمة
    preferences = intelligence['dna'].get_preferences()
    if preferences:
        st.markdown("### 🎯 التفضيلات المتعلمة")
        for key, value in preferences.items():
            st.markdown(f"- **{key}:** {value}")

# Tab 3: Intent Layers
with tab3:
    st.markdown("## 🎯 طبقات النية")
    st.markdown("*فهم ما وراء الكلمات*")

    test_input = st.text_input(
        "جرّب إعادة بناء النية",
        placeholder="اكتب أي نص غامض..."
    )

    if st.button("🔍 تحليل النية"):
        if test_input:
            reconstructed = intelligence['intent'].reconstruct(test_input)

            st.markdown(f"**الهدف الرئيسي:** {reconstructed.primary_goal}")
            st.markdown(f"**درجة الغموض:** {reconstructed.ambiguity_score:.0%}")

            st.markdown("### 📊 طبقات الفهم")

            for layer in reconstructed.intent_layers:
                st.markdown('<div class="intent-layer">', unsafe_allow_html=True)
                st.markdown(f"**المستوى {layer.level}:** {layer.interpretation}")
                st.progress(layer.confidence)
                st.caption(f"التفسير: {layer.reasoning}")
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("### 🎯 الأهداف الفرعية")
            for goal in reconstructed.sub_goals:
                st.markdown(f"- {goal}")

            st.markdown("### ⚡ الإجراءات المقترحة")
            for action in reconstructed.suggested_actions:
                st.markdown(f"**{action['step']}.** {action['description']}")

# Tab 4: Shadow Plans
with tab4:
    st.markdown("## 👁️ Shadow Planning System")
    st.markdown("*الخطط الخفية - دائماً جاهزة*")

    if st.session_state.current_task:
        compiled = st.session_state.current_task

        st.markdown(f"### المهمة الحالية: {compiled.reconstructed_intent.primary_goal}")

        if compiled.shadow_plans:
            for i, plan in enumerate(compiled.shadow_plans):
                st.markdown('<div class="shadow-plan">', unsafe_allow_html=True)
                st.markdown(f"**خطة {i+1}:** {plan.plan_type}")
                st.markdown(f"*السبب:* {plan.reasoning}")
                st.markdown(f"*الثقة:* {plan.confidence:.0%}")

                if plan.risks:
                    with st.expander("⚠️ المخاطر"):
                        for risk in plan.risks:
                            st.markdown(f"- **{risk.risk_type}** ({risk.probability:.0%}): {risk.mitigation}")

                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("لا توجد خطط خفية حالياً")
    else:
        st.info("قم بترجمة فكرة أولاً في تبويب Idea Compiler")

    # الحالة المعرفية
    if st.session_state.cognitive_state:
        st.markdown("### 🧠 Cognitive Briefing")

        state = st.session_state.cognitive_state

        st.markdown(f"**خطط نشطة:** {state.active_plans}")
        st.markdown(f"**خطط خفية:** {state.shadow_plans}")
        st.markdown(f"**ثقة النظام:** {state.system_confidence:.0%}")

        if state.detected_patterns:
            st.markdown("**أنماط مكتشفة:**")
            for pattern in state.detected_patterns:
                st.markdown(f"- {pattern}")

        if state.predicted_bottlenecks:
            st.warning("**اختناقات متوقعة:**")
            for bottleneck in state.predicted_bottlenecks:
                st.markdown(f"- {bottleneck}")

        if state.recommended_optimizations:
            st.success("**تحسينات مقترحة:**")
            for opt in state.recommended_optimizations:
                st.markdown(f"- {opt}")

# Tab 5: Cognitive Chat
with tab5:
    st.markdown("## 💬 Cognitive Chat")
    st.markdown("*محادثة ذكية مع ذاكرة دائمة*")

    # Chat history
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []

    # عرض المحادثات
    for msg in st.session_state.chat_history:
        with st.chat_message(msg['role']):
            st.markdown(msg['content'])

    # Input
    if prompt := st.chat_input("اكتب أي شيء..."):
        # إضافة رسالة المستخدم
        st.session_state.chat_history.append({
            'role': 'user',
            'content': prompt
        })

        with st.chat_message("user"):
            st.markdown(prompt)

        # الرد
        with st.chat_message("assistant"):
            with st.spinner("🤔 أفكر..."):
                try:
                    # استخدام AI Orchestrator
                    from core.ai_orchestrator import AIRequest

                    request = AIRequest(
                        task_type='quick_task',
                        prompt=prompt,
                        context={
                            'chat_history': st.session_state.chat_history[-5:],
                            'dna_stats': intelligence['dna'].get_stats()
                        }
                    )

                    response = asyncio.run(intelligence['ai'].execute(request))

                    st.markdown(response.content)

                    # إضافة للتاريخ
                    st.session_state.chat_history.append({
                        'role': 'assistant',
                        'content': response.content
                    })

                except Exception as e:
                    st.error(f"خطأ: {e}")
                    st.markdown("عذراً، حدث خطأ. تأكد من إعداد API keys في `.env`")

# Footer
st.markdown("---")
st.markdown(
    '<p style="text-align: center; color: #666;">RMF AI Dreams v2.0 | Built for Reem | Owner Code: REEM_RMF_2026</p>',
    unsafe_allow_html=True
)
