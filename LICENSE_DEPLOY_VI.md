# Triển khai License Rạng Đông 0.3.0

## 1. Những gì đã thay đổi và không thay đổi

Đã bổ sung website `license-server/` và các mô-đun license riêng. Không sửa giao
thức đăng nhập Rạng Đông, Java worker, chuẩn bị APK, UDP discovery, TCP LAN,
coordinator, switch/sensor hay dịch vụ điều khiển thiết bị.

Add-on chỉ còn **License → đăng nhập Rạng Đông → danh sách thiết bị**. API Android
root/Frida và import APK đã bỏ. Các mô-đun Android cũ vẫn nằm trong source để tránh
xáo trộn dependency; không còn route để gọi từ giao diện. Những trường options
cũ là tùy chọn để bản nâng cấp vẫn đọc được dữ liệu cũ, không cần điền.

**Quy tắc bảo toàn hệ thống:** kiểm tra license ở bước thêm tích hợp mới và trước
khi add-on đăng nhập cloud lấy key mới. Không ngắt thiết bị LAN/cloud đã cấu hình,
không xóa local key và không chặn dịch vụ điều khiển đã chạy vì license/server lỗi.
Nếu muốn chặn điều khiển thiết bị đang chạy theo license thì đó là chính sách khác,
không được bật âm thầm trong bản này.

## 2. Kiến trúc

- Next.js App Router, Node.js 24, Vercel; production dùng Cloudflare D1 qua
  Worker gateway HTTPS riêng. PostgreSQL/Neon vẫn được hỗ trợ bằng
  `DATABASE_PROVIDER=postgres` để không phá lựa chọn đã kiểm thử trước đó.
- Đăng ký/đăng nhập email + mật khẩu (12–128 ký tự), không cần OTP. Email mọi
  nhà cung cấp được chấp nhận, nhưng đây không phải xác minh quyền sở hữu hộp thư.
  Mật khẩu băm scrypt có salt riêng, không lưu plaintext. Số điện thoại tùy chọn.
- Bảng `plans`: `trial` miễn phí 1 ngày; `monthly` 50.000 VND/30 ngày;
  `lifetime` 200.000 VND không hết hạn. Gói tháng không tự động trừ tiền gia hạn.
- Trial bắt đầu 24 giờ từ lần kích hoạt đầu tiên, không qua PayOS. Cấp một key
  duy nhất/tài khoản, dùng chung hai suất custom/add-on. Bảng `trial_claims` và
  `trial_installations` không bị cron, reset hoặc thu hồi xóa lịch sử dùng thử.
  Đổi email không nhận thêm trial trên cùng installation. Trial không được gia hạn;
  reset chỉ đổi key/slot, không đổi installation hoặc kéo dài thời hạn trial đã dùng.
- Mỗi đơn có UUID nội bộ, `order_code` số duy nhất do DB cấp, snapshot
  giá và thời hạn gói. Giá không lấy từ trình duyệt.
- PayOS tạo checkout chứa QR. Sau chuyển khoản, webhook được SDK chính thức xác
  minh chữ ký, rồi server **gọi PayOS lại** để đối chiếu mã đơn, paymentLinkId,
  số tiền và trạng thái PAID trước khi cấp key.
- Cấp key, lưu giao dịch và đánh dấu PAID cùng một transaction. D1 dùng
  `DB.batch` và các điều kiện kiểm tra ngay trong batch; PostgreSQL dùng
  `FOR UPDATE`. Unique transaction reference, unique order/license chống cấp trùng.
- Khi mất webhook, người mua bấm **Kiểm tra thanh toán** để server đối soát PayOS.
  Query string `status=PAID` hoặc trang return của trình duyệt không cấp key.
- Key ngẫu nhiên 192 bit, lookup bằng SHA-256; bản key để chủ tài khoản xem lại
  được mã hóa AES-256-GCM trong DB. Không gửi key qua URL hoặc log.
