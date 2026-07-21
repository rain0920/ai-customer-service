"""
知识库运营脚本 - 商品 FAQ 模板生成 + 未命中 Query 聚类分析

对应文档：产品化方案/知识库可持续运营方案.md

使用场景：
1. 商品 FAQ 模板生成：新商品上线时，用商品属性自动生成 FAQ 文档
2. 未命中 Query 聚类：分析知识检索失败的问题，发现知识缺口
"""

import json
import re
from collections import defaultdict
from typing import Optional


# ============================================================
# 模块一：商品 FAQ 模板自动生成
# 在 Dify Code 节点中使用，或作为独立脚本运行
# ============================================================

# 服装类目 FAQ 模板
CLOTHING_FAQ_TEMPLATE = """# {商品名称}-商品FAQ

## 材质相关
- Q: {商品名称}是什么材质？
  A: {材质成分}，{材质特点}
- Q: {商品名称}会起球吗？
  A: {起球说明}
- Q: {商品名称}会缩水吗？
  A: {缩水说明}
- Q: {商品名称}会掉色吗？
  A: {掉色说明}

## 尺码相关
- Q: {商品名称}偏大还是偏小？
  A: {版型说明}，{尺码建议}
- Q: 身高{身高示例1}体重{体重示例1}穿什么码？
  A: 参考尺码表，建议{推荐尺码1}
- Q: 身高{身高示例2}体重{体重示例2}穿什么码？
  A: 参考尺码表，建议{推荐尺码2}
- Q: {商品名称}有加大码吗？
  A: {大码说明}

## 颜色相关
- Q: {商品名称}有哪些颜色？
  A: {颜色列表}
- Q: {商品名称}白色会透吗？
  A: {透度说明}
- Q: {商品名称}实物和图片有色差吗？
  A: {色差说明}

## 穿着场景
- Q: {商品名称}适合什么季节穿？
  A: {季节说明}
- Q: {商品名称}适合什么场合穿？
  A: {场合说明}

## 洗涤保养
- Q: {商品名称}怎么洗？
  A: {洗涤说明}
- Q: {商品名称}能用洗衣机洗吗？
  A: {机洗说明}
"""

# 商品属性默认值（按类目）
DEFAULT_VALUES = {
    "T恤": {
        "材质成分": "100%新疆长绒棉",
        "材质特点": "220g高克重，精梳棉工艺，柔软亲肤",
        "起球说明": "精梳工艺处理，不易起球",
        "缩水说明": "预缩处理，缩水率<3%",
        "掉色说明": "活性染色工艺，正常洗涤不掉色",
        "版型说明": "标准版型，不挑身材",
        "尺码建议": "按身高体重对照尺码表选择",
        "身高示例1": "170cm", "体重示例1": "60kg", "推荐尺码1": "M码",
        "身高示例2": "175cm", "体重示例2": "75kg", "推荐尺码2": "L码",
        "大码说明": "最大到XXL，适合体重90kg以内",
        "颜色列表": "白色、黑色、灰色、藏青色、军绿色",
        "透度说明": "220g高克重面料，白色不透",
        "色差说明": "实物拍摄，因显示器不同可能有轻微色差",
        "季节说明": "四季通用，夏季单穿、春秋打底",
        "场合说明": "日常休闲、通勤百搭",
        "洗涤说明": "建议手洗或轻柔机洗，水温不超过30℃，阴凉处晾干",
        "机洗说明": "可以机洗，建议放入洗衣袋，选择轻柔模式",
    },
    "卫衣": {
        "材质成分": "320g重磅毛圈面料，棉+聚酯纤维混纺",
        "材质特点": "320g重磅，抗起球处理，抗静电",
        "起球说明": "抗起球处理，正常穿着不易起球",
        "缩水说明": "预缩处理，缩水率<3%",
        "掉色说明": "活性染色工艺，正常洗涤不掉色",
        "版型说明": "宽松oversized版型，落肩设计",
        "尺码建议": "喜欢合身选小一码，喜欢宽松按正常尺码",
        "身高示例1": "165cm", "体重示例1": "55kg", "推荐尺码1": "M码（宽松效果）",
        "身高示例2": "180cm", "体重示例2": "80kg", "推荐尺码2": "XL码",
        "大码说明": "最大到3XL，宽松版型包容度高",
        "颜色列表": "白色、黑色、灰色、卡其色、藏青色",
        "透度说明": "320g重磅面料，不透",
        "色差说明": "实物拍摄，因显示器不同可能有轻微色差",
        "季节说明": "春秋单穿、冬季叠穿，加绒款适合0-10℃",
        "场合说明": "日常休闲、运动、校园",
        "洗涤说明": "建议手洗或轻柔机洗，水温不超过30℃",
        "机洗说明": "可以机洗，建议翻面洗涤、放入洗衣袋",
    },
    "牛仔裤": {
        "材质成分": "95%棉+5%氨纶微弹面料",
        "材质特点": "含氨纶微弹，穿着舒适不紧绷",
        "起球说明": "不易起球",
        "缩水说明": "预缩处理，缩水率<3%",
        "掉色说明": "深色首次洗涤有轻微浮色属正常，建议加盐固色",
        "版型说明": "直筒版型，高腰设计，立体裁剪不卡裆",
        "尺码建议": "按腰围选择尺码，68-72cm选M码",
        "身高示例1": "170cm", "体重示例1": "60kg", "推荐尺码1": "M码（腰围72cm）",
        "身高示例2": "175cm", "体重示例2": "75kg", "推荐尺码2": "L码（腰围76cm）",
        "大码说明": "最大到36码，腰围92cm",
        "颜色列表": "深蓝色、浅蓝色、黑色",
        "透度说明": "牛仔面料，不透",
        "色差说明": "实物拍摄，因显示器不同可能有轻微色差",
        "季节说明": "四季通用，常规厚度",
        "场合说明": "日常休闲、通勤百搭",
        "洗涤说明": "建议翻面手洗或机洗，深色与浅色分开，水温不超过30℃",
        "机洗说明": "可以机洗，建议翻面、使用洗衣袋",
    },
    "羽绒服": {
        "材质成分": "90%白鸭绒，防钻绒面料",
        "材质特点": "90%白鸭绒填充，蓬松度700+，四层锁绒工艺",
        "起球说明": "防钻绒面料，不易起球",
        "缩水说明": "建议干洗，水洗可能影响蓬松度",
        "掉色说明": "正常不掉色",
        "版型说明": "宽松版型，可内搭厚毛衣",
        "尺码建议": "按身高体重对照尺码表，160cm/50kg建议S码",
        "身高示例1": "160cm", "体重示例1": "50kg", "推荐尺码1": "S码",
        "身高示例2": "175cm", "体重示例2": "75kg", "推荐尺码2": "L码",
        "大码说明": "最大到3XL，适合体重100kg以内",
        "颜色列表": "黑色、白色、藏青色、卡其色",
        "透度说明": "羽绒服不透",
        "色差说明": "实物拍摄，因显示器不同可能有轻微色差",
        "季节说明": "冬季，适合0℃-10℃穿着",
        "场合说明": "日常保暖、通勤、户外",
        "洗涤说明": "建议干洗，不可水洗，不可暴晒，收纳时避免真空压缩",
        "机洗说明": "不建议机洗，可能影响羽绒蓬松度",
    },
}


