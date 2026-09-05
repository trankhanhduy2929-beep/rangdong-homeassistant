# PoC cloud Rạng Đông không cần điện thoại Android

**Chỉ dành cho thử nghiệm phát triển, chưa phải tính năng của add-on/HACS.**

PoC chạy thư viện ARM trong APK chính thức bằng Unidbg trên Linux amd64.
Không đóng gói APK, thư viện độc quyền, app secret hay tài khoản vào repository.
Không cần Android root hoặc Tuya IoT Cloud project để chạy thử giao thức này.

## Kết quả đã xác minh ngày 04/09/2026

- Native signer chạy trên Linux amd64, chữ ký lặp lại ổn định.
- Request token với số giả nhận HTTP 200 và `success=true`.
- Xác minh chữ ký và giải mã AES-GCM của phản hồi cloud thành công.
- Một lần đăng nhập bằng thông tin được chủ tài khoản cung cấp nhận
  `USER_PASSWD_WRONG`. Đã dừng, không tự đổi định dạng số hoặc thử lại mật khẩu.
- **Chưa đăng nhập thành công, chưa xác minh danh sách nhà, thiết bị hoặc local key.**
- Chưa kiểm thử aarch64 hoặc đóng gói vào Home Assistant add-on.

Token trước đăng nhập không phải access token và không chứng minh mật khẩu đúng.
Chi tiết bằng chứng và giới hạn nằm trong `REPORT.md` cùng thư mục.

## Điều kiện

- Linux amd64, JDK và Maven. Môi trường thử nghiệm dùng Java 21, Unidbg 0.9.8.
- Python 3 để chuẩn bị tài nguyên riêng tư.
- Base APK `com.rd.smart` phiên bản đã phân tích 5.7.2 và ABI split armeabi-v7a
  **do bạn có quyền sử dụng**. Không tải APK từ nguồn không rõ nguồn gốc.
- Bản Apktool đã giải mã, có `smali/com/smart/app/SmartApplication.smali`.
- Mạng truy cập được cloud; không tắt kiểm tra TLS để xử lý lỗi mạng.

## Chuẩn bị

Chạy từ thư mục `poc/native-cloud`. Thay các đường dẫn ví dụ bằng đường dẫn của bạn.
Thư mục đầu ra phải chưa tồn tại; công cụ không ghi đè dữ liệu cũ.

```bash
python3 prepare.py \
  --smali /duong-dan/apktool_base/smali/com/smart/app/SmartApplication.smali \
  --abi-apk /duong-dan/config.armeabi_v7a.apk \
  --output ./private

mvn -q compile dependency:build-classpath -Dmdep.outputFile=classpath.txt
```

`private` có quyền 0700; tài nguyên bên trong có quyền 0600. `app-credentials`
chứa định danh/bí mật ứng dụng trích từ APK, **không phải mật khẩu tài khoản**.
Công cụ chỉ nhận bố cục APK đã nghiên cứu; nếu không khớp thì dừng thay vì đoán.
Không gửi hoặc commit thư mục này. Xóa tài nguyên riêng tư khi không dùng nữa.

## Kiểm thử không đăng nhập

Kiểm thử giao thức và công cụ chuẩn bị bằng dữ liệu giả:

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
mvn -q test-compile
java -cp target/classes:target/test-classes local.rangdong.ProtocolTest
```

Kiểm tra native offline, không gửi request cloud:

```bash
java -cp "target/classes:$(cat classpath.txt)" local.rangdong.NativeProbe \
  /duong-dan/com.rd.smart.apk ./private/libs ./private/app-credentials
```

Thêm `--token-probe` vào cuối lệnh để gửi **một** request lấy token với số giả.
Không chạy vòng lặp hoặc dùng để kiểm tra tài khoản người khác.

## Thử đăng nhập có kiểm soát

```bash
java -cp "target/classes:$(cat classpath.txt)" local.rangdong.NativeProbe \
  /duong-dan/com.rd.smart.apk ./private/libs ./private/app-credentials --login-probe
```

Chương trình yêu cầu terminal tương tác, nhập số điện thoại và mật khẩu đều được
ẩn. Không đặt mật khẩu trong lệnh, file cấu hình, issue GitHub hoặc chat.
Không dùng `mvn exec:java` cho bước này vì có thể không có `System.console()`.

PoC chỉ thử một lần đăng nhập theo API tìm thấy trong APK, rồi thử liệt kê nhà nếu
server trả đủ thông tin phiên. Không lưu phiên, không xuất local key, không đổi
mật khẩu hoặc đăng ký tài khoản. Lỗi đăng nhập dừng ngay và trả mã thoát khác 0.

Nếu gặp `USER_PASSWD_WRONG`, kiểm tra đăng nhập trên ứng dụng Rạng Đông chính thức
và đổi mật khẩu nếu cần. Nếu gặp CAPTCHA/MFA hoặc yêu cầu app được chỉ định, hoàn
thành trên app chính thức; PoC không tự xử lý hay bỏ qua các bước này.

## Giới hạn trước khi tích hợp add-on

1. Xác minh đăng nhập hợp lệ và cơ chế vùng cloud/phiên thực tế.
2. Đọc danh sách nhà/thiết bị và xác nhận cloud thực sự trả local key.
3. Làm worker JSON-lines có timeout, giới hạn đầu vào và thông báo lỗi đã che bí mật.
4. Kiểm thử Unidbg/native backend trên kiến trúc Home Assistant cần hỗ trợ.
5. Chỉ sau đó thêm giao diện tải APK, đăng nhập và import key vào bridge hiện có.

Hiện code thử nghiệm dùng endpoint đã xác minh từ APK, chưa tự đổi endpoint sau
đăng nhập. Khi chưa hoàn thành các bước trên, không quảng cáo add-on là đã lấy key
trực tiếp được. Dù lấy được key từ cloud, điều khiển LAN vẫn cần Home Assistant
truy cập được mạng của thiết bị; việc iPhone khác mạng không tạo đường kết nối LAN.