- HA sinh private key Ed25519 riêng, lưu trong `.storage` quyền private. Add-on
  có UUID riêng ở `/data/license-client-id`, gửi yêu cầu qua API HA có xác thực.
  HA ký proof; server bind **một installation public key + một custom slot + một
  add-on slot**. Nhiều thiết bị Rạng Đông trong cùng HA dùng chung suất custom.
- Server trả lease ký Ed25519. Client kiểm tra public key đã ghim, thời hạn và
  đúng installation/component/client ID; không chỉ tin trường `valid` trên mạng.
- Lease tối đa 72 giờ, làm mới khi sử dụng nếu đã qua 1 giờ, không thử dồn trong
  60 giây. Mất mạng dùng lease đã ký còn hạn; server trả khóa/thu hồi rõ ràng thì
  không tiếp tục dùng cache. Việc khóa có thể chậm tối đa 1 giờ khi online có sử
  dụng và tối đa phần còn lại của 72 giờ khi offline.

## 3. Chuẩn bị

1. Tài khoản Vercel và domain HTTPS cho website.
2. Cloudflare D1 và quyền deploy Worker; hoặc PostgreSQL pooled hỗ trợ TLS.
3. Tài khoản PayOS/kênh thanh toán đã hoạt động: Client ID, API Key, Checksum Key.
4. Email riêng của chủ dự án để dự trữ tài khoản admin, nên bật MFA cho hộp thư.
5. Resend là tùy chọn cho API OTP cũ, không cần cho đăng ký/đăng nhập mới.

D1 đã có schema và các thao tác batch riêng trong `cloudflare/` và
`lib/d1-operations.ts`. Không chuyển database đang chứa dữ liệu bằng cách đổi
biến môi trường: cần kế hoạch migrate dữ liệu riêng. Production D1 được tạo mới,
không đụng database hay dịch vụ khác trong tài khoản.

## 4. Tạo secret

Từ thư mục repo:

```bash
cd license-server
npm ci
npm run keys:generate -- /duong-dan-rieng/ngoai-repo/rangdong-secrets
```

Công cụ tạo `server-secrets.env` và `public-key.txt`, quyền 0600; không ghi đè file
đã có, không in secret ra terminal. **Sao lưu an toàn**: mất encryption key thì
không đọc lại được key đã mã hóa trong DB; đổi signing key mà chưa phát hành
public key mới sẽ làm client không xác minh được lease.

Không upload thư mục secret này vào GitHub. `.env.example` là mẫu, không chứa
secret thật. Client ID/secret PayOS không phải thông tin tài khoản Rạng Đông.

## 5. Cấu hình database

### Production Cloudflare D1

Database `rangdong-license-production` đã được tạo và Worker
`rangdong-license-db` đã deploy. Các lệnh cho lần triển khai mới:

```bash
cd license-server
npx wrangler d1 create rangdong-license-production
# Điền database_id trả về vào cloudflare/wrangler.jsonc.
npx wrangler d1 execute rangdong-license-production --remote --file cloudflare/schema.sql --config cloudflare/wrangler.jsonc
npx wrangler d1 execute rangdong-license-production --remote --file cloudflare/002.sql --config cloudflare/wrangler.jsonc
npx wrangler secret put GATEWAY_SECRET --config cloudflare/wrangler.jsonc
npx wrangler deploy --config cloudflare/wrangler.jsonc
```

Đặt trên Vercel `DATABASE_PROVIDER=d1`, `D1_GATEWAY_URL` là URL HTTPS Worker
với path `/batch`, `D1_GATEWAY_SECRET` trùng secret riêng của gateway.
Không chuyển token OAuth Cloudflare vào Vercel. Worker không mở CORS, yêu cầu
secret cho mọi truy vấn, giới hạn request và không trả lỗi SQL chứa dữ liệu.
Không bật log nội dung truy vấn, OTP hoặc header xác thực.

