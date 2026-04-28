import json
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from cchwc.adapters.base import SessionAdapter
from cchwc.core.schemas import ParsedMessage, ParsedSession, TokenUsage


def encode_cwd(cwd: str) -> str:
    """cwd 경로를 Claude가 사용하는 디렉토리명으로 인코딩."""
    return re.sub(r"[:\\/]", "-", cwd)


class ClaudeAdapter(SessionAdapter):
    agent_type = "claude"

    def __init__(self, root: Path | None = None, scan_roots: list[str] | None = None):
        self._root = root or (Path.home() / ".claude" / "projects")
        self._scan_roots = scan_roots  # None = global, [] = no filter, [cwd...] = project filter

    def session_root(self) -> Path:
        return self._root

    def discover_session_files(self) -> Iterator[Path]:
        root = self.session_root()
        if not root.exists():
            return

        if not self._scan_roots:
            yield from root.rglob("*.jsonl")
            return

        for cwd in self._scan_roots:
            encoded = encode_cwd(cwd)
            project_dir = root / encoded
            if project_dir.exists():
                yield from project_dir.glob("*.jsonl")
            else:
                # 대소문자 무관 탐색 (Windows 경로)
                for d in root.iterdir():
                    if d.is_dir() and d.name.lower() == encoded.lower():
                        yield from d.glob("*.jsonl")
                        break

    def parse_file(self, path: Path) -> ParsedSession | None:
        lines = self._read_jsonl(path)
        if not lines:
            return None

        session_id = None
        cwd = None
        messages: list[ParsedMessage] = []
        total = TokenUsage()
        seq = 0

        for record in lines:
            rec_type = record.get("type")

            if rec_type == "permission-mode":
                session_id = record.get("sessionId", session_id)
                continue

            if session_id is None:
                session_id = record.get("sessionId")

            if cwd is None:
                cwd = record.get("cwd")

            if rec_type in ("user", "assistant"):
                msg = record.get("message", {})
                role = msg.get("role", rec_type)
                content = msg.get("content")
                # tool_result 블록만 있는 user 메시지는 별도 role로 분리
                if (
                    role == "user"
                    and isinstance(content, list)
                    and content
                    and all(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content
                        if isinstance(b, dict)
                    )
                ):
                    role = "tool_result"
                content_text = self._extract_text(content)
                ts = record.get("timestamp", "")
                model = msg.get("model")

                usage = msg.get("usage", {})
                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)
                cache_create = usage.get("cache_creation_input_tokens", 0)

                total.input_tokens += inp
                total.output_tokens += out
                total.cache_read_tokens += cache_read
                total.cache_creation_tokens += cache_create

                messages.append(
                    ParsedMessage(
                        sequence=seq,
                        role=role,
                        content_text=content_text,
                        content_json=json.dumps(msg, ensure_ascii=False),
                        timestamp=self._parse_ts(ts),
                        input_tokens=inp or None,
                        output_tokens=out or None,
                        cache_read_tokens=cache_read or None,
                        cache_creation_tokens=cache_create or None,
                        model=model,
                    )
                )
                seq += 1

        if not messages or session_id is None:
            return None

        if cwd is None:
            cwd = self.extract_cwd(path)

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
        """프로젝트 디렉토리명에서 cwd를 역디코딩 (JSONL에 cwd 필드가 없을 때 fallback)."""
        project_dir = path.parent.name
        if not project_dir:
            return None
        decoded = re.sub(r"^-", "/", project_dir)
        decoded = decoded.replace("-", "/")
        if len(decoded) > 2 and decoded[2] == "/":
            decoded = decoded[0] + ":" + decoded[2:]
        return decoded

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
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        parts.append(f"[tool_use: {block.get('name', '')}]")
                    elif block.get("type") == "tool_result":
                        result_content = block.get("content", "")
                        if isinstance(result_content, str):
                            parts.append(result_content[:500])
                    elif block.get("type") == "thinking":
                        pass
            return "\n".join(parts) if parts else None
        return None

    def _parse_ts(self, ts: str) -> datetime:
        if not ts:
            return datetime.now()
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now()
