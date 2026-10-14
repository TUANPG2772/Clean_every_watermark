# Verification — v1.0

Kiểm tra trong môi trường Linux, Python 3.12, OpenCV 4.14, FFmpeg và Chromium headless.

## Đã chạy thành công

- `python -m pytest -q`: **10 passed**.
- `node --check app/static/app.js`: hợp lệ.
- `python -m compileall -q app run.py`: hợp lệ.
- Browser smoke test: upload ảnh, kéo vùng trên canvas, preview, cắt mẫu, tìm mẫu, lưu preset, tạo job, tải PNG kết quả.
- Chromium không ghi nhận lỗi JavaScript trong luồng trên.
- Viewport 390 px: không tràn ngang.
- Kiểm tra hình chụp giao diện desktop và trạng thái xử lý.
- Test video tổng hợp xác nhận có âm thanh đầu ra, thời lượng 2.25 giây, clip thử 1 giây và vùng watermark được xử lý.
- Test ảnh kiểm tra vùng bên ngoài mask không bị sửa và alpha được giữ.

## Chưa kiểm chứng trực tiếp

- Chạy launcher trên Windows/macOS thật.
- GPU NVIDIA/Intel/AMD và driver tương ứng.
- Chất lượng trên logo/video thực tế của người dùng: chưa được cung cấp mẫu ảnh/video để benchmark.
- Video HDR, VFR phức tạp, video dài nhiều giờ: ngoài phạm vi bảo đảm chất lượng của v1.

Kết quả trên dữ liệu tổng hợp xác minh luồng và tính đúng kỹ thuật, không chứng minh công cụ xóa sạch mọi watermark. Hãy dùng preview và clip thử trước khi xử lý batch.
