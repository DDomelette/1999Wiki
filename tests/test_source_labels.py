from src.rag.source_labels import format_source_label


def test_source_label_does_not_repeat_entity_name():
    assert format_source_label("APPLe", "APPLe / 基础资料") == "APPLe / 基础资料"
    assert format_source_label("APPLe", "基础资料") == "APPLe / 基础资料"
    assert format_source_label("APPLe", "") == "APPLe"
