"""Frame similarity service using SSIM."""

import tempfile
from typing import Optional

import cv2
import numpy as np
import yt_dlp
from skimage.metrics import structural_similarity as ssim

from ..utils.proxy_helper import get_ytdlp_proxy, is_proxy_configured


class SimilarityService:
    """Compare video frames using SSIM."""

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        ydl_opts = {'quiet': True}
        proxy = get_ytdlp_proxy()
        if proxy:
            ydl_opts['proxy'] = proxy
        self.ydl = yt_dlp.YoutubeDL(ydl_opts)

    def _get_stream_url(self, video_id: str) -> Optional[str]:
        """Get direct stream URL using yt-dlp."""
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            info = self.ydl.extract_info(url, download=False)
            return info.get('url')
        except Exception:
            return None

    def _get_frame_stream(self, video_id: str, timestamp: float) -> Optional[np.ndarray]:
        """Get frame at timestamp from stream URL."""
        stream_url = self._get_stream_url(video_id)
        if not stream_url:
            return None

        try:
            cap = cv2.VideoCapture(stream_url)
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ret, frame = cap.read()
            cap.release()
            return frame if ret else None
        except Exception:
            return None

    def _compute_ssim(self, frame_a: np.ndarray, frame_b: np.ndarray) -> float:
        """Compute SSIM between two frames."""
        if frame_a.shape != frame_b.shape:
            frame_b = cv2.resize(
                frame_b,
                (frame_a.shape[1], frame_a.shape[0])
            )

        gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)

        score = ssim(gray_a, gray_b)
        return float(score)

    async def compare_videos(
        self,
        video_a_id: str,
        video_b_id: str,
        threshold: float = 0.7,
        num_samples: int = 5,
    ) -> int:
        """
        Compare frames at multiple timestamps.

        Uses yt-dlp to get stream URL, then cv2 to read frames directly.

        Returns number of frames that passed (score >= threshold).
        """
        passed = 0
        timestamps = [30, 60, 90, 120, 150]

        for i in range(num_samples):
            if i >= len(timestamps):
                break
            t = timestamps[i]

            frame_a = self._get_frame_stream(video_a_id, t)
            frame_b = self._get_frame_stream(video_b_id, t)

            if frame_a is not None and frame_b is not None:
                score = self._compute_ssim(frame_a, frame_b)
                if score >= threshold:
                    passed += 1
                    print(f"Frame {i+1}: SSIM = {score:.2f} (PASS)")
                else:
                    print(f"Frame {i+1}: SSIM = {score:.2f} (FAIL)")
            else:
                print(f"Frame {i+1}: Failed to extract frames")

        return passed

    def cleanup(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)