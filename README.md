# Clean Local · Watermark Studio

Ứng dụng web **chạy trên chính máy tính của bạn** để chọn, tìm theo mẫu và lấp vùng watermark trong ảnh/video. Giao diện tiếng Việt, không tài khoản, không API cloud. Mở trình duyệt tại `http://127.0.0.1:8765` sau khi chạy ứng dụng.

> Tên repo là `Clean_every_watermark`, nhưng công cụ **không thể xóa sạch mọi watermark**. Bản v1 dùng inpainting cổ điển OpenCV, phù hợp logo nhỏ trên nền tương đối đơn giản. Không có mô hình AI tạo sinh hoặc bảo đảm tái tạo đúng nội dung bị che. Chỉ dùng với nội dung bạn sở hữu hoặc được phép chỉnh sửa.

## Chạy nhanh trên Windows

1. Tải repo: **Code → Download ZIP**, giải nén vào một thư mục có quyền ghi (ví dụ `D:\CleanLocal`).
2. Cài [Python 3.11 trở lên](https://www.python.org/downloads/), bản 64-bit. Khi cài, chọn **Add Python to PATH**. Python 3.12 được dùng để kiểm thử dự án.
3. Để xử lý video, cài [FFmpeg](https://ffmpeg.org/download.html). Trong trang tải FFmpeg, chọn Windows build; giải nén và thêm thư mục `bin` (chứa `ffmpeg.exe`, `ffprobe.exe`) vào biến môi trường `Path`. Mở terminal mới, kiểm tra:

   ```bat
   ffmpeg -version
   ffprobe -version
   ```

4. Bấm đúp **`start.bat`**. Lần đầu cần Internet để tải thư viện Python. Các lần sau chạy local; thư viện, video và ảnh không được gửi tới dịch vụ ngoài.
5. Trình duyệt tự mở. Giữ cửa sổ terminal hoạt động; nhấn `Ctrl+C` để dừng.

Nếu chưa cài FFmpeg, phần xử lý ảnh vẫn dùng được. Khi gặp lỗi, cửa sổ BAT giữ lại thông báo để kiểm tra.

### macOS / Linux

Cài Python 3.11+ và FFmpeg bằng trình quản lý gói của hệ điều hành, rồi:

```sh
sh start.sh
```

### Cài thủ công / phát triển

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

Đổi cổng: `python run.py --port 8766`. Không tự mở trình duyệt: `python run.py --no-browser`.

Sau khi cập nhật mã nguồn, cập nhật thư viện bằng `.venv\Scripts\python.exe -m pip install -r requirements.txt` trên Windows hoặc `.venv/bin/python -m pip install -r requirements.txt` trên macOS/Linux.

## Quy trình sử dụng

### 1. Khoanh vùng / tô cọ

- Thêm ảnh hoặc video bằng kéo thả hay chọn file.
- Chọn công cụ **Vùng** rồi kéo hình chữ nhật; dùng **Cọ** để tô sát hình dạng chữ/logo.
- Với video, kéo thanh thời gian để chọn khung hình. Mỗi vùng hoặc nét cọ có thời gian **Từ / đến** (đơn vị giây, tính từ đầu video). Để trống kết thúc nghĩa là đến hết file. Các khoảng là `[bắt đầu, kết thúc)`.
- **Mở rộng mask** giúp phủ hết viền/bóng logo. **Bán kính lấp** điều khiển phạm vi lấy thông tin lân cận. Các giá trị này tính bằng pixel nguồn.
- Bấm **Xem thử khung hình**, chuyển giữa Gốc và Sau xử lý.

### 2. Tìm theo mẫu logo

- Tải PNG trong suốt (giữ một ít lề trống quanh nét logo), hoặc khoanh logo trong ảnh rồi bấm **Dùng vùng chữ nhật cuối làm mẫu watermark**.
- Vùng chữ nhật đã dùng để cắt mẫu vẫn được giữ. Xóa vùng đó nếu chỉ muốn xóa theo kết quả tìm mẫu.
- Chọn **Phạm vi tìm** và kéo để giới hạn nơi tìm logo (ví dụ góc dưới phải).
- Bấm **Tìm watermark**, kiểm tra những khung xanh. Đây là các ứng viên theo độ giống đường nét, không phải nhận diện chắc chắn.
- Giảm ngưỡng nếu bỏ sót, tăng ngưỡng nếu nhận nhầm. Tỷ lệ `1.0` là kích thước pixel của mẫu; khoảng mặc định `0.75–1.25`.
- PNG có alpha tạo mask theo độ trong suốt của logo; mẫu ảnh không alpha tạo mask hình chữ nhật.
- Mẫu cố định: tìm tại khung đầu của phần video xuất, dùng vị trí đó cho cả đoạn. Mẫu không có ở khung đầu: hãy khoanh thủ công hoặc bật tìm lại mỗi khung.
- Logo di chuyển: bật **Tìm lại mẫu mỗi khung hình**. Chế độ này tốn CPU và có thể nhấp nháy khi mẫu bị bỏ sót; không phải object tracking hay temporal AI inpainting.
- Nếu mẫu không xuất hiện ở một số khung hình, tác vụ báo cảnh báo. Nếu toàn bộ tác vụ không có pixel nào để xử lý, tác vụ thất bại rõ ràng, không âm thầm đưa file gốc làm kết quả thành công.

### 3. Xuất và xử lý hàng loạt

- **Xuất thử 3 giây** bắt đầu ở vị trí đang xem; nếu gần hết video, xuất phần còn lại.
- Tích các file trong thư viện rồi **Xử lý file đã chọn**. Nếu không tích file nào, xử lý file đang mở.
- Vùng chọn được lưu theo tỷ lệ kích thước ảnh, nhưng kích thước mẫu logo và bán kính lấp vẫn tính theo pixel. Với batch khác độ phân giải, kiểm tra phạm vi scale và preview từng loại.
- Hàng đợi xử lý tuần tự để hạn chế RAM. Có tiến độ, hủy, thông báo lỗi, tải file và xóa kết quả.
- Ảnh xuất PNG 8-bit (giữ alpha); video xuất MP4 H.264 + track âm thanh đầu tiên mã hóa AAC. Video không âm thanh cũng hỗ trợ.
- Video đầu ra dùng FPS cố định theo FPS trung bình đầu vào. Kích thước lẻ được đệm tối đa 1 pixel để mã hóa H.264. Giữ thời lượng trong sai số khung hình; không hứa giữ nguyên mọi timestamp VFR.

### 4. Lưu hồ sơ watermark

Đặt tên và **Lưu** để dùng lại vùng chọn, cọ, phạm vi tìm, mẫu, độ nhạy và phương pháp xử lý. Xuất/nhập JSON để sao lưu cấu hình. JSON chứa ID mẫu local, không nhúng hình logo: chuyển sang máy khác cần tải lại và chọn lại mẫu. Với cấu hình chỉ có mẫu, phải chọn một mẫu trên máy đích trước khi lưu lại cấu hình.

## Phần cứng và giới hạn

| Thành phần | Cách sử dụng phần cứng |
|---|---|
| Tìm mẫu + inpainting | CPU, OpenCV; không cần GPU |
| Giải mã video | FFmpeg, mặc định CPU |
| Mã hóa video | CPU H.264 mặc định; có lựa chọn NVIDIA NVENC, Intel QSV, AMD AMF nếu FFmpeg build có hỗ trợ |
| Bộ nhớ | Đọc/ghi theo khung hình, không nạp toàn bộ video vào RAM |

Danh sách GPU trong giao diện dựa trên **encoder được biên dịch vào FFmpeg**, không chứng minh máy có GPU/driver tương thích. Nếu xuất GPU lỗi, chọn CPU và chạy lại. Mã hóa GPU không tăng tốc phần xóa watermark.

- Nên bắt đầu với CPU 4 nhân, RAM 8 GB và video 1080p ngắn; đây là gợi ý, chưa phải cấu hình được benchmark. 4K hoặc logo di chuyển có thể chậm đáng kể.
- Logo bán trong suốt vẫn được lấp vùng; v1 **chưa** đảo phép alpha blending.
- Chữ thay đổi theo tài khoản, logo xoay, phối cảnh, logo gần như không có tương phản, nền phức tạp: nên dùng khoanh vùng/cọ hoặc chuẩn bị mẫu riêng. Chưa có OCR hay AI nhận diện tổng quát.
- Chưa có AI temporal inpainting, xử lý HDR/10-bit, bảo toàn color profile/metadata, subtitles hoặc nhiều audio tracks. Đầu ra là SDR 8-bit; nên chuyển HDR sang SDR trước để tránh màu sai.
- Giới hạn mặc định: 4 GB/file, 40 megapixel/frame, mẫu 4 megapixel. Không có giới hạn video 8 giây.
- Bộ nhận diện dùng tối đa 13 kích thước, thu nhỏ vùng tìm về cạnh lớn nhất 1280 px, triệt ứng viên trùng nhau. Logo cực nhỏ có thể bị bỏ sót.
- Không tích hợp hay phân phối `GeminiWatermarkTool-Video.exe` từ gói RAR vì chưa có mã nguồn hoặc thông tin giấy phép của phần mềm đó. Dự án này là bộ xử lý độc lập.

## Dữ liệu và vận hành local

Dữ liệu ở `data/` trong thư mục dự án; ảnh/video và kết quả không được đưa lên Git. Có thể đổi nơi lưu bằng biến môi trường `CLEAN_LOCAL_DATA`. Giới hạn tải lên cấu hình qua `CLEAN_LOCAL_MAX_UPLOAD_MB`.

- File nguồn được sao chép vào thư viện local. Ảnh được chuẩn hóa hướng EXIF và chuyển PNG 8-bit để giao diện/mask khớp nhau; file gốc bên ngoài ứng dụng không thay đổi.
- Có thể xóa từng file hoặc kết quả từ UI. File đang chạy và mẫu được cấu hình sử dụng được bảo vệ khỏi xóa.
- Khi tắt ứng dụng, tác vụ đang chạy bị hủy/gián đoạn; **không tự tiếp tục từ khung dở dang**. Tạo lại tác vụ để xử lý từ đầu.
- Có thể xóa toàn bộ `data/` sau khi dừng ứng dụng để dọn sạch media, cấu hình và lịch sử.
- Server chỉ bind `127.0.0.1`, kiểm tra Host/Origin, không bật CORS, không dùng shell để chạy FFmpeg. Không mở cổng ra Internet/LAN; bản này không có cơ chế đăng nhập cho triển khai public.
- Không telemetry, không CDN font/script, không model/API cloud. Trình duyệt gửi file tới server trên chính máy tính của bạn.

## Kiểm thử

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check app/static/app.js
```

Các test tự tạo ảnh/video tổng hợp, kiểm tra tìm mẫu, mask alpha, cửa sổ thời gian, inpainting, upload, preview, preset, hủy, input validation, chặn cross-origin, đầu ra video/âm thanh/thời lượng và xử lý không có match. Test video cần FFmpeg; nếu thiếu sẽ được đánh dấu skip. GitHub Actions cài FFmpeg và chạy bộ test trên Linux.

UI dùng JavaScript thuần, không cần Node/npm để chạy ứng dụng. Node chỉ dùng tùy chọn để kiểm tra cú pháp JS.

## Cấu trúc

```text
app/
  main.py        API local, uploads, preview, presets
  models.py      Validation cấu hình/vùng chọn
  engine.py      Nhận diện mẫu, mask, CPU inpainting
  media.py       Đọc ảnh, FFprobe, trích khung hình
  jobs.py        Hàng đợi, streaming video, hủy/lưu trạng thái
  static/        Giao diện HTML/CSS/JavaScript
run.py           Khởi động loopback + mở trình duyệt
start.bat        Windows launcher
start.sh         macOS/Linux launcher
tests/           Kiểm thử bằng media tổng hợp
```

Mã nguồn dự án theo giấy phép MIT; thư viện phụ thuộc có giấy phép riêng. FFmpeg build và codec có các điều kiện phân phối riêng; dự án không đóng gói binary FFmpeg.
