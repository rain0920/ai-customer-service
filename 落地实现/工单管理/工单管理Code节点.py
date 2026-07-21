"""
工单管理 Code 节点 - Dify 工作流工单创建与流转
直接复制到 Dify Code 节点中使用

对应文档：产品化方案/工单全生命周期管理方案.md

功能：
1. 工单创建（解析 LLM 生成的工单 JSON，补充系统字段）
2. 工单状态流转（状态机）
3. 飞书多维表格写入
"""

import json
import re
import time
from datetime import datetime, timedelta
from typing import Optional


# ============================================================
# 模块一：工单创建 - 解析 LLM 输出 + 补充系统字段
# 放在 [LLM: 工单生成] 节点之后
# 输入变量：llm_output(str), user_id(str), conversation_summary(str)
# ============================================================

# 工单状态定义
TICKET_STATUS = {
    "pending": "待分配",
    "assigned": "处理中",
    "resolved": "已解决",
    "closed": "已关闭",
    "reopened": "已重新打开",
}

# 优先级 SLA 时效（小时）
PRIORITY_SLA = {
    "紧急": 2,
    "高": 4,
    "中": 8,
    "低": 24,
}


def parse_ticket_json(llm_output: str) -> dict:
    """解析 LLM 工单生成输出，兼容各种格式"""
    text = llm_output.strip()
    
    # 去除 <think> 标签
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    
    # 去除 markdown 代码块
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    text = text.strip()
    
    # 尝试提取 JSON
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    
    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    return {}


def generate_ticket_id() -> str:
    """生成唯一工单编号"""
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    # 简单计数器（实际使用时可用数据库自增或时间戳+随机数）
    seq = str(int(time.time() * 1000))[-4:]
    return f"TK-{date_str}-{seq}"


def calculate_sla_deadline(priority: str) -> str:
    """根据优先级计算 SLA 截止时间"""
    hours = PRIORITY_SLA.get(priority, 24)
    deadline = datetime.now() + timedelta(hours=hours)
    return deadline.strftime("%Y-%m-%dT%H:%M:%S")


def create_ticket(
    llm_output: str,
    user_id: str = "",
    source: str = "AI客服",
    conversation_snapshot: str = "",
) -> dict:
    """创建完整工单
    
    Args:
        llm_output: LLM 工单生成的原始输出
        user_id: 用户标识（脱敏后）
        source: 来源渠道
        conversation_snapshot: 对话摘要（脱敏后）
    
    Returns:
        完整工单对象
    """
    parsed = parse_ticket_json(llm_output)
    
    ticket_id = generate_ticket_id()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    priority = parsed.get("priority", "中")
    
    ticket = {
        # 系统字段
        "ticket_id": ticket_id,
        "created_at": now,
        "status": TICKET_STATUS["pending"],
        "user_id": user_id,
        "source": source,
        "sla_deadline": calculate_sla_deadline(priority),
        "conversation_snapshot": conversation_snapshot,
        
        # LLM 生成字段
        "summary": parsed.get("summary", ""),
        "category": parsed.get("category", "其他"),
        "priority": priority,
        "required_action": parsed.get("required_action", ""),
        "order_id": parsed.get("order_id", "无"),
        
        # 处理记录（初始为空）
        "assignee": "",
        "assigned_at": "",
        "resolved_at": "",
        "resolution_note": "",
        "satisfaction": 0,
    }
    
    return ticket


# Dify Code 节点入口：工单创建
def main(
    llm_output: str,
    user_id: str = "",
    conversation_snapshot: str = "",
) -> dict:
    """Dify Code 节点入口：创建工单
    
    放在 [LLM: 工单生成] 之后
    """
    ticket = create_ticket(
        llm_output=llm_output,
        user_id=user_id,
        conversation_snapshot=conversation_snapshot,
    )
    
    # 构造飞书多维表格的 fields
    feishu_fields = {
        "工单编号": ticket["ticket_id"],
        "创建时间": ticket["created_at"],
        "工单类型": ticket["category"],
        "优先级": ticket["priority"],
        "问题摘要": ticket["summary"],
        "用户标识": ticket["user_id"] or "未知",
        "处理状态": ticket["status"],
        "SLA截止时间": ticket["sla_deadline"],
        "建议处理方式": ticket["required_action"],
        "关联订单号": ticket["order_id"],
    }
    
    # 用户展示文本
    display_text = (
        f"工单已生成 ✅\n"
        f"编号：{ticket['ticket_id']}\n"
        f"类型：{ticket['category']} | 优先级：{ticket['priority']}\n"
        f"摘要：{ticket['summary']}\n"
        f"预计处理时效：{ticket['sla_deadline']}\n\n"
        f"💡 如需加急，输入「转人工」联系人工客服"
    )
    
    return {
        "ticket_created": True,
        "ticket_id": ticket["ticket_id"],
        "ticket_json": json.dumps(ticket, ensure_ascii=False),
        "feishu_fields_json": json.dumps(feishu_fields, ensure_ascii=False),
        "display_text": display_text,
        "category": ticket["category"],
        "priority": ticket["priority"],
        "summary": ticket["summary"],
    }


# ============================================================
# 模块二：工单状态机
# 用于工单状态流转（在工单管理后台调用，非 Dify 工作流中）
# ============================================================