Nâng cấp database cũ chỉ chạy `cloudflare/002.sql`; không cần tạo lại D1 hoặc
xóa dữ liệu. Migration giữ đơn/license cũ, chuyển bảng gói để cho phép giá 0,
kiểm tra khóa ngoại trước commit và thêm bảng credential/role/trial. Có thể chạy
bằng gateway thành một batch: `node --env-file=/private/production.env --import
tsx scripts/migrate-d1.ts 002`. Sao lưu trước migration trên database có khách.

Khi batch có một điều kiện không còn đúng do thao tác đồng thời, toàn bộ batch
rollback và API trả HTTP 409; người dùng có thể thử lại. D1 không chạy các callback
transaction PostgreSQL và không giả lập `FOR UPDATE` bằng cách bỏ khóa.

### Lựa chọn PostgreSQL tương thích

Đặt `DATABASE_PROVIDER=postgres`, rồi thực hiện các bước sau:

1. Tạo database production riêng. Dùng user chỉ dành cho ứng dụng, không dùng DB
   dùng chung với dịch vụ khác. Bật backup/point-in-time recovery theo gói.
2. Lấy pooled connection string có `sslmode=require`; không tắt kiểm tra TLS.
3. Đặt `DATABASE_URL` trong shell riêng rồi chạy migration:

```bash
cd license-server
npm run db:migrate
```

Script dùng biến môi trường tiến trình, không tự load `.env.local` cho CLI.
Có thể dùng `node --env-file=/duong-dan-rieng/server.env --import tsx scripts/migrate.ts`.
Không dán secret trực tiếp vào câu lệnh có lịch sử shell. Migration idempotent,
không xóa dữ liệu cũ. Với production lớn, dùng DB user migration riêng có DDL,
còn user runtime chỉ cần CRUD trên bảng và quyền sequence.

## 6. Deploy Vercel

Import repository (hoặc upload source website lên repository riêng). Chọn:

- Framework: **Next.js**.
- Root Directory: **license-server** (nếu repo chứa toàn bộ dự án); với ZIP website
  giải nén làm repo riêng thì Root Directory là `.`.
- Node.js: **24.x**; Build: `npm run build`; Install: `npm ci`.
- Dùng domain production cố định, không dùng preview URL để phát hành client.

### Environment Variables chỉ nằm ở Vercel/server

| Biến | Giá trị |
| --- | --- |
| `APP_URL` | HTTPS origin chính xác, ví dụ `https://license-tenmiencuaban.vn`, không thêm path |
| `DATABASE_URL` | Connection string PostgreSQL pooled có TLS |
| `DATABASE_PROVIDER` | `d1` cho production hiện tại; `postgres` cho lựa chọn cũ |
| `D1_GATEWAY_URL` | HTTPS URL Worker với path `/batch`, chỉ cần khi dùng D1 |
| `D1_GATEWAY_SECRET` | Secret riêng của Worker gateway, không phải token Cloudflare |
| `ADMIN_EMAILS` | Email admin dành riêng, bị chặn đăng ký công khai; quyền admin còn cần record cấp qua script |
| `PAYOS_CLIENT_ID` | Client ID kênh PayOS |
| `PAYOS_API_KEY` | API Key kênh PayOS |
| `PAYOS_CHECKSUM_KEY` | Checksum Key kênh PayOS |
| `RESEND_API_KEY` | Tùy chọn: secret gửi email cho API OTP cũ |
| `EMAIL_FROM` | Tùy chọn: địa chỉ gửi mail thuộc domain đã xác minh |
| `AUTH_SECRET` | Giá trị được công cụ sinh |
| `LICENSE_ENCRYPTION_KEY` | Base64 của 32 byte ngẫu nhiên do công cụ sinh |
| `LICENSE_SIGNING_PRIVATE_KEY` | Private PEM Ed25519; hỗ trợ xuống dòng thật hoặc `\n` |
| `CRON_SECRET` | Secret cron do công cụ sinh |

**Không thêm tiền tố `NEXT_PUBLIC_` cho bất kỳ secret nào.** Không điền chúng
vào add-on options, YAML HA, License Key form hoặc file cấu hình public client.

