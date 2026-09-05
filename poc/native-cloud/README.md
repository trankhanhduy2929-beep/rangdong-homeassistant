# PoC cloud Rạng Đông không cần điện thoại Android

**Chỉ dành cho thử nghiệm phát triển, chưa phải tính năng của add-on/HACS.**

PoC chạy thư viện ARM trong APK chính thức bằng Unidbg trên Linux amd64.
Không đóng gói APK, thư viện độc quyền, app secret hay tài khoản vào repository.
Không cần Android root hoặc Tuya IoT Cloud project để chạy thử giao thức này.

## Kết quả mới nhất ngày 05/09/2026

- Chủ tài khoản cung cấp email và mật khẩu Rạng Đông qua file riêng, không qua log.
- Đăng nhập email API `thing.m.user.email.password.login` 3.0 thành công, có `sid`/`ecode`.
- Đọc được danh sách nhà và thiết bị; **lấy được 9 local key hợp lệ 16 byte**.
- File JSON xuất riêng quyền 0600 đã qua bộ kiểm tra dữ liệu của helper hiện có.
- Không cần Android root hoặc Tuya IoT project cho lần thử này.
- **Chưa kiểm thử điều khiển LAN và chưa tích hợp luồng cloud này vào add-on.**

Đây là đăng nhập email + mật khẩu của tài khoản **Rạng Đông**, không phải OAuth
Google và không yêu cầu mật khẩu tài khoản Google. Không công khai email, mật khẩu
hoặc file key. Các lần thử số điện thoại bị từ chối bên dưới là lịch sử, không
phải kết quả của tài khoản email mới.

## Lịch sử thử nghiệm ngày 04/09/2026

- Native signer chạy trên Linux amd64, chữ ký lặp lại ổn định.
- Request token với số giả nhận HTTP 200 và `success=true`.
- Xác minh chữ ký và giải mã AES-GCM của phản hồi cloud thành công.
- Một lần đăng nhập bằng thông tin được chủ tài khoản cung cấp nhận
  `USER_PASSWD_WRONG`. Đã dừng, không tự đổi định dạng số hoặc thử lại mật khẩu.
- **Chưa đăng nhập thành công, chưa xác minh danh sách nhà, thiết bị hoặc local key.**
- Chưa kiểm thử aarch64 hoặc đóng gói vào Home Assistant add-on.

Token trước đăng nhập không phải access token và không chứng minh mật khẩu đúng.
Chi tiết bằng chứng và giới hạn nằm trong `REPORT.md` cùng thư mục.

**Lần đối chiếu số điện thoại ngày 05/09/2026:** chủ tài khoản xác nhận đăng nhập app bình thường. Đối chiếu
nhánh `loginWithPassword` trong APK phát hiện PoC trước đây chọn API 3.0 của SDK,
trong khi nhánh này dùng 4.0 với `mfaCode` trong options. Đã sửa PoC cho khớp;
đã kiểm tra lại có giới hạn: bản 4.0 vẫn nhận `USER_PASSWD_WRONG`, cả với định dạng
số ban đầu và một lần dùng định dạng bỏ số 0 đầu như helper hiện có. Không thử thêm.
Không kết luận mật khẩu người dùng sai; nguyên nhân từ chối xác thực chưa xác định.

Đã truy vết được đường đọc key từ APK và bổ sung `--device-probe`: sau đăng nhập
hợp lệ, gọi home list 7.0, device list 2.2 và local-device list 1.1, rồi đếm key
16 byte. Luồng này sau đó đã chạy thành công với tài khoản email mới, ngoài kiểm
thử bằng dữ liệu giả. Chưa tìm thấy cơ chế lấy key riêng của thiết bị từ APK mà không có phiên
đăng nhập hoặc dữ liệu cache của tài khoản.

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
java -cp "target/classes:target/test-classes:$(cat classpath.txt)" local.rangdong.CloudDevicesTest
java -cp "target/classes:target/test-classes:$(cat classpath.txt)" local.rangdong.LoginInputTest
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
ẩn. Không đặt mật khẩu trong lệnh, cấu hình add-on công khai, issue GitHub hoặc chat.
Không dùng `mvn exec:java` cho bước này vì có thể không có `System.console()`.

