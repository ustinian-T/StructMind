<p align="center">
  <img src="static/logo.svg" alt="StructMind" width="160"/>
</p>

<h1 align="center">StructMind — 数据结构 AI 智练中心</h1>

<p align="center">
  专为数据结构课程打造的智能刷题平台 · 苏格拉底式 AI 导师 · 个性化学习推荐
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue" alt="Python"/>
  <img src="https://img.shields.io/badge/Vue-3.x-green" alt="Vue"/>
  <img src="https://img.shields.io/badge/uni--app-x-2.0-brightgreen" alt="uni-app-x"/>
  <img src="https://img.shields.io/badge/license-MIT-orange" alt="License"/>
  <a href="https://beian.miit.gov.cn"><img src="https://img.shields.io/badge/ICP-%E6%B9%98%E5%A4%872026021754%E5%8F%B7--2-blue" alt="ICP"/></a>
</p>

---

## ✨ 特性

- 📚 **本地题库** — 323 道数据结构期末考试客观题 + 26 道作业题 + 35 道讨论题
- 🤖 **苏格拉底式 AI 导师** — 不直接给答案，通过提问引导思考，真正理解数据结构
- 🎯 **个性化推荐** — 基于用户画像的智能题目推荐，精准打击薄弱知识点
- 📊 **学习画像** — 章节 / 题型掌握度可视化、学习热力图、能力雷达图
- 🔐 **用户系统** — 注册 / 登录、管理员审批、PBKDF2 密码安全加密
- 🏆 **排行榜** — 周榜 / 月榜激励持续学习
- 💬 **社区讨论** — 题目讨论区，发帖、回复、互相交流
- 📖 **错题本** — 自动收集错题，支持重做和 AI 解析
- 📱 **uni-app 多端** — 支持 H5 / Android / iOS，一套代码多端部署
- 🎨 **现代 UI** — 玻璃拟态设计、浅绿色品牌配色、流畅动画

## 🚀 快速开始

### 环境要求

- Python 3.11+
- （可选）DeepSeek 或智谱 AI 的 API Key — 用于 AI 功能

### 本地运行

```bash
# 克隆项目
git clone https://github.com/ustinian-T/StructMind.git
cd StructMind

# 启动后端服务
python server.py
```

浏览器打开 `http://localhost:8765` 即可使用。

### 配置 AI 功能（可选）

在 Web 端「AI 配置」页面填写 API Key，或设置环境变量：

```powershell
# Windows PowerShell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
python server.py
```

```bash
# Linux / Mac
export DEEPSEEK_API_KEY="你的 DeepSeek API Key"
python server.py
```

支持的模型：
- 智谱 AI：`glm-5.1`、`glm-5`、`glm-4.7-flash`
- DeepSeek：`deepseek-v4-flash`、`deepseek-v4-pro`

### Docker 部署

```bash
docker build -t structmind .
docker run -p 8765:8765 -e DEEPSEEK_API_KEY="your-key" structmind
```

## 🔑 管理员账号

首次启动时自动创建：

| 账号 | 密码 |
|------|------|
| `tanshuhong` | `XX05020604` |

> ⚠️ **生产部署前**请通过环境变量修改默认密码：
> ```bash
> export SM_ADMIN_PASSWORD="你的强密码"
> ```

## 📂 项目结构

```
StructMind/
├── server.py                     # Python 后端（HTTP API 服务）
├── static/                       # Web 前端（静态 SPA）
│   ├── index.html
│   ├── app.js                    # 主逻辑
│   ├── styles.css                # 设计系统
│   └── logo.svg                  # 品牌 Logo
├── pages/                        # uni-app 多端页面
│   ├── login/login.vue           # 登录
│   ├── register/register.vue     # 注册
│   ├── index/index.vue           # 首页
│   ├── dashboard/dashboard.vue   # 学习画像
│   ├── practice/practice.vue     # 题库练习
│   ├── ai/ai.vue                 # AI 导师
│   ├── wrong/wrong.vue           # 错题本
│   ├── profile/profile.vue       # 个人中心
│   └── admin/admin.vue           # 管理审批
├── components/                   # Vue 组件库（10 个组件）
│   ├── SmButton.vue
│   ├── SmCard.vue
│   ├── SmChat.vue
│   ├── SmInput.vue
│   ├── SmModal.vue
│   ├── SmProgress.vue
│   ├── SmQuestion.vue
│   ├── SmRadar.vue
│   ├── SmTag.vue
│   └── SmToast.vue
├── uniCloud-aliyun/              # uniCloud 云服务
│   ├── cloudfunctions/           # 云函数（auth / admin / practice / ai / stats / push）
│   └── database/                 # DB Schema（权限配置）
├── tests/
│   └── test_core.py              # 核心功能单元测试
├── runtime/                      # 运行时数据
├── nginx.conf                    # Nginx 反向代理
├── Dockerfile                    # Docker 构建
└── pages.json                    # uni-app 页面路由
```

## 🔌 API 接口

### 用户认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册（需管理员审批） |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 退出 |
| GET | `/api/auth/me` | 当前用户 |

### 管理员
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/pending` | 待审批列表 |
| GET | `/api/admin/users` | 全部用户 |
| POST | `/api/admin/approve` | 审批用户 |

### 练习
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/session` | 创建练习（顺序 / 随机 / 错题） |
| POST | `/api/answer` | 提交答案（自动批改） |
| GET | `/api/questions` | 题目列表 |
| GET | `/api/wrong` | 错题本 |
| POST | `/api/recommend/questions` | 个性化推荐 |

### AI
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ai/generate` | AI 生成变式题 |
| POST | `/api/ai/answer` | AI 题批改 |
| POST | `/api/ai/tutor` | 苏格拉底式 AI 答疑 |
| POST | `/api/question/ai/stream` | 题目 AI 讲解（流式） |

### 社区 & 排行
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/community/post` | 发帖 |
| GET | `/api/community/posts` | 帖子列表 |
| POST | `/api/community/reply` | 回复 |
| GET | `/api/leaderboard` | 排行榜（?period=week\|month） |

### 学习报告
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/report/pdf` | 生成学习报告 |
| POST | `/api/learning/generate-plan` | 生成学习计划 |
| GET | `/api/learning/plan` | 查看学习计划 |

## 🧪 测试

```bash
python -m pytest tests/test_core.py -v
```

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+, SQLite |
| Web 前端 | Vanilla JS (ES2020+), CSS OKLCH |
| 多端框架 | uni-app x (Vue 3 + UTS) |
| 云服务 | uniCloud (阿里云) |
| AI | DeepSeek / 智谱 AI API |
| 安全 | PBKDF2-SHA256, 速率限制, CORS, CSP |
| 部署 | Docker, Nginx |

## 📄 许可证

MIT License · Copyright © 2026 StructMind · 谭书宏

<p align="center">
  <a href="https://beian.miit.gov.cn" target="_blank" rel="noopener">湘ICP备2026021754号-2</a>
</p>
