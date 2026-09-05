# Nhật ký thay đổi

## 0.2.1 - 2026-09-05

- Tích hợp sẵn cặp APK 5.7.2 trong image: mở add-on, nhập tài khoản và lấy key ngay.
- Không còn yêu cầu chọn hoặc tải lên hai APK; lần chạy đầu tự chuẩn bị thư viện.
- Tải tài nguyên lúc build, kiểm tra SHA-256 và giới hạn kích thước.
- Giữ import thủ công trong mục nâng cao; xóa cache không xóa bộ đăng nhập sẵn.

## 0.2.0 - 2026-09-05

- Thêm đăng nhập cloud bằng tài khoản Rạng Đông, không cần Android root hay Tuya IoT project.
- Upload cặp APK 5.7.2 có kiểm tra SHA-256, trích xuất native riêng trong add-on.
- Worker Java/Unidbg một lần, tài khoản qua stdin, không kế thừa Supervisor token.
- Tự lấy local key và Device ID, kiểm tra rồi chuyển vào bridge có xác thực.
- Che key trên giao diện, giới hạn upload/đầu ra/thời gian và nhịp đăng nhập.
- Giữ chế độ Android ADB/Frida làm phương án bổ sung.

## 0.1.0 - 2026-09-04

- Thêm trang Ingress Home Assistant chỉ dành cho quản trị viên.
- Kiểm tra nhóm quản trị viên của người dùng Ingress thông qua WebSocket API
  của Home Assistant.
- Ghép đôi và kết nối Android Wireless debugging qua ADB.
- Tải Frida server phiên bản đã ghim từ bản phát hành chính thức và kiểm tra
  SHA-256.
- Chỉ khởi động Frida thông qua trình quản lý root trong thời gian thao tác
  đang thực hiện.
- Hỗ trợ đăng nhập tạm thời bằng số điện thoại/mật khẩu thông qua SDK trong
  ứng dụng Rạng Đông chính thức.
- Thu thập, kiểm tra và nhập local key vào bridge tích hợp đã xác thực.
- Kích hoạt rồi hủy ngay luồng tích hợp tạm thời nếu bridge chưa được đăng ký.
- Che local key trên giao diện và không ghi thông tin tài khoản hoặc key thô
  vào log.
