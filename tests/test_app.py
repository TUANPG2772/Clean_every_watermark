import importlib
import json
import os
import shutil
import subprocess
import time
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.engine import detect, make_mask, restore
from app.models import Settings

@pytest.fixture(scope='module')
def client(tmp_path_factory):
    os.environ['CLEAN_LOCAL_DATA']=str(tmp_path_factory.mktemp('store'))
    main=importlib.import_module('app.main')
    with TestClient(main.app) as test:
        yield test

def sample():
    image=np.full((120,200,3),75,np.uint8)
    cv2.putText(image,'TEST',(115,100),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),2)
    return image

def upload(client,image=None):
    data=cv2.imencode('.png',sample() if image is None else image)[1].tobytes()
    response=client.post('/api/assets',files={'file':('demo.png',data,'image/png')})
    assert response.status_code==200,response.text
    return response.json()

def wait_job(client,jid,timeout=30):
    start=time.time()
    while time.time()-start<timeout:
        job=next(j for j in client.get('/api/jobs').json() if j['id']==jid)
        if job['status'] not in ('queued','running','cancelling'):
            return job
        time.sleep(.05)
    pytest.fail('job timed out')

REGION={'x':.55,'y':.68,'w':.38,'h':.2}

def test_inpainting_improves_background_and_preserves_outside():
    image=sample(); s=Settings(regions=[REGION],expand=2)
    mask=make_mask(image,s); out=restore(image,mask,s)
    assert np.mean(np.abs(out.astype(float)-75)) < np.mean(np.abs(image.astype(float)-75))*.2
    assert np.array_equal(out[mask==0],image[mask==0])

def test_multiscale_detection_and_search_region():
    image=sample(); template=image[78:108,108:190]
    s=Settings(threshold=.5,scale_min=.8,scale_max=1.2,max_matches=1)
    boxes=detect(image,template,s)
    assert boxes and abs(boxes[0]['x']-108)<4 and abs(boxes[0]['y']-78)<4
    restricted=Settings(threshold=.8,search={'x':0,'y':0,'w':.4,'h':.5})
    assert not detect(image,template,restricted)

def test_alpha_mask_and_time_windows():
    frame=np.zeros((100,100,3),np.uint8); template=np.zeros((20,20,4),np.uint8)
    template[5:15,5:15,3]=255
    s=Settings(expand=0,regions=[{'x':0,'y':0,'w':.1,'h':.1,'start':1,'end':2}])
    mask=make_mask(frame,s,0,template,[dict(x=40,y=40,w=20,h=20)])
    assert mask[46,46]==255 and mask[41,41]==0 and mask[1,1]==0
    assert make_mask(frame,s,1.5)[1,1]==255
    assert make_mask(frame,s,2)[1,1]==0

def test_preview_presets_and_image_export(client):
    a=upload(client); s={'regions':[REGION]}
    response=client.post('/api/preview',json={'asset_id':a['id'],'settings':s})
    assert response.status_code==200,response.text
    assert response.json()['coverage']>0
    preset=client.post('/api/presets',json={'name':'Test','settings':s}).json()
    assert any(p['id']==preset['id'] for p in client.get('/api/presets').json())
    job=client.post('/api/jobs',json={'asset_ids':[a['id']],'settings':s}).json()[0]
    done=wait_job(client,job['id']); assert done['status']=='done',done
    data=client.get(f"/api/jobs/{job['id']}/output").content
    out=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    assert out.shape==(120,200,3)
    assert client.delete(f"/api/presets/{preset['id']}").status_code==200

def test_crop_and_detect(client):
    a=upload(client)
    cropped=client.post('/api/templates/crop',json={'asset_id':a['id'],'region':{'x':.54,'y':.65,'w':.41,'h':.25}})
    assert cropped.status_code==200,cropped.text
    response=client.post('/api/detect',json={'asset_id':a['id'],'settings':{'template_id':cropped.json()['id'],'threshold':.5,'max_matches':1}})
    assert response.status_code==200,response.text
    assert response.json()['boxes']

def test_validation_and_local_security(client):
    assert client.post('/api/jobs',json={'asset_ids':['bad'],'settings':{}}).status_code==400
    assert client.post('/api/presets',json={'name':'bad','settings':{'regions':[{'x':.9,'y':0,'w':.5,'h':.2}]}}).status_code==422
    assert client.post('/api/assets',files={'file':('malware.exe',b'abc')}).status_code==400
    assert client.post('/api/assets',headers={'Origin':'https://evil.test'},files={'file':('x.png',b'abc')}).status_code==403
    assert client.get('/',headers={'Host':'evil.test'}).status_code==400
    assert client.get('/api/assets/not-an-id/frame').status_code==404

def test_no_match_reports_failure(client):
    a=upload(client,np.full((120,200,3),75,np.uint8)); template=upload(client,sample()[78:108,108:190])
    job=client.post('/api/jobs',json={'asset_ids':[a['id']],'settings':{'template_id':template['id'],'threshold':.9}}).json()[0]
    assert wait_job(client,job['id'])['status']=='failed'
    assert client.get(f"/api/jobs/{job['id']}/output").status_code==404

@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='FFmpeg not installed')
def test_video_audio_duration_and_clip(client,tmp_path):
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=gray:s=200x120:r=12:d=2.25',
                    '-f','lavfi','-i','sine=frequency=440:duration=2.25','-vf','drawbox=x=140:y=80:w=30:h=20:color=white:t=fill',
                    '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    a=client.post('/api/assets',files={'file':('source.mp4',source.read_bytes(),'video/mp4')}).json()
    assert a['audio'] and a['duration']>2
    for clip in (False,True):
        request={'asset_ids':[a['id']],'settings':{'regions':[{'x':.68,'y':.63,'w':.2,'h':.25}]}}
        if clip: request.update(clip_start=.5,clip_duration=1)
        job=client.post('/api/jobs',json=request).json()[0]
        done=wait_job(client,job['id']); assert done['status']=='done',done
        out=tmp_path/f'out-{clip}.mp4'; out.write_bytes(client.get(f"/api/jobs/{job['id']}/output").content)
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(out)]))
        assert any(s['codec_type']=='audio' for s in info['streams'])
        assert abs(float(info['format']['duration'])-(1 if clip else 2.25))<.15
        cap=cv2.VideoCapture(str(out));ok,frame=cap.read();cap.release()
        assert ok and frame[90,150].mean()<180

def test_cancel_queued(client):
    from app.main import manager
    a=upload(client)
    with manager.lock:
        job=manager.submit(a['id'],Settings(regions=[REGION]))
        manager.update(job['id'],status='cancelling')
    assert wait_job(client,job['id'])['status']=='cancelled'

def test_alpha_image_preserved(client):
    image=np.dstack((sample(),np.full((120,200),128,np.uint8))); a=upload(client,image)
    job=client.post('/api/jobs',json={'asset_ids':[a['id']],'settings':{'regions':[REGION]}}).json()[0]
    assert wait_job(client,job['id'])['status']=='done'
    data=client.get(f"/api/jobs/{job['id']}/output").content
    out=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_UNCHANGED)
    assert out.shape[2]==4 and np.all(out[:,:,3]==128)
