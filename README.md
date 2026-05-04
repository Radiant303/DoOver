# DoOver

<div align="center">

### 致那个回不去的夏天，和那个没说出口的“如果”

*An emotionally aware LLM project for replaying missed moments, unresolved choices, and alternate futures.*

<p align="center">
  <a href="https://github.com/Radiant303/DoOver"><img src="https://img.shields.io/badge/version-v0.0.1-blue" alt="version" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-green" alt="license" /></a>
  <a href="https://docs.astrbot.app/dev/star/plugin-new.html"><img src="https://img.shields.io/badge/docs-langgraph-orange" alt="docs" /></a>
</p>
<p align="center">
  <img src="https://count.getloli.com/@DoOver?name=DoOver&theme=miku&padding=7&offset=0&align=center&scale=0.3&pixelated=1&darkmode=auto" alt="visitor count" />
</p>

</div>
<img src="https://raw.githubusercontent.com/Radiant303/Radiant303/refs/heads/main/image/%E6%B3%A2%E5%A5%87%E9%85%B1_%E5%89%AF%E6%9C%AC_t.png" width = "318" height = "180" alt="NapCat" align=right />

---

### 🌧️ 你懂那种感觉吗？

那是 16 岁的午后，阳光透过树叶洒在课桌上，你偷偷看了一眼前排的背影，心跳快得像要跳出胸膛。  
那是 18 岁的路口，你们说好一起考去同一个城市，最后却在一个岔路口走散，谁也没敢回头。  
那是 20 岁的深夜，看着手机里那条发不出去的消息，你无数次问自己：  
**“如果当时我勇敢一点，如果当时我没有误会，现在我们会怎样？”**

青春里的感情，往往没有对错，只有来不及。  
那些未说出口的爱意，那些因为胆小而错过的拥抱，成了我们心里永远拔不掉的刺。

**DoOver，不想教你做大人，只想陪你找回那个少年的勇气。**

> “那年夏天，我以为来日方长，却忘了世事无常。  
> 如果当初我主动牵起她的手，结局会不会不一样？”

> “年少轻狂，为了所谓的‘义气’或‘爱情’，我们做过很多傻事。  
> 如果当时冷静一点，是不是就不会弄丢那段珍贵的友谊或恋情？”

> “我们总以为，只要回到过去，就能改写结局。  
> 但 DoOver 告诉你：无论选哪条路，都有风景，也有风雨。”

有人说，青春就是一场盛大的告别。  
我们告别了那个爱做梦的自己，告别了那个以为世界非黑即白的年纪。

但请相信，所有的遗憾，都是为了成全后来的圆满。

DoOver，愿做你青春回忆录里的最后一章。  
它不承诺改变过去，但它承诺给你一个清晰的答案。  
让你知道，那条没走的路，或许并不如想象中美好；  
让你知道，现在的你，比任何时候都更懂得如何去爱。


## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- npm 或 yarn

### 安装步骤

#### 1. 克隆项目

```bash
git clone https://github.com/Radiant303/DoOver.git
cd DoOver
```

#### 2. 安装后端依赖

```bash
pip install -r requirements.txt
```

#### 3. 安装前端依赖

```bash
cd dashboard
npm install
cd ..
```

#### 4. 配置 LLM 服务

复制配置文件并填写你的 API 密钥：

```bash
cp llm/config/provider.json.example llm/config/provider.json
cp tools/config/tools.example tools/config/tools.json
```

编辑 `llm/config/provider.json`：

```json
{
  "active_llm_provider": "your-provider",
  "active_llm_model": "your-model",
  "llm_providers": {
    "your-provider": {
      "type": "openai",
      "base_url": "https://api.example.com/v1",
      "api_key": "your-api-key",
      "models": ["your-model"]
    }
  }
}
```

支持的 LLM 类型：
- `openai` - OpenAI API 兼容接口
- `moonshot` - 月之暗面 (Kimi)
- `stepfun` - 阶跃函数

### 启动服务

#### 方式一：使用测试脚本（推荐）

```bash
python test.py
```

#### 方式二：手动启动

**启动后端：**
```bash
uvicorn test:app --host 0.0.0.0 --port 8000
```

**启动前端：**
```bash
cd dashboard
npm run dev
```

### 访问应用

打开浏览器访问：http://localhost:5173

---

## 📖 使用教程

### 基本流程

1. **输入你的故事** - 在对话框中输入你想要重新体验的回忆或遗憾

2. **分析背景** - 系统会分析你的故事，提取关键人物、时间和地点