PoC chỉ thử một lần đăng nhập theo API tìm thấy trong APK, rồi thử liệt kê nhà nếu
server trả đủ thông tin phiên. Không lưu phiên, mặc định không xuất local key, không đổi
mật khẩu hoặc đăng ký tài khoản. Lỗi đăng nhập dừng ngay và trả mã thoát khác 0.

Thay `--login-probe` bằng `--device-probe` để kiểm tra đường đọc key sau đăng nhập.
Chế độ này chỉ in `devices.validLocalKeyCount`, không in Device ID hay key; chỉ
xuất JSON khi thêm tùy chọn bên dưới, chưa tự import sang add-on. Không thay `localKey` bằng `devKey`/`secKey`:
đó là các trường khác nhau trong APK. Dữ liệu không đúng cấu trúc, session bị từ
chối hoặc hai nguồn trả key mâu thuẫn đều làm quá trình dừng ngay.

### Đọc tài khoản từ file riêng và xuất key

File JSON riêng, nằm ngoài repo, quyền 0600, nhận `country_code`, `email` (hoặc
`Gmail`, `username`, `phone`) và `password`. Tên trường không phân biệt hoa thường;
bỏ qua trường tài khoản rỗng nhưng dừng nếu có hai tài khoản khác nhau trong file.
Không tự sửa nội dung mật khẩu hoặc chuyển email thành số điện thoại.

```bash
java -cp "target/classes:$(cat classpath.txt)" local.rangdong.NativeProbe \
  /duong-dan/com.rd.smart.apk ./private/libs ./private/app-credentials \
  --device-probe --account-file /thu-muc-rieng/account.json \
  --export-file /thu-muc-rieng/local-keys.json
```

Tùy chọn xuất chỉ nhận file **chưa tồn tại**, cùng thư mục với file tài khoản,
tạo với quyền 0600 và không in dữ liệu ra stdout. Không chép file vào repo.
Email gọi API 3.0, số điện thoại gọi API 4.0 theo APK. Chỉ đọc thiết bị trong phiên
đăng nhập được cấp quyền; không tự thử lại khi bị từ chối. Nếu danh sách local bổ
sung thiếu/null `deviceList`, bỏ qua giống `ThingListDataBean.addDevices` trong APK,
không bỏ mất key hợp lệ từ danh sách thiết bị chính.

Nếu gặp `USER_PASSWD_WRONG`, kiểm tra đăng nhập trên ứng dụng Rạng Đông chính thức
và đổi mật khẩu nếu cần. Nếu gặp CAPTCHA/MFA hoặc yêu cầu app được chỉ định, hoàn
thành trên app chính thức; PoC không tự xử lý hay bỏ qua các bước này.

## Giới hạn trước khi tích hợp add-on

1. Mở rộng kiểm thử vùng cloud/phiên; email đã xác minh trên tài khoản thử nghiệm.
2. Kiểm thử điều khiển LAN với key đã lấy và các loại thiết bị khác.
3. Làm worker JSON-lines có timeout, giới hạn đầu vào và thông báo lỗi đã che bí mật.
4. Kiểm thử Unidbg/native backend trên kiến trúc Home Assistant cần hỗ trợ.
5. Chỉ sau đó thêm giao diện tải APK, đăng nhập và import key vào bridge hiện có.

Hiện code thử nghiệm dùng endpoint đã xác minh từ APK, chưa tự đổi endpoint sau
đăng nhập. Khi chưa hoàn thành các bước trên, không quảng cáo add-on là đã lấy key
trực tiếp được. Dù lấy được key từ cloud, điều khiển LAN vẫn cần Home Assistant
truy cập được mạng của thiết bị; việc iPhone khác mạng không tạo đường kết nối LAN.
# Lưu ý bản add-on

Người dùng Home Assistant nên dùng add-on **0.2.0** theo
[hướng dẫn giao diện cloud](../../rangdong_key_helper/DOCS.md), không cần chạy
PoC này. Nguồn Java chính nằm tại `rangdong_key_helper/native-cloud/src`;
POM của PoC trỏ tới cùng nguồn để tiếp tục phục vụ nghiên cứu dòng lệnh.
