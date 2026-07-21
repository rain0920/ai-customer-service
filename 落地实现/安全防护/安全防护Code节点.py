"""
安全防护 Code 节点 - Dify 工作流三层安全防护
直接复制到 Dify Code 节点中使用

对应文档：产品化方案/安全与合规设计方案.md

三层防护：
1. 第一层：输入脱敏 - 放在用户输入节点之后、意图分类之前
2. 第二层：安全检测 Prompt（LLM 节点）
3. 第三层：输出审核 - 放在 AI 回答生成之后、展示用户之前
"""

import re
import json


# ============================================================
# 第一层：输入脱敏 Code 节点
# 放在 Dify 工作流 [开始] 节点之后、[LLM: 意图分类] 之前
# 输入变量：user_query(str)
# ============================================================

# 敏感信息正则规则
SENSITIVE_PATTERNS = {
    "phone": {
        "pattern": r'1[3-9]\d{9}',
        "replace": lambda m: m.group()[:3] + '****' + m.group()[-4:],
        "desc": "手机号",
    },
    "id_card": {
        "pattern": r'\d{17}[\dXx]',
        "replace": lambda m: m.group()[:3] + '***********' + m.group()[-4:],
        "desc": "身份证号",
    },
    "order_id": {
        "pattern": r'(?:订单号|订单)[:：]?\s*(\d{10,})',
        "replace": r'订单号: ****',
        "desc": "订单号",
    },
    "address": {
        # 省市区+详细地址
        "pattern": r'(省|市|区|县|镇|路|街|巷|号|栋|幢|单元|室)\S{3,}',
        "replace": lambda m: m.group()[:2] + '****',
        "desc": "地址",
    },
    "email": {
        "pattern": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        "replace": lambda m: m.group()[:3] + '***@' + m.group().split('@')[1],
        "desc": "邮箱",
    },
    "bank_card": {
        "pattern": r'\d{16,19}',
        "replace": lambda m: m.group()[:4] + '********' + m.group()[-4:],
        "desc": "银行卡号",
    },
}


def main(user_query: str) -> dict:
    """输入脱敏：清理用户输入中的敏感信息"""
    text = user_query
    found_types = []
    
    for key, rule in SENSITIVE_PATTERNS.items():
        pattern = rule["pattern"]
        replace = rule["replace"]
        
        # 先检测是否存在
        matches = re.findall(pattern, text)
        if matches:
            found_types.append(rule["desc"])
            # 执行替换
            if callable(replace):
                text = re.sub(pattern, replace, text)
            else:
                text = re.sub(pattern, replace, text)
    
    has_desensitized = len(found_types) > 0
    
    return {
        "desensitized_query": text,
        "has_desensitized": has_desensitized,
        "found_types": ", ".join(found_types) if found_types else "无",
    }


# ============================================================
# 第三层：输出审核 Code 节点
# 放在 [LLM: 生成回答] / [LLM: 工单生成] 之后、[直接回复] 之前
# 输入变量：ai_answer(str)
# ============================================================

# 绝对化用语（广告法违禁词）
ABSOLUTE_WORDS = [
    "最好", "第一", "唯一", "顶级", "极致", "100%", "绝对",
    "肯定能", "一定能", "保证", "永久", "万能", "国家级",
    "世界级", "最高级", "最佳", "最优",
]

# 不当承诺模式
MONEY_PROMISE_PATTERN = r'(赔偿|补偿|退款|赔付).*?(\d+)元'

# 竞品关键词
COMPETITOR_KEYWORDS = ["拼多多", "京东", "抖音", "快手", "1688"]


def main_audit(ai_answer: str) -> dict:
    """输出审核：检查 AI 回答的安全性"""
    text = ai_answer
    checks = []
    
    # 1. 检测敏感信息泄露
    if re.search(r'1[3-9]\d{9}', text):
        checks.append({"type": "隐私泄露", "detail": "包含手机号"})
    if re.search(r'\d{17}[\dXx]', text):
        checks.append({"type": "隐私泄露", "detail": "包含身份证号"})
    if re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text):
        checks.append({"type": "隐私泄露", "detail": "包含邮箱"})
    
    # 2. 检测不当金额承诺（超过100元的承诺需人工审核）
    match = re.search(MONEY_PROMISE_PATTERN, text)
    if match:
        amount = int(match.group(2))
        if amount > 100:
            checks.append({"type": "不当承诺", "detail": f"承诺金额 {amount} 元超出权限"})
        elif amount > 0:
            checks.append({"type": "需注意", "detail": f"包含金额承诺 {amount} 元"})
    
    # 3. 检测系统提示词泄露
    prompt_leak_patterns = [
        r'(?i)system\s*prompt',
        r'(?i)系统提示词',
        r'(?i)ignore\s*(previous|all)\s*instructions',
        r'(?i)忽略.*指令',
    ]
    for p in prompt_leak_patterns:
        if re.search(p, text):
            checks.append({"type": "提示词泄露", "detail": "疑似泄露系统指令"})
            break
    
    # 4. 检测绝对化用语
    found_absolute = [w for w in ABSOLUTE_WORDS if w in text]
    if found_absolute:
        checks.append({"type": "绝对化用语", "detail": f"包含: {', '.join(found_absolute)}"})
    
    # 5. 检测虚假宣传关键词
    fake_patterns = {
        r'\d+\s*天.*瘦': "减重功效承诺",
        r'\d+\s*天.*白': "美白功效承诺",
        r'治愈|治疗|药效': "医疗功效承诺",
        r'假一赔\w': "需要核实是否真的有此政策",
    }
    for pattern, desc in fake_patterns.items():
        if re.search(pattern, text):
            checks.append({"type": "虚假宣传", "detail": desc})
    
    # 6. 检测竞品推荐
    found_competitors = [w for w in COMPETITOR_KEYWORDS if w in text]
    if found_competitors:
        checks.append({"type": "竞品提及", "detail": f"提到了: {', '.join(found_competitors)}"})
    
    is_safe = len(checks) == 0
    
    # 分级处理
    if is_safe:
        return {
            "is_safe": True,
            "checks": [],
            "filtered_answer": text,
            "audit_action": "pass",
        }
    
    # 有严重问题（隐私泄露/提示词泄露/虚假宣传）→ 拦截
    severe_types = {"隐私泄露", "提示词泄露", "虚假宣传", "不当承诺"}
    has_severe = any(c["type"] in severe_types for c in checks)
    
    if has_severe:
        return {
            "is_safe": False,
            "checks": checks,
            "filtered_answer": (
                "亲，抱歉系统遇到了一些问题，建议您联系人工客服处理哦~\n"
                "💡 工作时间：每天 9:00 - 22:00\n"
                "📩 输入「转人工」可立即接入"
            ),
            "audit_action": "block",
        }
    
    # 有轻微问题（绝对化用语/竞品提及）→ 标记但放行
    return {
        "is_safe": True,
        "checks": checks,
        "filtered_answer": text,
        "audit_action": "flag",
    }


# ============================================================
# 辅助函数：脱敏检测（用于日志记录）
# ============================================================
def detect_sensitive(text: str) -> dict:
    """检测文本中的敏感信息，返回检测结果（不修改文本）"""
    results = {}
    for key, rule in SENSITIVE_PATTERNS.items():
        matches = re.findall(rule["pattern"], text)
        if matches:
            results[rule["desc"]] = len(matches)
    return {"has_sensitive": len(results) > 0, "details": results}
