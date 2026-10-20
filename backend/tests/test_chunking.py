from app.rag import split_text


def test_split_text_has_overlap_and_content():
    text = ("Primera frase. " * 150) + ("Segunda frase. " * 150)
    chunks = split_text(text, chunk_size=500, overlap=80)
    assert len(chunks) > 2
    assert all(chunk.strip() for chunk in chunks)
    assert all(len(chunk) <= 510 for chunk in chunks)
