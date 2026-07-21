"""
意图分类持续优化脚本 - Bad Case 采集 + 回归测试集管理

对应文档：产品化方案/意图分类持续优化闭环.md

功能：
1. Bad Case 自动采集（在 Dify 工作流中触发）
2. Bad Case 分类与优先级判定
3. 回归测试集管理
4. Prompt 迭代记录模板
"""

import json
from datetime import datetime
from collections import defaultdict
from typing import Optional


# ============================================================
# 模块一：Bad Case 自动采集
# 放在 Dify 工作流的以下位置：
#   - 转人工分支 → 采集 Bad Case
#   - 低置信度分支 → 采集 Bad Case
# ============================================================

# Bad Case 分类体系
BAD_CASE_TYPES = {
    "边界混淆": {
        "description": "两个意图之间边界模糊",
        "example": '"质量差想退款" → 投诉 vs 退换货',
        "impact": "高",
    },
    "规则缺失": {
        "description": "新出现的表达方式未被覆盖",
        "example": '"这个踩雷了"（=不满意）',
        "impact": "高",
    },
    "规则冲突": {
        "description": "两条规则给出相反结论",
        "example": '同时命中投诉和退换货规则',
        "impact": "中",
    },
    "关键词误判": {
        "description": "关键词匹配过于粗暴",
        "example": '"这衣服投诉率低吗"（售前咨询，非投诉）',
        "impact": "中",
    },
    "情绪误判": {
        "description": "把中性表达当负面情绪",
        "example": '"怎么样"被误判为不满',
        "impact": "低",
    },
    "模型幻觉": {
        "description": "模型输出与 Prompt 规则矛盾",
        "example": 'Prompt 明确写了规则，模型没遵守',
        "impact": "低",
    },
}


def classify_bad_case(
    user_query: str,
    ai_intent: str,
    ai_confidence: float,
    ai_reason: str,
    expected_intent: str = "",
) -> dict:
    """自动分类 Bad Case 类型
    
    基于启发式规则进行初步分类，人工复核确认
    """
    classifications = []
    
    # 规则1：置信度低但无特殊表达 → 规则缺失
    if ai_confidence < 0.5:
        classifications.append({"type": "规则缺失", "confidence": 0.8})
    
    # 规则2：AI 分类与预期不同且涉及关键词 → 关键词误判
    if expected_intent and expected_intent != ai_intent:
        if any(kw in user_query for kw in ["投诉", "退货", "退款", "质量", "材质", "颜色"]):
            classifications.append({"type": "关键词误判", "confidence": 0.6})
    
    # 规则3：confidence > 0.7 但分类错误 → 边界混淆
    if expected_intent and expected_intent != ai_intent and ai_confidence > 0.7:
        classifications.append({"type": "边界混淆", "confidence": 0.7})
    
    # 规则4：confidence 高但 reason 与 Prompt 矛盾 → 模型幻觉
    if ai_confidence > 0.8:
        classifications.append({"type": "模型幻觉", "confidence": 0.4})
    
    # 规则5：包含情感词但非投诉场景 → 情绪误判
    emotion_words = ["烦", "气死", "无语", "失望", "垃圾"]
    if any(w in user_query for w in emotion_words) and expected_intent != "投诉":
        classifications.append({"type": "情绪误判", "confidence": 0.5})
    
    if not classifications:
        classifications.append({"type": "规则缺失", "confidence": 0.5})
    
    # 取置信度最高的
    classifications.sort(key=lambda x: x["confidence"], reverse=True)
    return classifications[0]


def calculate_priority(bad_case_type: str, frequency: int = 0) -> dict:
    """根据 Bad Case 类型和频率计算优先级
    
    Returns:
        {"priority": "P0/P1/P2/P3", "score": int, "suggestion": str}
    """
    impact_map = {
        "边界混淆": 3,
        "规则缺失": 3,
        "规则冲突": 2,
        "关键词误判": 2,
        "情绪误判": 1,
        "模型幻觉": 1,
    }
    
    freq_map = {1: 3, 2: 2, 3: 1}  # frequency -> score
    if frequency >= 5:
        freq_score = 3
    elif frequency >= 2:
        freq_score = 2
    else:
        freq_score = 1
    
    impact_score = impact_map.get(bad_case_type, 1)
    total_score = impact_score * 10 + freq_score
    
    if total_score >= 33:
        priority = "P0"
        suggestion = "立即修复（本周内）"
    elif total_score >= 22:
        priority = "P1"
        suggestion = "下个迭代修复"
    elif total_score >= 11:
        priority = "P2"
        suggestion = "排入 Backlog"
    else:
        priority = "P3"
        suggestion = "暂缓，持续观察"
    
    return {
        "priority": priority,
        "score": total_score,
        "suggestion": suggestion,
    }


