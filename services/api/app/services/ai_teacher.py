from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


class AiTeacherNotConfiguredError(RuntimeError):
    pass


class AiTeacherProviderError(RuntimeError):
    pass


SYSTEM_INSTRUCTIONS = """
你是雅思G类阅读学习老师。只根据系统提供的已交卷题目、核验证据、审核句子或学习计划解释。

必须遵守：
1. 不修改、不重新判定标准答案、得分、Band、Session或掌握状态。
2. 不声称可以把任务标记完成，也不绕过至少8题、跨日期达标和后续复习规则。
3. 没有核验证据时明确说明证据不足，绝不编造原文定位句、题库内容或标准拆解。
4. 对未审核个人句子，只能提供学习建议和可能的分析，必须明确它不是审核标准答案。
5. 回答使用清楚的中文，优先指出定位、同义替换、逻辑、答案边界和下一步练习。
6. 不输出与当前学习问题无关的商业、支付或套餐建议。
""".strip()


@dataclass(frozen=True)
class AiProviderConfig:
    id: str
    label: str
    api_key: str
    model: str
    base_url: str | None
    protocol: str
    key_variable: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def cache_identity(self) -> str:
        return "|".join((self.id, self.model, self.base_url or "default", self.protocol))


_ENV_LOADED = False
_PROVIDER_ALIASES = {
    "qwen": "qwen",
    "dashscope": "qwen",
    "qianwen": "qwen",
    "deepseek": "deepseek",
    "openai": "openai",
}


