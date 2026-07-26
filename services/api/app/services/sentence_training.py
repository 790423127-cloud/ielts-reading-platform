from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

STEP_KEYS = ("predicate", "subject", "object", "scope", "logic")
STEP_DEFINITIONS = (
    {"key": "predicate", "label": "1. 谓语", "prompt": "先找承载时态、语态或情态的核心谓语。"},
    {"key": "subject", "label": "2. 主语", "prompt": "确认是谁或什么执行动作、处于状态。"},
    {"key": "object", "label": "3. 宾语或补语", "prompt": "找出动作对象或补充说明；没有时可留空。"},
    {"key": "scope", "label": "4. 修饰与范围", "prompt": "标出条件、时间、地点、比较和限定范围。"},
    {"key": "logic", "label": "5. 逻辑", "prompt": "判断转折、因果、条件、时间、目的或并列关系。"},
)
LOGIC_ALIASES = {
    "cause": "cause_effect",
    "cause-effect": "cause_effect",
    "cause and effect": "cause_effect",
    "因果": "cause_effect",
    "condition": "condition",
    "条件": "condition",
    "contrast": "contrast",
    "转折": "contrast",
    "comparison": "comparison",
    "比较": "comparison",
    "time": "time",
    "时间": "time",
    "purpose": "purpose",
    "目的": "purpose",
    "addition": "addition",
    "并列": "addition",
    "restriction": "restriction",
    "限定": "restriction",
    "none": "none",
    "无": "none",
}


class SentenceTrainingDataError(RuntimeError):
    pass


def normalize_span(value: Any) -> str:
    text = str(value or "").casefold().replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" .,:;!?\"'")


def normalize_logic(value: Any) -> str:
    text = normalize_span(value).replace("_", " ")
    return LOGIC_ALIASES.get(text, text.replace(" ", "_"))


def canonical_training_bytes(raw: bytes) -> bytes:
    """Return the repository-canonical UTF-8/LF representation.

    Git on Windows may check text files out with CRLF and some editors may add a
    UTF-8 BOM. Neither changes the JSON content, so manifest verification uses
    the canonical bytes while still rejecting any real content modification.
    """

    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


class SentenceTrainingBank:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.data_path = self.root / "index.json"
        self.manifest_path = self.root / "migration_manifest.json"
        self._items: list[dict[str, Any]] | None = None

    def validate(self) -> dict[str, Any]:
        if not self.data_path.exists() or not self.manifest_path.exists():
            raise SentenceTrainingDataError("Verified sentence-training data is missing")
        source_raw = self.data_path.read_bytes()
        raw = canonical_training_bytes(source_raw)
        manifest = json.loads(self.manifest_path.read_text("utf-8-sig"))
        if int(manifest.get("bytes") or 0) != len(raw):
            raise SentenceTrainingDataError("Sentence-training byte count does not match manifest")
        digest = hashlib.sha256(raw).hexdigest()
        if digest != str(manifest.get("sha256") or ""):
            raise SentenceTrainingDataError("Sentence-training SHA-256 does not match manifest")
        data = json.loads(raw.decode("utf-8"))
        if data.get("version") != 1:
            raise SentenceTrainingDataError("Unsupported sentence-training data version")
        items = data.get("items") or []
        if len(items) != int(manifest.get("item_count") or 0):
            raise SentenceTrainingDataError("Sentence-training item count does not match manifest")
        ids: set[str] = set()
        for item in items:
            item_id = str(item.get("id") or "")
            if not item_id or item_id in ids:
                raise SentenceTrainingDataError("Sentence-training IDs must be unique")
            ids.add(item_id)
            if item.get("status") != "verified":
                raise SentenceTrainingDataError(f"Sentence {item_id} is not verified")
            roles = item.get("roles") or {}
            if not str(roles.get("subject") or "").strip() or not str(roles.get("predicate") or "").strip():
                raise SentenceTrainingDataError(f"Sentence {item_id} lacks verified subject/predicate")
        self._items = [dict(item) for item in items]
        return {
            "version": 1,
            "item_count": len(items),
            "bytes": len(raw),
            "sha256": digest,
            "source_git_blob_sha": manifest.get("source_git_blob_sha"),
            "verified": True,
            "checkout_normalized": source_raw != raw,
        }

    def items(self) -> list[dict[str, Any]]:
        if self._items is None:
            self.validate()
        return [dict(item) for item in (self._items or [])]

    def get(self, item_id: str) -> dict[str, Any]:
        item = next((row for row in self.items() if str(row.get("id")) == item_id), None)
        if not item:
            raise KeyError(item_id)
        return item

    def find_exact_sentence(self, sentence: str) -> dict[str, Any] | None:
        normalized = normalize_span(sentence)
        if not normalized:
            return None
        return next(
            (item for item in self.items() if normalize_span(item.get("sentence")) == normalized),
            None,
        )

    def public_catalog(self) -> dict[str, Any]:
        status = self.validate()
        items = [
            {
                "id": item["id"],
                "sentence": item["sentence"],
                "difficulty": item.get("difficulty") or "medium",
                "source": item.get("source") or {},
                "status": "verified",
            }
            for item in self.items()
        ]
        return {
            "version": 1,
            "status": status,
            "steps": [dict(step) for step in STEP_DEFINITIONS],
            "items": items,
            "answer_fields_exposed_before_submit": False,
            "ai_calls": 0,
        }

    def evaluate(self, item_id: str, answers: dict[str, Any]) -> dict[str, Any]:
        item = self.get(item_id)
        roles = item.get("roles") or {}
        expected = {
            "predicate": str(roles.get("predicate") or ""),
            "subject": str(roles.get("subject") or ""),
            "object": str(roles.get("object") or ""),
            "scope": str(roles.get("scope") or ""),
            "logic": str(item.get("logic") or "none"),
        }
        rows: list[dict[str, Any]] = []
        for key in STEP_KEYS:
            user_value = str(answers.get(key) or "")
            expected_value = expected[key]
            if key == "logic":
                correct = normalize_logic(user_value) == normalize_logic(expected_value)
            else:
                correct = normalize_span(user_value) == normalize_span(expected_value)
            rows.append(
                {
                    "key": key,
                    "correct": correct,
                    "user_answer": user_value,
                    "expected_answer": expected_value,
                }
            )
        score = sum(1 for row in rows if row["correct"])
        return {
            "item_id": item_id,
            "sentence": item["sentence"],
            "score": score,
            "total": len(STEP_KEYS),
            "accuracy": round(100 * score / len(STEP_KEYS), 1),
            "steps": rows,
            "explanation": item.get("explanation") or "",
            "simplified_zh": item.get("simplified_zh") or "",
            "answer_impact": item.get("answer_impact") or "",
            "source": item.get("source") or {},
            "verified_standard": True,
            "ai_calls": 0,
        }