Chọn scope Production đúng; Preview nên dùng DB và kênh test riêng. Redeploy sau
khi thay environment. Vercel cron tại `/api/cron/cleanup` dọn OTP/session/nonce
hết hạn hằng ngày, xác thực bằng `CRON_SECRET`; không xóa đơn hàng/license.

## 7. PayOS webhook và kiểm thử thanh toán

Webhook production:

```text
https://DOMAIN-CUA-BAN/api/payos/webhook
```

Đăng ký URL này trong kênh PayOS hoặc dùng SDK chính thức:

```javascript
import { PayOS } from '@payos/node';
const payos = new PayOS({
  clientId: process.env.PAYOS_CLIENT_ID,
  apiKey: process.env.PAYOS_API_KEY,
  checksumKey: process.env.PAYOS_CHECKSUM_KEY,
});
await payos.webhooks.confirm(`${process.env.APP_URL}/api/payos/webhook`);
```

Webhook không dùng cookie/admin login/CSRF của website; chữ ký PayOS là bắt buộc.
Thông báo test có chữ ký hợp lệ nhưng không thuộc đơn của hệ thống được ACK,
không tạo license. Không tắt signature verification để vượt lỗi confirm.

Trước khi bán thật:

1. Xác minh email, đăng nhập dashboard, tạo đơn. Kiểm tra đúng giá **200.000đ**,
   tên/ngân hàng nhận tiền và nội dung mã đơn trên checkout PayOS.
2. Dùng môi trường/kênh thử nếu PayOS cung cấp; nếu phải thử chuyển thật, chỉ chủ
   dự án tự thực hiện. Công cụ này **chưa thực hiện chuyển tiền thật**.
3. Kiểm tra webhook → trạng thái PAID → đúng một license trong dashboard.
4. Gửi lại cùng webhook có chữ ký hợp lệ: vẫn một license. Thay amount hoặc chữ
   ký: không cấp key. Nếu webhook bị chậm, bấm **Kiểm tra thanh toán**.
5. Hoàn tất bước acceptance trên Vercel/PayOS thật rồi mới phát hành bản enforced.

## 8. Gắn website vào add-on/custom (chỉ thông tin công khai)

Từ root repo:

```bash
python3 tools/configure_license.py \
  --server https://DOMAIN-CUA-BAN \
  --public-key-file /duong-dan-rieng/ngoai-repo/rangdong-secrets/public-key.txt
python3 tools/package_release.py
```

Script chỉ ghi HTTPS origin, public key kiểm tra chữ ký và cờ `ENFORCE=True` vào
hai file `license_config.py`. Không cần và không được cung cấp private key.
Muốn rollout không chặn trước: thêm `--compatibility`. Bản `licensed` đã gắn
public URL/key production, yêu cầu license khi setup mới hoặc lấy key cloud mới.
Thiết bị cũ vẫn điều khiển bình thường. **Không bán bản `setup` như bản khóa license.**

Sau cấu hình, push source của anh và để GitHub Actions build image add-on 0.3.0.
Chỉ phát hành HACS khi image tương ứng đã build và kiểm thử xong. Nếu thay đổi
public config sau khi đã phát hành, tăng version rồi build/release lại.

## 9. ZIP, cài local và push GitHub

`tools/package_release.py` tạo trong `dist/`:

- `rangdong_smart-v0.3.0-setup.zip` hoặc `...-licensed.zip`: giải nén vào thư mục
  cấu hình HA, có đường dẫn `custom_components/rangdong_smart/`.
- `rangdong-key-helper-local-0.3.0-setup.zip` hoặc `...-licensed.zip`: giải nén vào
  `/addons/` của HA OS để có `/addons/rangdong_key_helper/config.yaml`. Bản local
  bỏ trường `image` trong ZIP để Supervisor build đúng source mới, không kéo nhầm
  image 0.3.0 chưa tồn tại. Refresh store → Local add-ons → cài/build. Build cần
  Internet để lấy dependency và tài nguyên APK đã ghim.
