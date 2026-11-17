# Website License Rạng Đông

Next.js/Vercel + PostgreSQL/Neon + PayOS. Đăng ký/đăng nhập email OTP qua Resend,
dashboard mua/xem key, admin riêng và API activation có chữ ký.

## Chạy và triển khai

1. Cài Node.js 24, chạy `npm ci`.
2. Đọc `.env.example`, cấu hình các biến ở Vercel. Không đặt secret vào `NEXT_PUBLIC_*`.
3. Sinh secret bằng `npm run keys:generate -- /thu-muc-rieng/ngoai-repo`.
4. Với `DATABASE_URL` trong môi trường, chạy `npm run db:migrate`.
5. `npm test`, `npm run typecheck`, `npm run build`.
6. Deploy lên Vercel, root directory là thư mục chứa file này.
7. Đăng ký PayOS webhook `https://DOMAIN/api/payos/webhook`.
8. Admin là email đã xác minh và nằm trong `ADMIN_EMAILS`; truy cập `/admin`.

Hướng dẫn đầy đủ: `LICENSE_DEPLOY_VI.md` tại root repo (cũng có trong ZIP source
tổng). Chưa thể nhận tiền/gửi email khi chưa cấu hình PayOS/Resend/Neon thật.
Test sử dụng PostgreSQL WASM và mock PayOS/email, không tạo giao dịch tiền thật.

Không có trial. Mỗi key ràng buộc một HA, một add-on, một custom integration.
License vĩnh viễn có `expires_at=NULL`. Key khóa/thu hồi không được cấp lease mới.
Reset đổi key và gỡ binding; chỉ admin được thực hiện.

API phía HA: `POST /api/licenses/activate`; xác minh proof installation và nonce,
trả lease Ed25519 tối đa 72 giờ. Các giá trị secret chỉ dùng server-side.
