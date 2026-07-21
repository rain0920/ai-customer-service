"""
埋点 Code 节点 - 用于 Dify Chatflow 中各关键节点的数据采集
直接复制到 Dify Code 节点中使用

对应文档：效果评估/效果评估方案.md 第五节
"""

import json
import re
import time


# ============================================================
# 节点 A：意图分类埋点
# 放在 [Code: 解析意图] 节点之后
# 输入变量：intent(str), confidence(float), query(str), reason(str)
# ============================================================
def main(intent: str, confidence: float, query: str, reason: str = "") -> dict:
    """意图分类事件埋点"""
    payload = {
        "event": "intent_classify",
        "intent": intent,
        "confidence": confidence,
        "query": query,
        "reason": reason,
        "timestamp": int(time.time() * 1000),
    }
    # 后续通过 HTTP 请求节点发送到飞书多维表格
    # 此处返回 payload，供下游 HTTP 请求节点使用
    return {
        "logged": True,
        "event_type": "intent_classify",
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }


# ============================================================
# 节点 B：Code 解析结果埋点
# 放在 [Code: 解析意图] 节点之后
# 输入变量：parse_success(bool), error_reason(str)
# ============================================================
def main_parse(parse_success: bool = True, error_reason: str = "") -> dict:
    """JSON 解析事件埋点"""
    payload = {
        "event": "code_parse",
        "parse_success": parse_success,
        "error_reason": error_reason,
        "timestamp": int(time.time() * 1000),
    }
    return {
        "logged": True,
        "event_type": "code_parse",
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }


# ============================================================
# 节点 C：知识检索埋点
# 放在 [知识检索] 节点之后
# 输入变量：query(str), result_count(int), top_score(float), has_result(bool)
# ============================================================
def main_knowledge(query: str, result_count: int = 0, top_score: float = 0.0, has_result: bool = False) -> dict:
    """知识检索事件埋点"""
    payload = {
        "event": "knowledge_search",
        "query": query,
        "result_count": result_count,
        "top_score": top_score,
        "has_result": has_result,
        "timestamp": int(time.time() * 1000),
    }
    return {
        "logged": True,
        "event_type": "knowledge_search",
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }


# ============================================================
# 节点 D：回答生成埋点
# 放在 [LLM: 生成回答] 节点之后
# 输入变量：intent(str), has_knowledge(bool), answer_length(int)
# ============================================================
def main_answer(intent: str, has_knowledge: bool = False, answer_length: int = 0) -> dict:
    """回答生成事件埋点"""
    payload = {
        "event": "answer_generate",
        "intent": intent,
        "has_knowledge": has_knowledge,
        "answer_length": answer_length,
        "timestamp": int(time.time() * 1000),
    }
    return {
        "logged": True,
        "event_type": "answer_generate",
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }


# ============================================================
# 节点 E：转人工埋点
# 放在转人工分支
# 输入变量：reason(str), intent(str), confidence(float)
# ============================================================
def main_transfer(reason: str, intent: str = "", confidence: float = 0.0) -> dict:
    """转人工事件埋点"""
    payload = {
        "event": "transfer_human",
        "reason": reason,
        "intent": intent,
        "confidence": confidence,
        "timestamp": int(time.time() * 1000),
    }
    return {
        "logged": True,
        "event_type": "transfer_human",
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }


# ============================================================
# 节点 F：工单创建埋点
# 放在 [LLM: 工单生成] 节点之后
# 输入变量：category(str), priority(str)
# ============================================================
def main_ticket(category: str, priority: str) -> dict:
    """工单创建事件埋点"""
    payload = {
        "event": "ticket_create",
        "category": category,
        "priority": priority,
        "timestamp": int(time.time() * 1000),
    }
    return {
        "logged": True,
        "event_type": "ticket_create",
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }


# ============================================================
# 通用：会话汇总埋点
# 放在 [结束] 节点之前
# 输入变量：session_id(str), intent(str), resolution(str), 
#           turn_count(int), start_time(int)
# ============================================================
def main_session(session_id: str, intent: str, resolution: str, 
                 turn_count: int = 1, start_time: int = 0) -> dict:
    """会话结束汇总埋点
    
    resolution 取值：
    - "ai_resolved": AI 独立解决
    - "transferred": 转人工
    - "ticket_created": 生成工单
    - "abandoned": 用户中途离开
    """
    end_time = int(time.time() * 1000)
    duration = end_time - start_time if start_time > 0 else 0
    
    payload = {
        "event": "session_end",
        "session_id": session_id,
        "intent": intent,
        "resolution": resolution,
        "turn_count": turn_count,
        "duration_ms": duration,
        "timestamp": end_time,
    }
    return {
        "logged": True,
        "event_type": "session_end",
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }
