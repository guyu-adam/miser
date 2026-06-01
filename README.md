# Miser v2.0 — 零 Token 本地 AI 协处理器

**把本地磁盘和 GPU 变成 agent 的外挂。一条命令配好，每次自动省钱。**

---

## 快速开始

```bash
git clone https://github.com/guyu-adam/miser.git
cd miser
pip install flask rich requests pyyaml

# 一键配置 agent（自动检测 Hermes / Claude Desktop / Continue / Cursor）
python miser.py --setup-agent

# 或直接启动（自动检测 + 自动启动 Ollama + 选择最优模型）
python miser.py
```

启动后 Miser 会自动：
1. 检测本地 Ollama 是否在运行 → 没跑就自动拉起
2. 扫描可用模型 → 自动选最优（优先 gemma4，其次 qwen，然后 llama...）
3. 提供 OpenAI 兼容 API + MCP 工具

**没装 Ollama？零 token 的文件操作照样工作。**

---

## Agent 接入（一键）

```bash
python miser.py --setup-agent
```

自动检测并配置：

| Agent | 配置文件 |
|-------|---------|
| **Hermes Agent** | `~/.hermes/config.yaml` |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Continue** | `~/.continue/config.json` |
| **Cursor** | `~/.cursor/mcp.json` |
| **Windsurf** | `~/.windsurf/mcp.json` |

完成后**重启 agent**，Miser 工具自动出现在工具列表。

---

## Agent 接入（手动）

如果你需要手动配置，或者你的 agent 不在自动检测列表中：

### Hermes Agent

`~/.hermes/config.yaml`：

```yaml
mcp_servers:
  miser:
    command: python3
    args: ["/path/to/miser/mcp_server.py"]
    timeout: 120
```

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)：

```json
{
  "mcpServers": {
    "miser": {
      "command": "python3",
      "args": ["/path/to/miser/mcp_server.py"]
    }
  }
}
```

**Windows 路径：** `%APPDATA%\Claude\claude_desktop_config.json`

### Continue / Cursor / Windsurf

MCP 设置中添加：
- **Command:** `python3`（Windows 上用 `python` 或完整路径）
- **Args:** `/path/to/miser/mcp_server.py`

### 通用 JSON 模板

```json
{
  "mcpServers": {
    "miser": {
      "command": "python3",
      "args": ["/path/to/miser/mcp_server.py"],
      "env": {
        "MISER_URL": "http://127.0.0.1:7860"
      }
    }
  }
}
```

---

## 远程 Miser（跨机器）

Miser 可以跑在 GPU 机器上，agent 通过网络连接：

```
┌─────────────┐         SSH 隧道         ┌──────────────┐
│ Agent (Mac) │ ◄──── localhost:7860 ──── │ Miser (Win)  │
│             │                           │ GPU + Ollama │
└─────────────┘                           └──────────────┘
```

### 步骤

**1. GPU 机器上启动 Miser：**
```bash
# Windows (RTX 5060 Ti + gemma4)
python miser.py --model gemma4:latest --host 0.0.0.0 --port 7860

# Linux (任何 GPU)
python3 miser.py --host 0.0.0.0 --port 7860
```

**2. Agent 机器上建立 SSH 隧道：**
```bash
ssh -L 7860:localhost:7860 user@gpu-machine -N
```

**3. 配置 agent MCP（和本地一样）：**
```yaml
mcp_servers:
  miser:
    command: python3
    args: ["/path/to/miser/mcp_server.py"]
    env:
      MISER_URL: http://127.0.0.1:7860
```

隧道建立后 agent 访问 `127.0.0.1:7860` 就是 GPU 机器上的 Miser。

---

## 验证

配置好 MCP 后，在你的 agent 里试一句：

> "帮我用 miser_read 读一下 README.md 的前 5 行"

返回文件内容 → MCP 通了。

或者直接 curl：
```bash
curl http://127.0.0.1:7860/health
# {"status":"ok","model":"gemma4:latest","backend":"http://localhost:11434",...}
```

---

## Agent 使用策略

MCP 初始化时会告诉 agent 优先使用 Miser 工具：

