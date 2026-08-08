import tempfile
from pathlib import Path
import unittest

from app.services.ocr_service import TesseractOCRService


class TestOCRService(unittest.TestCase):
    def test_is_text_garbage(self):
        service = TesseractOCRService()
        garbage = "er g oo\n\nate 2 Pre Ter ot ee Sie,\n\n[oe te ume\nLRA Hah bite sel"
        self.assertTrue(service._is_text_garbage(garbage))

        good_text = "Customer Name: John Doe\nAccount Number: 12345\nDate of Application: 2026-08-08"
        self.assertFalse(service._is_text_garbage(good_text))


if __name__ == '__main__':
    unittest.main()
