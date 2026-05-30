# Miser v2.0 — 零 Token 本地 AI 协处理器

**把你的本地 GPU 变成 AI 助手的外挂。零 API token，零延迟，零配置。**

Miser 运行在 `localhost:7860`，自动检测你本地任何 LLM 后端：

- **Ollama** (推荐) — 自动发现，自动选模型
- **LM Studio** — 端口扫描，开箱即用
- **llama.cpp / vLLM / LocalAI** — OpenAI 兼容，即插即用

支持 **Claude Code、Codex CLI、Hermes Agent、Continue.dev、Cursor、Windsurf** 等任何支持 MCP 或 HTTP 的工具。

---

## 快速开始

```bash
git clone https://github.com/guyu-adam/miser.git
cd miser

# 方式 1：直接运行 (零安装)
python3 miser.py

# 方式 2：pip 安装 (全局可用)
pip install -e .
miser
```

Windows：双击 `miser.bat`  
macOS/Linux：`./miser.sh`

**自动检测后端 → 自动选择模型 → 直接可用。** 没有本地 LLM 也能用零 token 文件操作。

---

## API

### 零 Token 端点 (<50ms, 无需模型)

```bash
curl -X POST localhost:7860/read    -d '{"path":"~/project/app.py"}'
curl -X POST localhost:7860/grep    -d '{"path":"~/project/","pattern":"def "}'
curl -X POST localhost:7860/outline -d '{"path":"~/project/app.py"}'
curl -X POST localhost:7860/tree    -d '{"path":"~/project/","depth":2}'
curl -X POST localhost:7860/run     -d '{"cmd":"pytest --tb=short -q"}'
curl -X POST localhost:7860/write   -d '{"path":"~/out.txt","content":"hi"}'
curl -X POST localhost:7860/patch   -d '{"path":"~/f.py","old":"foo","new":"bar"}'
curl -X POST localhost:7860/exists  -d '{"path":"~/project/.env"}'
```

### 本地 LLM 端点 (零 API 费用)

```bash
curl -X POST localhost:7860/ask        -d '{"task":"What is 2+3?"}'
curl -X POST localhost:7860/explain    -d '{"path":"~/project/app.py"}'
curl -X POST localhost:7860/fix        -d '{"error":"TypeError: NoneType","code":"..."}'
curl -X POST localhost:7860/test       -d '{"path":"~/project/utils.py"}'
curl -X POST localhost:7860/review     -d '{"path":"~/project/app.py"}'
curl -X POST localhost:7860/codegen    -d '{"task":"RSI indicator","lang":"python"}'
curl -X POST localhost:7860/summarize  -d '{"path":"~/project/app.py"}'
curl -X POST localhost:7860/git_summary -d '{"path":"~/project/","n":10}'
curl -X POST localhost:7860/condense   -d '{"path":"~/project/app.py"}'
```

### Admin 端点

```bash
curl localhost:7860/health
curl localhost:7860/status
curl localhost:7860/metrics
```

---

## MCP 集成 (Claude Desktop / Hermes / Continue / Cursor)

```json
{
  "mcpServers": {
    "miser": {
      "command": "python3",
      "args": ["/path/to/miser/mcp_server.py"],
      "env": { "MISER_URL": "http://localhost:7860" }
    }
  }
}
```

MCP 提供 11 个工具：`miser_read`、`miser_grep`、`miser_run`、`miser_write`、`miser_patch`、`miser_tree`、`miser_ask`、`miser_codegen`、`miser_explain`、`miser_review`、`miser_summarize`

---

## OpenAI 兼容 API

Miser 暴露标准 `/v1/chat/completions` 和 `/v1/models`，可直接接入 Continue.dev、LangChain、CrewAI 等：

```python
import openai
client = openai.OpenAI(base_url="http://localhost:7860/v1", api_key="local")
client.chat.completions.create(
    model="auto",  # auto = 使用检测到的模型
    messages=[{"role": "user", "content": "Hello!"}],
)
```

---

## 配置

```bash
# 环境变量
MISER_MODEL=gemma4:latest  miser     # 指定模型
MISER_PORT=8080             miser     # 自定义端口

# CLI 参数
miser --port 8080 --model mistral:7b --auth-token my-secret --log-format json
```

---

## Python 客户端

```python
from client import W

W.outline("~/project/app.py")   # 函数/类结构
W.grep("~/project/", "def fn")  # 搜索
W.explain("~/project/utils.py") # 解释代码 (本地 LLM)
W.test("~/project/utils.py")    # 生成测试 (本地 LLM)
W.review("~/project/app.py")    # 代码审查 (本地 LLM)
```

---

## 平台

| 平台 | 启动方式 | 自动启动 |
|------|---------|---------|
| macOS | `./miser.sh` | `bash scripts/install.sh` → LaunchAgent |
| Linux | `./miser.sh` | `bash scripts/install.sh` → systemd user service |
| Windows | `miser.bat` (双击) | 手动 / Task Scheduler |

---

## License

MIT
