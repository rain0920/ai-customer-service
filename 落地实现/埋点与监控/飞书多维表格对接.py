"""
飞书多维表格对接 - 用于 Dify Chatflow 中 HTTP 请求节点
将埋点数据写入飞书多维表格，实现实时监控看板

对应文档：效果评估/效果评估方案.md 第七节 + 工单全生命周期管理方案.md 第三节

使用方式：
1. 在飞书创建多维表格，获取 app_token 和 table_id
2. 在飞书开放平台创建应用，获取 tenant_access_token
3. 在 Dify 中添加 HTTP 请求节点，调用飞书 API
"""

# ============================================================
# 飞书 API 配置（在 Dify HTTP 请求节点中配置）
# ============================================================
FEISHU_CONFIG = {
    "base_url": "https://open.feishu.cn/open-apis",
    "app_id": "cli_xxxxxxxxxxxxx",        # 替换为实际 App ID
    "app_secret": "xxxxxxxxxxxxxxxx",      # 替换为实际 App Secret
}


# ============================================================
# 方案一：通过 Dify HTTP 请求节点直接调用
# ============================================================
"""
在 Dify 工作流中，每个埋点 Code 节点之后添加 HTTP 请求节点：

HTTP 请求节点配置：
- 请求方法：POST
- URL：https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records
- 请求头：
  Authorization: Bearer {{飞书 tenant_access_token}}
  Content-Type: application/json
- 请求体：
{
  "fields": {
    "事件类型": "{{埋点Code.payload_json中的event_type}}",
    "事件详情": "{{埋点Code.payload_json中的payload}}",
    "时间": "{{埋点Code.payload_json中的timestamp}}"
  }
}
"""

# ============================================================
# 方案二：通过 Code 节点内调用（更灵活）
# ============================================================

import json
import time
import hmac
import hashlib
import requests


def get_tenant_token(app_id: str, app_secret: str) -> str:
    """获取飞书 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": app_id,
        "app_secret": app_secret
    })
    return resp.json().get("tenant_access_token", "")


def write_to_bitable(token: str, app_token: str, table_id: str, fields: dict) -> dict:
    """写入飞书多维表格"""
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json={"fields": fields})
    return resp.json()


# ============================================================
# Dify Code 节点入口：埋点数据写入飞书
# 输入变量：payload_json(str)
# ============================================================
def main(payload_json: str) -> dict:
    """将埋点数据写入飞书多维表格"""
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return {"success": False, "error": "payload 解析失败"}
    
    event_type = payload.get("event", "unknown")
    timestamp = payload.get("timestamp", int(time.time() * 1000))
    
    # 根据事件类型映射到飞书表格字段
    fields_map = {
        "intent_classify": {
            "事件类型": "意图分类",
            "意图": payload.get("intent", ""),
            "置信度": payload.get("confidence", 0),
            "用户问题": payload.get("query", ""),
            "分类理由": payload.get("reason", ""),
        },
        "code_parse": {
            "事件类型": "JSON解析",
            "解析成功": "是" if payload.get("parse_success") else "否",
            "失败原因": payload.get("error_reason", ""),
        },
        "knowledge_search": {
            "事件类型": "知识检索",
            "检索词": payload.get("query", ""),
            "结果数": payload.get("result_count", 0),
            "最高分": payload.get("top_score", 0),
            "有结果": "是" if payload.get("has_result") else "否",
        },
        "answer_generate": {
            "事件类型": "生成回答",
            "意图": payload.get("intent", ""),
            "有知识": "是" if payload.get("has_knowledge") else "否",
            "回答长度": payload.get("answer_length", 0),
        },
        "transfer_human": {
            "事件类型": "转人工",
            "转人工原因": payload.get("reason", ""),
            "意图": payload.get("intent", ""),
            "置信度": payload.get("confidence", 0),
        },
        "ticket_create": {
            "事件类型": "工单创建",
            "工单类型": payload.get("category", ""),
            "优先级": payload.get("priority", ""),
        },
        "session_end": {
            "事件类型": "会话结束",
            "意图": payload.get("intent", ""),
            "解决方式": payload.get("resolution", ""),
            "对话轮次": payload.get("turn_count", 0),
            "耗时(ms)": payload.get("duration_ms", 0),
        },
    }
    
    fields = fields_map.get(event_type, {"事件类型": event_type, "原始数据": payload_json})
    
    # 注意：在 Dify 中，以下飞书 API 调用需要通过 HTTP 请求节点完成
    # 此处返回结构化的 fields，供下游 HTTP 请求节点使用
    return {
        "success": True,
        "event_type": event_type,
        "fields_json": json.dumps(fields, ensure_ascii=False),
        # 以下是 HTTP 请求节点需要的参数
        "api_url": "https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
        "request_body": json.dumps({"fields": fields}, ensure_ascii=False),
    }