- `rangdong-license-server-1.0.0.zip`: source website để deploy.
- `rangdong-source-0.3.0-setup.zip` hoặc `...-licensed.zip`: repo source đã lọc cho
  anh tự push; bao gồm CI, tài liệu và công cụ đóng gói.
- `SHA256SUMS.txt`: kiểm tra toàn vẹn ZIP.

Không cài song song add-on cũ và local add-on mới khi cùng dùng một license.
Sao lưu HA trước nâng cấp; cập nhật custom rồi restart HA, sau đó cập nhật add-on.
Không xóa `.storage/rangdong_smart_license` hoặc `/data/license-client-id` tùy tiện:
đó là danh tính kích hoạt, xóa sẽ cần admin reset.

Không có tài khoản/secret thật được đóng ZIP. ZIP source không có `.git`, cache,
node_modules, `.next`, Java target, `.env` thật, private test account hoặc APK gốc.
APK vẫn được build từ tài nguyên công khai đã kiểm chứng của bản trước.

## 10. Admin và quản lý gói

### Đổi mật khẩu tài khoản

Đăng nhập `/dashboard` → mở **Đổi mật khẩu** → nhập mật khẩu hiện tại, mật khẩu
mới và xác nhận → **Lưu mật khẩu mới**. Áp dụng cho cả khách và admin, không cần
email/OTP. Mật khẩu mới cần 12–128 ký tự và phải khác mật khẩu cũ.

Server xác minh mật khẩu hiện tại, băm scrypt, thay mật khẩu và thu hồi tất cả
session cũ trong một transaction. Trình duyệt hiện tại nhận cookie mới; thiết bị
khác phải đăng nhập lại. Không đổi license, trial, đơn hàng hay quyền admin.
Nếu trước đây lưu mật khẩu admin trong file riêng, chủ tài khoản cần cập nhật bản
lưu đó sau khi tự đổi; hệ thống không lưu lại mật khẩu plaintext mới.

Đây là **đổi mật khẩu khi còn nhớ mật khẩu cũ**, không phải chức năng quên mật khẩu.

### Tối ưu giao diện và tải dữ liệu

- Dashboard gom ba truy vấn dữ liệu vào một batch D1; admin gom sáu truy vấn.
  Response chứa key/session vẫn `no-store`, không cache công khai.
- Chỉ tự cập nhật 15 giây khi còn đơn pending và tab đang hiển thị/có mạng.
  Không polling khi không có đơn chờ; dùng **Tải lại** để cập nhật thủ công.
- Không tải lại danh sách gói khi chuyển trang, hủy response cũ để tránh ghi đè
  trang mới, không làm mất số điện thoại đang nhập khi dữ liệu cập nhật.
- Điện thoại: form một cột, ô nhập 16px, nút tối thiểu 44px, bảng admin chuyển
  thành thẻ có nhãn, key/email dài tự xuống dòng, vẫn cho phép phóng to trang.

### Tạo và sử dụng admin

Admin phải được tạo riêng; đăng ký một email trùng admin không tự được cấp quyền.
Script sau chỉ tạo tài khoản chưa tồn tại, ghi mật khẩu ngẫu nhiên vào file riêng
quyền 0600, không in mật khẩu ra terminal và không ghi đè tài khoản có sẵn:

```bash
cd license-server
node --env-file=/private/production.env --import tsx scripts/bootstrap-admin.ts ADMIN_EMAIL /private/admin-login.txt
```

Sau đó đăng nhập bằng email/mật khẩu này ở `/dashboard`, mở `/admin`:

- Danh sách user, đơn, tổng doanh thu PAID, license và audit; có phân trang.
- Tạo license thủ công cho **tài khoản đã đăng ký**; không cộng doanh thu giả.
- Khóa/mở khóa; thu hồi vĩnh viễn; reset đổi key ngẫu nhiên và gỡ binding cũ.
- Gia hạn chỉ dùng key trả phí có ngày hết hạn. Trial không gia hạn, vĩnh viễn không cần gia hạn; key
  đã thu hồi không mở lại bằng nút unlock. Khi cần thay thế, cấp key mới.