# Dify Code 节点入口：Bad Case 采集
def main_collect(
    source: str,
    user_query: str,
    ai_intent: str,
    ai_confidence: float,
    ai_reason: str = "",
    expected_intent: str = "",
    context_json: str = "[]",
) -> dict:
    """Dify Code 节点入口：采集 Bad Case
    
    输入变量：
    - source: 触发来源（transfer_human / low_confidence / user_deny / user_complaint）
    - user_query: 用户原始问题
    - ai_intent: AI 分类意图
    - ai_confidence: AI 置信度
    - ai_reason: AI 分类理由
    - expected_intent: 人工标注的正确意图（可选）
    - context_json: 对话上下文 JSON
    """
    try:
        context = json.loads(context_json) if isinstance(context_json, str) else context_json
    except json.JSONDecodeError:
        context = []
    
    # 自动分类
    auto_class = classify_bad_case(user_query, ai_intent, ai_confidence, ai_reason, expected_intent)
    
    # 格式化 Bad Case
    case_id = f"BC-{datetime.now().strftime('%Y%m%d')}-{_get_seq()}"
    bad_case = {
        "bad_case_id": case_id,
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source": source,
        "user_query": user_query,
        "ai_intent": ai_intent,
        "ai_confidence": ai_confidence,
        "ai_reason": ai_reason,
        "expected_intent": expected_intent or ai_intent,
        "auto_classification": auto_class["type"],
        "context": context,
        "status": "待分析",
    }
    
    return {
        "collected": True,
        "case_id": case_id,
        "auto_type": auto_class["type"],
        "bad_case_json": json.dumps(bad_case, ensure_ascii=False),
    }


# ============================================================
# 模块二：回归测试集管理
# ============================================================

class RegressionTestManager:
    """回归测试集管理器
    
    维护三套测试集：
    1. 全量回归集（100条）：每次 Prompt 变更必须全部通过
    2. Bad Case 专项集：本次修复相关的 5-10 条，必须 100% 通过
    3. 易误判集（10条）：边界场景，准确率 ≥ 90%
    """
    
    def __init__(self):
        self.full_regression: list[dict] = []
        self.bad_case_specific: list[dict] = []
        self.edge_cases: list[dict] = []
    
    def add_to_regression(self, case: dict, test_set: str = "full"):
        """添加用例到测试集"""
        test_case = {
            "case_id": case.get("case_id", f"REG-{len(self.full_regression)+1}"),
            "query": case["query"],
            "expected_intent": case["expected_intent"],
            "source": case.get("source", "manual"),
            "added_at": datetime.now().strftime("%Y-%m-%d"),
            "notes": case.get("notes", ""),
        }
        
        if test_set == "bad_case":
            self.bad_case_specific.append(test_case)
        elif test_set == "edge":
            self.edge_cases.append(test_case)
        else:
            self.full_regression.append(test_case)
    
    def from_bad_case(self, bad_case: dict) -> dict:
        """将 Bad Case 转化为回归测试用例"""
        return {
            "case_id": f"REG-{bad_case.get('bad_case_id', 'NEW')}",
            "query": bad_case["user_query"],
            "expected_intent": bad_case["expected_intent"],
            "source": f"bad_case:{bad_case.get('source', 'unknown')}",
            "added_at": datetime.now().strftime("%Y-%m-%d"),
            "notes": f"原始 Bad Case: {bad_case.get('auto_classification', '未知')}",
        }
    
    def run_regression(self, test_results: list[dict]) -> dict:
        """运行回归测试并统计结果
        
        Args:
            test_results: 测试结果列表
        
        Returns:
            测试报告
        """
        total = len(test_results)
        if total == 0:
            return {"passed": True, "accuracy": 0, "message": "无测试用例"}
        
        passed = sum(1 for r in test_results if r.get("expected_intent") == r.get("actual_intent"))
        accuracy = passed / total
        
        return {
            "passed": accuracy >= 0.90,  # 90% 为通过线
            "accuracy": round(accuracy * 100, 1),
            "total": total,
            "passed_count": passed,
            "failed_count": total - passed,
            "failed_cases": [
                {
                    "case_id": r.get("case_id", ""),
                    "query": r.get("query", ""),
                    "expected": r.get("expected_intent", ""),
                    "actual": r.get("actual_intent", ""),
                }
                for r in test_results
                if r.get("expected_intent") != r.get("actual_intent")
            ],
        }