class TicketStateMachine:
    """工单状态流转状态机
    
    状态转移规则：
    - 待分配 → 处理中（分配处理人）
    - 处理中 → 已解决（问题解决）
    - 处理中 → 已关闭（无效工单）
    - 已解决 → 已关闭（用户确认/超时自动）
    - 已解决 → 已重新打开（用户追问）
    - 已重新打开 → 处理中
    - 已关闭 → 已重新打开（用户重新反馈）
    """
    
    TRANSITIONS = {
        "待分配": ["处理中"],
        "处理中": ["已解决", "已关闭"],
        "已解决": ["已关闭", "已重新打开"],
        "已重新打开": ["处理中"],
        "已关闭": ["已重新打开"],
    }
    
    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        """检查状态流转是否合法"""
        allowed = cls.TRANSITIONS.get(from_status, [])
        return to_status in allowed
    
    @classmethod
    def transition(cls, ticket: dict, to_status: str, **kwargs) -> dict:
        """执行状态流转
        
        Args:
            ticket: 当前工单
            to_status: 目标状态
            **kwargs: 附加字段（assignee, resolution_note, satisfaction 等）
        
        Returns:
            更新后的工单
        """
        from_status = ticket.get("status", "待分配")
        
        if not cls.can_transition(from_status, to_status):
            raise ValueError(f"不允许从 [{from_status}] 流转到 [{to_status}]")
        
        ticket["status"] = to_status
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        # 根据目标状态更新对应字段
        if to_status == "处理中":
            ticket["assignee"] = kwargs.get("assignee", ticket.get("assignee", ""))
            ticket["assigned_at"] = now
        
        elif to_status == "已解决":
            ticket["resolved_at"] = now
            ticket["resolution_note"] = kwargs.get("resolution_note", "")
        
        elif to_status == "已关闭":
            ticket["satisfaction"] = kwargs.get("satisfaction", 0)
        
        elif to_status == "已重新打开":
            ticket["resolved_at"] = ""  # 清除解决时间
            ticket["satisfaction"] = 0  # 清除满意度
        
        return ticket
    
    @classmethod
    def check_sla(cls, ticket: dict) -> dict:
        """检查 SLA 状态
        
        Returns:
            {"sla_status": "正常/即将超时/已超时", "remaining_hours": float}
        """
        deadline_str = ticket.get("sla_deadline", "")
        if not deadline_str:
            return {"sla_status": "未知", "remaining_hours": 0}
        
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return {"sla_status": "未知", "remaining_hours": 0}
        
        now = datetime.now()
        remaining = (deadline - now).total_seconds() / 3600
        
        if remaining <= 0:
            return {"sla_status": "已超时", "remaining_hours": round(remaining, 1)}
        elif remaining <= 1:
            return {"sla_status": "即将超时", "remaining_hours": round(remaining, 1)}
        else:
            return {"sla_status": "正常", "remaining_hours": round(remaining, 1)}


# ============================================================
# 模块三：飞书多维表格工单查询
# 用于在 Dify 中查询已有工单状态
# ============================================================

def format_ticket_status_reply(ticket: dict) -> str:
    """格式化工单状态回复（用户查询工单进度时使用）"""
    status_emoji = {
        "待分配": "⏳",
        "处理中": "🔧",
        "已解决": "✅",
        "已关闭": "📁",
        "已重新打开": "🔄",
    }
    
    emoji = status_emoji.get(ticket.get("status", ""), "📋")
    
    return (
        f"亲，您的工单进度如下：\n\n"
        f"{emoji} 工单编号：{ticket.get('ticket_id', '')}\n"
        f"状态：{ticket.get('status', '')}\n"
        f"类型：{ticket.get('category', '')}\n"
        f"摘要：{ticket.get('summary', '')}\n\n"
        f"💡 如对处理进度有疑问，输入「转人工」联系客服"
    )


# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    # 测试工单创建
    print("=" * 60)
    print("工单创建测试")
    print("=" * 60)
    
    llm_out = '{"summary": "用户申请退货退款，原因是尺码偏大", "category": "退换货", "priority": "中", "required_action": "核实订单→确认退货地址→发起退款", "order_id": "无"}'
    ticket = create_ticket(llm_out, user_id="u_***1234")
    print(json.dumps(ticket, ensure_ascii=False, indent=2))
    
    # 测试状态流转
    print("\n" + "=" * 60)
    print("状态流转测试")
    print("=" * 60)
    
    sm = TicketStateMachine()
    
    # 待分配 → 处理中
    ticket = sm.transition(ticket, "处理中", assignee="张三")
    print(f"状态: {ticket['status']}, 处理人: {ticket['assignee']}")
    
    # 处理中 → 已解决
    ticket = sm.transition(ticket, "已解决", resolution_note="已联系用户确认退款")
    print(f"状态: {ticket['status']}, 备注: {ticket['resolution_note']}")
    
    # 已解决 → 已关闭
    ticket = sm.transition(ticket, "已关闭", satisfaction=5)
    print(f"状态: {ticket['status']}, 满意度: {ticket['satisfaction']}")
    
    # SLA 检查
    sla = sm.check_sla(ticket)
    print(f"SLA: {sla}")
    
    # 测试非法流转
    try:
        sm.transition(ticket, "待分配")
    except ValueError as e:
        print(f"预期错误: {e}")
