"""工具註冊一致性：tools.py 的定義與 executor 的分派表必須完全對應。

這正是把工具名稱抽成常數 + 改用 dispatch 表要守住的性質——
少了任一邊、或名稱漂移，工具會靜默掉進「未知的工具」而不報錯。這裡用測試擋掉。
"""

from app.ai import executor
from app.ai.tools import TOOLS


def _defined_tool_names() -> set[str]:
    return {tool["name"] for tool in TOOLS}


def _dispatched_tool_names() -> set[str]:
    return set(executor._READ_HANDLERS) | set(executor._WRITE_HANDLERS)


def test_every_defined_tool_has_a_handler():
    missing = _defined_tool_names() - _dispatched_tool_names()
    assert not missing, f"這些工具有定義卻沒有 handler（會掉進『未知的工具』）：{missing}"


def test_no_orphan_handlers():
    orphan = _dispatched_tool_names() - _defined_tool_names()
    assert not orphan, f"這些 handler 沒有對應的工具定義（模型永遠不會呼叫到）：{orphan}"


def test_read_and_write_handlers_are_disjoint():
    overlap = set(executor._READ_HANDLERS) & set(executor._WRITE_HANDLERS)
    assert not overlap, f"同一工具不可同時在唯讀與寫入表：{overlap}"


def test_write_tools_matches_write_handlers():
    # _WRITE_TOOLS 用於 no-op log 判斷，必須恰好等於寫入 handler 的集合
    assert executor._WRITE_TOOLS == frozenset(executor._WRITE_HANDLERS)
