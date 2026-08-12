"""应用配置 —— 常量、环境变量、运行时状态。"""

from __future__ import annotations

import os
from pathlib import Path

# ── 路径 ──
ROOT = Path(__file__).resolve().parents[1]
DOCX_PATH = ROOT / "数据结构期末考试题库.docx"
ASSIGNMENT_DOCX_PATH = ROOT / "期末考试作业题库.docx"
STATIC_DIR = ROOT / "static"
RUNTIME_DIR = ROOT / "runtime"
ASSET_DIR = RUNTIME_DIR / "assets"
DB_PATH = RUNTIME_DIR / "practice.sqlite3"

# ── 会话 ──
MAX_SESSION_AGE = 86400 * 7  # 7 天

# ── AI Provider 配置 ──
ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
AI_TIMEOUT_SECONDS = 120
AI_MAX_RETRIES = 2
AI_RATE_LIMIT_WINDOW = int(os.environ.get("SM_AI_RATE_LIMIT_WINDOW", "60"))
AI_RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("SM_AI_RATE_LIMIT_MAX", "20"))
AGENT_MAX_TOOL_ROUNDS = int(os.environ.get("SM_AGENT_MAX_TOOL_ROUNDS", "2"))
AGENT_MAX_OUTPUT_TOKENS = int(os.environ.get("SM_AGENT_MAX_OUTPUT_TOKENS", "1200"))
AGENT_TIMEOUT_SECONDS = float(os.environ.get("SM_AGENT_TIMEOUT_SECONDS", "45"))
AGENT_MAX_HISTORY_MESSAGES = int(os.environ.get("SM_AGENT_MAX_HISTORY_MESSAGES", "12"))
AGENT_SERVICE_KEY = os.environ.get("SM_AGENT_SERVICE_KEY", "")

AI_PROVIDERS: dict[str, dict] = {
    "zhipu": {
        "label": "智谱AI",
        "url": ZHIPU_URL,
        "models": ["glm-5.1", "glm-5", "glm-4.7-flash"],
        "default_model": "glm-5.1",
        "env": ["BIGMODEL_API_KEY", "ZHIPU_API_KEY", "ZHIPUAI_API_KEY"],
    },
    "deepseek": {
        "label": "DeepSeek",
        "url": DEEPSEEK_URL,
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "default_model": "deepseek-v4-flash",
        "env": ["DEEPSEEK_API_KEY"],
    },
}
ALLOWED_MODELS = {
    model for provider in AI_PROVIDERS.values() for model in provider["models"]
}
MODEL_ALIASES = {"gml-4.7-flash": "glm-4.7-flash"}

RUNTIME_CONFIG: dict = {
    "api_keys": {"zhipu": "", "deepseek": ""},
    "default_provider": "zhipu",
    "default_model": "glm-5.1",
}

# ── 管理员 ──
ADMIN_ACCOUNT = os.environ.get("SM_ADMIN_ACCOUNT", "tanshuhong")
ADMIN_PASSWORD = os.environ.get("SM_ADMIN_PASSWORD")

# ── 速率限制 ──
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 120
AUTH_RATE_LIMIT_MAX = 10

# ── 题库校验常量 ──
QUESTION_RE_STR = r"(\d+)\.\s*\[(单选题|多选题|填空题|判断题)\]"
DISCUSSION_RE_STR = r"第[一二三四五六七八九十0-9]+章讨论"
OPTION_RE_STR = r"^([A-H])\.\s*(.*)$"
IMAGE_RE_STR = r"\[IMAGE:([^\]]+)\]"

FILL_REPAIRS = [
    {"contains": "123按顺序进栈", "answer": "312"},
    {"contains": "按列存储时元素A36", "answer": "1192"},
    {"contains": "该树中叶子结点的个数", "answer": "8"},
    {"contains": "拥有100个结点的完全二叉树的最大层数", "answer": "7"},
    {"contains": "入度之和是所有顶点出度之和的____倍", "answer": "1"},
]

