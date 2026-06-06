"""agentic loop 測試：用假的 Anthropic client 腳本化模型回應，不碰真 API。

驗證的契約（M3 review commit 宣稱、但先前無測試守住的行為）：
  - 純文字回應 → 串 delta 後收一個 done
  - tool_use 一輪 → 推 tool 事件、執行工具、把 assistant content + tool_result 原樣回灌
  - 工具拋例外 → 回 is_error tool_result 並續跑（不死在 except）
  - 一直 tool_use → 用盡 MAX_TOOL_ROUNDS 後給可重試的 done
"""

from types import SimpleNamespace

import pytest

from app.ai import agent
from app.ai.agent import MAX_TOOL_ROUNDS, stream_chat
from app.ai.executor import ToolResult

pytestmark = pytest.mark.asyncio


# ── 假的 streaming client ───────────────────────────────────────

def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_block(name: str, tid: str, args: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, id=tid, input=args)


def _thinking_block(text: str, signature: str) -> SimpleNamespace:
    return SimpleNamespace(type="thinking", thinking=text, signature=signature)


def _delta_event(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


class _FakeStream:
    """模擬 client.messages.stream(...) 回傳的 async context manager + async iterator。"""

    def __init__(self, deltas: list[str], final: SimpleNamespace):
        self._deltas = deltas
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._agen()

    async def _agen(self):
        for d in self._deltas:
            yield _delta_event(d)

    async def get_final_message(self):
        return self._final


class _FakeClient:
    """messages.stream 依序吐出腳本化回應，並記錄每次傳入的 messages 以供斷言。"""

    def __init__(self, scripted: list[tuple[list[str], SimpleNamespace]]):
        self._scripted = list(scripted)
        self.sent_messages: list[list] = []
        self.messages = self

    def stream(self, **kwargs):
        # 鎖住送往 Anthropic 的請求形狀：fake 用 **kwargs 很容易連帶吞掉壞掉的 payload，
        # 造成「測試全綠、真打 API 卻 400」。這裡把最容易出錯的參數釘死。
        assert kwargs["model"], "model 不可為空"
        assert kwargs["tools"], "tools 不可為空"
        assert kwargs["system"], "system 不可為空"
        assert kwargs["thinking"] == {"type": "adaptive"}
        assert kwargs["output_config"] == {"effort": "medium"}
        self.sent_messages.append(kwargs["messages"])
        deltas, final = self._scripted.pop(0)
        return _FakeStream(deltas, final)


def _final(stop_reason: str, content: list) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=content)


class _FakeDB:
    """agent 測試不碰真 DB（run_tool 都被 monkeypatch），只需支援失敗路徑的 rollback。"""

    async def rollback(self):
        pass


async def _collect(history=None, user_text="嗨"):
    return [ev async for ev in stream_chat(_FakeDB(), history or [], user_text)]


# ── 測試 ────────────────────────────────────────────────────────

