from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.services import ai_teacher
from app.repositories.ai_teacher_repository import AiTeacherRepository
from app.repositories.session_repository import SQLiteSessionRepository


_ENV_NAMES = (
    "AI_PROVIDER",
    "AI_API_KEY",
    "AI_MODEL",
    "AI_BASE_URL",
    "DASHSCOPE_API_KEY",
    "QWEN_MODEL",
    "QWEN_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_BASE_URL",
)


def _clean_env(monkeypatch) -> None:
    monkeypatch.setattr(ai_teacher, "_ENV_LOADED", True)
    monkeypatch.setattr(ai_teacher, "_PROVIDER_OVERRIDE", None)
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_old_qwen_environment_is_supported(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "qwen-secret")
    monkeypatch.setenv("QWEN_MODEL", "qwen-test")
    monkeypatch.setenv("QWEN_BASE_URL", "https://qwen.example/v1")

    config = ai_teacher.resolve_ai_provider_config()

    assert config.id == "qwen"
    assert config.label == "千问"
    assert config.api_key == "qwen-secret"
    assert config.model == "qwen-test"
    assert config.base_url == "https://qwen.example/v1"
    assert config.protocol == "chat_completions"


def test_old_deepseek_environment_is_supported(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example")

    config = ai_teacher.resolve_ai_provider_config()

    assert config.id == "deepseek"
    assert config.label == "DeepSeek"
    assert config.api_key == "deepseek-secret"
    assert config.model == "deepseek-test"
    assert config.base_url == "https://deepseek.example"
    assert config.protocol == "chat_completions"


def test_selected_provider_never_silently_falls_back(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "qwen")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")

    with pytest.raises(ai_teacher.AiTeacherNotConfiguredError) as error:
        ai_teacher.resolve_ai_provider_config()

    assert "DASHSCOPE_API_KEY" in str(error.value)


def test_existing_openai_environment_remains_backward_compatible(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("OPENAI_MODEL", "openai-test")

    config = ai_teacher.resolve_ai_provider_config()

    assert config.id == "openai"
    assert config.model == "openai-test"
    assert config.protocol == "responses"


def test_qwen_uses_openai_compatible_chat_completions(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "qwen-secret")
    monkeypatch.setenv("QWEN_MODEL", "qwen-test")
    monkeypatch.setenv("QWEN_BASE_URL", "https://qwen.example/v1")
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                id="qwen-request-1",
                choices=[SimpleNamespace(message=SimpleNamespace(content="千问回答"))],
                usage=SimpleNamespace(prompt_tokens=21, completion_tokens=9),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    result = ai_teacher.generate_ai_reply(
        question="我为什么错了？",
        context_type="wrong_question",
        context={"question": {"correct_answer": "FALSE"}},
        history=[
            {"role": "user", "content": "这里的 ones 指什么？"},
            {"role": "assistant", "content": "指前面的 shoes。"},
        ],
    )

    assert captured["client"]["api_key"] == "qwen-secret"
    assert captured["client"]["base_url"] == "https://qwen.example/v1"
    assert captured["request"]["model"] == "qwen-test"
    assert captured["request"]["extra_body"] == {"enable_thinking": False}
    assert [message["role"] for message in captured["request"]["messages"]] == [
        "system",
        "user",
        "user",
        "assistant",
        "user",
    ]
    assert captured["request"]["messages"][-3]["content"] == "这里的 ones 指什么？"
    assert captured["request"]["messages"][-2]["content"] == "指前面的 shoes。"
    assert captured["request"]["messages"][-1]["content"] == "我为什么错了？"
    assert result == {
        "answer": "千问回答",
        "input_tokens": 21,
        "output_tokens": 9,
        "provider_request_id": "qwen-request-1",
        "provider": "qwen",
        "model": "qwen-test",
    }


def test_teacher_prompt_prefers_natural_explanation_without_fixed_sections() -> None:
    instructions = ai_teacher._instructions_for("wrong_question")

    assert "像正常老师和学生交流" in instructions
    assert "不要机械套用固定栏目" in instructions
    assert "2 至 4 个短段落" in instructions
    assert "只输出请求指定的 JSON" in ai_teacher._instructions_for(
        "wrong_question_paraphrase_extraction"
    )


def test_deepseek_uses_openai_compatible_chat_completions(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example")
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                id="deepseek-request-1",
                choices=[SimpleNamespace(message=SimpleNamespace(content="DeepSeek回答"))],
                usage=SimpleNamespace(prompt_tokens=18, completion_tokens=7),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    result = ai_teacher.generate_ai_reply(
        question="下一步练什么？",
        context_type="plan",
        context={"tasks": []},
        history=[],
    )

    assert captured["client"]["api_key"] == "deepseek-secret"
    assert captured["client"]["base_url"] == "https://deepseek.example"
    assert captured["client"]["timeout"] == 60.0
    assert captured["request"]["model"] == "deepseek-test"
    assert captured["request"]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert captured["request"]["reasoning_effort"] == "high"
    assert captured["request"]["max_tokens"] == 2400
    assert result["answer"] == "DeepSeek回答"
    assert result["provider"] == "deepseek"


def test_deepseek_thinking_can_be_disabled(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_THINKING", "disabled")
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                id="deepseek-request-2",
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    ai_teacher.generate_ai_reply(
        question="hello",
        context_type="plan",
        context={"tasks": []},
        history=[],
    )
    assert captured["request"]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in captured["request"]


def test_deepseek_paraphrase_extraction_forces_non_thinking_json(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                id="deepseek-json-1",
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"items":[]}'))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    ai_teacher.generate_ai_reply(
        question="只输出 JSON",
        context_type="wrong_question_paraphrase_extraction",
        context={"wrong_questions": []},
        history=[],
    )

    assert captured["request"]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert captured["request"]["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in captured["request"]


def test_public_status_never_exposes_api_keys(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "never-return-this")

    status = ai_teacher.ai_provider_public_status()

    assert status["selected"] == "deepseek"
    assert status["configured"] is True
    assert "never-return-this" not in repr(status)


def test_provider_can_be_switched_without_calling_external_service(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "qwen-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")

    selected = ai_teacher.select_ai_provider("deepseek")
    status = ai_teacher.ai_provider_public_status()

    assert selected == "deepseek"
    assert status["selected"] == "deepseek"
    assert status["configured"] is True


def test_background_provider_event_is_included_in_daily_limit(tmp_path) -> None:
    repository = AiTeacherRepository(tmp_path / "provider-events.sqlite3")

    repository.record_provider_event(
        user_id="owner",
        purpose="wrong_question_paraphrase_extraction",
        provider="deepseek",
        model="deepseek-v4-flash",
        input_tokens=120,
        output_tokens=30,
        provider_request_id="request-1",
    )

    assert repository.provider_calls_today(user_id="owner") == 1


def test_provider_selection_setting_survives_repository_reopen(tmp_path) -> None:
    database_path = tmp_path / "provider-settings.sqlite3"
    first = SQLiteSessionRepository(database_path)
    first.set_setting("ai_provider", "deepseek")

    reopened = SQLiteSessionRepository(database_path)

    assert reopened.get_setting("ai_provider") == "deepseek"
