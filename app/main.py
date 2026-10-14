import base64
import json
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
import cv2
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .engine import read_image, detect, make_mask, restore, rect_pixels
from .media import inspect, frame_at, encoders, IMAGE_EXT, VIDEO_EXT
from .models import Settings, PreviewRequest, JobRequest, CropRequest, PresetRequest
from .jobs import JobManager

ROOT = Path(os.environ.get('CLEAN_LOCAL_DATA',Path(__file__).resolve().parent.parent/'data')).resolve()
MAX_UPLOAD = int(os.environ.get('CLEAN_LOCAL_MAX_UPLOAD_MB','4096')) * 1024 * 1024
for name in ('assets','presets','jobs'):
    (ROOT/name).mkdir(parents=True,exist_ok=True)
STATIC = Path(__file__).parent/'static'

def valid_id(value):
    if not re.fullmatch(r'[a-f0-9]{32}',value):
        raise HTTPException(404,'Không tìm thấy mục này')
    return value

def asset(aid):
    path = ROOT/'assets'/f'{valid_id(aid)}.json'
    if not path.exists():
        raise HTTPException(404,'Không tìm thấy file')
    return json.loads(path.read_text('utf-8'))

def asset_path(meta):
    return ROOT/'assets'/meta['file']

def store_meta(aid,path,name,meta):
    meta.update(id=aid,file=path.name,name=name)
    (ROOT/'assets'/f'{aid}.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8')
    return meta

manager = JobManager(ROOT,asset)

@asynccontextmanager
async def lifespan(app):
    manager.start()
    yield
    manager.stop()

