"""Provider-reported usage only; no guessed balances or stored API keys."""
import hashlib
from datetime import UTC, datetime
from threading import RLock

from jarvis.core.personal_memory import PersonalMemory


class ApiUsage:
    def __init__(self, memory: PersonalMemory):
        self.memory = memory
        self.lock = RLock()

    @staticmethod
    def identity(source, key):
        return source + ":" + hashlib.sha256(key.encode()).hexdigest()

    def record(self, source, key, usage, headers):
        def count(*names):
            for name in names:
                value = usage.get(name)
                if isinstance(value, int) and value >= 0:
                    return value
            return 0
        identity = self.identity(source, key)
        day = datetime.now(UTC).date().isoformat()
        name = identity + ":" + day
        with self.lock:
            row = next((r for r in self.memory.records("api_usage") if r.get("id") == name), {})
            row.update({"id": name, "connection": identity, "day": day,
                        "responses": int(str(row.get("responses", 0))) + 1,
                        "input": int(str(row.get("input", 0))) + count("prompt_tokens", "promptTokenCount"),
                        "output": int(str(row.get("output", 0))) + count("completion_tokens", "candidatesTokenCount"),
                        "total": int(str(row.get("total", 0))) + count("total_tokens", "totalTokenCount"),
                        "reported": bool(usage) or bool(row.get("reported")),
                        "checked_at": datetime.now(UTC).isoformat()})
            for field in ("requests", "tokens"):
                value = headers.get("x-ratelimit-remaining-" + field)
                if value is not None and str(value).isdigit():
                    row["remaining_" + field] = int(value)
            self.memory.save_record("api_usage", name, row)

    def report(self, source, key):
        identity = self.identity(source, key)
        day = datetime.now(UTC).date().isoformat()
        row = next((r for r in self.memory.records("api_usage") if r.get("id") == identity + ":" + day), {})
        lines = [f"{source} · this key · today (UTC)",
                 f"Completed responses tracked by JARVIS: {row.get('responses', 0)}"]
        if row.get("reported"):
            lines.append(f"Reported tokens: input {row.get('input', 0)} · output {row.get('output', 0)} · total {row.get('total', 0)}")
        else:
            lines.append("Tokens used: not reported yet. Tracking starts with this update; previous usage is not backfilled.")
        for field in ("requests", "tokens"):
            if "remaining_" + field in row:
                lines.append(f"Last reported remaining {field} in provider rate-limit window: {row['remaining_' + field]}")
        lines.append("Remaining free quota / credit balance: not reported here. See provider dashboard. This counter covers JARVIS only, not other apps or keys sharing the account/project.")
        if row.get("checked_at"):
            lines.append("Last usage response: " + str(row["checked_at"]))
        return "\n".join(lines)
