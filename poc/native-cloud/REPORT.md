# Báo cáo nghiên cứu cloud native Rạng Đông — 04/09/2026

## Phát hiện đã xác minh

Thử nghiệm thực tế trên Linux amd64 với APK `com.rd.smart` 5.7.2 do người dùng
cung cấp, Unidbg 0.9.8, Java 21. Không sửa APK gốc.

| Bước | Kết quả |
| --- | --- |
| Khởi tạo native từ APK, chứng thư và tài nguyên | Chạy được |
| `getChKey` | Chuỗi 8 ký tự, không ghi giá trị |
| `getEncryptoKey(requestId, null)` | Khóa 16 byte, không ghi giá trị |
| `encryptPostData` / `computeDigest` | 16 byte / 32 ký tự |
| Ký bằng native command 1 | 64 ký tự, ổn định khi đầu vào giống nhau |
| Token API 2.0, số giả | HTTP 200, `success=true` |
| Chữ ký phản hồi, AES-GCM và JSON | Xác minh/giải mã được trong request token kiểm tra lại |
| Token API với tài khoản được cung cấp | HTTP 200, `success=true` |
| Mobile password login 3.0, một lần | HTTP 200, `success=false`, `USER_PASSWD_WRONG` |

Không thử lại mật khẩu, không thử biến thể số điện thoại hoặc API hàng loạt.
Mã `USER_PASSWD_WRONG` là kết quả server, chưa đủ để phân biệt mật khẩu đã đổi,
thông tin tài khoản không khớp hay chi tiết client đăng nhập còn thiếu. Không kết
luận rằng chỉ đổi mật khẩu là chắc chắn hoạt động.

Trong quá trình thử, DNS từng lỗi ở cả cloud và GitHub rồi phục hồi. Sau phục hồi
đã kiểm tra lại token cùng xác minh chữ ký phản hồi. **Trở ngại hiện tại là chưa có
phiên đăng nhập thành công**, không còn lấy sự cố DNS làm kết luận cuối cùng.

## Giao thức đã đối chiếu

- Endpoint thử nghiệm: `https://a1-us.iotbing.com/api.json`.
- POST form chứa metadata, ciphertext `postData` và `sign`; URL không chứa phiên.
- `et=3`: AES-GCM, nonce 12 byte đứng **đầu** ciphertext và tag 16 byte, Base64.
- Request chưa đăng nhập: khóa native lấy từ request ID, ecode null.
- Chuỗi ký chỉ lấy whitelist, sort tên trường, bỏ giá trị rỗng. `postData` thay
  bằng MD5 hex đã đổi thứ tự các đoạn 8 ký tự; ciphertext gốc vẫn nằm trong form.
- Khởi tạo command 0 nhận app secret rồi app ID; command 1 ký chuỗi canonical.
- Chữ ký phản hồi là MD5 của `result=<ciphertext>||t=<timestamp>||<request-key>`.
  Kiểm tra trước khi giải mã; GCM tiếp tục kiểm tra authentication tag.
- Payload đăng nhập dùng MD5 mật khẩu rồi RSA PKCS#1 v1.5 theo public key/exponent
  từ token API. Chưa xác minh thành công cuối luồng với tài khoản hợp lệ.

## Bằng chứng từ APK trong workspace nghiên cứu

Các đường dẫn sau tương đối với `/opt/apk-lab/input/rangdong`, không đóng gói vào Git:

- `analysis/apktool_base/AndroidManifest.xml`: package và thông tin Android.
- `analysis/apktool_base/smali_classes6/com/thingclips/smart/android/common/utils/AesGcmUtil.smali`:
  `encryptBytes2BytesAppendNonce`, `decryptBytesAppendedNonce2Bytes`.
- `analysis/apktool_base/smali_classes6/com/thingclips/smart/android/network/ThingApiParams.smali`:
  `getEncryptPostDataString`, `getRequestBody`, `getRequestUrl`, `initUrlParams`.
- `analysis/apktool_base/smali_classes4/com/thingclips/sdk/network/ThingApiSignManager.smali`:
  whitelist, `generateSignatureSdk`, `postDataMD5Hex`, `swapSignString`.
- `analysis/apktool_base/smali_classes6/com/thingclips/smart/android/network/Business.smali`:
  `verifyResponseResult`, giải mã và giải nén phản hồi.
- `analysis/apktool_base/smali_classes5/com/thingclips/sdk/user/pqdbppq.smali`:
  `thing.m.user.mobile.passwd.login`, phiên bản 3.0, `options`, `ifencrypt`.
- `analysis/apktool_base/smali_classes14/com/thingclips/smart/security/jni/SecureNativeApi.smali`:
  chữ ký phương thức JNI.

PoC có shim kiểu đối tượng X509Certificate và callback `checkStatus` để nạp JNI.
Đây không phải môi trường Android hoàn chỉnh hoặc bằng chứng vượt attestation;
không dùng shim để bỏ qua yêu cầu xác minh mà server trả về.

## Giả thuyết và phần còn thiếu

- Có thể tái sử dụng native client trong worker add-on, nhưng mới xác minh bước
  trước đăng nhập và phản hồi từ chối mật khẩu.
- Chưa xác nhận `sid`, `ecode`, domain sau đăng nhập, home list, device list, local
  key, refresh session hoặc khả năng điều khiển thiết bị thật.
- Chưa có worker JSON-lines, giao diện tải APK hoặc tích hợp cloud vào bridge.
- Chưa kiểm thử aarch64; không tăng phiên bản add-on/integration hay phát hành HACS.
- Không có tài khoản, mật khẩu, token, chữ ký request hoặc local key trong báo cáo.

## Kế hoạch kiểm thử tiếp

1. Chủ tài khoản kiểm tra thông tin đăng nhập trên app chính thức; không gửi lại
   mật khẩu trong chat. Chạy PoC qua terminal nhập ẩn bằng thông tin hợp lệ.
2. Khi đăng nhập thành công, xác minh vùng cloud, cấu trúc phiên và danh sách nhà.
3. Chỉ đọc thiết bị thuộc phiên đã xác thực; đếm số key hợp lệ, không log giá trị.
4. Thêm fixture giả cho phản hồi thực tế, rồi mới nối vào bridge/import hiện có.
5. Kiểm thử container và kiến trúc trước khi xuất bản add-on.

## Kiểm thử mã nguồn đã lưu

- Maven compile/test-compile: đạt.
- `ProtocolTest`: 10 kiểm tra đạt, gồm vector AES-GCM cố định, nonce prefix,
  từ chối tag bị sửa, envelope ngắn, canonical/MD5 swap và chữ ký phản hồi.
- Python unittest cho chuẩn bị tài nguyên: 4 kiểm tra đạt, gồm quyền file,
  allowlist ZIP, không ghi đè và dừng khi thiếu dữ liệu.
- Ruff check và format check cho Python mới: đạt.
- Native smoke test sau refactor: đạt, chỉ in độ dài/kết quả so sánh.
- 16 kiểm tra add-on hiện có: đạt bằng môi trường test sẵn có của dự án.
  Python hệ thống thiếu aiohttp/PyYAML; không sửa dependency hệ thống.
- Quét giá trị app ID/app secret trích từ APK trong các file nguồn mới: không có.
- Chưa kiểm thử đăng nhập thành công hoặc thiết bị thật; không phát hành phiên bản mới.
