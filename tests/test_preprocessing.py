import cv2
import numpy as np
import unittest

from app.ocr_pipeline.preprocessing import order_quad_points, perspective_correct


class TestPreprocessing(unittest.TestCase):
    def test_perspective_correct_rotates_landscape_output_to_portrait(self):
        # Create a landscape-like quad such that the warped rectangle is rotated to portrait.
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        cv2.rectangle(image, (20, 20), (180, 80), (255, 255, 255), -1)

        quad = np.array(
            [[20.0, 20.0], [180.0, 20.0], [180.0, 80.0], [20.0, 80.0]],
            dtype=np.float32,
        )
        quad = order_quad_points(quad)

        warped = perspective_correct(image, quad)

        self.assertEqual(warped.shape[0], 160)
        self.assertEqual(warped.shape[1], 60)
        self.assertGreater(np.mean(warped), 0)


if __name__ == "__main__":
    unittest.main()
