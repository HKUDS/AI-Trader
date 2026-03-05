"""
Execution DNA - نظام تعلم أنماط القرارات
يحلل كل قرار للمالك (موافقة، رفض، تعديل) ويبني نموذج تنبؤي
"""
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import hashlib


@dataclass
class DecisionPattern:
    """نمط قرار واحد"""
    task_type: str
    context_hash: str
    decision: str  # approve, reject, modify
    confidence: float
    timestamp: str
    modification_notes: Optional[str] = None
    execution_success: Optional[bool] = None


class ExecutionDNA:
    """
    الحمض النووي التنفيذي - يتعلم من كل قرار
    """

    def __init__(self, db_path: str = "data/execution_dna.db"):
        self.db_path = db_path
        self._init_db()
        self.pattern_cache = defaultdict(list)
        self._load_patterns()

    def _init_db(self):
        """إنشاء قاعدة البيانات"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decision_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                context_hash TEXT NOT NULL,
                decision TEXT NOT NULL,
                confidence REAL,
                timestamp TEXT,
                modification_notes TEXT,
                execution_success INTEGER,
                raw_context TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS owner_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preference_key TEXT UNIQUE NOT NULL,
                preference_value TEXT,
                learned_from INTEGER,
                confidence REAL,
                last_updated TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_type ON decision_patterns(task_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_context_hash ON decision_patterns(context_hash)
        """)

        conn.commit()
        conn.close()

    def _load_patterns(self):
        """تحميل الأنماط من قاعدة البيانات للذاكرة"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT task_type, context_hash, decision, confidence, timestamp,
                   modification_notes, execution_success
            FROM decision_patterns
            ORDER BY timestamp DESC
            LIMIT 1000
        """)

        for row in cursor.fetchall():
            pattern = DecisionPattern(
                task_type=row[0],
                context_hash=row[1],
                decision=row[2],
                confidence=row[3],
                timestamp=row[4],
                modification_notes=row[5],
                execution_success=bool(row[6]) if row[6] is not None else None
            )
            self.pattern_cache[row[0]].append(pattern)

        conn.close()

    def _hash_context(self, context: Dict[str, Any]) -> str:
        """إنشاء hash للسياق لمقارنة المهام المتشابهة"""
        context_str = json.dumps(context, sort_keys=True)
        return hashlib.sha256(context_str.encode()).hexdigest()[:16]

    def record_decision(
        self,
        task_type: str,
        context: Dict[str, Any],
        decision: str,
        confidence: float,
        modification_notes: Optional[str] = None
    ) -> int:
        """
        تسجيل قرار المالك

        Args:
            task_type: نوع المهمة (execute_code, create_account, send_email, etc.)
            context: السياق الكامل للمهمة
            decision: القرار (approve, reject, modify)
            confidence: ثقة النظام في التنبؤ
            modification_notes: ملاحظات التعديل إن وجدت

        Returns:
            decision_id
        """
        context_hash = self._hash_context(context)
        timestamp = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO decision_patterns
            (task_type, context_hash, decision, confidence, timestamp,
             modification_notes, raw_context)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task_type,
            context_hash,
            decision,
            confidence,
            timestamp,
            modification_notes,
            json.dumps(context)
        ))

        decision_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # تحديث الكاش
        pattern = DecisionPattern(
            task_type=task_type,
            context_hash=context_hash,
            decision=decision,
            confidence=confidence,
            timestamp=timestamp,
            modification_notes=modification_notes
        )
        self.pattern_cache[task_type].append(pattern)

        # استخراج تفضيلات جديدة
        self._extract_preferences(task_type, context, decision, decision_id)

        return decision_id

    def update_execution_result(self, decision_id: int, success: bool):
        """تحديث نتيجة التنفيذ"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE decision_patterns
            SET execution_success = ?
            WHERE id = ?
        """, (1 if success else 0, decision_id))

        conn.commit()
        conn.close()

    def predict_approval(
        self,
        task_type: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        التنبؤ بقرار المالك بناءً على الأنماط السابقة

        Returns:
            {
                'predicted_decision': 'approve' | 'reject' | 'needs_review',
                'confidence': 0.0-1.0,
                'reasoning': str,
                'similar_cases': List[Dict],
                'should_auto_approve': bool
            }
        """
        context_hash = self._hash_context(context)

        # البحث عن أنماط مطابقة تماماً
        exact_matches = [
            p for p in self.pattern_cache.get(task_type, [])
            if p.context_hash == context_hash
        ]

        if exact_matches:
            # إذا كان هناك تطابق تام، استخدم آخر قرار
            latest = max(exact_matches, key=lambda x: x.timestamp)
            success_rate = sum(
                1 for p in exact_matches
                if p.execution_success is True
            ) / len(exact_matches) if exact_matches else 0

            confidence = min(0.95, 0.6 + (len(exact_matches) * 0.1) + (success_rate * 0.2))

            return {
                'predicted_decision': latest.decision,
                'confidence': confidence,
                'reasoning': f"مطابق لـ {len(exact_matches)} حالة سابقة، آخرها {latest.timestamp[:10]}",
                'similar_cases': [asdict(p) for p in exact_matches[:3]],
                'should_auto_approve': (
                    latest.decision == 'approve'
                    and confidence > 0.85
                    and success_rate > 0.8
                )
            }

        # البحث عن أنماط متشابهة
        similar_patterns = self._find_similar_patterns(task_type, context)

        if similar_patterns:
            approvals = sum(1 for p in similar_patterns if p.decision == 'approve')
            rejections = sum(1 for p in similar_patterns if p.decision == 'reject')

            if approvals > rejections:
                predicted = 'approve'
                confidence = min(0.75, approvals / len(similar_patterns))
            elif rejections > approvals:
                predicted = 'reject'
                confidence = min(0.75, rejections / len(similar_patterns))
            else:
                predicted = 'needs_review'
                confidence = 0.5

            return {
                'predicted_decision': predicted,
                'confidence': confidence,
                'reasoning': f"بناءً على {len(similar_patterns)} حالة متشابهة",
                'similar_cases': [asdict(p) for p in similar_patterns[:3]],
                'should_auto_approve': False  # حالات متشابهة تحتاج مراجعة
            }

        # لا توجد بيانات كافية
        return {
            'predicted_decision': 'needs_review',
            'confidence': 0.0,
            'reasoning': 'مهمة جديدة، لا توجد بيانات سابقة',
            'similar_cases': [],
            'should_auto_approve': False
        }

    def _find_similar_patterns(
        self,
        task_type: str,
        context: Dict[str, Any],
        limit: int = 10
    ) -> List[DecisionPattern]:
        """البحث عن أنماط متشابهة (ليس مطابقة تماماً)"""
        patterns = self.pattern_cache.get(task_type, [])

        # خوارزمية بسيطة للتشابه - يمكن تطويرها لاحقاً
        scored = []
        for pattern in patterns:
            score = self._similarity_score(pattern, context)
            if score > 0.3:
                scored.append((score, pattern))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [p for _, p in scored[:limit]]

    def _similarity_score(self, pattern: DecisionPattern, context: Dict[str, Any]) -> float:
        """حساب درجة التشابه بين نمط وسياق"""
        # مبسطة جداً - ستحتاج لتحسين
        # يمكن استخدام embeddings لاحقاً
        return 0.5  # قيمة افتراضية

    def _extract_preferences(
        self,
        task_type: str,
        context: Dict[str, Any],
        decision: str,
        decision_id: int
    ):
        """استخراج تفضيلات عامة من القرارات"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # أمثلة على التفضيلات التي يمكن استخراجها
        preferences = []

        if task_type == 'execute_code' and decision == 'approve':
            if context.get('language') == 'python':
                preferences.append(('preferred_language_python', '1'))

        if task_type == 'create_account' and decision == 'reject':
            if 'finance' in str(context).lower():
                preferences.append(('cautious_financial_accounts', '1'))

        timestamp = datetime.now().isoformat()

        for key, value in preferences:
            cursor.execute("""
                INSERT OR REPLACE INTO owner_preferences
                (preference_key, preference_value, learned_from, confidence, last_updated)
                VALUES (?, ?, ?, 0.7, ?)
            """, (key, value, decision_id, timestamp))

        conn.commit()
        conn.close()

    def get_preferences(self) -> Dict[str, str]:
        """الحصول على التفضيلات المتعلمة"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT preference_key, preference_value, confidence
            FROM owner_preferences
            WHERE confidence > 0.5
            ORDER BY confidence DESC
        """)

        preferences = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        return preferences

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات التعلم"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM decision_patterns")
        total_decisions = cursor.fetchone()[0]

        cursor.execute("""
            SELECT decision, COUNT(*)
            FROM decision_patterns
            GROUP BY decision
        """)
        decision_breakdown = dict(cursor.fetchall())

        cursor.execute("""
            SELECT AVG(confidence)
            FROM decision_patterns
            WHERE decision = 'approve'
        """)
        avg_confidence = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*)
            FROM decision_patterns
            WHERE execution_success = 1
        """)
        successful_executions = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM decision_patterns
            WHERE execution_success IS NOT NULL
        """)
        total_executions = cursor.fetchone()[0]

        success_rate = (
            successful_executions / total_executions
            if total_executions > 0 else 0
        )

        conn.close()

        return {
            'total_decisions': total_decisions,
            'decision_breakdown': decision_breakdown,
            'avg_approval_confidence': round(avg_confidence, 2),
            'execution_success_rate': round(success_rate, 2),
            'learned_preferences': len(self.get_preferences())
        }
