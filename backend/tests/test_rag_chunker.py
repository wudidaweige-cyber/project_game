"""Knowledge chunker unit tests."""

from app.rag.chunker import chunk_markdown


def test_chunk_markdown_splits_by_headings_and_size():
    text = """# 标题A

第一段内容。""" + ("详细说明。" * 40) + """

## 标题B

第二段内容。
"""
    chunks = chunk_markdown(text, max_chars=120)
    assert len(chunks) >= 2
    assert all(c["content"].strip() for c in chunks)
    assert chunks[0]["chunk_index"] == 0
