from __future__ import annotations

import json
import os
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


def generate_ai_reply(
    *,
    question: str,
    context_type: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AiTeacherNotConfiguredError("未配置 OPENAI_API_KEY，AI学习老师暂不可用。")

    model = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=45.0, max_retries=1)
        compact_history = history[-8:]
        payload = {
            "context_type": context_type,
            "verified_context": context,
            "recent_conversation": compact_history,
            "learner_question": question,
        }
        response = client.responses.create(
            model=model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=json.dumps(payload, ensure_ascii=False),
            max_output_tokens=900,
            store=False,
        )
        answer = str(getattr(response, "output_text", "") or "").strip()
        if not answer:
            raise AiTeacherProviderError("AI服务没有返回可显示的文字。")
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return {
            "answer": answer,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "provider_request_id": str(getattr(response, "id", "") or "") or None,
        }
    except AiTeacherProviderError:
        raise
    except Exception as error:
        raise AiTeacherProviderError("AI服务调用失败，请稍后重新提交。") from error
