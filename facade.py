"""
facade.py — OpenAI-compatible API facade for Miser v1.4.1 (Agent adaptation #6).

Exposes a /v1/chat/completions endpoint that translates OpenAI-format
requests into local Ollama calls. This single endpoint unlocks:
  - Continue.dev
  - LangChain (ChatOpenAI)
  - CrewAI
  - AutoGPT
  - Any tool that speaks OpenAI API format
"""

import json, re, time
from flask import Blueprint, request, jsonify, Response, stream_with_context

from model_adapter import ModelAdapter
from breaker import ollama_breaker, BreakerOpenError

import requests as req

facade = Blueprint("facade", __name__)

MODEL = None
ADAPTER = None


def set_facade_model(model_name: str, adapter: ModelAdapter):
    global MODEL, ADAPTER
    MODEL = model_name
    ADAPTER = adapter


@facade.route("/chat/completions", methods=["POST"])
def chat_completions():
    """OpenAI-compatible /v1/chat/completions endpoint."""
    d = request.json or {}
    messages = d.get("messages", [])

    if not messages:
        return jsonify({"error": {"message": "messages required", "type": "invalid_request_error"}}), 400

    # Extract system + user messages
    system = ""
    user_msgs = []
    for m in messages:
        if m.get("role") == "system":
            system = m.get("content", "")
        elif m.get("role") == "user":
            user_msgs.append(m.get("content", ""))

    user = "\n".join(user_msgs) if user_msgs else ""
    if not user:
        return jsonify({"error": {"message": "No user message found", "type": "invalid_request_error"}}), 400

    stream = d.get("stream", False)
    max_tokens = d.get("max_tokens", 600)

    if stream:
        return _stream_response(system, user, max_tokens, d.get("model", MODEL))

    # Non-streaming: call Ollama and translate response
    try:
        payload = ADAPTER.generate_payload(system, user, max_tokens=max_tokens)
        resp = req.post(ADAPTER.url, json=payload, timeout=120)
        raw = ADAPTER.extract_text(resp.json())
        answer = ADAPTER.clean(raw, mode="text")

        return jsonify({
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": d.get("model", MODEL),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": len(system + user) // 4,
                "completion_tokens": len(answer) // 4,
                "total_tokens": (len(system + user) + len(answer)) // 4,
            },
        })
    except Exception as e:
        return jsonify({"error": {"message": str(e), "type": "api_error"}}), 500


def _stream_response(system: str, user: str, max_tokens: int, model_name: str):
    """SSE streaming response."""
    def generate():
        try:
            payload = ADAPTER.generate_payload(system, user, max_tokens=max_tokens)
            payload["stream"] = True
            resp = req.post(ADAPTER.url, json=payload, stream=True, timeout=120)
            idx = 0
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode())
                        text = chunk.get("response", "") or chunk.get("message", {}).get("content", "")
                        if text:
                            idx += 1
                            yield f"data: {json.dumps({'id': f'chatcmpl-{int(time.time())}', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model_name, 'choices': [{'index': 0, 'delta': {'content': text}, 'finish_reason': None}]})}\n\n"
                    except Exception:
                        continue
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@facade.route("/models", methods=["GET"])
def list_models():
    """OpenAI-compatible /v1/models endpoint."""
    return jsonify({
        "object": "list",
        "data": [{
            "id": MODEL,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "miser",
        }],
    })