def generate_faq(
    product_name: str,
    category: str = "T恤",
    overrides: Optional[dict] = None,
) -> str:
    """根据商品属性自动生成 FAQ 文档
    
    Args:
        product_name: 商品名称，如 "纯棉宽松T恤"
        category: 商品类目，如 "T恤"、"卫衣"、"牛仔裤"、"羽绒服"
        overrides: 覆盖默认值的自定义属性 dict
    
    Returns:
        生成的 FAQ Markdown 文本
    """
    # 获取类目默认值
    defaults = DEFAULT_VALUES.get(category, DEFAULT_VALUES["T恤"]).copy()
    
    # 用自定义属性覆盖
    if overrides:
        defaults.update(overrides)
    
    # 填充模板
    defaults["商品名称"] = product_name
    return CLOTHING_FAQ_TEMPLATE.format(**defaults)


# Dify Code 节点入口：商品 FAQ 生成
def main(product_name: str, category: str = "T恤", custom_attrs: str = "{}") -> dict:
    """Dify Code 节点入口：根据商品属性生成 FAQ
    
    输入变量：
    - product_name: 商品名称
    - category: 类目（T恤/卫衣/牛仔裤/羽绒服）
    - custom_attrs: 自定义属性 JSON 字符串（可选）
    """
    try:
        overrides = json.loads(custom_attrs) if custom_attrs else {}
    except json.JSONDecodeError:
        overrides = {}
    
    faq_content = generate_faq(product_name, category, overrides)
    
    return {
        "faq_markdown": faq_content,
        "product_name": product_name,
        "category": category,
        "generated": True,
    }


# ============================================================
# 模块二：未命中 Query 聚类分析
# 用于分析知识检索失败的问题，发现知识缺口
# ============================================================

# 简单的语义相似度计算（基于 Jaccard 相似度）
def jaccard_similarity(text1: str, text2: str) -> float:
    """计算两个文本的 Jaccard 相似度"""
    set1 = set(text1)
    set2 = set(text2)
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union) if union else 0


