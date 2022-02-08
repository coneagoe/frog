import unittest
import baidu_ocr as ocr


class MyTestCase(unittest.TestCase):
    def test_position_ttjj_app(self):
        words = ocr.get_funds_position_ttjj_app('test.jpg', ('002943', '001718', '000297', '001532', '000991'))
        print(words)

if __name__ == '__main__':
    unittest.main()