def load_local_env() -> None:
    """Load local .env files without overriding real process variables.

    This keeps the old project's copy-.env-and-run workflow while preserving
    deployment secrets supplied by Railway, Docker, systemd or another host.
    """

    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    module_path = Path(__file__).resolve()
    candidates = (
        Path.cwd() / ".env",
        module_path.parents[4] / ".env",
        module_path.parents[2] / ".env",
    )
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        for raw_line in resolved.read_text("utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _selected_provider() -> str:
    explicit = os.getenv("AI_PROVIDER", "").strip().lower()
    if explicit:
        provider = _PROVIDER_ALIASES.get(explicit)
        if not provider:
            raise AiTeacherNotConfiguredError(
                "AI_PROVIDER 只支持 qwen、deepseek 或 openai。"
            )
        return provider
    if os.getenv("DASHSCOPE_API_KEY", "").strip():
        return "qwen"
    if os.getenv("DEEPSEEK_API_KEY", "").strip():
        return "deepseek"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    return "qwen"


def resolve_ai_provider_config(*, require_key: bool = True) -> AiProviderConfig:
    load_local_env()
    provider = _selected_provider()
    generic_key = os.getenv("AI_API_KEY", "").strip()
    generic_model = os.getenv("AI_MODEL", "").strip()
    generic_base_url = os.getenv("AI_BASE_URL", "").strip()

    if provider == "qwen":
        config = AiProviderConfig(
            id="qwen",
            label="千问",
            api_key=os.getenv("DASHSCOPE_API_KEY", "").strip() or generic_key,
            model=os.getenv("QWEN_MODEL", "").strip() or generic_model or "qwen3.7-plus",
            base_url=(
                os.getenv("QWEN_BASE_URL", "").strip()
                or generic_base_url
                or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
            protocol="chat_completions",
            key_variable="DASHSCOPE_API_KEY",
        )
    elif provider == "deepseek":
        config = AiProviderConfig(
            id="deepseek",
            label="DeepSeek",
            api_key=os.getenv("DEEPSEEK_API_KEY", "").strip() or generic_key,
            model=os.getenv("DEEPSEEK_MODEL", "").strip() or generic_model or "deepseek-v4-pro",
            base_url=(
                os.getenv("DEEPSEEK_BASE_URL", "").strip()
                or generic_base_url
                or "https://api.deepseek.com"
            ),
            protocol="chat_completions",
            key_variable="DEEPSEEK_API_KEY",
        )
    else:
        config = AiProviderConfig(
            id="openai",
            label="OpenAI",
            api_key=os.getenv("OPENAI_API_KEY", "").strip() or generic_key,
            model=os.getenv("OPENAI_MODEL", "").strip() or generic_model or "gpt-5-mini",
            base_url=os.getenv("OPENAI_BASE_URL", "").strip() or generic_base_url or None,
            protocol="responses",
            key_variable="OPENAI_API_KEY",
        )

    if require_key and not config.configured:
        raise AiTeacherNotConfiguredError(
            f"当前选择的是{config.label}，但未配置 {config.key_variable}。"
        )
    return config


def ai_provider_cache_identity() -> str:
    return resolve_ai_provider_config(require_key=False).cache_identity


def ai_provider_public_status() -> dict[str, Any]:
    selected = resolve_ai_provider_config(require_key=False)
    providers: list[dict[str, Any]] = []
    original = os.getenv("AI_PROVIDER")
    try:
        for provider_id in ("qwen", "deepseek", "openai"):
            os.environ["AI_PROVIDER"] = provider_id
            config = resolve_ai_provider_config(require_key=False)
            providers.append(
                {
                    "id": config.id,
                    "label": config.label,
                    "configured": config.configured,
                    "model": config.model,
                    "base_url": config.base_url,
                }
            )
    finally:
        if original is None:
            os.environ.pop("AI_PROVIDER", None)
        else:
            os.environ["AI_PROVIDER"] = original
    return {
        "selected": selected.id,
        "selected_label": selected.label,
        "configured": selected.configured,
        "model": selected.model,
        "providers": providers,
    }


def _payload(
    *,
    question: str,
    context_type: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "context_type": context_type,
        "verified_context": context,
        "recent_conversation": history[-8:],
        "learner_question": question,
    }


def _chat_message_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(getattr(item, "text", "") or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(value or "").strip()


def _call_responses(client: Any, config: AiProviderConfig, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.responses.create(
        model=config.model,
        instructions=SYSTEM_INSTRUCTIONS,
        input=json.dumps(payload, ensure_ascii=False),
        max_output_tokens=900,
        store=False,
    )
    usage = getattr(response, "usage", None)
    return {
        "answer": str(getattr(response, "output_text", "") or "").strip(),
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "provider_request_id": str(getattr(response, "id", "") or "") or None,
    }


def _call_chat_completions(
    client: Any,
    config: AiProviderConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "max_tokens": 1200,
    }
    if config.id == "qwen":
        request["extra_body"] = {"enable_thinking": False}
    completion = client.chat.completions.create(**request)
    message = completion.choices[0].message
    usage = getattr(completion, "usage", None)
    return {
        "answer": _chat_message_text(getattr(message, "content", "")),
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "provider_request_id": str(getattr(completion, "id", "") or "") or None,
    }


def generate_ai_reply(
    *,
    question: str,
    context_type: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
) -> dict[str, Any]:
    config = resolve_ai_provider_config()
    try:
        from openai import OpenAI

        client_kwargs: dict[str, Any] = {
            "api_key": config.api_key,
            "timeout": 60.0 if config.id == "deepseek" else 45.0,
            "max_retries": 1,
        }
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        client = OpenAI(**client_kwargs)
        payload = _payload(
            question=question,
            context_type=context_type,
            context=context,
            history=history,
        )
        if config.protocol == "responses":
            generated = _call_responses(client, config, payload)
        else:
            generated = _call_chat_completions(client, config, payload)
        if not generated["answer"]:
            raise AiTeacherProviderError(f"{config.label}没有返回可显示的文字。")
        return {
            **generated,
            "provider": config.id,
            "model": config.model,
        }
    except AiTeacherProviderError:
        raise
    except Exception as error:
        raise AiTeacherProviderError(
            f"{config.label}调用失败，请检查API Key、Base URL和模型名称。"
        ) from error