# ============================================================
# 模块三：Prompt 迭代记录模板
# ============================================================

def generate_iteration_record(
    iteration_number: int,
    fixed_issue: str,
    bad_case_count: int,
    root_cause: str,
    changes: str,
    examples_added: list[str],
    regression_accuracy_before: float,
    regression_accuracy_after: float,
    side_effects_checked: str,
) -> str:
    """生成 Prompt 迭代记录（Markdown 格式）"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    record = f"""## 迭代 #{iteration_number} - {date_str}

**修复问题：** {fixed_issue}
**Bad Case 数量：** 本周出现 {bad_case_count} 次
**根因：** {root_cause}

**修改内容：**
{changes}

**新增示例：**
{chr(10).join(f'- "{ex}"' for ex in examples_added)}

**回归测试结果：**
- 变更前准确率：{regression_accuracy_before}%
- 变更后准确率：{regression_accuracy_after}%
- 变化：{regression_accuracy_after - regression_accuracy_before:+.1f}%

**副作用检查：** {side_effects_checked}
"""
    return record


# Dify Code 节点入口：迭代记录生成
def main_iteration_record(
    iteration_number: int,
    fixed_issue: str,
    bad_case_count: int,
    root_cause: str,
    changes: str,
    examples_json: str = "[]",
    regression_before: float = 0.0,
    regression_after: float = 0.0,
    side_effects: str = "未发现副作用",
) -> dict:
    """Dify Code 节点入口：生成迭代记录"""
    try:
        examples = json.loads(examples_json)
    except json.JSONDecodeError:
        examples = []
    
    record = generate_iteration_record(
        iteration_number=iteration_number,
        fixed_issue=fixed_issue,
        bad_case_count=bad_case_count,
        root_cause=root_cause,
        changes=changes,
        examples_added=examples,
        regression_accuracy_before=regression_before,
        regression_accuracy_after=regression_after,
        side_effects_checked=side_effects,
    )
    
    return {
        "generated": True,
        "record_markdown": record,
    }


# ============================================================
# 辅助函数
# ============================================================
_seq_counter = 0

def _get_seq() -> str:
    global _seq_counter
    _seq_counter += 1
    return str(_seq_counter).zfill(3)


# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    # 测试 Bad Case 分类
    print("=" * 60)
    print("Bad Case 分类测试")
    print("=" * 60)
    
    test_cases = [
        ("这件衣服质量太差我要退款", "投诉", 0.88, "包含'质量太差'表达不满", "退换货"),
        ("这个踩雷了，太差了", "售前咨询", 0.55, "没有明确意图", "投诉"),
        ("T恤是什么材质", "投诉", 0.92, "可能对质量问题不满", "售前咨询"),
    ]
    
    for query, intent, conf, reason, expected in test_cases:
        result = classify_bad_case(query, intent, conf, reason, expected)
        priority = calculate_priority(result["type"], frequency=5)
        print(f"Query: {query}")
        print(f"  AI: {intent}({conf}) | Expected: {expected}")
        print(f"  Type: {result['type']} | Priority: {priority['priority']}")
        print()
    
    # 测试迭代记录生成
    print("=" * 60)
    print("迭代记录生成测试")
    print("=" * 60)
    record = generate_iteration_record(
        iteration_number=3,
        fixed_issue='"质量差想退款"被误判为投诉',
        bad_case_count=8,
        root_cause='"质量差"触发了投诉规则，但用户实际诉求是退款（退换货）',
        changes="- 新增规则：当同时出现"质量描述+退款诉求"时，优先判为退换货\n- 新增示例：用户说"质量太差想退款"→ 退换货",
        examples_added=['"质量太差想退款"→ 退换货', '"这衣服有问题我要退"→ 退换货'],
        regression_accuracy_before=90.0,
        regression_accuracy_after=92.0,
        side_effects_checked='真正投诉场景（"质量太差我要投诉你们"）仍正确分类',
    )
    print(record)