app = FastAPI(title='Clean Local',lifespan=lifespan,docs_url=None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','[::1]','testserver'])

@app.middleware('http')
async def local_only(request: Request,call_next):
    if request.url.path == '/api/assets' and request.method == 'POST':
        length = request.headers.get('content-length', '')
        if length.isdigit() and int(length) > MAX_UPLOAD + 1024*1024:
            return JSONResponse({'detail':'File vượt giới hạn tải lên'},status_code=413)
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
        return JSONResponse({'detail':'Chỉ chấp nhận yêu cầu cùng nguồn local'},status_code=403)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return JSONResponse({'detail':'Không chấp nhận yêu cầu từ website khác'},status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response

@app.exception_handler(ValueError)
async def value_error(request,exc):
    return JSONResponse({'detail':str(exc)},status_code=400)

@app.get('/api/health')
def health():
    return dict(ffmpeg=bool(shutil.which('ffmpeg') and shutil.which('ffprobe')),
                encoders=encoders(),engine='OpenCV CPU',data_dir=str(ROOT),max_upload_mb=MAX_UPLOAD//1024//1024)

@app.post('/api/assets')
async def upload(file: UploadFile=File(...)):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in IMAGE_EXT|VIDEO_EXT:
        raise HTTPException(400,'Hỗ trợ PNG, JPG, WEBP, BMP, MP4, MOV, MKV, WEBM, AVI, M4V')
    aid = uuid.uuid4().hex
    path = ROOT/'assets'/f'{aid}{suffix}'
    total = 0
    try:
        with path.open('wb') as out:
            while chunk := await file.read(1024*1024):
                total += len(chunk)
                if total > MAX_UPLOAD:
                    raise HTTPException(413,'File vượt giới hạn tải lên')
                out.write(chunk)
        path,meta = await run_in_threadpool(inspect,path)
        return store_meta(aid,path,Path(file.filename).name,meta)
    except Exception as exc:
        for p in (ROOT/'assets').glob(f'{aid}.*'):
            p.unlink(missing_ok=True)
        if isinstance(exc, HTTPException):
            raise
        raise ValueError(f'Không nhập được file: {exc}') from exc
    finally:
        await file.close()

@app.get('/api/assets')
def list_assets():
    return [json.loads(p.read_text('utf-8')) for p in sorted((ROOT/'assets').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)]

@app.get('/api/assets/{aid}/frame')
def frame(aid: str,time: float=0):
    if time<0:
        raise HTTPException(400,'Thời điểm không hợp lệ')
    meta = asset(aid)
    image = frame_at(asset_path(meta),meta,time)
    return Response(cv2.imencode('.png',image)[1].tobytes(),media_type='image/png')

@app.delete('/api/assets/{aid}')
def delete_asset(aid: str):
    meta = asset(aid)
    if any(j['status'] in ('running','queued','cancelling') and (j['asset_id']==aid or j['settings'].get('template_id')==aid) for j in manager.list()):
        raise HTTPException(409,'File đang được sử dụng bởi hàng đợi')
    for preset in list_presets():
        if preset['settings'].get('template_id')==aid:
            raise HTTPException(409,'Mẫu đang được một cấu hình sử dụng. Xóa cấu hình trước.')
    asset_path(meta).unlink(missing_ok=True)
    (ROOT/'assets'/f'{aid}.json').unlink()
    return {'ok':True}

def validate_settings(settings: Settings):
    if not settings.regions and not settings.strokes and not settings.template_id:
        raise ValueError('Hãy khoanh/tô vùng hoặc chọn mẫu watermark')
    if settings.template_id:
        meta = asset(settings.template_id)
        if meta['kind']!='image':
            raise ValueError('Mẫu watermark phải là ảnh')
        if meta['width']*meta['height']>4_000_000:
            raise ValueError('Mẫu quá lớn; hãy cắt sát logo (tối đa 4 megapixel)')

def template_for(settings):
    return read_image(asset_path(asset(settings.template_id))) if settings.template_id else None

@app.post('/api/preview')
def preview(req: PreviewRequest):
    validate_settings(req.settings)
    meta = asset(req.asset_id)
    image = frame_at(asset_path(meta),meta,req.time)
    template = template_for(req.settings)
    boxes = detect(image,template,req.settings) if template is not None else []
    mask = make_mask(image,req.settings,req.time,template,boxes)
    if not mask.any():
        raise ValueError('Không tìm thấy vùng cần xóa ở khung hình này. Giảm ngưỡng tìm hoặc khoanh vùng thủ công.')
    result = restore(image,mask,req.settings)
    encode = lambda img: 'data:image/png;base64,'+base64.b64encode(cv2.imencode('.png',img)[1]).decode()
    return dict(image=encode(result),mask=encode(mask),boxes=boxes,
                coverage=round(float((mask>0).mean())*100,2))

@app.post('/api/detect')
def find_template(req: PreviewRequest):
    if not req.settings.template_id:
        raise ValueError('Chưa chọn mẫu watermark')
    validate_settings(req.settings)
    meta = asset(req.asset_id)
    image = frame_at(asset_path(meta),meta,req.time)
    return {'boxes':detect(image,template_for(req.settings),req.settings)}

@app.post('/api/templates/crop')
def crop(req: CropRequest):
    meta = asset(req.asset_id)
    image = frame_at(asset_path(meta),meta,req.time)
    x,y,w,h = rect_pixels(req.region,image.shape[1],image.shape[0])
    if min(w,h)<4 or w*h>4_000_000:
        raise ValueError('Vùng mẫu cần ít nhất 4×4 pixel và tối đa 4 megapixel')
    aid = uuid.uuid4().hex
    path = ROOT/'assets'/f'{aid}.png'
    path.write_bytes(cv2.imencode('.png',image[y:y+h,x:x+w])[1].tobytes())
    return store_meta(aid,path,'Mẫu cắt — '+meta['name'],dict(kind='image',width=w,height=h,duration=0,fps=0,template=True))

@app.post('/api/jobs')
def create_jobs(req: JobRequest):
    validate_settings(req.settings)
    for aid in req.asset_ids:
        meta = asset(aid)
        if meta['kind']=='video' and req.clip_start>=meta['duration']:
            raise ValueError('Thời điểm bắt đầu nằm ngoài video: '+meta['name'])
    return [manager.submit(aid,req.settings,req.clip_start,req.clip_duration) for aid in req.asset_ids]

@app.get('/api/jobs')
def jobs():
    return manager.list()

@app.post('/api/jobs/{jid}/cancel')
def cancel(jid: str):
    valid_id(jid)
    with manager.lock:
        if jid not in manager.items:
            raise HTTPException(404,'Không tìm thấy tác vụ')
        if manager.items[jid]['status'] in ('queued','running'):
            manager.update(jid,status='cancelling')
    return {'ok':True}

@app.get('/api/jobs/{jid}/output')
def output(jid: str):
    valid_id(jid)
    job = manager.items.get(jid)
    if not job or job['status']!='done':
        raise HTTPException(404,'Chưa có kết quả')
    path = manager.folder/job['output']
    if not path.exists():
        raise HTTPException(404,'Kết quả không còn trên ổ đĩa')
    return FileResponse(path,filename=Path(job['name']).stem+'_cleaned'+path.suffix)

@app.delete('/api/jobs/{jid}')
def delete_job(jid: str):
    valid_id(jid)
    with manager.lock:
        job = manager.items.get(jid)
        if not job:
            raise HTTPException(404,'Không tìm thấy tác vụ')
        if job['status'] in ('running','queued','cancelling'):
            raise HTTPException(409,'Hủy tác vụ và đợi dừng trước khi xóa')
        for path in manager.folder.glob(f'{jid}.*'):
            path.unlink(missing_ok=True)
        del manager.items[jid]
    return {'ok':True}

@app.get('/api/presets')
def list_presets():
    return [json.loads(p.read_text('utf-8')) for p in (ROOT/'presets').glob('*.json')]

@app.post('/api/presets')
def save_preset(req: PresetRequest):
    validate_settings(req.settings)
    pid = uuid.uuid4().hex
    data = dict(id=pid,**req.model_dump())
    (ROOT/'presets'/f'{pid}.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    return data

@app.delete('/api/presets/{pid}')
def delete_preset(pid: str):
    (ROOT/'presets'/f'{valid_id(pid)}.json').unlink(missing_ok=True)
    return {'ok':True}

app.mount('/static',StaticFiles(directory=STATIC),name='static')

@app.get('/')
def index():
    return FileResponse(STATIC/'index.html')
