import unittest

from pipelines.ingest.chunker import chunk_document


class ChunkerTests(unittest.TestCase):
    def test_empty_text_returns_empty(self):
        self.assertEqual(chunk_document(text="", doc_id="doc-1"), [])

    def test_short_text_returns_single_chunk_with_title(self):
        chunks = chunk_document(
            text="Apple reported a concise operating update.",
            doc_id="doc-1",
            title="Apple update",
            target_tokens=64,
            overlap_tokens=8,
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "doc-1__c00")
        self.assertEqual(chunks[0].parent_doc_id, "doc-1")
        self.assertTrue(chunks[0].text.startswith("[Apple update]"))

    def test_long_single_paragraph_uses_sliding_windows(self):
        text = " ".join(f"word{i}" for i in range(260))

        chunks = chunk_document(text=text, doc_id="doc-2", target_tokens=80, overlap_tokens=16)

        self.assertGreater(len(chunks), 1)
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))
        self.assertTrue(all(chunk.total_chunks == len(chunks) for chunk in chunks))
        self.assertTrue(all(chunk.char_span[0] <= chunk.char_span[1] for chunk in chunks))

    def test_paragraph_boundary_prefers_coherent_chunks(self):
        para1 = " ".join(["revenue expanded"] * 40)
        para2 = " ".join(["margin pressure"] * 40)
        chunks = chunk_document(
            text=f"{para1}\n\n{para2}",
            doc_id="doc-3",
            target_tokens=80,
            overlap_tokens=8,
        )

        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("revenue expanded", chunks[0].text)
        self.assertTrue(any("margin pressure" in chunk.text for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
