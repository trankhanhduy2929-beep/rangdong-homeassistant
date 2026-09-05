"""Single-file Ingress page with no external browser dependencies."""

PAGE_TEMPLATE = r"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Rạng Đông Key Helper</title>
  <style nonce="__NONCE__">
    :root { color-scheme: light dark; font-family: Inter, system-ui, sans-serif; }
    body { margin: 0; background: #f3f5f7; color: #17202a; }
    main { max-width: 920px; margin: 0 auto; padding: 22px 16px 48px; }
    h1 { margin: 0 0 6px; font-size: 1.8rem; }
    h2 { margin: 0 0 14px; font-size: 1.18rem; }
    p { line-height: 1.5; }
    .subtle { margin-top: 0; color: #59636e; }
    .warning { border-left: 5px solid #d98200; background: #fff6df; }
    .card { background: #fff; border-radius: 14px; padding: 18px; margin-top: 16px;
      box-shadow: 0 2px 10px rgba(0,0,0,.08); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(190px,1fr)); gap: 13px; }
    label { display: flex; flex-direction: column; gap: 6px; font-weight: 650; }
    input { padding: 11px 12px; border: 1px solid #aab2ba; border-radius: 9px;
      background: #fff; color: #17202a; font: inherit; }
    .buttons { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px; }
    button { border: 0; border-radius: 9px; padding: 11px 15px; font: inherit;
      font-weight: 700; cursor: pointer; background: #00639b; color: #fff; }
    button.secondary { background: #59636e; }
    button.danger { background: #a83b32; }
    button:disabled { opacity: .55; cursor: wait; }
    #message { white-space: pre-wrap; border-radius: 10px; padding: 12px; margin-top: 16px;
      background: #e8f2f8; min-height: 24px; }
    #message.error { background: #fde8e6; color: #8c251f; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { text-align: left; border-bottom: 1px solid #d8dde2; padding: 9px 7px; }
    code { font-family: ui-monospace, SFMono-Regular, monospace; }
    .small { font-size: .9rem; color: #59636e; }
    @media (prefers-color-scheme: dark) {
      body { background: #111820; color: #ecf0f3; }
      .card { background: #1c2630; }
      .warning { background: #3a2d13; }
      .subtle, .small { color: #b9c1c8; }
      input { background: #101820; color: #ecf0f3; border-color: #65727f; }
      #message { background: #193447; }
      #message.error { background: #47201d; color: #ffb5ae; }
      th, td { border-color: #46515c; }
    }
  </style>
</head>
<body>
<main>
  <h1>Rạng Đông Key Helper</h1>
  <p class="subtle">Đăng nhập cloud Rạng Đông để lấy local key và chuyển vào Home Assistant. Không cần Android root ở chế độ cloud.</p>

  <section class="card">
    <h2>Cloud — không cần điện thoại Android</h2>
    <p>Đã tích hợp sẵn phương thức lấy key. Chỉ cần nhập tài khoản Rạng Đông và bấm đăng nhập; không cần tải APK, Android hay Tuya IoT project.</p>
    <p id="cloudStatus" class="small">Đang kiểm tra bộ đăng nhập…</p>
    <details><summary>Cài đặt nâng cao</summary>
    <label>Mã quốc gia<input id="cloudCountry" value="84" inputmode="numeric"></label>
    <p class="small">Chỉ chấp nhận đúng bản APK có checksum trong Hướng dẫn add-on. Nếu APK khác, hệ thống dừng thay vì chạy thư viện không rõ nguồn gốc.</p>
    <div class="grid">
      <label>Base com.rd.smart.apk<input id="cloudBase" type="file" accept=".apk"></label>
      <label>Split config.armeabi_v7a.apk<input id="cloudAbi" type="file" accept=".apk"></label>
    </div>
    <div class="buttons"><button id="cloudUpload">Tải lên và kiểm tra APK</button><button id="cloudClear" class="danger">Xóa bản nhập tay và cache</button></div>
    </details>
    <div class="grid">
      <label>Email hoặc số điện thoại Rạng Đông<input id="cloudAccount" autocomplete="off" spellcheck="false"></label>
      <label>Mật khẩu Rạng Đông<input id="cloudPassword" type="password" autocomplete="off"></label>
    </div>
    <p class="small">Email + mật khẩu Rạng Đông, không phải mật khẩu Google. Đã kiểm chứng lấy key qua email. Mật khẩu không được lưu; mỗi lần bấm chỉ đăng nhập một lần, cách nhau ít nhất 60 giây. MFA/CAPTCHA phải xử lý trong app chính thức. Thiết bị LAN cần cùng mạng với Home Assistant, không cần cùng mạng iPhone.</p>
    <div class="buttons"><button id="cloudLogin">Đăng nhập cloud và lấy key</button></div>
  </section>

  <details class="card"><summary>Chế độ dự phòng: Android root / Frida</summary>

  <section class="card warning">
    <strong>Yêu cầu bắt buộc:</strong> điện thoại Android đã root, bật Wireless debugging,
    cài app <code>com.rd.smart</code> và cùng mạng LAN. ADB thường không thể đọc key trên máy chưa root
    vì APK đặt <code>allowBackup=false</code> và không bật debug.
  </section>

  <section class="card">
    <h2>1. Kết nối điện thoại</h2>
    <div class="grid">
      <label>IP điện thoại<input id="host" inputmode="url" placeholder="192.168.1.50"></label>
      <label>Cổng kết nối ADB<input id="adbPort" type="number" min="1" max="65535"></label>
      <label>Android package<input id="packageName" spellcheck="false"></label>
    </div>
    <p class="small">Android 11+: màn hình Wireless debugging hiển thị cổng ghép đôi và cổng kết nối riêng; hai cổng này thường khác nhau.</p>
    <div class="grid">
      <label>Cổng ghép đôi<input id="pairPort" type="number" min="1" max="65535" placeholder="37001"></label>
      <label>Mã ghép đôi 6 số<input id="pairCode" inputmode="numeric" maxlength="6" autocomplete="one-time-code"></label>
    </div>
    <div class="buttons">
      <button id="pairButton" class="secondary">Ghép đôi ADB</button>
      <button id="prepareButton">Kết nối & chuẩn bị Frida</button>
    </div>
  </section>

  <section class="card">
    <h2>2. Đăng nhập và dò key</h2>
    <div class="grid">
      <label>Mã quốc gia<input id="countryCode" inputmode="numeric" value="84"></label>
      <label>Số điện thoại<input id="phone" inputmode="tel" autocomplete="off" placeholder="09xxxxxxxx"></label>
      <label>Mật khẩu<input id="password" type="password" autocomplete="off"></label>
    </div>
    <p class="small">Mật khẩu chỉ đi qua RAM của add-on và được chuyển vào SDK trong app Android; không ghi vào options, log hoặc GitHub. Nếu tài khoản yêu cầu captcha, hãy đăng nhập sẵn trong app rồi dùng nút bên cạnh.</p>
    <div class="buttons">
      <button id="loginScanButton">Đăng nhập & dò</button>
      <button id="scanButton" class="secondary">Dò bằng phiên app hiện có</button>
      <button id="clearButton" class="danger">Xóa key tạm khỏi bridge</button>
    </div>
  </section>

  </details>
  <div id="message" role="status" aria-live="polite">Sẵn sàng.</div>

  <section class="card">
    <h2>Thiết bị đã import</h2>
    <div id="emptyDevices" class="small">Chưa có thiết bị.</div>
    <table id="deviceTable" hidden>
      <thead><tr><th>Tên</th><th>Device ID</th><th>IP</th><th>Local key</th></tr></thead>
      <tbody id="deviceBody"></tbody>
    </table>
  </section>
</main>
<script nonce="__NONCE__">
  "use strict";
  const csrfToken = __CSRF_JSON__;
  const initialConfig = __CONFIG_JSON__;
  const path = window.location.pathname.endsWith("/")
    ? window.location.pathname : `${window.location.pathname}/`;
  const elements = Object.fromEntries([
    "host", "adbPort", "packageName", "pairPort", "pairCode", "countryCode",
    "phone", "password", "pairButton", "prepareButton", "loginScanButton",
    "scanButton", "clearButton", "message", "deviceTable", "deviceBody",
    "emptyDevices",
    "cloudBase", "cloudAbi", "cloudUpload", "cloudClear", "cloudStatus",
    "cloudCountry", "cloudAccount", "cloudPassword", "cloudLogin",
  ].map((id) => [id, document.getElementById(id)]));

  elements.host.value = initialConfig.host || "";
  elements.adbPort.value = initialConfig.adb_port || 5555;
  elements.packageName.value = initialConfig.package_name || "com.rd.smart";

  function targetPayload() {
    return {
      host: elements.host.value.trim(),
      adb_port: Number(elements.adbPort.value),
      package_name: elements.packageName.value.trim(),
    };
  }

  function setBusy(busy) {
    document.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
  }

  function showMessage(message, error = false) {
    elements.message.textContent = message;
    elements.message.classList.toggle("error", error);
  }

  function renderCloud(cloud) {
    if (!cloud) return;
    if (cloud.bundled && cloud.supported !== false) {
      elements.cloudStatus.textContent = "Bộ đăng nhập đã có sẵn — anh chỉ cần đăng nhập.";
      return;
    }
    elements.cloudStatus.textContent = `Base: ${cloud.base_uploaded ? "đã có" : "chưa có"} · ABI: ${cloud.abi_uploaded ? "đã có" : "chưa có"} · APK ${cloud.apk_version || "5.7.2"}`;
    if (cloud.supported === false) elements.cloudStatus.textContent += " · Kiến trúc chưa hỗ trợ cloud";
  }

  function renderDevices(devices) {
    const safeDevices = Array.isArray(devices) ? devices : [];
    elements.deviceBody.replaceChildren();
    for (const device of safeDevices) {
      const row = document.createElement("tr");
      for (const value of [
        device.name || "—", device.device_id || "—", device.host || "—",
        device.local_key || "<redacted>",
      ]) {
        const cell = document.createElement("td");
        cell.textContent = String(value);
        row.appendChild(cell);
      }
      elements.deviceBody.appendChild(row);
    }
    elements.deviceTable.hidden = safeDevices.length === 0;
    elements.emptyDevices.hidden = safeDevices.length !== 0;
  }

  async function api(endpoint, payload = undefined, method = "POST") {
    const options = { method, headers: { "X-CSRF-Token": csrfToken } };
    if (payload !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    const response = await fetch(`${path}${endpoint}`, options);
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  async function run(action) {
    setBusy(true);
    showMessage("Đang xử lý…");
    try {
      const data = await action();
      showMessage(data.message || "Hoàn tất.");
      if (data.devices) renderDevices(data.devices);
      if (data.cloud) renderCloud(data.cloud);
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Thao tác thất bại.", true);
    } finally {
      elements.password.value = "";
      elements.cloudPassword.value = "";
      elements.pairCode.value = "";
      setBusy(false);
    }
  }

  elements.pairButton.addEventListener("click", () => run(() => api("api/pair", {
    host: elements.host.value.trim(),
    pairing_port: Number(elements.pairPort.value),
    pairing_code: elements.pairCode.value.trim(),
  })));
  elements.prepareButton.addEventListener("click", () => run(() => api("api/prepare", targetPayload())));
  elements.scanButton.addEventListener("click", () => run(() => api("api/scan", targetPayload())));
  elements.loginScanButton.addEventListener("click", () => {
    const payload = {
      ...targetPayload(),
      country_code: elements.countryCode.value.trim(),
      phone: elements.phone.value.trim(),
      password: elements.password.value,
    };
    run(() => api("api/login-scan", payload));
  });
  elements.clearButton.addEventListener("click", () => run(() => api("api/bridge", undefined, "DELETE")));

  elements.cloudLogin.addEventListener("click", () => {
    const payload = {
      username: elements.cloudAccount.value.trim(),
      country_code: elements.cloudCountry.value.trim(),
      password: elements.cloudPassword.value,
    };
    elements.cloudPassword.value = "";
    run(async () => {
      try { return await api("api/cloud/login-scan", payload); }
      finally { payload.password = ""; }
    });
  });
  elements.cloudClear.addEventListener("click", () => run(() => api("api/cloud/apk", undefined, "DELETE")));
  elements.cloudUpload.addEventListener("click", () => run(async () => {
    let result;
    for (const [kind, input] of [["base", elements.cloudBase], ["abi", elements.cloudAbi]]) {
      const file = input.files[0];
      if (!file) continue;
      showMessage(`Đang tải ${kind} APK…`);
      const response = await fetch(`${path}api/cloud/apk/${kind}`, {
        method: "POST", headers: { "X-CSRF-Token": csrfToken, "Content-Type": "application/octet-stream" }, body: file,
      });
      result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.message || "Tải APK thất bại.");
      renderCloud(result.cloud);
      input.value = "";
    }
    if (!result) throw new Error("Hãy chọn APK cần tải lên.");
    return result;
  }));

  fetch(`${path}api/status`, { cache: "no-store" })
    .then((response) => response.json())
    .then((data) => { if (data.devices) renderDevices(data.devices); renderCloud(data.cloud); })
    .catch(() => {});
</script>
</body>
</html>
"""