3. **选择转折点** - 系统会生成 3-5 个关键转折点供你选择

4. **角色扮演互动** - 根据你的选择，与相关角色进行对话

5. **获得感悟** - 系统会给出故事的结局和人生感悟

### 示例场景

**场景：青春遗憾**

```
用户："那年夏天，我鼓起勇气想向她表白，但最终还是退缩了。"

系统：分析背景 → 生成转折点
  1. 在那个瞬间，你决定鼓起勇气表白
  2. 你决定等到毕业再说
  3. 你假装什么都没发生

用户选择："在那个瞬间，你决定鼓起勇气表白"

系统：创建角色"她"
她："谢谢你告诉我，其实我也一直喜欢你..."

用户："那我们现在还能在一起吗？"

她："时间会给我们答案，但至少现在，我们都没有遗憾了。"
```

### 功能特性

- ✅ **会话持久化** - 页面刷新后自动恢复之前的对话状态
- ✅ **多重转折点** - 每个故事都有多种可能的发展方向
- ✅ **角色扮演** - 与故事中的角色进行真实对话
- ✅ **情感分析** - 理解故事中的情感基调
- ✅ **重置会话** - 随时可以重新开始新的故事

---

## 📁 项目结构

```
DoOver/
├── dashboard/          # 前端 Vue 应用
│   ├── src/
│   │   ├── components/  # Vue 组件
│   │   ├── composables/ # 组合式函数
│   │   ├── views/       # 页面视图
│   │   └── router/      # 路由配置
│   └── package.json
├── graph/              # LangGraph 工作流
│   ├── graph.py        # 图定义
│   ├── nodes.py        # 节点逻辑
│   ├── state.py        # 状态管理
│   └── prompts.py      # 提示词模板
├── llm/                # LLM 客户端
│   ├── client.py       # LLM 客户端
│   ├── provider/       # LLM 提供商
│   └── config/         # LLM 配置
├── tools/              # 工具模块
│   ├── search.py       # 搜索工具
│   └── config/         # 工具配置
├── utils/              # 通用工具
│   ├── websocket.py    # WebSocket 服务
│   └── session.py      # 会话管理
├── test.py             # 主入口（FastAPI）
└── requirements.txt    # Python 依赖
```

---

## 🔧 配置说明

### LLM 配置 (`llm/config/provider.json`)

| 参数 | 说明 | 示例 |
|------|------|------|
| `active_llm_provider` | 当前激活的提供商 | `openai` |
| `active_llm_model` | 当前使用的模型 | `gpt-4o-mini` |
| `llm_providers.*.type` | 提供商类型 | `openai`, `moonshot`, `stepfun` |
| `llm_providers.*.base_url` | API 地址 | `https://api.example.com/v1` |
| `llm_providers.*.api_key` | API 密钥 | `sk-xxx` |
| `llm_providers.*.models` | 可用模型列表 | `["model-a", "model-b"]` |

### 搜索工具配置 (`tools/config/tools.json`)

| 参数 | 说明 |
|------|------|
| `search.active_search_provider` | 激活的搜索提供商 |
| `search.baidu.api_key` | 百度搜索 API 密钥 |
| `search.tavily.api_key` | Tavily 搜索 API 密钥 |

---

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

---

## 📝 常见问题

### Q: 页面刷新后会话丢失怎么办？

A: 不用担心！我们已经实现了会话持久化功能。页面刷新后，所有对话状态会自动从浏览器本地存储中恢复。

### Q: 如何重置会话？

A: 点击左侧面板的"🔄"重置按钮即可清空当前会话，开始新的故事。

### Q: 支持哪些 LLM 服务？

A: 当前支持 OpenAI 兼容接口、月之暗面 (Kimi)、阶跃函数等服务。

### Q: 如何配置多个 LLM 提供商？

A: 在 `llm/config/provider.json` 中添加多个提供商配置，然后通过前端设置页面切换。

---

## ⭐ Star History

> [!TIP]
> 如果本项目对您的生活 / 工作产生了帮助，或者您关注本项目的未来发展，请给项目 Star，这是我们维护这个开源项目的动力 <3

<div align="center">

<a href="https://www.star-history.com/?repos=Radiant303%2FDoOver&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=Radiant303/DoOver&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=Radiant303/DoOver&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=Radiant303/DoOver&type=date&legend=top-left" />
 </picture>
</a>
</div>
<div align="center">

别让你的青春，只留在回忆里。  
打开 DoOver，给那个夏天的自己，写一封迟到的信。
</div>
