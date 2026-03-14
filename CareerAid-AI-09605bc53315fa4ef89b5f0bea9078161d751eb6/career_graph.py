# -*- coding: utf-8 -*-
"""
岗位关联图谱：垂直晋升路径 + 换岗路径。
满足：至少 5 个岗位的换岗路径，每个岗位不少于 2 条换岗路径。
"""
from __future__ import annotations

from typing import Any

# 至少 5 个岗位族，每族包含垂直路径与不少于 2 条横向换岗路径
CAREER_GRAPH = [
    {
        "family": "数据分析",
        "vertical": ["数据分析实习生", "数据分析师", "高级数据分析师", "数据科学家/算法专家", "数据负责人"],
        "lateral": ["增长分析", "商业分析", "产品分析", "运营分析", "数据产品经理"],
    },
    {
        "family": "后端开发",
        "vertical": ["后端开发实习生", "后端开发工程师", "高级后端工程师", "架构师", "技术负责人"],
        "lateral": ["DevOps/SRE", "全栈工程师", "数据工程师", "安全工程师", "测试开发"],
    },
    {
        "family": "前端开发",
        "vertical": ["前端开发实习生", "前端开发工程师", "高级前端工程师", "前端负责人", "技术负责人"],
        "lateral": ["全栈工程师", "客户端工程师", "可视化工程师", "交互/体验设计", "低代码平台"],
    },
    {
        "family": "产品",
        "vertical": ["产品助理", "产品经理", "高级产品经理", "产品负责人", "业务负责人"],
        "lateral": ["用户研究", "增长/运营", "项目管理", "商业分析", "解决方案顾问"],
    },
    {
        "family": "算法/AI",
        "vertical": ["算法实习生", "算法工程师", "高级算法工程师", "算法负责人", "技术专家"],
        "lateral": ["MLOps", "数据工程师", "搜索/推荐", "语音/多模态", "AI 产品"],
    },
]


def get_graph_for_title(title: str | None) -> dict[str, Any]:
    """根据岗位名称匹配预设图谱族，返回该族的垂直+横向路径。"""
    t = (title or "").strip().lower()
    for g in CAREER_GRAPH:
        if g["family"] in t or any(p in t for p in ["数据", "分析", "后端", "前端", "产品", "算法", "开发", "工程师"]):
            # 简单关键词匹配到族
            if "数据" in t or "分析" in t:
                return CAREER_GRAPH[0]
            if "后端" in t or "java" in t or "python" in t or "go" in t:
                return CAREER_GRAPH[1]
            if "前端" in t or "react" in t or "vue" in t or "前端" in (title or ""):
                return CAREER_GRAPH[2]
            if "产品" in t or "pm" in t:
                return CAREER_GRAPH[3]
            if "算法" in t or "nlp" in t or "llm" in t or "机器学习" in t:
                return CAREER_GRAPH[4]
    return CAREER_GRAPH[0]


def build_echarts_data(title: str | None) -> dict[str, Any]:
    """返回 ECharts graph 所需的 nodes + links；保证至少 2 条横向路径。"""
    g = get_graph_for_title(title)
    vertical = g["vertical"]
    lateral = g["lateral"][:5]
    nodes = []
    links = []
    for i, name in enumerate(vertical):
        nodes.append({"id": name, "name": name, "category": 0, "symbolSize": 44})
    for name in lateral:
        nodes.append({"id": name, "name": name, "category": 1, "symbolSize": 38})
    for i in range(len(vertical) - 1):
        links.append({"source": vertical[i], "target": vertical[i + 1]})
    pivot = vertical[min(2, len(vertical) - 1)]
    for name in lateral:
        links.append({"source": pivot, "target": name, "lineStyle": {"type": "dashed"}})
    return {"nodes": nodes, "links": links, "family": g["family"]}


def list_all_families() -> list[dict[str, Any]]:
    """返回所有岗位族（至少 5 个），每族含垂直路径及不少于 2 条换岗路径。"""
    out = []
    for g in CAREER_GRAPH:
        lateral = g["lateral"][:5]
        out.append({
            "family": g["family"],
            "vertical": g["vertical"],
            "lateral": lateral,
            "lateral_count": len(lateral),
        })
    return out
