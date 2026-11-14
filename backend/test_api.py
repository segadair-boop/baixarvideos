import unittest
from fastapi import HTTPException
from backend.main import validated_url, FORMATS

class UrlSecurityTests(unittest.TestCase):
    def test_valid(self):
        for url in ["https://www.youtube.com/watch?v=123","https://www.instagram.com/reel/123","https://m.tiktok.com/@test/video/123","https://youtu.be/abc"]:
            self.assertEqual(validated_url(url),url)
    def test_rejected(self):
        for url in ["http://youtube.com/watch?v=1","https://youtube.com.evil.com/watch?v=1","https://127.0.0.1/admin","https://169.254.169.254/latest/meta-data","https://localhost/","https://user:pass@youtube.com/x","file:///etc/passwd","https://youtube.com:8443/test"]:
            with self.subTest(url=url):
                with self.assertRaises(HTTPException):
                    validated_url(url)
    def test_formats(self):
        self.assertIn("video_720", FORMATS)
        self.assertIn("audio_mp3", FORMATS)

if __name__=="__main__":
    unittest.main()
