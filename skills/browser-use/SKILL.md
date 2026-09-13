---
name: browser-use
description: AI browser automation agent — navigate websites, fill forms, extract data, click elements, search the web, take screenshots, download files, and automate any browser task using natural language. Uses anthropic/claude-sonnet-4.6 via OpenRouter with Playwright Chromium. Use when asked to browse websites, scrape data, fill web forms, automate repetitive browser tasks, search and extract information from web pages, or interact with any web application programmatically.
---

# Browser-Use

AI-powered browser automation. The agent sees the page, decides what to do, and acts — all from a natural language task description.

**Versions:** `browser-use 0.12.9` · `langchain-openai 1.2.2` · `playwright 1.58.0`

## Architecture

```
Task (natural language) → LLM (anthropic/claude-sonnet-4.6 via OpenRouter) → Action Plan
→ Playwright Chromium (headless) → DOM snapshot → LLM evaluates
→ Next action → ... → Done
```

## Quick Usage

### Basic agent

```python
import asyncio, os
from langchain_openai import ChatOpenAI
from browser_use import Agent

llm = ChatOpenAI(
    model='anthropic/claude-sonnet-4.6',
    base_url='https://openrouter.ai/api/v1',
    api_key=os.getenv('OPENROUTER_API_KEY'),
)

async def main():
    agent = Agent(
        task='Go to hackernews and find the top 5 stories',
        llm=llm,
        use_vision=True,  # claude-sonnet-4.6 supports vision
    )
    result = await agent.run(max_steps=25)
    print(result.final_result())

asyncio.run(main())
```

### With explicit browser config (0.12.x flat kwargs)

```python
from browser_use import Agent, Browser

# Browser now takes flat kwargs directly — no BrowserConfig wrapper needed
browser = Browser(
    headless=True,
    disable_security=True,
    proxy='http://proxy:8080',
)

agent = Agent(
    task='Login to example.com with user x and pass y',
    llm=llm,
    browser=browser,
    use_vision=True,
)
result = await agent.run(max_steps=25)
```

## Model Configuration

The skill is pre-configured for **anthropic/claude-sonnet-4.6** via **OpenRouter**:

```python
from langchain_openai import ChatOpenAI
import os

llm = ChatOpenAI(
    model='anthropic/claude-sonnet-4.6',
    base_url='https://openrouter.ai/api/v1',
    api_key=os.getenv('OPENROUTER_API_KEY'),  # from scrt: openrouter-api-key
)
```

**Note**: `anthropic/claude-sonnet-4.6` supports vision. Set `use_vision=True` for screenshot-based browsing (recommended), or `use_vision=False` for text-only DOM mode (faster, cheaper).

### Switching models

```python
# GPT-4o via OpenRouter
llm = ChatOpenAI(model='openai/gpt-4o', base_url='https://openrouter.ai/api/v1', api_key=os.getenv('OPENROUTER_API_KEY'))
agent = Agent(task='...', llm=llm, use_vision=True)

# Anthropic native SDK
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model='claude-sonnet-4-5')
agent = Agent(task='...', llm=llm, use_vision=True)
```

## Agent Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | str | required | Natural language description of what to do |
| `llm` | BaseChatModel | None | LangChain-compatible LLM |
| `browser` | Browser | auto | Custom browser instance |
| `use_vision` | bool | True | Enable screenshot-based vision |
| `sensitive_data` | dict | None | Credentials the LLM references but never sees |
| `controller` | Controller | default | Custom action registry |
| `flash_mode` | bool | False | Fast mode — skips planning |
| `use_thinking` | bool | True | Enable extended thinking (0.12.x) |
| `enable_planning` | bool | True | Enable multi-step planning (0.12.x) |
| `use_judge` | bool | True | Enable judge LLM to verify task completion (0.12.x) |
| `max_actions_per_step` | int | 5 | Actions per LLM step (0.12.x) |
| `step_timeout` | int | 180 | Seconds per step before timeout (0.12.x) |
| `save_conversation_path` | str | None | Save full LLM conversation log to file |
| `initial_actions` | list | None | Actions to run before LLM takes over |
| `message_compaction` | bool | True | Compact old messages to save context (0.12.x) |

## Browser Options (0.12.x flat kwargs)

```python
from browser_use import Browser

browser = Browser(
    headless=True,                    # No visible window
    disable_security=True,            # Allow cross-origin iframes
    proxy='http://proxy:8080',        # HTTP/SOCKS proxy
    downloads_path='/tmp/downloads',  # Download destination
    args=[
        '--disable-blink-features=AutomationControlled',  # stealth
        '--window-size=1920,1080',
    ],
)
```

