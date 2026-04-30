import json
import os
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from cchwc.adapters.base import SessionAdapter
from cchwc.core.schemas import ParsedMessage, ParsedSession, TokenUsage


class CodexAdapter(SessionAdapter):
    agent_type = "codex"

    def __init__(self, root: Path | None = None, scan_roots: list[str] | None = None):
        self._root = root or (Path.home() / ".codex" / "sessions")
        self._scan_roots = scan_roots  # None = global, [cwd...] = filter by cwd

    def _matches_scan_roots(self, cwd: str) -> bool:
        if not self._scan_roots:
            return True
        cwd_norm = os.path.normcase(os.path.normpath(cwd))
        for r in self._scan_roots:
            r_norm = os.path.normcase(os.path.normpath(r))
            if cwd_norm == r_norm or cwd_norm.startswith(r_norm + os.sep):
                return True
        return False

    def session_root(self) -> Path:
        return self._root

    def discover_session_files(self) -> Iterator[Path]:
        root = self.session_root()
        if not root.exists():
            return
        yield from root.rglob("*.jsonl")

    def parse_file(self, path: Path) -> ParsedSession | None:
        lines = self._read_jsonl(path)
        if not lines:
            return None

        session_id = None
        cwd = None
        messages: list[ParsedMessage] = []
        total = TokenUsage()
        seq = 0
        model: str | None = None

        for record in lines:
            rec_type = record.get("type")
            ts = record.get("timestamp", "")
            payload = record.get("payload", {})

            if rec_type == "session_meta":
                session_id = payload.get("id")
                cwd = payload.get("cwd")
                continue

            if rec_type == "turn_context":
                model = payload.get("model")
                if cwd is None:
                    cwd = payload.get("cwd")
                continue

            if rec_type == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info")
                if info:
                    usage = info.get("last_token_usage", {})
                    total.input_tokens += usage.get("input_tokens", 0)
                    total.output_tokens += usage.get("output_tokens", 0)
                    total.cache_read_tokens += usage.get("cached_input_tokens", 0)
                continue

            if rec_type == "response_item":
                item_type = payload.get("type")
                role = payload.get("role")

                if item_type == "message" and role in ("user", "assistant"):
                    content_text = self._extract_text(payload.get("content", []))
                    if content_text and "<environment_context>" in content_text:
                        extracted_cwd = self._extract_cwd_from_env_context(content_text)
                        if extracted_cwd and cwd is None:
                            cwd = extracted_cwd
                        continue

                    messages.append(
                        ParsedMessage(
                            sequence=seq,
                            role=role,
                            content_text=content_text,
                            content_json=json.dumps(payload, ensure_ascii=False),
                            timestamp=self._parse_ts(ts),
                            model=model,
                        )
                    )
                    seq += 1

                elif item_type == "function_call":
                    fn_name = payload.get("name", "")
                    messages.append(
                        ParsedMessage(
                            sequence=seq,
                            role="tool_use",
                            content_text=f"[function_call: {fn_name}]",
                            content_json=json.dumps(payload, ensure_ascii=False),
                            timestamp=self._parse_ts(ts),
                            model=model,
                        )
                    )
                    seq += 1

                elif item_type == "function_call_output":
                    output = payload.get("output", "")
                    if isinstance(output, str) and len(output) > 500:
                        output = output[:500]
                    messages.append(
                        ParsedMessage(
                            sequence=seq,
                            role="tool_result",
                            content_text=output,
                            content_json=json.dumps(payload, ensure_ascii=False),
                            timestamp=self._parse_ts(ts),
                            model=model,
                        )
                    )
                    seq += 1

        if not messages:
            return None

        if session_id is None:
            session_id = path.stem

        if cwd is not None and self._scan_roots is not None and not self._matches_scan_roots(cwd):
            return None

        return ParsedSession(
            agent_type=self.agent_type,
            external_id=session_id,
            file_path=str(path),
            cwd=cwd,
            started_at=messages[0].timestamp,
            last_message_at=messages[-1].timestamp,
            messages=messages,
            total_usage=total,
        )

    def extract_cwd(self, path: Path) -> str | None:
        lines = self._read_jsonl(path)
        for record in lines:
            if record.get("type") == "session_meta":
                return record.get("payload", {}).get("cwd")
            if record.get("type") == "response_item":
                payload = record.get("payload", {})
                content = payload.get("content", [])
                text = self._extract_text(content)
                if text and "<environment_context>" in text:
                    return self._extract_cwd_from_env_context(text)
        return None

    def _extract_cwd_from_env_context(self, text: str) -> str | None:
        match = re.search(r"<cwd>(.*?)</cwd>", text)
        return match.group(1) if match else None

    def _read_jsonl(self, path: Path) -> list[dict]:
        records = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return records

    def _extract_text(self, content) -> str | None:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") in ("input_text", "text"):
                    parts.append(block.get("text", ""))
            return "\n".join(parts) if parts else None
        return None

    def _parse_ts(self, ts: str) -> datetime:
        if not ts:
            return datetime.now()
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now()