- Key thô chỉ xuất hiện trong dashboard của chủ key, không phơi toàn bộ key tại
  danh sách admin. Admin reset thì user lấy key mới từ dashboard.
- Các thao tác ghi audit, không ghi raw key/secret. Khóa/thu hồi không tự hoàn tiền.

Thêm gói sau này bằng migration SQL, không sửa logic cấp key:

```sql
INSERT INTO plans(id,name,amount,duration_days,active)
VALUES ('annual','Một năm',100000,365,true);
```

Gói mới tự hiện ở màn hình mua và cấp key thủ công. Gói đang bán có thể tắt
`active=false`; đơn cũ giữ snapshot giá/thời hạn để không bị thay đổi sau thanh toán.

## 11. Giới hạn bảo mật cần hiểu rõ

- Đăng ký tối đa 5 tài khoản/IP/24 giờ; đăng nhập có hạn mức IP và email.
  Trial một lần/tài khoản và installation được bảo vệ bằng unique constraints,
  điều kiện trong transaction và chữ ký installation. Tạo lại toàn bộ danh tính
  HA và tài khoản mới vẫn là giới hạn không thể chặn tuyệt đối khi không có TPM.
  OTP/đơn/activation có rate limit; mỗi user tối đa 5 đơn pending/24 giờ.
- Không xác minh email nên chưa có tự khôi phục mật khẩu qua email. Không đặt
  quyền admin dựa đơn thuần vào chuỗi email khách nhập; dùng bảng role riêng.
- Chỉ một cặp addon/custom trên cùng HA theo private installation key và UUID.
  Bản sao nguyên `.storage` và dữ liệu add-on có thể giả cùng danh tính; không có
  TPM/hardware attestation nên **không tuyên bố chống clone/chỉnh source tuyệt đối**.
- Home Assistant/custom Python là mã phía người dùng có quyền admin; có thể sửa
  cờ license nếu cố tình chỉnh source. Giải pháp chống chia sẻ thông thường,
  không phải DRM không thể vượt qua. Không thể thu hồi local key đã biết.
- Backup HA chứa danh tính và license cần bảo vệ. Reset để chuyển HA nên do admin
  xác minh người mua; user không có API tự reset hàng loạt.
- Không log request body của `/api/licenses/activate`, `/api/auth/*`, webhook hoặc
  form key. Tắt capture body trong công cụ APM bên ngoài nếu có.
- Website này không nhận mật khẩu tài khoản Rạng Đông. Email đăng ký license và
  email Rạng Đông có thể khác nhau. Mật khẩu Rạng Đông chỉ nhập trong add-on HA.
- Đã deploy Vercel/Cloudflare D1, xác nhận webhook PayOS, kiểm thử đăng ký/mật khẩu,
  trial và chữ ký hai suất trực tiếp trên production. Chưa chuyển tiền thật hoặc
  nâng cấp HA đang vận hành.
  Trạng thái thực tế được ghi trong `DEPLOY_STATUS_VI.md`.

## 12. Kiểm thử tại máy phát triển

```bash
cd license-server
npm ci
npm run typecheck
npm test
npm run build
```

Test dùng PGlite (PostgreSQL chạy WASM), SQLite và Worker gateway để kiểm tra schema, transaction, cấp key
idempotent, sai tiền/link, webhook giả, OTP/replay, quyền admin và ràng buộc slot.
PayOS/email trong automated tests là mock, không gọi giao dịch thật. Production
thanh toán tiền thật cần acceptance theo mục 7. Batch rollback đã được kiểm tra
trên D1 production: batch thất bại không lưu user thử nghiệm.

Test integration/helper dùng bộ pytest hiện có. Trước mở bán, cài bản `licensed`
trên HA thử nghiệm, nhận trial, nhập key và kiểm tra bật/tắt thiết bị hiện có;
kiểm tra một khoản thanh toán thật trước khi phát hành đại trà.
