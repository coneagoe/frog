import unittest
import baidu_ocr as ocr


class MyTestCase(unittest.TestCase):
    def test_ocr(self):
        words = ocr.get_ocr('test.jpg')
        print(words)

if __name__ == '__main__':
    unittest.main()
