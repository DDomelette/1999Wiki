import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag.vectorstore import (
    HUIJI_BUSINESS_FIELDS,
    huiji_child_to_business_row,
    huiji_child_to_milvus_row,
)


def test_huiji_milvus_row_uses_one_business_projection():
    child = {
        "child_id": "c1",
        "text": "正文",
        "parent_id": "p1",
        "source_refs": [{"kind": "data_page"}],
    }

    business = huiji_child_to_business_row(child)
    row = huiji_child_to_milvus_row(child, [0.1, 0.2])

    assert row == {**business, "embedding": [0.1, 0.2]}
    assert tuple(business) == HUIJI_BUSINESS_FIELDS
    assert "embedding" not in business
    assert business["id"] == business["child_id"] == "c1"

