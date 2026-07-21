"""
效果评估脚本 - 测试执行 + Bad Case 采集 + 告警计算

对应文档：效果评估/效果评估方案.md

功能：
1. 测试结果自动统计（从测试日志中计算意图准确率、召回率等）
2. Bad Case 自动采集与格式化
3. 线上监控告警阈值计算
"""

import json
from typing import Optional
from collections import defaultdict


# ============================================================
# 模块一：测试结果统计
# 输入：测试日志（每条包含 expected_intent / actual_intent / has_result / answer_qualified）
# 输出：统计指标
# ============================================================

def calculate_metrics(test_results: list[dict]) -> dict:
    """计算测试指标
    
    Args:
        test_results: 测试结果列表
        [
            {
                "case_id": "SQ01",
                "query": "T恤是什么材质",
                "expected_intent": "售前咨询",
                "actual_intent": "售前咨询",
                "confidence": 0.95,
                "has_result": True,
                "answer_qualified": True,
                "notes": ""
            },
            ...
        ]
    """
    total = len(test_results)
    if total == 0:
        return {"error": "无测试数据"}
    
    # 意图准确率
    intent_correct = sum(1 for r in test_results if r.get("expected_intent") == r.get("actual_intent"))
    intent_accuracy = intent_correct / total
    
    # 知识检索命中率
    has_result_count = sum(1 for r in test_results if r.get("has_result"))
    knowledge_hit_rate = has_result_count / total
    
    # 回答合格率
    answer_qualified = sum(1 for r in test_results if r.get("answer_qualified"))
    answer_rate = answer_qualified / total
    
    # 综合评分
    overall_score = (intent_accuracy * 0.4 + knowledge_hit_rate * 0.3 + answer_rate * 0.3) * 100
    
    # 按意图分类统计
    intent_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in test_results:
        expected = r.get("expected_intent", "未知")
        intent_stats[expected]["total"] += 1
        if r.get("expected_intent") == r.get("actual_intent"):
            intent_stats[expected]["correct"] += 1
    
    intent_accuracy_detail = {}
    for intent, stats in intent_stats.items():
        intent_accuracy_detail[intent] = {
            "total": stats["total"],
            "correct": stats["correct"],
            "accuracy": round(stats["correct"] / stats["total"] * 100, 1),
        }
    
    # JSON 解析成功率（confidence > 0 视为解析成功）
    parse_success = sum(1 for r in test_results if r.get("confidence", 0) > 0)
    parse_rate = parse_success / total
    
    return {
        "total_cases": total,
        "intent_accuracy": round(intent_accuracy * 100, 1),
        "knowledge_hit_rate": round(knowledge_hit_rate * 100, 1),
        "answer_qualified_rate": round(answer_rate * 100, 1),
        "overall_score": round(overall_score, 1),
        "parse_success_rate": round(parse_rate * 100, 1),
        "intent_accuracy_detail": intent_accuracy_detail,
        "grade": _get_grade(overall_score),
    }


def _get_grade(score: float) -> str:
    """将综合评分转为等级"""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B+"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C"
    else:
        return "D"


# Dify Code 节点入口：测试结果统计
def main_metrics(test_results_json: str) -> dict:
    """Dify Code 节点入口：从 JSON 字符串解析并计算指标"""
    try:
        results = json.loads(test_results_json)
    except json.JSONDecodeError:
        return {"error": "测试数据 JSON 解析失败"}
    
    metrics = calculate_metrics(results)
    return {
        "metrics_json": json.dumps(metrics, ensure_ascii=False),
        **metrics,
    }


# ============================================================
# 模块二：Bad Case 自动采集与格式化
# 在 Dify 工作流中，当触发转人工/用户否定/低置信度时调用
# ============================================================

def format_bad_case(
    case_id: str,
    source: str,
    user_query: str,
    ai_intent: str,
    ai_confidence: float,
    ai_reason: str = "",
    expected_intent: str = "",
    correct_reason: str = "",
    context: list = None,
    status: str = "待分析",
) -> dict:
    """格式化 Bad Case 记录
    
    Args:
        case_id: Bad Case 编号
        source: 来源（转人工/用户否定/低置信度/用户投诉）
        user_query: 用户原始问题
        ai_intent: AI 识别的意图
        ai_confidence: AI 置信度
        ai_reason: AI 分类理由
        expected_intent: 期望的正确意图（人工标注）
        correct_reason: 正确分类的理由（人工标注）
        context: 对话上下文
        status: 处理状态
    """
    return {
        "bad_case_id": case_id,
        "timestamp": "",  # Dify 自动填充
        "source": source,
        "user_query": user_query,
        "ai_intent": ai_intent,
        "ai_confidence": ai_confidence,
        "ai_reason": ai_reason,
        "expected_intent": expected_intent,
        "correct_reason": correct_reason,
        "context": context or [],
        "status": status,
    }


# Bad Case 优先级判定
def calculate_priority(bad_case: dict, frequency: int = 0) -> dict:
    """根据 Bad Case 类型和频率计算优先级
    
    Returns:
        {"priority": "P0/P1/P2/P3", "score": int}
    """
    # 影响度评分
    impact_map = {
        "边界混淆": 3,   # 高影响
        "规则缺失": 3,
        "规则冲突": 2,   # 中影响
        "关键词误判": 2,
        "情绪误判": 1,   # 低影响
        "模型幻觉": 1,
    }
    
    # 频率评分
    if frequency >= 5:
        freq_score = 3  # 高频
    elif frequency >= 2:
        freq_score = 2  # 中频
    else:
        freq_score = 1  # 低频
    
    impact_score = impact_map.get(bad_case.get("type", "未知"), 1)
    total_score = impact_score * 10 + freq_score
    
    if total_score >= 33:
        priority = "P0"
    elif total_score >= 22:
        priority = "P1"
    elif total_score >= 11:
        priority = "P2"
    else:
        priority = "P3"
    
    return {"priority": priority, "score": total_score}


