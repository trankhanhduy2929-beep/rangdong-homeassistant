# Ứng dụng Home Assistant: Rạng Đông Key Helper

Nhập các giá trị `local_key` tương thích Tuya từ ứng dụng Rạng Đông chính
thức trên điện thoại Android đã root do bạn sở hữu và kiểm soát. Trang Ingress
chỉ dành cho quản trị viên có thể ghép đôi Wireless ADB, đăng nhập thông qua SDK
trong ứng dụng gốc, dò thiết bị và gửi key đã kiểm tra đến tích hợp Rạng Đông
Smart mà không cần tạo Tuya IoT Cloud project.

![Hỗ trợ kiến trúc aarch64][aarch64-shield]
![Hỗ trợ kiến trúc amd64][amd64-shield]

Điện thoại bắt buộc phải được root vì APK Rạng Đông không bật chế độ gỡ lỗi và
vô hiệu hóa Android backup. Xem [hướng dẫn sử dụng](DOCS.md) để biết cách ghép
đôi, đăng nhập và nhập dữ liệu.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
