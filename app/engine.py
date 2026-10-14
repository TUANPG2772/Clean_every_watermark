"""CPU inpainting and multiscale, edge-based template matching. No remote calls."""
import cv2
import numpy as np
from .models import Settings

cv2.setNumThreads(2)

def read_image(path):
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError('Không đọc được ảnh')
    if image.dtype != np.uint8:
        raise ValueError('Chỉ hỗ trợ ảnh 8-bit; hãy chuyển ảnh HDR/16-bit sang PNG 8-bit')
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image

def bgr(image):
    return image[:, :, :3].copy()

def edges(image):
    gray = cv2.cvtColor(bgr(image), cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    return cv2.magnitude(gx, gy)

def rect_pixels(r, width, height):
    x, y = int(r.x * width), int(r.y * height)
    return x, y, max(1, min(width-x, round(r.w * width))), max(1, min(height-y, round(r.h * height)))

def detect(frame, template, settings: Settings):
    """Return pixel boxes. Work at <=1280px, then map coordinates back."""
    height, width = frame.shape[:2]
    x0, y0, rw, rh = (0, 0, width, height)
    if settings.search:
        x0, y0, rw, rh = rect_pixels(settings.search, width, height)
    ratio = min(1., 1280 / max(rw, rh))
    scene = cv2.resize(frame[y0:y0+rh, x0:x0+rw], None, fx=ratio, fy=ratio)
    scene_edge = edges(scene)
    if template.shape[2] == 4 and np.ptp(template[:, :, 3]) > 0:
        # Alpha outline is stable against varying background and logo color.
        alpha = template[:, :, 3]
        feature_image = cv2.cvtColor(alpha, cv2.COLOR_GRAY2BGR)
    else:
        feature_image = bgr(template)
    candidates = []
    for scale in np.linspace(settings.scale_min, settings.scale_max, 13):
        tw = round(template.shape[1] * scale * ratio)
        th = round(template.shape[0] * scale * ratio)
        if min(tw, th) < 4 or tw > scene.shape[1] or th > scene.shape[0]:
            continue
        feature = edges(cv2.resize(feature_image, (tw, th)))
        if feature.std() < .01:
            continue
        scores = cv2.matchTemplate(scene_edge, feature, cv2.TM_CCOEFF_NORMED)
        scores = np.nan_to_num(scores, nan=-1., posinf=-1., neginf=-1.)
        for _ in range(settings.max_matches):
            _, score, _, (x, y) = cv2.minMaxLoc(scores)
            if score < settings.threshold:
                break
            candidates.append(dict(x=round(x/ratio)+x0, y=round(y/ratio)+y0,
                                   w=round(tw/ratio), h=round(th/ratio), score=round(score, 4)))
            scores[max(0,y-th//2):y+th//2+1, max(0,x-tw//2):x+tw//2+1] = -1
    boxes = []
    for box in sorted(candidates, key=lambda b: -b['score']):
        duplicate = False
        for old in boxes:
            iw = max(0, min(box['x']+box['w'], old['x']+old['w'])-max(box['x'],old['x']))
            ih = max(0, min(box['y']+box['h'], old['y']+old['h'])-max(box['y'],old['y']))
            if iw*ih / max(1,min(box['w']*box['h'],old['w']*old['h'])) > .3:
                duplicate = True
        if not duplicate:
            boxes.append(box)
        if len(boxes) >= settings.max_matches:
            break
    return boxes

def active(item, time):
    return time >= item.start and (item.end is None or time < item.end)

def make_mask(frame, settings, time=0, template=None, boxes=None):
    h, w = frame.shape[:2]
    mask = np.zeros((h,w), np.uint8)
    for r in settings.regions:
        if active(r,time):
            x,y,rw,rh = rect_pixels(r,w,h)
            mask[y:y+rh,x:x+rw] = 255
    for stroke in settings.strokes:
        if not active(stroke,time):
            continue
        pts = [(min(w-1,round(p.x*w)), min(h-1,round(p.y*h))) for p in stroke.points]
        thickness = max(1,round(stroke.width*min(w,h)))
        for p in pts:
            cv2.circle(mask,p,max(1,thickness//2),255,-1)
        for a,b in zip(pts,pts[1:]):
            cv2.line(mask,a,b,255,thickness)
    for box in boxes or []:
        x,y = max(0,box['x']),max(0,box['y'])
        tw,th = box['w'],box['h']
        rw,rh = min(tw,w-x),min(th,h-y)
        if rw <= 0 or rh <= 0:
            continue
        if template is not None and template.shape[2] == 4:
            alpha = cv2.resize(template[:,:,3], (tw,th))
            patch = np.where(alpha[:rh,:rw] > 8,255,0).astype(np.uint8)
        else:
            patch = np.full((rh,rw),255,np.uint8)
        mask[y:y+rh,x:x+rw] = cv2.bitwise_or(mask[y:y+rh,x:x+rw],patch)
    if settings.expand:
        size = settings.expand*2+1
        mask = cv2.dilate(mask,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(size,size)))
    return mask

def restore(frame, mask, settings):
    if not np.any(mask):
        return frame.copy()
    method = cv2.INPAINT_TELEA if settings.method == 'telea' else cv2.INPAINT_NS
    out = cv2.inpaint(bgr(frame), mask, settings.radius, method)
    if frame.shape[2] == 4:
        out = np.dstack((out,frame[:,:,3]))
    return out
