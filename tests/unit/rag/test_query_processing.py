from app.rag.query_processing import QueryProcessor


def test_query_processor_normalizes_unicode_and_outer_whitespace_only() -> None:
    processor = QueryProcessor()

    normalized = processor.normalize('  \uff2dodel-X\uff11\uff10\uff10 2.5% "do not disable"  ')

    assert normalized == 'Model-X100 2.5% "do not disable"'
