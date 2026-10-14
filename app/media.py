import json
import math
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps
from .engine import read_image

IMAGE_EXT = {'.png','.jpg','.jpeg','.webp','.bmp'}
VIDEO_EXT = {'.mp4','.mov','.mkv','.webm','.avi','.m4v'}
MAX_PIXELS = 40_000_000

def run(command, timeout=30):
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace')[-2500:])
    return result.stdout

def require_ffmpeg():
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('Thiếu FFmpeg/ffprobe. Cài FFmpeg rồi khởi động lại ứng dụng.')

def inspect(path: Path):
    if path.suffix.lower() in IMAGE_EXT:
        with Image.open(path) as im:
            if im.width*im.height > MAX_PIXELS:
                raise ValueError('Ảnh vượt giới hạn 40 megapixel')
            if im.mode.startswith('I') or im.mode == 'F':
                raise ValueError('Hãy chuyển ảnh 16-bit/HDR sang PNG 8-bit')
            normalized = ImageOps.exif_transpose(im)
            normalized = normalized.convert('RGBA' if 'A' in normalized.getbands() or 'transparency' in im.info else 'RGB')
            target = path.with_suffix('.png')
            normalized.save(target)
        if path != target:
            path.unlink()
        frame = read_image(target)
        return target, dict(kind='image',width=frame.shape[1],height=frame.shape[0],duration=0,fps=0)
    require_ffmpeg()
    info = json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
    stream = next((s for s in info['streams'] if s['codec_type']=='video'),None)
    if not stream:
        raise ValueError('File không có luồng video')
    w,h = stream['width'],stream['height']
    if w*h > MAX_PIXELS:
        raise ValueError('Video vượt giới hạn 40 megapixel')
    rotation = float(stream.get('tags',{}).get('rotate',0))
    for side in stream.get('side_data_list',[]):
        rotation = float(side.get('rotation',rotation))
    if abs(round(rotation)) % 180 == 90:
        w,h = h,w
    try:
        fps = float(Fraction(stream.get('avg_frame_rate','0/1')))
    except (ValueError, ZeroDivisionError):
        fps = 0
    if not math.isfinite(fps) or fps <= 0 or fps > 240:
        raise ValueError('Không xác định được FPS hợp lệ (1–240)')
    duration = float(info.get('format',{}).get('duration',stream.get('duration',0)))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Không xác định được thời lượng')
    return path, dict(kind='video',width=w,height=h,fps=fps,duration=duration,
                      audio=any(s['codec_type']=='audio' for s in info['streams']))

def frame_at(path, meta, time=0):
    if meta['kind']=='image':
        return read_image(path)
    require_ffmpeg()
    t = min(time,max(0,meta['duration']-1/meta['fps']))
    raw = run(['ffmpeg','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','-threads','1','pipe:1'])
    frame = cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError('Không đọc được khung hình tại thời điểm này')
    return frame

def encoders():
    if not shutil.which('ffmpeg'):
        return []
    text = run(['ffmpeg','-hide_banner','-encoders']).decode(errors='replace')
    return [e for e in ['libx264','h264_nvenc','h264_qsv','h264_amf'] if e in text]