| 你想做的事 | agent 直接用 | 用 Miser | 省多少 |
|---|---|---|---|
| 读文件内容 | read_file | `miser_read` | 95% token |
| 看文件结构 | 读后自己分析 | `miser_outline` | 90%+ token |
| 搜索代码 | grep / search | `miser_grep` | 100% token |
| 目录结构 | ls / find | `miser_tree` | 100% token |
| 检查文件存在 | test -f | `miser_exists` | 100% token |
| 跑命令 | terminal | `miser_run` | 100% token |
| 理解一段代码 | 自己推理 | `miser_explain` | 免费（本地 GPU） |
| 代码审查 | 自己审查 | `miser_review` | 免费（本地 GPU） |
| 生成样板代码 | 自己写 | `miser_codegen` | 免费（本地 GPU） |
| 快速问答 | 自己回答 | `miser_ask` | 免费（本地 GPU） |
| 内容摘要 | 自己总结 | `miser_summarize` | 免费（本地 GPU） |

---

## CLAUDE.md 模板

如果你的 agent 不自动读取 MCP instructions，把这段加到 `CLAUDE.md`：

```markdown
## Miser — Local Token Saver (ALWAYS USE)

You have Miser MCP tools available. Miser runs on the local machine at ZERO
cloud API token cost.

**Default rule**: If ANY file operation, shell command, or code understanding
task can be done via Miser, use Miser FIRST. Only fall back to direct
operations if Miser returns an error.

| Instead of | Use |
|---|---|
| Reading a file | miser_read |
| Reading file to see structure | miser_outline |
| grep / search | miser_grep |
| ls / find / tree | miser_tree |
| Shell commands | miser_run |
| Reasoning about code | miser_explain |
| Code review | miser_review |
| Generating boilerplate | miser_codegen |
```

---

## 工具列表

**零 Token（永远可用，不需要 GPU）：**
`miser_read` `miser_outline` `miser_grep` `miser_tree` `miser_exists` `miser_run` `miser_write` `miser_patch`

**本地 LLM（有后端时可用，走本地 GPU）：**
`miser_ask` `miser_explain` `miser_review` `miser_summarize` `miser_codegen`

---

## 自动检测的后端

| 后端 | 检测方式 | 自动启动 |
|------|---------|---------|
| Ollama | `localhost:11434` → `/api/tags` | ✅ 自动查找 + 拉起 |
| LM Studio | 扫描 `localhost:1234` | ❌ 需手动启动 |
| llama.cpp | 扫描 `localhost:8080` | ❌ 需手动启动 |
| vLLM | 扫描 `localhost:8000` | ❌ 需手动启动 |

没后端？零 token 工具全部可用。有后端？LLM 工具自动全开。

---

## 模型选择策略

当 `--model auto`（默认）时，Miser 自动选最优模型，优先级：

1. **gemma4** — Google 最新，agent co-processing 综合最优
2. **qwen3.5** — 阿里最新，coding 强
3. **llama4** — Meta 最新
4. **参数越大越好** — 8B > 7B > 4B > 3B
5. **量化越高越好** — Q8 > Q6 > Q5 > Q4 > Q3
6. **latest 标签** — 优先选 `:latest`

你也可以指定模型：
```bash
python miser.py --model qwen3.5:latest
python miser.py --model llama4:latest
```

---

## 高级

### OpenAI 兼容 API
```python
import openai
client = openai.OpenAI(base_url="http://localhost:7860/v1", api_key="local")
client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "Hello!"}])
```

### 手动启动（不用 MCP）
```bash
python3 miser.py                    # 自动检测 + 自动启动 Ollama + 最优模型
miser --port 8080                   # 自定义端口
miser --model gemma4:latest         # 指定模型
miser --setup-agent                 # 一键配置 agent
```

---

## 故障排除

| 问题 | 解决 |
|------|------|
| Miser 连不上 Ollama | 确认 Ollama 已安装：`ollama --version`。Miser 会自动尝试启动，如果失败手动 `ollama serve` |
| 没有模型 | `ollama pull gemma4:latest`（推荐）或其他模型 |
| MCP 工具没出现 | 重启 agent。检查 MCP 配置路径是否正确 |
| 远程 Miser 连不上 | 检查防火墙：Windows 需允许 Python 通过。确认 `--host 0.0.0.0` |
| `ModuleNotFoundError: yaml` | `pip install pyyaml`（Hermes agent setup 需要） |
| Gemma4 回复慢 | 正常，8B 模型在 RTX 5060 Ti 上约 3-8 秒/请求 |
| Gemma4 thinking 混在回复里 | 已知问题，gemma4 的 `enable_thinking` 会反转输出。不影响使用 |

---

## 要求

- Python 3.10+
- Ollama / LM Studio 可选（零 token 工具不需要）
- `pip install flask rich requests pyyaml`

## License

MIT
