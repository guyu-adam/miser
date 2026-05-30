# Miser v1.5 — 零 Token 本地 AI 协处理器

**把本地磁盘和 GPU 变成 agent 的外挂。配一次，每次自动省钱。**

---

## 使用方式

```bash
git clone https://github.com/guyu-adam/miser.git
cd miser
pip install flask rich requests
```

然后在你 agent 的 MCP 配置里加一段 JSON。agent 调 Miser 工具时，服务自动后台拉起。

**没装 Ollama？零 token 的文件操作照样工作。**

---

## 各 Agent MCP 配置

### Claude Desktop
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)

### Hermes Agent
`~/.hermes/config.yaml`:
```yaml
mcp_servers:
  miser:
    command: python3
    args: ["/path/to/miser/mcp_server.py"]
```

### Continue / Cursor / Windsurf
MCP 设置中添加：
- Command: `python3`
- Args: `/path/to/miser/mcp_server.py`

**通用 JSON 模板：**
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

---

## Agent 使用策略（自动注入）

MCP 初始化时会告诉 agent：

| 你想做的事 | agent 直接用 | 用 Miser | 省多少 |
|---|---|---|---|
| 读文件内容 | Read | `miser_read` | 95% |
| 看文件结构 | Read 后自己分析 | `miser_outline` | 90%+ |
| 搜索代码 | grep / search | `miser_grep` | 100% |
| 目录结构 | ls / find | `miser_tree` | 100% |
| 检查文件存在 | test -f | `miser_exists` | 100% |
| 跑命令 | bash | `miser_run` | 100% |
| 理解一段代码 | 自己推理 | `miser_explain` | 本地 GPU，免费 |
| 代码审查 | 自己审查 | `miser_review` | 本地 GPU，免费 |
| 生成测试/样板 | 自己写 | `miser_codegen` | 本地 GPU，免费 |

---

## CLAUDE.md 模板（可选手动强化）

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

## 验证

装好 MCP 后，在 agent 里试一句就知道通没通：

> "帮我用 miser_read 读一下 ~/.hermes/config.yaml 的前 5 行"

返回文件内容 → MCP 通了。

---

## 自动检测的后端

| 后端 | 检测方式 |
|------|---------|
| Ollama | `localhost:11434` → `/api/tags` |
| LM Studio | 扫描 `localhost:1234` |
| llama.cpp | 扫描 `localhost:8080` |
| vLLM | 扫描 `localhost:8000` |

没后端？零 token 工具全部可用。有后端？LLM 工具自动全开。

---

## 工具列表

**零 Token（永远可用）：** `miser_read` `miser_outline` `miser_grep` `miser_tree` `miser_exists` `miser_run` `miser_write` `miser_patch`

**本地 LLM（有后端时可用）：** `miser_ask` `miser_explain` `miser_review` `miser_summarize` `miser_codegen`

---

## 高级

### 手动启动（不用 MCP）
```bash
python3 miser.py            # 自动检测
miser --port 8080           # 自定义端口
miser --model gemma4:latest # 指定模型
```

### OpenAI 兼容 API
```python
import openai
client = openai.OpenAI(base_url="http://localhost:7860/v1", api_key="local")
client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "Hello!"}])
```

---

## 要求

Python 3.10+。Ollama/LM Studio 可选（零 token 工具不需要）。

## License

MIT
