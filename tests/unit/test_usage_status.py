import json

from cchwc.server.usage_status import (
    parse_claude_rate_limit_output,
    parse_codex_rate_limit_line,
    read_codex_limit_status,
)


def test_parse_codex_rate_limit_line():
    line = json.dumps(
        {
            "timestamp": "2026-04-30T08:00:00.000Z",
            "type": "event_msg",
            "rate_limits": {
                "limit_id": "codex",
                "primary": {"used_percent": 5.0, "window_minutes": 300, "resets_at": 1777439491},
                "secondary": {"used_percent": 15.0, "window_minutes": 10080, "resets_at": 1777965935},
                "credits": None,
                "plan_type": "plus",
                "rate_limit_reached_type": None,
            },
        }
    )

    parsed = parse_codex_rate_limit_line(line, file_path="session.jsonl", file_mtime="2026-04-30T08:00:00")

    assert parsed is not None
    assert parsed["available"] is True
    assert parsed["plan_type"] == "plus"
    assert parsed["primary"]["label"] == "5h"
    assert parsed["primary"]["remaining_percent"] == 95.0
    assert parsed["secondary"]["label"] == "7d"
    assert parsed["secondary"]["remaining_percent"] == 85.0


def test_read_codex_limit_status_uses_latest_rate_limit_event(local_tmp_path):
    session = local_tmp_path / "2026" / "04" / "30" / "rollout.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-04-30T08:00:00.000Z",
                        "rate_limits": {
                            "primary": {"used_percent": 10, "window_minutes": 300},
                            "secondary": {"used_percent": 20, "window_minutes": 10080},
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-04-30T08:10:00.000Z",
                        "payload": {
                            "type": "token_count",
                            "rate_limits": {
                                "primary": {"used_percent": 25, "window_minutes": 300},
                                "secondary": {"used_percent": 40, "window_minutes": 10080},
                            },
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    parsed = read_codex_limit_status(local_tmp_path)

    assert parsed["available"] is True
    assert parsed["primary"]["remaining_percent"] == 75.0
    assert parsed["secondary"]["remaining_percent"] == 60.0


def test_parse_claude_rate_limit_output():
    output = "\n".join(
        [
            json.dumps(
                {
                    "type": "rate_limit_event",
                    "rate_limit_info": {
                        "status": "allowed",
                        "resetsAt": 1777544400,
                        "rateLimitType": "five_hour",
                        "overageStatus": "allowed",
                        "overageResetsAt": 1777593600,
                        "isUsingOverage": False,
                    },
                }
            ),
            json.dumps({"type": "assistant", "message": {"content": "status-probe"}}),
        ]
    )

    parsed = parse_claude_rate_limit_output(output)

    assert parsed is not None
    assert parsed["available"] is True
    assert parsed["status"] == "allowed"
    assert parsed["rate_limit_type"] == "five_hour"
    assert parsed["is_using_overage"] is False
