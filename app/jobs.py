import json
import os
import queue
import subprocess
import threading
import time
import uuid
from pathlib import Path
import cv2
from .engine import detect, make_mask, restore, read_image, bgr
from .media import frame_at, require_ffmpeg
from .models import Settings

class Cancelled(Exception):
    pass

class JobManager:
    def __init__(self, root, asset):
        self.root = root
        self.asset = asset
        self.folder = root / 'jobs'
        self.folder.mkdir(parents=True,exist_ok=True)
        self.items = {}
        self.lock = threading.RLock()
        self.queue = queue.Queue()
        self.stopping = threading.Event()
        self.worker = None
        for path in self.folder.glob('*.json'):
            try:
                item = json.loads(path.read_text('utf-8'))
                if item['status'] in ('queued','running','cancelling'):
                    item.update(status='interrupted',error='Ứng dụng đã dừng. Hãy tạo tác vụ mới.')
                self.items[item['id']] = item
            except (ValueError,KeyError):
                continue

    def start(self):
        self.worker = threading.Thread(target=self.loop,daemon=True)
        self.worker.start()

    def stop(self):
        self.stopping.set()
        with self.lock:
            for j in self.items.values():
                if j['status'] in ('queued','running'):
                    self.update(j['id'],status='cancelling')
        self.queue.put(None)
        if self.worker:
            self.worker.join(timeout=15)

    def update(self, jid, **values):
        with self.lock:
            self.items[jid].update(values)
            path = self.folder / f'{jid}.json'
            tmp = path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.items[jid],ensure_ascii=False),encoding='utf-8')
            os.replace(tmp,path)

    def list(self):
        with self.lock:
            return [dict(j) for j in sorted(self.items.values(),key=lambda x:x['created'],reverse=True)]

    def submit(self, aid, settings, start=0, duration=None):
        asset = self.asset(aid)
        jid = uuid.uuid4().hex
        with self.lock:
            self.items[jid] = dict(id=jid,asset_id=aid,name=asset['name'],status='queued',progress=0,
                                  created=time.time(),settings=settings.model_dump(),clip_start=start,
                                  clip_duration=duration,error=None,warning=None)
            self.update(jid)
        self.queue.put(jid)
        return dict(self.items[jid])

    def check(self,jid):
        if self.stopping.is_set() or self.items[jid]['status']=='cancelling':
            raise Cancelled()

    def loop(self):
        while not self.stopping.is_set():
            jid = self.queue.get()
            if jid is None:
                break
            try:
                self.check(jid)
                self.update(jid,status='running')
                self.process(jid)
                self.check(jid)
                self.update(jid,status='done',progress=100)
            except Cancelled:
                self.update(jid,status='cancelled')
            except Exception as exc:
                self.update(jid,status='failed',error=str(exc)[-3000:])
            finally:
                for path in self.folder.glob(f'{jid}.partial.*'):
                    path.unlink(missing_ok=True)
                if self.items[jid]['status'] != 'done':
                    for ext in ('.mp4','.png'):
                        (self.folder / (jid+ext)).unlink(missing_ok=True)
                self.queue.task_done()

    def process(self,jid):
        job = self.items[jid]
        settings = Settings(**job['settings'])
        asset = self.asset(job['asset_id'])
        path = self.root / 'assets' / asset['file']
        template = None
        if settings.template_id:
            template_meta = self.asset(settings.template_id)
            template = read_image(self.root/'assets'/template_meta['file'])
        start = job['clip_start'] if asset['kind']=='video' else 0
        first = frame_at(path,asset,start)
        fixed = detect(first,template,settings) if template is not None else []
        matched_frames = 0
        total_frames = 0
        any_pixels = False
        def apply(frame,t):
            nonlocal matched_frames,total_frames,any_pixels
            self.check(jid)
            boxes = detect(frame,template,settings) if template is not None and settings.moving else fixed
            total_frames += 1
            matched_frames += bool(boxes)
            mask = make_mask(frame,settings,t,template,boxes)
            any_pixels |= bool(mask.any())
            return restore(frame,mask,settings)
        if asset['kind']=='image':
            out = apply(first,0)
            if not any_pixels:
                raise ValueError('Không tìm thấy vùng cần xóa. Hãy chỉnh mẫu/độ nhạy hoặc khoanh vùng thủ công.')
            target = self.folder / f'{jid}.png'
            target.write_bytes(cv2.imencode('.png',out)[1].tobytes())
        else:
            duration = min(job['clip_duration'] or asset['duration'],asset['duration']-start)
            if duration <= 0:
                raise ValueError('Thời điểm bắt đầu nằm ngoài video')
            target = self.folder/f'{jid}.mp4'
            self.video(jid,path,asset,settings,start,duration,apply,target)
            if not any_pixels:
                raise ValueError('Không có vùng nào được xử lý. Hãy kiểm tra mẫu hoặc thời gian của vùng chọn.')
        warning = None
        if template is not None and matched_frames < total_frames:
            warning = f'Không tìm thấy mẫu ở {total_frames-matched_frames}/{total_frames} khung hình. Những khung này chỉ áp dụng vùng chọn thủ công (nếu có).'
        self.update(jid,output=target.name,warning=warning)

    def video(self,jid,path,meta,settings,start,duration,apply,target):
        require_ffmpeg()
        w,h,fps = meta['width'],meta['height'],meta['fps']
        partial = self.folder/f'{jid}.partial.mp4'
        logpath = self.folder/f'{jid}.partial.log'
        decoder = encoder = None
        with logpath.open('wb+') as log:
            try:
                decoder = subprocess.Popen(['ffmpeg','-v','error','-ss',str(start),'-i',str(path),
                    '-t',str(duration),'-an','-vf',f'fps={fps},scale={w}:{h}',
                    '-pix_fmt','bgr24','-f','rawvideo','-threads','1','pipe:1'],stdout=subprocess.PIPE,stderr=log)
                quality = ['-crf',str(settings.crf),'-preset','fast'] if settings.encoder=='libx264' else (
                    ['-cq',str(settings.crf),'-preset','p4'] if settings.encoder=='h264_nvenc' else
                    ['-global_quality',str(settings.crf)] if settings.encoder=='h264_qsv' else
                    ['-qp_i',str(settings.crf),'-qp_p',str(settings.crf)])
                encoder = subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','bgr24',
                    '-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-ss',str(start),'-i',str(path),
                    '-map','0:v:0','-map','1:a:0?','-t',str(duration),'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2',
                    '-c:v',settings.encoder,*quality,'-pix_fmt','yuv420p','-c:a','aac','-b:a','192k',
                    '-movflags','+faststart','-map_metadata','-1','-threads','2',str(partial)],stdin=subprocess.PIPE,stderr=log)
                size = w*h*3
                count = 0
                import numpy as np
                while True:
                    self.check(jid)
                    raw = bytearray()
                    while len(raw)<size:
                        chunk = decoder.stdout.read(size-len(raw))
                        if not chunk:
                            break
                        raw.extend(chunk)
                    if not raw:
                        break
                    if len(raw)!=size:
                        raise ValueError('Khung hình không đầy đủ; không xuất video bị thiếu dữ liệu')
                    frame = np.frombuffer(raw,np.uint8).reshape(h,w,3)
                    processed = apply(frame,start+count/fps)
                    encoder.stdin.write(bgr(processed).tobytes())
                    count += 1
                    if count % max(1,round(fps/2))==0:
                        self.update(jid,progress=min(99,round(count/(duration*fps)*100,1)))
                encoder.stdin.close()
                decoder.wait(timeout=30)
                encoder.wait(timeout=60)
                if decoder.returncode or encoder.returncode or count==0:
                    raise ValueError('FFmpeg không hoàn thành')
                # Reject unexpected early EOF; allow one frame for fractional durations.
                if count < max(1,int(duration*fps)-2):
                    raise ValueError('Video kết thúc sớm hơn thời lượng dự kiến')
                os.replace(partial,target)
            except Cancelled:
                raise
            except Exception as exc:
                log.flush()
                detail = logpath.read_text(errors='replace')[-1800:]
                raise ValueError(f'{exc}\n{detail}\nNếu chọn GPU: kiểm tra driver hoặc chọn CPU (libx264).') from exc
            finally:
                for process in (decoder,encoder):
                    if process is not None:
                        if process.poll() is None:
                            process.kill()
                        process.wait()
                        for stream in (process.stdin,process.stdout):
                            if stream:
                                try:
                                    stream.close()
                                except OSError:
                                    pass