# Dify Code 节点入口：Bad Case 采集
def main_badcase(
    source: str,
    user_query: str,
    ai_intent: str,
    ai_confidence: float,
    ai_reason: str = "",
    context_json: str = "[]",
) -> dict:
    """Dify Code 节点入口：采集并格式化 Bad Case"""
    try:
        context = json.loads(context_json)
    except json.JSONDecodeError:
        context = []
    
    case_id = f"BC-{_get_date_str()}-{_get_counter()}"
    bad_case = format_bad_case(
        case_id=case_id,
        source=source,
        user_query=user_query,
        ai_intent=ai_intent,
        ai_confidence=ai_confidence,
        ai_reason=ai_reason,
        context=context,
    )
    
    return {
        "collected": True,
        "bad_case_json": json.dumps(bad_case, ensure_ascii=False),
        "case_id": case_id,
    }


# ============================================================
# 模块三：线上监控告警阈值计算
# ============================================================

class AlertEngine:
    """简易告警引擎 - 在 Dify Code 节点中使用"""
    
    # 告警阈值配置
    THRESHOLDS = {
        "transfer_rate_spike": {
            "name": "转人工率飙升",
            "description": "最近1小时转人工率 vs 过去24小时均值",
            "threshold": 2.0,  # 倍数
            "priority": "P0",
            "action": "飞书通知产品+运营",
        },
        "parse_failure_rate": {
            "name": "JSON解析失败率",
            "description": "解析失败次数 / 总分类次数",
            "threshold": 0.10,  # 10%
            "priority": "P0",
            "action": "飞书通知产品",
        },
        "knowledge_empty_rate": {
            "name": "知识检索空结果率",
            "description": "result为空 / 总检索次数",
            "threshold": 0.30,  # 30%
            "priority": "P1",
            "action": "飞书通知运营",
        },
        "long_conversation_rate": {
            "name": "单次对话轮次异常",
            "description": "单会话>10轮的占比",
            "threshold": 0.05,  # 5%
            "priority": "P1",
            "action": "标记待复查",
        },
        "intent_shift": {
            "name": "意图分布偏移",
            "description": "某类意图占比波动>50%",
            "threshold": 0.50,  # 50%
            "priority": "P2",
            "action": "次日周报体现",
        },
    }
    
    @staticmethod
    def check(current_value: float, baseline: float, alert_key: str) -> dict:
        """检查是否触发告警
        
        Args:
            current_value: 当前值
            baseline: 基线值（过去24小时均值）
            alert_key: 告警指标 key
        
        Returns:
            {"triggered": bool, "message": str, "priority": str}
        """
        config = AlertEngine.THRESHOLDS.get(alert_key)
        if not config:
            return {"triggered": False, "message": "未知告警指标", "priority": "无"}
        
        if baseline == 0:
            ratio = float('inf') if current_value > 0 else 0
        else:
            ratio = current_value / baseline
        
        triggered = ratio >= config["threshold"]
        
        return {
            "triggered": triggered,
            "metric": config["name"],
            "current_value": current_value,
            "baseline": baseline,
            "ratio": round(ratio, 2),
            "threshold": config["threshold"],
            "priority": config["priority"],
            "action": config["action"] if triggered else "无需处理",
            "message": (
                f"⚠️ {config['name']}告警：当前{current_value}，基线{baseline}，"
                f"比值{ratio:.2f}，超过阈值{config['threshold']}"
            ) if triggered else "正常",
        }


# Dify Code 节点入口：告警检查
def main_alert(
    metric_key: str,
    current_value: float,
    baseline: float,
) -> dict:
    """Dify Code 节点入口：检查是否触发告警"""
    result = AlertEngine.check(current_value, baseline, metric_key)
    return result


# ============================================================
# 辅助函数
# ============================================================
_counter = 0

def _get_date_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d")

def _get_counter() -> str:
    global _counter
    _counter += 1
    return str(_counter).zfill(3)


# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    # 测试指标计算
    print("=" * 60)
    print("效果指标计算测试")
    print("=" * 60)
    
    test_data = [
        {"case_id": "SQ01", "expected_intent": "售前咨询", "actual_intent": "售前咨询", "confidence": 0.95, "has_result": True, "answer_qualified": True},
        {"case_id": "SQ02", "expected_intent": "售前咨询", "actual_intent": "售前咨询", "confidence": 0.92, "has_result": True, "answer_qualified": True},
        {"case_id": "DD01", "expected_intent": "订单查询", "actual_intent": "订单查询", "confidence": 0.88, "has_result": True, "answer_qualified": True},
        {"case_id": "TH01", "expected_intent": "退换货", "actual_intent": "退换货", "confidence": 0.90, "has_result": False, "answer_qualified": False},
        {"case_id": "TS01", "expected_intent": "投诉", "actual_intent": "退换货", "confidence": 0.70, "has_result": True, "answer_qualified": False},
        {"case_id": "XL01", "expected_intent": "闲聊", "actual_intent": "闲聊", "confidence": 0.96, "has_result": True, "answer_qualified": True},
        {"case_id": "QT01", "expected_intent": "其他", "actual_intent": "其他", "confidence": 0.85, "has_result": False, "answer_qualified": False},
    ]
    
    metrics = calculate_metrics(test_data)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    
    # 测试告警
    print("\n" + "=" * 60)
    print("告警检查测试")
    print("=" * 60)
    alert = AlertEngine.check(current_value=0.55, baseline=0.20, alert_key="transfer_rate_spike")
    print(json.dumps(alert, ensure_ascii=False, indent=2))