DS_CONCEPTS = {
    "linear_list": ["线性表", "顺序表", "链表"],
    "stack_queue": ["栈", "队列", "循环队列"],
    "string": ["串", "字符串", "模式匹配"],
    "tree_basic": ["树", "二叉树", "树的基本概念", "二叉树性质"],
    "tree_traversal": ["遍历", "先序", "中序", "后序", "层次遍历"],
    "tree_advanced": ["线索二叉树", "哈夫曼树", "二叉排序树", "平衡二叉树"],
    "graph_basic": ["图", "有向图", "无向图", "度", "路径"],
    "graph_traversal": ["图的遍历", "DFS", "BFS"],
    "graph_advanced": ["最小生成树", "最短路径", "拓扑排序", "关键路径"],
    "search": ["查找", "顺序查找", "折半查找", "分块查找"],
    "hash": ["哈希表", "散列表", "冲突", "哈希函数"],
    "sort_insert": ["插入排序", "直接插入", "希尔排序"],
    "sort_swap": ["交换排序", "冒泡排序", "快速排序"],
    "sort_select": ["选择排序", "简单选择", "堆排序"],
    "sort_merge": ["归并排序"],
    "complexity": ["时间复杂度", "空间复杂度", "O", "算法分析"],
}

AI_OPTION_SUPPLEMENTS: dict[int, dict] = {
    6: {
        "contains": ["执行下面的程序段的时间复杂度", "a[i][j]=i*j"],
        "note": "补全时间复杂度选项，标准答案仍为 C。",
        "options": {"A": "O(m)", "B": "O(n)", "C": "O(m*n)", "D": "O(m+n)"},
    },
    7: {
        "contains": ["执行下面程序段时", "语句S的执行次数"],
        "note": "补全语句频度选项，标准答案仍为 D。",
        "options": {"A": "n", "B": "n^2", "C": "n(n+1)", "D": "n(n+1)/2"},
    },
    14: {
        "contains": ["顺序表", "插入一个元素", "移动表中"],
        "note": "补全顺序表平均移动次数干扰项，标准答案仍为 C。",
        "options": {"A": "n", "B": "n+1", "C": "n/2", "D": "(n-1)/2"},
    },
    117: {
        "contains": ["n行n列的带状矩阵", "非零元素的个数"],
        "note": "补全三对角带状矩阵非零元素个数选项，标准答案仍为 B。",
        "options": {"A": "3n", "B": "3n-2", "C": "3n+2", "D": "n^2"},
    },
    118: {
        "contains": ["上三角矩阵", "按列优先", "非零元素aij"],
        "note": "补全上三角矩阵列优先压缩地址公式，标准答案仍为 D。",
        "options": {
            "A": "i(i-1)/2+j-1",
            "B": "j(j+1)/2+i-1",
            "C": "j(j-1)/2+i",
            "D": "j(j-1)/2+i-1",
        },
    },
    151: {
        "contains": ["高度为h的完全二叉树", "至少有"],
        "note": "补全完全二叉树最少结点数选项，标准答案仍为 C。",
        "options": {"A": "2^h-1", "B": "2^(h-1)-1", "C": "2^(h-1)", "D": "2^h"},
    },
    158: {
        "contains": ["高度为k的满二叉树", "结点总数"],
        "note": "补全满二叉树结点总数公式选项，标准答案仍为 C。",
        "options": {"A": "2^(k-1)", "B": "2^(k-1)-1", "C": "2^k-1", "D": "2k"},
    },
    209: {
        "contains": ["n个顶点的无向图", "邻接矩阵表示", "矩阵的大小"],
        "note": "补全邻接矩阵规模选项，标准答案仍为 C。",
        "options": {"A": "n", "B": "n(n-1)", "C": "n^2", "D": "n(n-1)/2"},
    },
}

ASSIGNMENT_AI_REFERENCES = [
    {
        "contains": ["七个带权结点", "3,5,7,2,6,12,15", "哈夫曼树"],
        "answer": "按哈夫曼算法依次合并最小权值：2+3=5，5+5=10，6+7=13，10+12=22，13+15=28，22+28=50。带权路径长度 WPL 等于各次合并权值之和：5+10+13+22+28+50=128。",
    },
    {
        "contains": ["10个结点的折半判定树", "查找成功的平均查找长度"],
        "answer": "10 个结点的折半判定树按折半查找划分，层数分布为第 1 层 1 个结点、第 2 层 2 个结点、第 3 层 4 个结点、第 4 层 3 个结点。等概率查找成功的平均查找长度 ASL=(1*1+2*2+3*4+4*3)/10=29/10。",
    },
    {
        "contains": ["Hash(key)=key%7", "线性探测", "查找成功和不成功"],
        "answer": "散列地址依次为：36->1，13->6，40->5，63->0，22->1，6->6。采用线性探测后，哈希表 A[0..9] 为：[63,36,22,空,空,40,13,6,空,空]。查找成功比较次数为 1,1,1,1,2,2，ASL成功=8/6=4/3。查找不成功按地址 0..6 计算，比较次数为 4,3,2,1,1,4,3，ASL不成功=18/7。",
    },
]
