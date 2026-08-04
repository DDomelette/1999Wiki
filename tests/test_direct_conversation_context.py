from __future__ import annotations

from src.rag.chain import RAGChain


class _RecordingExecutionService:
    def __init__(self) -> None:
        self.requests = []

    def execute(self, request, conversation, trace):
        self.requests.append(request)
        return "normal-result"


def test_bare_usage_with_memory_delegates_to_normal_rag_execution() -> None:
    service = _RecordingExecutionService()
    chain = RAGChain.__new__(RAGChain)
    chain._execution_service = service

    result = chain.execute("怎么用", memory_turns_used=1)

    assert result == "normal-result"
    assert service.requests[0].question == "怎么用"
