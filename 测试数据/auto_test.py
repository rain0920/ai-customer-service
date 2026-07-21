"""
Dify 工作流批量测试脚本
读取 测试用例集.md，逐条调用 Dify API，结果写入本地 JSON
"""

import requests
import json
import time
import re
import os
import sys
import io

# 修复 Windows 控制台编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ============ 配置 ============
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"
API_KEY = "app-o5x7BbvpICVtzruI3IW9wCMp"
USER_ID = "auto-test-batch"
DELAY = 1.5  # 每条间隔秒数，避免限流

TEST_FILE = os.path.join(os.path.dirname(__file__), "测试用例集.md")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "测试结果.json")

# ============ 解析测试用例 ============
def parse_test_cases(filepath):
    """从 Markdown 表格中提取测试用例"""
    cases = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 匹配表格行：| 编号 | 用户输入 | 期望意图 | ... |
    pattern = r"\|\s*([A-Z]+?\d+)\s*\|\s*(.+?)\s*\|"
    for match in re.finditer(pattern, content):
        case_id = match.group(1)
        query = match.group(2).strip()
        # 跳过表头
        if case_id == "编号" or query == "用户输入":
            continue
        cases.append({"id": case_id, "query": query})

    return cases

# ============ 调用 Dify API ============
def call_dify(query):
    """调用 Dify 工作流，返回响应"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {},
        "query": query,
        "response_mode": "blocking",
        "user": USER_ID,
    }
    try:
        resp = requests.post(DIFY_API_URL, headers=headers, json=payload, timeout=30)
        return {
            "status_code": resp.status_code,
            "response": resp.json() if resp.status_code == 200 else resp.text,
        }
    except Exception as e:
        return {"status_code": 0, "response": str(e)}

# ============ 主流程 ============
def main():
    print("=" * 60)
    print("  Dify 工作流批量测试")
    print("=" * 60)

    cases = parse_test_cases(TEST_FILE)
    print(f"\n[INFO] 共解析 {len(cases)} 条测试用例\n")

    results = []
    success, fail = 0, 0
    start_time = time.time()

    for i, case in enumerate(cases, 1):
        case_id = case["id"]
        query = case["query"]

        print(f"[{i}/{len(cases)}] {case_id}: {query[:40]}{'...' if len(query) > 40 else ''}", end=" → ")

        result = call_dify(query)
        status = "PASS" if result["status_code"] == 200 else "FAIL"
        print(f"{status} (HTTP {result['status_code']})")

        if result["status_code"] == 200:
            # 提取关键信息
            resp_data = result["response"]
            results.append({
                "case_id": case_id,
                "query": query,
                "answer": resp_data.get("answer", ""),
                "conversation_id": resp_data.get("conversation_id", ""),
                "status": "success",
            })
            success += 1
        else:
            results.append({
                "case_id": case_id,
                "query": query,
                "error": str(result["response"]),
                "status": "failed",
            })
            fail += 1

        time.sleep(DELAY)

    elapsed = time.time() - start_time

    # 保存结果
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"  完成! 总耗时 {elapsed:.1f}s")
    print(f"  PASS: {success}   FAIL: {fail}")
    print(f"  结果已保存到: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
