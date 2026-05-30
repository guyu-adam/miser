# Miser v2.0 — 零 Token 本地 AI 协处理器

**把你的本地 GPU 变成 AI 助手的外挂。零 API token，零延迟，零配置。**

配一次 MCP JSON，以后每次用 agent 自动就位。

---

## 使用方式（最终形态）

```bash
git clone https://github.com/guyu-adam/miser.git
cd miser
pip install flask rich requests
```

然后在你的 agent 的 MCP 配置里加一段 JSON：

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

**就这样。** agent 调 Miser 工具时，Miser 服务自动后台拉起。设备上没 Ollama？零 token 的文件操作照样能用。

---

## 自动检测的后端

| 后端 | 检测方式 | 零配置 |
|------|---------|--------|
| Ollama | `localhost:11434` → `/api/tags` | ✓ |
| LM Studio | 扫描 `localhost:1234` | ✓ |
| llama.cpp | 扫描 `localhost:8080` | ✓ |
| vLLM | 扫描 `localhost:8000` | ✓ |

---

## 工具列表

**零 Token（无需模型，永远可用）：**
`miser_read` / `miser_grep` / `miser_run` / `miser_write` / `miser_patch` / `miser_tree`

**本地 LLM（有后端时自动可用）：**
`miser_ask` / `miser_codegen` / `miser_explain` / `miser_review` / `miser_summarize`

---

## 各 Agent 配置

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) 或 `%APPDATA%\Claude\claude_desktop_config.json` (Windows)：

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

### Hermes Agent

`~/.hermes/config.yaml`:

```yaml
mcp_servers:
  miser:
    command: python3
    args: ["/path/to/miser/mcp_server.py"]
```

### Continue.dev

`~/.continue/config.json`:

```json
{
  "experimental": {
    "mcpServers": {
      "miser": {
        "command": "python3",
        "args": ["/path/to/miser/mcp_server.py"]
      }
    }
  }
}
```

### Cursor / Windsurf

在设置中搜索 "MCP"，添加 server：

- Name: `miser`
- Command: `python3 /path/to/miser/mcp_server.py`

---

## 高级用法

### 手动启动（不需要 MCP）

```bash
python3 miser.py            # 自动检测后端
miser --port 8080           # 自定义端口
miser --model gemma4:latest # 指定模型
```

### OpenAI 兼容 API

```python
import openai
client = openai.OpenAI(base_url="http://localhost:7860/v1", api_key="local")
client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

---

## 平台

| 平台 | MCP server | 开机自启 |
|------|-----------|---------|
| macOS | `python3 mcp_server.py` | `bash scripts/install.sh` → LaunchAgent |
| Linux | `python3 mcp_server.py` | `bash scripts/install.sh` → systemd |
| Windows | `python mcp_server.py` 或 `mcp_server.bat` | 手动 / Task Scheduler |

---

## 要求

- Python 3.10+
- （可选）Ollama / LM Studio — 零 token 工具不需要

## License

MIT
