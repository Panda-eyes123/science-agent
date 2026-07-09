"""Small in-memory todo service used by tools and tests."""

from dataclasses import asdict, dataclass, field
from typing import Literal

from science_agent.types import utc_now_iso

TodoStatus = Literal["pending", "in_progress", "completed"]


@dataclass(slots=True)
class TodoItem:
    id: str
    content: str
    status: TodoStatus = "pending"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


class TodoService:
    def __init__(self) -> None:
        self._items: dict[str, TodoItem] = {}

    def list_items(self) -> list[TodoItem]:
        return list(self._items.values())

    def upsert(
        self, item_id: str, content: str, status: TodoStatus = "pending"
    ) -> TodoItem:
        existing = self._items.get(item_id)
        if existing is None:
            item = TodoItem(id=item_id, content=content, status=status)
            self._items[item_id] = item
            return item
        existing.content = content
        existing.status = status
        existing.updated_at = utc_now_iso()
        return existing

    def complete(self, item_id: str) -> TodoItem:
        item = self._items[item_id]
        item.status = "completed"
        item.updated_at = utc_now_iso()
        return item

    def snapshot(self) -> list[dict]:
        return [asdict(item) for item in self.list_items()]

    def load_snapshot(self, rows: list[dict]) -> None:
        self._items = {row["id"]: TodoItem(**row) for row in rows}