async def test_plain_text_response(monkeypatch):
    fake = _FakeClient([(["你好", "！"], _final("end_turn", [_text_block("你好！")]))])
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    events = await _collect()

    assert [e["type"] for e in events] == ["delta", "delta", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "你好！"
    assert events[-1]["text"] == "你好！"
    assert len(fake.sent_messages) == 1  # 沒有工具 → 只打一次


async def test_single_tool_round_reinjects_result(monkeypatch):
    fake = _FakeClient([
        ([], _final("tool_use", [_tool_block("get_schedule", "t1", {"date": "2026-06-05"})])),
        (["今天有 2 個行程。"], _final("end_turn", [_text_block("今天有 2 個行程。")])),
    ])
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    called = {}

    async def fake_run_tool(db, name, args):
        called["name"] = name
        called["args"] = args
        return ToolResult("SCHEDULE_RESULT")

    monkeypatch.setattr(agent, "run_tool", fake_run_tool)

    events = await _collect()
    types = [e["type"] for e in events]

    assert "tool" in types
    tool_ev = next(e for e in events if e["type"] == "tool")
    assert tool_ev["name"] == "get_schedule"
    assert called == {"name": "get_schedule", "args": {"date": "2026-06-05"}}
    assert events[-1] == {"type": "done", "text": "今天有 2 個行程。"}

    # 第二次請求要帶上 assistant content + 工具結果（tool_result 內含 SCHEDULE_RESULT）
    assert len(fake.sent_messages) == 2
    second = fake.sent_messages[1]
    assert second[-2]["role"] == "assistant"  # 回灌的整段 assistant content
    tool_result_msg = second[-1]
    assert tool_result_msg["role"] == "user"
    tr = tool_result_msg["content"][0]
    assert tr["type"] == "tool_result"
    assert tr["tool_use_id"] == "t1"
    assert tr["content"] == "SCHEDULE_RESULT"
    assert "is_error" not in tr


async def test_tool_failure_is_recoverable(monkeypatch):
    fake = _FakeClient([
        ([], _final("tool_use", [_tool_block("get_schedule", "t1", {})])),
        (["抱歉剛剛查詢出了點問題。"], _final("end_turn", [_text_block("抱歉剛剛查詢出了點問題。")])),
    ])
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    async def boom(db, name, args):
        raise RuntimeError("DB exploded")

    monkeypatch.setattr(agent, "run_tool", boom)

    events = await _collect()

    # 不該死在 except；仍以 done 收尾
    assert events[-1]["type"] == "done"
    assert events[-1]["text"] == "抱歉剛剛查詢出了點問題。"
    # 第二次請求的 tool_result 標了 is_error，且內容帶上例外訊息（模型要靠它自我修正）
    tr = fake.sent_messages[1][-1]["content"][0]
    assert tr["type"] == "tool_result"
    assert tr["is_error"] is True
    assert "DB exploded" in tr["content"]


async def test_thinking_block_reinjected_verbatim(monkeypatch):
    # thinking 區塊（含簽章）必須原樣回灌到下一輪 assistant content，否則 adaptive thinking 會 400
    think = _thinking_block("讓我查一下行程", "sig-abc123")
    fake = _FakeClient([
        ([], _final("tool_use", [think, _tool_block("get_schedule", "t1", {})])),
        (["好的"], _final("end_turn", [_text_block("好的")])),
    ])
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    async def ok(db, name, args):
        return ToolResult("R")

    monkeypatch.setattr(agent, "run_tool", ok)

    await _collect()

    reinjected = fake.sent_messages[1][-2]
    assert reinjected["role"] == "assistant"
    assert think in reinjected["content"]  # 同一個 thinking 物件原樣帶回，簽章未被動過


async def test_write_tool_emits_state_changed(monkeypatch):
    # 寫入工具回傳 changed 時，agent 要在 tool 與 done 之間推 state_changed，前端才會重抓
    fake = _FakeClient([
        ([], _final("tool_use", [_tool_block("add_task", "t1", {"title": "回信"})])),
        (["好，加進待辦了"], _final("end_turn", [_text_block("好，加進待辦了")])),
    ])
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    async def fake_run_tool(db, name, args):
        return ToolResult("已加入待辦：回信。", changed="tasks")

    monkeypatch.setattr(agent, "run_tool", fake_run_tool)

    events = await _collect()
    sc = [e for e in events if e["type"] == "state_changed"]
    assert sc == [{"type": "state_changed", "resource": "tasks"}]
    # 順序：tool 在前、state_changed 隨後、done 最後
    types = [e["type"] for e in events]
    assert types.index("tool") < types.index("state_changed") < types.index("done")


async def test_readonly_tool_emits_no_state_changed(monkeypatch):
    fake = _FakeClient([
        ([], _final("tool_use", [_tool_block("get_schedule", "t1", {})])),
        (["今天兩個行程"], _final("end_turn", [_text_block("今天兩個行程")])),
    ])
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    async def fake_run_tool(db, name, args):
        return ToolResult("今天有 2 個行程。")  # changed=None

    monkeypatch.setattr(agent, "run_tool", fake_run_tool)

    events = await _collect()
    assert not [e for e in events if e["type"] == "state_changed"]


async def test_parallel_writers_emit_state_changed_per_resource(monkeypatch):
    # 一輪多個寫入工具 → 每個改動各發一個 state_changed，resource 對、順序對
    fake = _FakeClient([
        ([], _final("tool_use", [
            _tool_block("add_task", "t1", {"title": "A"}),
            _tool_block("create_event", "t2", {"title": "B", "start_at": "2026-06-07T15:00", "duration_min": 30}),
        ])),
        (["都處理好了"], _final("end_turn", [_text_block("都處理好了")])),
    ])
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    resource_of = {"add_task": "tasks", "create_event": "events"}

    async def rt(db, name, args):
        return ToolResult(f"done {name}", changed=resource_of[name])

    monkeypatch.setattr(agent, "run_tool", rt)

    events = await _collect()
    sc = [e["resource"] for e in events if e["type"] == "state_changed"]
    assert sc == ["tasks", "events"]


async def test_multiple_tool_calls_in_one_round(monkeypatch):
    # 單輪可能有多個 tool_use（未停用 parallel tool use）→ 必須產生等量、id 對應的 tool_result
    fake = _FakeClient([
        ([], _final("tool_use", [
            _tool_block("get_schedule", "t1", {}),
            _tool_block("find_free_slots", "t2", {}),
        ])),
        (["都查好了"], _final("end_turn", [_text_block("都查好了")])),
    ])
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    calls = []

    async def rec(db, name, args):
        calls.append(name)
        return ToolResult(f"R-{name}")

    monkeypatch.setattr(agent, "run_tool", rec)

    events = await _collect()

    tool_names = [e["name"] for e in events if e["type"] == "tool"]
    assert tool_names == ["get_schedule", "find_free_slots"]
    assert calls == ["get_schedule", "find_free_slots"]

    results = fake.sent_messages[1][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert all(r["type"] == "tool_result" for r in results)


async def test_round_cap_returns_retry_message(monkeypatch):
    # 每一輪都回 tool_use → 永遠不收尾，應在 MAX_TOOL_ROUNDS 後給可重試提示
    scripted = [
        ([], _final("tool_use", [_tool_block("get_schedule", f"t{i}", {})]))
        for i in range(MAX_TOOL_ROUNDS)
    ]
    fake = _FakeClient(scripted)
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    async def ok(db, name, args):
        return ToolResult("ok")

    monkeypatch.setattr(agent, "run_tool", ok)

    events = await _collect()

    assert len(fake.sent_messages) == MAX_TOOL_ROUNDS  # 沒有超打
    assert events[-1]["type"] == "done"
    assert "換個方式再問" in events[-1]["text"]


async def test_history_is_passed_through(monkeypatch):
    fake = _FakeClient([(["好的"], _final("end_turn", [_text_block("好的")]))])
    monkeypatch.setattr(agent, "get_client", lambda: fake)

    history = [{"role": "user", "content": "先前的話"}, {"role": "assistant", "content": "先前的回覆"}]
    await _collect(history=history, user_text="新問題")

    sent = fake.sent_messages[0]
    assert sent[0] == {"role": "user", "content": "先前的話"}
    assert sent[1] == {"role": "assistant", "content": "先前的回覆"}
    # 最後一則是注入了現在時間情境的本次 user 輸入
    assert sent[-1]["role"] == "user"
    assert "新問題" in sent[-1]["content"]