## Security: Sensitive Data

Never put passwords/API keys in the task text. Use `sensitive_data` instead:

```python
sensitive_data = {
    'https://example.com': {
        'username': 'actual_username',
        'password': 'actual_password',
    },
}

agent = Agent(
    task='Go to https://example.com and login with username and password',
    llm=llm,
    sensitive_data=sensitive_data,  # LLM sees placeholders, never real values
)
```

## Custom Actions

Register your own tools the agent can use:

```python
from browser_use import Controller

controller = Controller()

@controller.action('Save data to file')
def save_data(text: str, filename: str):
    with open(filename, 'w') as f:
        f.write(text)
    return f'Saved to {filename}'

agent = Agent(
    task='Search for competitor pricing and save to prices.csv',
    llm=llm,
    controller=controller,
)
```

## Parallel Agents

```python
agents = [
    Agent(task=f'Find the price of {item} on Amazon', llm=llm, browser=Browser())
    for item in ['laptop', 'phone', 'tablet']
]
results = await asyncio.gather(*[agent.run(max_steps=10) for agent in agents])
```

## Common Task Patterns

### Web scraping
```python
agent = Agent(
    task='Go to https://news.ycombinator.com and extract the title, score, and URL of the top 10 stories. Return as JSON.',
    llm=llm, use_vision=True,
)
```

### Form filling
```python
agent = Agent(
    task='Go to https://httpbin.org/forms/post and fill in the form with name "Test User", email "test@example.com"',
    llm=llm, use_vision=True,
)
```

### Login + action
```python
sensitive_data = {'https://app.example.com': {'user': 'my@email.com', 'pass': '****'}}
agent = Agent(
    task='Go to https://app.example.com, login with user and pass, then find total revenue for this month',
    llm=llm, sensitive_data=sensitive_data, use_vision=True,
)
```

### Research
```python
agent = Agent(
    task='Search for "best open source SIEM tools 2026" and compile a comparison table with name, license, stars, and key features',
    llm=llm, use_vision=True, max_steps=30,
)
```

## Retrieving Results

```python
result = await agent.run(max_steps=25)

# Final text output
print(result.final_result())

# All extracted content
for action_result in result.all_results:
    print(action_result.extracted_content)

# Cost (if calculate_cost=True)
# print(result.total_cost())
```

## Script Template

```python
#!/usr/bin/env python3
"""browser-use agent script — edit task and run"""
import asyncio, os
from langchain_openai import ChatOpenAI
from browser_use import Agent, Browser

TASK = """EDIT THIS: Describe what you want the browser agent to do."""

llm = ChatOpenAI(
    model='anthropic/claude-sonnet-4.6',
    base_url='https://openrouter.ai/api/v1',
    api_key=os.getenv('OPENROUTER_API_KEY'),
)

async def main():
    browser = Browser(headless=True)
    agent = Agent(task=TASK, llm=llm, browser=browser, use_vision=True)
    result = await agent.run(max_steps=25)
    print(result.final_result())

asyncio.run(main())
```

## Environment

- **Python**: >= 3.11
- **browser-use**: 0.12.9
- **langchain-openai**: 1.2.2
- **playwright**: 1.58.0
- **Chromium**: Auto-installed by `playwright install chromium`
- **API Key**: `OPENROUTER_API_KEY` env var (from scrt: `openrouter-api-key`)
- **Install**: `pip install browser-use langchain-openai && playwright install chromium`

## Migration Notes (0.3.x → 0.12.x)

| Old (0.3.x) | New (0.12.x) |
|---|---|
| `from browser_use import BrowserConfig` | Removed — use `Browser(headless=True, ...)` flat kwargs |
| `Browser(config=BrowserConfig(...))` | `Browser(headless=True, disable_security=True, ...)` |
| `agent.run_sync()` | `asyncio.run(agent.run())` |
| No planning | `enable_planning=True` (default) |
| No judge | `use_judge=True` (default) |
| No thinking | `use_thinking=True` (default) |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ImportError: BrowserConfig` | Removed in 0.12.x — use flat `Browser(headless=True)` kwargs |
| `AttributeError: run_sync` | Removed — use `asyncio.run(agent.run())` |
| Chromium not found | `playwright install chromium` |
| OpenRouter 429 errors | Reduce `max_steps` or add retry logic |
| Agent loops on same action | Increase `max_steps`, set `loop_detection_enabled=True` |
| Vision not working | Set `use_vision=True` explicitly |
| Cookie consent blocking | `initial_actions=[{"click_element_by_index": {"index": 0}}]` |
| Step timeout | Increase `step_timeout=300` (default 180s) |