def cluster_queries(queries: list, threshold: float = 0.35) -> list[dict]:
    """对未命中 Query 进行简单聚类
    
    Args:
        queries: 未命中的 query 列表，如 ["能穿着睡觉吗", "能当睡衣吗", "胖子能穿吗", ...]
        threshold: 相似度阈值，高于此值归为一类
    
    Returns:
        聚类结果列表
    """
    if not queries:
        return []
    
    clusters = []
    used = set()
    
    for i, q in enumerate(queries):
        if i in used:
            continue
        
        cluster = [q]
        used.add(i)
        
        for j, other_q in enumerate(queries):
            if j in used:
                continue
            sim = jaccard_similarity(q, other_q)
            if sim >= threshold:
                cluster.append(other_q)
                used.add(j)
        
        clusters.append({
            "representative": q,
            "count": len(cluster),
            "queries": cluster,
            "suggested_topic": _infer_topic(cluster),
        })
    
    # 按数量排序
    clusters.sort(key=lambda x: x["count"], reverse=True)
    return clusters


def _infer_topic(queries: list) -> str:
    """根据聚类中的 query 推断主题"""
    topics_keywords = {
        "穿着场景": ["穿", "睡", "运动", "健身", "跑步", "上班", "上学", "约会", "面试", "聚会"],
        "大码适配": ["胖", "大码", "加大", "加肥", "胖人", "壮", "微胖"],
        "送礼场景": ["送", "礼物", "生日", "男朋友", "女朋友", "父母", "朋友", "包装", "礼盒"],
        "搭配建议": ["搭", "配", "怎么穿", "裤子", "鞋子", "外套", "配什么"],
        "真假鉴别": ["真假", "正品", "假货", "防伪", "验货", "授权"],
        "质量疑虑": ["质量", "耐穿", "变形", "起球", "褪色", "缩水", "开线"],
        "价格对比": ["贵", "便宜", "降价", "优惠", "折扣", "活动"],
        "竞品对比": ["和", "比", "哪个好", "区别", "差别"],
    }
    
    best_topic = "其他"
    max_score = 0
    
    for topic, keywords in topics_keywords.items():
        score = 0
        for q in queries:
            for kw in keywords:
                if kw in q:
                    score += 1
        if score > max_score:
            max_score = score
            best_topic = topic
    
    return best_topic


# Dify Code 节点入口：未命中 Query 聚类
def main_cluster(unmatched_queries: str, threshold: float = 0.35) -> dict:
    """Dify Code 节点入口：对未命中 Query 进行聚类分析
    
    输入变量：
    - unmatched_queries: JSON 数组字符串，如 '["能穿着睡觉吗","能当睡衣吗","胖子能穿吗"]'
    - threshold: 相似度阈值
    """
    try:
        queries = json.loads(unmatched_queries) if isinstance(unmatched_queries, str) else unmatched_queries
    except json.JSONDecodeError:
        # 尝试按换行解析
        queries = [q.strip() for q in unmatched_queries.split("\n") if q.strip()]
    
    clusters = cluster_queries(queries, threshold)
    
    # 生成知识补充建议
    suggestions = []
    for c in clusters[:5]:  # Top 5 聚类
        if c["count"] >= 2:  # 至少出现2次才建议
            suggestions.append({
                "topic": c["suggested_topic"],
                "representative_query": c["representative"],
                "frequency": c["count"],
                "suggested_action": f"建议补充 [{c['suggested_topic']}] 相关知识，覆盖 query: {', '.join(c['queries'][:3])}",
            })
    
    return {
        "total_queries": len(queries),
        "cluster_count": len(clusters),
        "clusters_json": json.dumps(clusters, ensure_ascii=False),
        "suggestions": suggestions,
        "suggestions_json": json.dumps(suggestions, ensure_ascii=False),
    }


# ============================================================
# 测试代码（本地运行时使用）
# ============================================================
if __name__ == "__main__":
    # 测试 FAQ 生成
    print("=" * 60)
    print("商品 FAQ 生成测试")
    print("=" * 60)
    faq = generate_faq("夏季冰丝T恤", "T恤", {
        "材质成分": "冰丝面料（粘胶纤维+氨纶）",
        "材质特点": "冰丝面料，清凉透气，触感丝滑",
        "季节说明": "夏季专属，凉爽透气",
    })
    print(faq[:500])
    
    # 测试聚类
    print("\n" + "=" * 60)
    print("未命中 Query 聚类测试")
    print("=" * 60)
    test_queries = [
        "能穿着睡觉吗", "能当睡衣吗", "睡觉穿舒服吗",
        "胖子能穿吗", "大码的有吗", "200斤能穿吗",
        "送男朋友合适吗", "生日礼物送什么", "有礼品包装吗",
        "和优衣库的比哪个好", "跟HM有什么区别",
    ]
    result = cluster_queries(test_queries)
    for c in result:
        print(f"  [{c['suggested_topic']}] ({c['count']}条): {', '.join(c['queries'])}")
