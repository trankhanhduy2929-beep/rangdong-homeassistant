# Rạng Đông Smart cho Home Assistant

Custom integration điều khiển thiết bị Rạng Đông Smart tương thích Tuya trong
Home Assistant. Bản này ưu tiên kết nối **LAN nội bộ**, không cần Android root,
ADB, Frida, import APK hoặc Tuya IoT Cloud project.

## Cài qua HACS

1. Mở **HACS → Integrations**.
2. Tìm `Rạng Đông Smart` hoặc thêm repository này bằng **Custom repositories**.
3. Chọn loại **Integration**, cài đặt và restart Home Assistant.
4. Vào **Settings → Devices & services → Add integration**.
5. Chọn **Rạng Đông Smart**.
6. Nhập License Key nếu được yêu cầu.
7. Nhập tên thiết bị, Device ID, địa chỉ IP, local key và phiên bản giao thức.

## License

Khi được yêu cầu, mở website license từ màn hình cấu hình. Tạo tài khoản bằng
email + mật khẩu, nhận trial 1 ngày hoặc mua gói 1 tháng/vĩnh viễn rồi nhập key.

Một key dùng cho một custom integration và một add-on trên cùng Home Assistant.
Trial chỉ nhận một lần cho mỗi tài khoản và installation; đổi email không tạo thêm
lượt dùng thử trên cùng Home Assistant.

## Cấu hình thiết bị

- **LAN nội bộ:** nhập thủ công Device ID, địa chỉ IP và local key.
- Có thể lấy các thông tin này từ add-on Key Helper rồi nhập vào custom integration.
- Sau khi thêm thiết bị, đổi tên và khu vực trong Home Assistant như bình thường.
- Đảm bảo Home Assistant và thiết bị cùng mạng LAN, không bị client isolation.

## Điều khiển

Integration hỗ trợ các entity và dịch vụ tương thích với thiết bị Rạng Đông đã
được nhận diện. Tính năng thực tế phụ thuộc model, firmware và chức năng thiết bị.

## Xử lý lỗi

- **Không tìm thấy thiết bị:** kiểm tra IP, VLAN, firewall và mạng LAN.
- **Sai local key:** lấy lại key từ Key Helper, kiểm tra đúng Device ID.
- **License lỗi:** kiểm tra key trên website và installation Home Assistant.
- Không cần quét QR hoặc đăng nhập cloud trong custom integration.

Không nhập mật khẩu tài khoản Rạng Đông vào website license. Không chia sẻ local
key hoặc License Key.
