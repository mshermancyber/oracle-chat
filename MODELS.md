# Oracle Chat — Model Configuration Guide

Oracle connects to AI models via 4 authentication modes. This guide explains how to configure each one.

---

## Quick Setup

1. Open Settings: **Ctrl+,** or click **Settings** in the sidebar
2. Go to the **Auth** tab
3. Pick your mode and fill in the fields
4. Click **OK** — Oracle restarts with your new provider

---

## Mode 1: Anthropic API (Direct)

The recommended mode for Claude models. Uses the official Anthropic Python SDK.

**Setup:**
1. Get an API key from [console.anthropic.com](https://console.anthropic.com)
2. In Settings > Auth, select "Anthropic API key (direct)"
3. Paste your `sk-ant-...` key

**Available models** (in the model picker dropdown):

| Display Name | Model ID | Context | Best For |
|-------------|----------|---------|----------|
| Claude Opus 4.8 | `claude-opus-4-8` | 200k | Complex reasoning, coding |
| Claude Opus 4.7 | `claude-opus-4-7` | 200k | Complex reasoning, coding |
| Claude Opus 4.6 | `claude-opus-4-6` | 200k | Complex reasoning, coding |
| Claude Opus 4.5 | `claude-opus-4-5` | 200k | Complex reasoning, coding |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | 200k | Balanced speed + quality |
| Claude Sonnet 4.5 | `claude-sonnet-4-5` | 200k | Balanced speed + quality |
| Claude Haiku 4.5 | `claude-haiku-4-5` | 200k | Fast, cheap, simple tasks |

**Switch models on the fly:** use the dropdown in the top bar, or type `/model sonnet` (fuzzy match).

**Thinking effort:** `/thinking low|high|max` enables extended thinking (Anthropic API only).

---

## Mode 2: Claude Code Relay (Experimental)

Pipes through your local `claude` CLI binary. Uses your Claude Code subscription — no separate API key.

**Setup:**
1. Install [Claude Code](https://docs.claude.com/en/docs/claude-code/overview)
2. Run `claude /login` to authenticate
3. In Settings > Auth, select "Relay through Claude Code"
4. Leave binary path as `claude` (or set a custom path)

**Caveats:**
- Subscription ToS may not cover third-party UI relay
- ~100-500ms cold start per turn (subprocess)
- CLI schema can break on Claude Code updates

---

## Mode 3: Bridge Gateway

Points Oracle at a local `bridge_to_claude` instance (OpenAI-compatible HTTP gateway).

**Setup:**
1. Start `bridge_to_claude` on your machine or LAN
2. In Settings > Auth, select "Bridge"
3. Enter the bridge IP (default: `127.0.0.1`, port 7331 is fixed)

---

## Mode 4: Custom OpenAI Gateway

Connect to **any** OpenAI-compatible API. Works with Ollama, ChatGPT, Gemini, Grok, DeepSeek, Groq, Together, OpenRouter, LM Studio, and more.

**Setup:**
1. In Settings > Auth, select "Custom Gateway"
2. Pick a provider from the dropdown — URL and model auto-fill
3. Enter your API key (leave blank for local providers like Ollama)
4. Adjust the model name if needed
5. Click OK — Oracle restarts with the new provider

### Provider Presets

| Provider | Default URL | Default Model | API Key Required? |
|----------|------------|---------------|-------------------|
| **Custom (localhost)** | `http://localhost:11434` | `deepseek-r1` | No |
| **Ollama** | `http://localhost:11434` | `llama3.1` | No |
| **OpenAI / ChatGPT** | `https://api.openai.com` | `gpt-4o` | Yes — from [platform.openai.com](https://platform.openai.com) |
| **Anthropic** | `https://api.anthropic.com` | `claude-sonnet-4-6` | Yes — from [console.anthropic.com](https://console.anthropic.com) |
| **Google Gemini** | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.5-flash` | Yes — from [aistudio.google.com](https://aistudio.google.com) |
| **Grok (xAI)** | `https://api.x.ai` | `grok-3` | Yes — from [console.x.ai](https://console.x.ai) |
| **DeepSeek** | `https://api.deepseek.com` | `deepseek-chat` | Yes — from [platform.deepseek.com](https://platform.deepseek.com) |
| **Together AI** | `https://api.together.xyz` | `meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo` | Yes — from [together.ai](https://together.ai) |
| **Groq** | `https://api.groq.com/openai` | `llama-3.3-70b-versatile` | Yes — from [console.groq.com](https://console.groq.com) |
| **OpenRouter** | `https://openrouter.ai/api` | `anthropic/claude-sonnet-4` | Yes — from [openrouter.ai](https://openrouter.ai) |
| **LM Studio** | `http://localhost:1234` | `local-model` | No |

### Ollama Example

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3.1

# Start serving (default port 11434)
ollama serve
```

In Oracle: Settings > Auth > Custom Gateway > pick "Ollama" > OK. The model `llama3.1` appears in the dropdown.

### ChatGPT Example

1. Get an API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Settings > Auth > Custom Gateway > pick "OpenAI / ChatGPT"
3. Paste your key in the API key field
4. Change model to `gpt-4o`, `gpt-4o-mini`, `o3`, etc.
5. Click OK

### Gemini Example

1. Get an API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Settings > Auth > Custom Gateway > pick "Google Gemini"
3. Paste your key
4. Model: `gemini-2.5-flash`, `gemini-2.5-pro`, etc.
5. Click OK

---

## Switching Models During a Chat

**Model picker dropdown:** top-right of the chat pane. Changes apply to the next message.

**Slash command:** `/model <name>` — fuzzy matches against model names and IDs.

```
/model opus        → switches to Claude Opus
/model sonnet      → switches to Claude Sonnet
/model haiku       → switches to Claude Haiku
/model gpt-4o      → switches to GPT-4o (custom gateway)
```

**Quick switch:** press **Ctrl+M** for a floating model palette.

**Favorite models:** `/favorite opus` pins it to the top of the dropdown with a star.

**Auto-model:** `/automodel` toggles automatic switching — short simple messages go to a fast model, complex/code messages go to a powerful one.

**Compare:** `/compare <model>` sends the same message to a second model so you can compare responses.

---

## Model-Specific Features

| Feature | Anthropic API | Custom Gateway |
|---------|:------------:|:--------------:|
| Streaming | Yes | Yes (SSE) |
| File uploads | Yes (native) | No (text fallback) |
| Extended thinking | Yes (`/thinking`) | Depends on provider |
| Thinking display | Yes | If provider returns thinking blocks |
| Stop reason | Yes | Yes |

---

## Custom Model Names

When using Custom Gateway, you can type any model name the provider supports. The model field is freeform — Oracle passes it directly to the API. Check your provider's documentation for available model IDs.

Common examples:
- **Ollama:** `llama3.1`, `codellama`, `mistral`, `deepseek-r1`, `qwen2.5`
- **OpenAI:** `gpt-4o`, `gpt-4o-mini`, `o3`, `o3-mini`
- **Gemini:** `gemini-2.5-flash`, `gemini-2.5-pro`
- **Grok:** `grok-3`, `grok-3-mini`
- **DeepSeek:** `deepseek-chat`, `deepseek-reasoner`

---

## Cost Estimation

Use `/cost` to see estimated API costs for the current chat. Pricing is based on approximate per-token rates:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Claude Opus | $15.00 | $75.00 |
| Claude Sonnet | $3.00 | $15.00 |
| Claude Haiku | $0.80 | $4.00 |

Custom gateway costs vary by provider — `/cost` uses Claude Sonnet pricing as a default estimate.
