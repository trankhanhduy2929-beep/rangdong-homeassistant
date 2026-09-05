package local.rangdong;

import com.github.unidbg.AndroidEmulator;
import com.github.unidbg.arm.backend.Unicorn2Factory;
import com.github.unidbg.linux.android.AndroidEmulatorBuilder;
import com.github.unidbg.linux.android.AndroidResolver;
import com.github.unidbg.linux.android.dvm.AbstractJni;
import com.github.unidbg.linux.android.dvm.BaseVM;
import com.github.unidbg.linux.android.dvm.DalvikModule;
import com.github.unidbg.linux.android.dvm.DvmClass;
import com.github.unidbg.linux.android.dvm.DvmMethod;
import com.github.unidbg.linux.android.dvm.DvmObject;
import com.github.unidbg.linux.android.dvm.StringObject;
import com.github.unidbg.linux.android.dvm.VaList;
import com.github.unidbg.linux.android.dvm.VM;
import com.github.unidbg.linux.android.dvm.array.ByteArray;
import com.github.unidbg.memory.Memory;
import com.github.unidbg.virtualmodule.android.AndroidModule;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.cert.Certificate;
import java.security.cert.CertificateEncodingException;
import java.util.List;
import java.util.Arrays;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.net.URL;
import java.net.URLEncoder;
import javax.net.ssl.HttpsURLConnection;
import javax.crypto.Cipher;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;

public final class NativeProbe implements AutoCloseable {
    private final AndroidEmulator emulator;
    private final VM vm;
    private final DvmClass secureNativeApi;
    private final DvmObject<?> application;
    private String lastCloudError = "cloud_request_failed";

    private NativeProbe(File apk, File libraryDirectory) {
        emulator = AndroidEmulatorBuilder.for32Bit()
                .setProcessName("com.rd.smart")
                .addBackendFactory(new Unicorn2Factory(true))
                .build();
        Memory memory = emulator.getMemory();
        memory.setLibraryResolver(new AndroidResolver(23));
        vm = emulator.createDalvikVM(apk);
        vm.setJni(new AbstractJni() {
            @Override
            public DvmObject<?> callObjectMethodV(
                    BaseVM currentVm,
                    DvmObject<?> object,
                    DvmMethod method,
                    VaList arguments
            ) {
                if ("java/security/cert/X509Certificate->getEncoded()[B"
                        .equals(method.getSignature())) {
                    try {
                        Certificate certificate = (Certificate) object.getValue();
                        return new ByteArray(currentVm, certificate.getEncoded());
                    } catch (CertificateEncodingException error) {
                        throw new IllegalStateException(error);
                    }
                }
                DvmObject<?> result = super.callObjectMethodV(currentVm, object, method, arguments);
                if ("java/security/cert/CertificateFactory->generateCertificate(Ljava/io/InputStream;)Ljava/security/cert/Certificate;"
                        .equals(method.getSignature())) {
                    return currentVm.resolveClass("java/security/cert/X509Certificate")
                            .newObject(result.getValue());
                }
                return result;
            }

            @Override
            public void callStaticVoidMethodV(
                    BaseVM currentVm,
                    DvmClass currentClass,
                    DvmMethod method,
                    VaList arguments
            ) {
                if ("com/thingclips/smart/security/jni/JNICLibrary->checkStatus(I)V"
                        .equals(method.getSignature())) {
                    return;
                }
                super.callStaticVoidMethodV(currentVm, currentClass, method, arguments);
            }
        });
        vm.setVerbose(false);
        new AndroidModule(emulator, vm).register(memory);

        load(libraryDirectory, "libc++_shared.so");
        load(libraryDirectory, "libmbedcrypto.so");
        load(libraryDirectory, "libmbedx509.so");
        load(libraryDirectory, "libmbedtls.so");
        load(libraryDirectory, "libthing_security_algorithm.so");
        DalvikModule security = load(libraryDirectory, "libthing_security.so");

        secureNativeApi = vm.resolveClass("com/thingclips/smart/security/jni/SecureNativeApi");
        application = vm.resolveClass("android/app/Application").newObject(null);
        security.callJNI_OnLoad(emulator);
    }

    private DalvikModule load(File directory, String name) {
        return vm.loadLibrary(new File(directory, name), false);
    }

    private String getChKey(String appId) {
        DvmObject<?> context = vm.resolveClass("android/content/Context").newObject(null);
        StringObject result = secureNativeApi.callStaticJniMethodObject(
                emulator,
                "getChKey(Landroid/content/Context;[B)Ljava/lang/String;",
                context,
                new ByteArray(vm, appId.getBytes(StandardCharsets.UTF_8))
        );
        return result == null ? null : result.getValue();
    }

    private byte[] encryptPostData(String key, byte[] input) {
        ByteArray result = secureNativeApi.callStaticJniMethodObject(
                emulator,
                "encryptPostData(Ljava/lang/String;[B)[B",
                key,
                new ByteArray(vm, input)
        );
        return result == null ? null : result.getValue();
    }

    private String computeDigest(String value, String key) {
        StringObject result = secureNativeApi.callStaticJniMethodObject(
                emulator,
                "computeDigest(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;",
                value,
                key
        );
        return result == null ? null : result.getValue();
    }

    private String sign(String canonicalValue) {
        StringObject result = secureNativeApi.callStaticJniMethodObject(
                emulator,
                "doCommandNative(Landroid/content/Context;I[B[BZ)Ljava/lang/Object;",
                application,
                1,
                new ByteArray(vm, canonicalValue.getBytes(StandardCharsets.UTF_8)),
                null,
                false
        );
        return result == null ? null : result.getValue();
    }

    private byte[] getEncryptoKey(String requestId, String ecode) {
        ByteArray result = secureNativeApi.callStaticJniMethodObject(
                emulator,
                "getEncryptoKey(Ljava/lang/String;Ljava/lang/String;)[B",
                requestId,
                ecode
        );
        if (result == null || result.getValue().length != 16) {
            throw new IllegalStateException("Invalid request encryption key");
        }
        return result.getValue();
    }

    private JSONObject request(String appId, String api, String version, String payload,
                               String sid, String ecode, String homeId) throws Exception {
        String requestId = UUID.randomUUID().toString();
        byte[] key = getEncryptoKey(requestId, ecode);
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        String encryptedPayload = payload == null ? null
                : Protocol.encrypt(key, payload.getBytes(StandardCharsets.UTF_8), nonce);
        Map<String, String> params = new TreeMap<>();
        params.put("a", api);
        params.put("v", version);
        if (sid != null) {
            params.put("sid", sid);
        }
        if (homeId != null) {
            params.put("gid", homeId);
        }
        params.put("clientId", appId);
        params.put("os", "Android");
        params.put("appVersion", "5.7.2");
        params.put("sdkVersion", "5.16.0");
        params.put("deviceCoreVersion", "5.16.0");
        params.put("ttid", "sdk_thing@" + appId);
        params.put("lang", "vi_VN");
        params.put("osSystem", "13");
        params.put("platform", "Android");
        params.put("timeZoneId", "Asia/Ho_Chi_Minh");
        params.put("requestId", requestId);
        params.put("et", "3");
        params.put("cp", "gzip");
        params.put("channel", "oem");
        params.put("bizData", "{\"appRnVersion\":\"5.87\"}");
        params.put("chKey", getChKey(appId));
        params.put("time", Long.toString(System.currentTimeMillis() / 1000));
        if (encryptedPayload != null) {
            params.put("postData", encryptedPayload);
        }
        params.put("sign", sign(Protocol.canonical(params)));
        StringBuilder body = new StringBuilder();
        for (Map.Entry<String, String> entry : params.entrySet()) {
            if (body.length() > 0) {
                body.append('&');
            }
            body.append(URLEncoder.encode(entry.getKey(), "UTF-8")).append('=')
                    .append(URLEncoder.encode(entry.getValue(), "UTF-8"));
        }
        HttpsURLConnection connection = (HttpsURLConnection) new URL("https://a1-us.iotbing.com/api.json").openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(15000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestMethod("POST");
        connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
        connection.setDoOutput(true);
        try (java.io.OutputStream output = connection.getOutputStream()) {
            output.write(body.toString().getBytes(StandardCharsets.UTF_8));
        }
        int status = connection.getResponseCode();
        System.out.println("http.status=" + status);
        try (InputStream input = status >= 400 ? connection.getErrorStream() : connection.getInputStream()) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
                if (output.size() > 1048576) {
                    throw new IllegalStateException("Response too large");
                }
            }
            JSONObject response = JSON.parseObject(new String(output.toByteArray(), StandardCharsets.UTF_8));
            if (response.get("result") instanceof String && !response.containsKey("success")) {
                Protocol.verifyResponse(key, response.getString("result"), response.getLongValue("t"),
                        response.getString("sign"));
                byte[] plaintext = Protocol.decrypt(key, response.getString("result"));
                if (plaintext.length >= 2 && plaintext[0] == (byte) 0x1f && plaintext[1] == (byte) 0x8b) {
                    try (InputStream gzip = new java.util.zip.GZIPInputStream(new java.io.ByteArrayInputStream(plaintext))) {
                        output.reset();
                        while ((count = gzip.read(buffer)) != -1) {
                            output.write(buffer, 0, count);
                            if (output.size() > 1048576) {
                                throw new IllegalStateException("Decompressed response too large");
                            }
                        }
                        plaintext = output.toByteArray();
                    }
                }
                response = JSON.parseObject(new String(plaintext, StandardCharsets.UTF_8));
                System.out.println("response.decrypted=true");
            }
            System.out.println("response.success=" + response.getBoolean("success"));
            Object code = response.containsKey("errorCode") ? response.get("errorCode") : response.get("code");
            if (!Boolean.TRUE.equals(response.get("success")) && code instanceof String
                    && ((String) code).matches("[A-Za-z0-9_-]{1,80}")) {
                lastCloudError = (String) code;
            }
            System.out.println("response.code=" + (code == null ? "absent" : code.toString().replaceAll("[^A-Za-z0-9_-]", "")));
            System.out.println("response.resultType=" + (response.get("result") == null ? "absent" : response.get("result").getClass().getSimpleName()));
            return response;
        } finally {
            Arrays.fill(key, (byte) 0);
            connection.disconnect();
        }
    }

    private static String hex(byte[] bytes) {
        return Protocol.hex(bytes);
    }

    private LoginInput readConsoleLogin() {
        java.io.Console console = System.console();
        if (console == null) {
            throw new IllegalStateException("Login requires an interactive terminal");
        }
        char[] suppliedUsername = console.readPassword("Email hoặc số điện thoại Rạng Đông (ẩn): ");
        String username = suppliedUsername == null ? null : new String(suppliedUsername);
        if (suppliedUsername != null) {
            Arrays.fill(suppliedUsername, '\0');
        }
        char[] password = console.readPassword("Mật khẩu (ẩn): ");
        JSONObject data = new JSONObject();
        try {
            data.put("username", username);
            data.put("password", password == null ? null : new String(password));
            return LoginInput.fromJson(data);
        } finally {
            data.clear();
            if (password != null) {
                Arrays.fill(password, '\0');
            }
        }
    }

    private com.alibaba.fastjson.JSONArray loginProbe(String appId, boolean scanDevices, LoginInput account,
                            java.nio.file.Path exportPath) throws Exception {
        String passwordMd5 = account.consumePasswordMd5();
        JSONObject tokenPayload = new JSONObject();
        tokenPayload.put("countryCode", account.countryCode);
        tokenPayload.put("username", account.username);
        tokenPayload.put("isUid", false);
        JSONObject tokenResponse = request(appId, "thing.m.user.username.token.get", "2.0",
                tokenPayload.toJSONString(), null, null, null);
        if (!Boolean.TRUE.equals(tokenResponse.getBoolean("success"))) {
            throw new IllegalStateException("Token request failed");
        }
        JSONObject token = tokenResponse.getJSONObject("result");
        java.security.spec.RSAPublicKeySpec publicSpec = new java.security.spec.RSAPublicKeySpec(
                new java.math.BigInteger(token.getString("publicKey")),
                new java.math.BigInteger(token.getString("exponent")));
        Cipher rsa = Cipher.getInstance("RSA/ECB/PKCS1Padding");
        rsa.init(Cipher.ENCRYPT_MODE, java.security.KeyFactory.getInstance("RSA").generatePublic(publicSpec));
        JSONObject loginPayload = new JSONObject();
        loginPayload.put("countryCode", account.countryCode);
        loginPayload.put(account.accountField(), account.username);
        loginPayload.put("passwd", hex(rsa.doFinal(passwordMd5.getBytes(StandardCharsets.UTF_8))));
        loginPayload.put("options", "{\"group\": 1,\"mfaCode\": \"\"}");
        loginPayload.put("token", token.getString("token"));
        loginPayload.put("ifencrypt", 1);
        JSONObject loginResponse = request(appId, account.api(), account.version(),
                loginPayload.toJSONString(), null, null, null);
        loginPayload.clear();
        token.clear();
        if (!Boolean.TRUE.equals(loginResponse.getBoolean("success"))) {
            System.out.println("login.stopped=true; no automatic retry");
            throw new IllegalStateException("Login failed");
        }
        JSONObject user = loginResponse.getJSONObject("result");
        System.out.println("login.sessionPresent=" + (user.getString("sid") != null));
        System.out.println("login.ecodePresent=" + (user.getString("ecode") != null));
        if (user.getString("sid") == null || user.getString("ecode") == null) {
            throw new IllegalStateException("Login session missing");
        }
        try {
            if (scanDevices) {
                com.alibaba.fastjson.JSONArray devices = CloudDevices.collect((api, version, payload) ->
                        request(appId, api, version, payload == null ? null : payload.toJSONString(),
                                user.getString("sid"), user.getString("ecode"), null));
                System.out.println("devices.validLocalKeyCount=" + devices.size());
                if (exportPath != null && !devices.isEmpty()) {
                    writePrivateExport(exportPath, devices);
                    System.out.println("devices.privateExportWritten=true");
                }
                return devices;
            } else {
                JSONObject homes = request(appId, "m.life.group.location.list", "7.0", null,
                        user.getString("sid"), user.getString("ecode"), null);
                boolean listed = Boolean.TRUE.equals(homes.getBoolean("success"))
                        && homes.get("result") instanceof com.alibaba.fastjson.JSONArray;
                System.out.println("homes.listed=" + listed);
                if (!listed) {
                    throw new IllegalStateException("Home listing not verified");
                }
            }
        } finally {
            user.clear();
        }
        return new com.alibaba.fastjson.JSONArray();
    }

    static void writePrivateExport(java.nio.file.Path path, com.alibaba.fastjson.JSONArray devices) throws Exception {
        byte[] encoded = devices.toJSONString().getBytes(StandardCharsets.UTF_8);
        try (java.nio.channels.SeekableByteChannel output = Files.newByteChannel(path,
                java.util.EnumSet.of(java.nio.file.StandardOpenOption.CREATE_NEW, java.nio.file.StandardOpenOption.WRITE),
                java.nio.file.attribute.PosixFilePermissions.asFileAttribute(
                        java.nio.file.attribute.PosixFilePermissions.fromString("rw-------")))) {
            java.nio.ByteBuffer buffer = java.nio.ByteBuffer.wrap(encoded);
            while (buffer.hasRemaining()) {
                output.write(buffer);
            }
        } finally {
            Arrays.fill(encoded, (byte) 0);
        }
    }

    private void initializeSecurity(String appId, String appSecret) {
        secureNativeApi.callStaticJniMethodObject(
                emulator,
                "doCommandNative(Landroid/content/Context;I[B[BZ)Ljava/lang/Object;",
                application,
                0,
                new ByteArray(vm, appSecret.getBytes(StandardCharsets.UTF_8)),
                new ByteArray(vm, appId.getBytes(StandardCharsets.UTF_8)),
                false
        );
    }

    @Override
    public void close() throws Exception {
        emulator.close();
    }

    public static void main(String[] args) {
        if (args.length == 4 && "--worker".equals(args[0])) {
            worker(args);
            return;
        }
        try {
            run(args);
        } catch (Exception error) {
            System.err.println("probe.failed=" + error.getClass().getSimpleName()
                    + "; chi tiết nhạy cảm đã được ẩn; không tự thử lại");
            System.exit(1);
        }
    }

    private static void worker(String[] args) {
        java.io.PrintStream channel = System.out;
        System.setOut(new java.io.PrintStream(new java.io.OutputStream() {
            @Override
            public void write(int value) {
            }
        }));
        com.alibaba.fastjson.parser.ParserConfig.getGlobalInstance().setSafeMode(true);
        JSONObject result = new JSONObject();
        NativeProbe probe = null;
        try {
            ByteArrayOutputStream input = new ByteArrayOutputStream();
            int value;
            while ((value = System.in.read()) != -1 && value != '\n') {
                if (input.size() >= 16384) {
                    throw new IllegalArgumentException("Worker input too large");
                }
                input.write(value);
            }
            JSONObject payload = JSON.parseObject(new String(input.toByteArray(), StandardCharsets.UTF_8));
            input.reset();
            try (LoginInput account = LoginInput.fromJson(payload)) {
                payload.clear();
                List<String> appCredentials = Files.readAllLines(new File(args[3]).toPath(), StandardCharsets.UTF_8);
                if (appCredentials.size() != 2) {
                    throw new IllegalArgumentException("Invalid app credentials");
                }
                probe = new NativeProbe(new File(args[1]), new File(args[2]));
                probe.initializeSecurity(appCredentials.get(0), appCredentials.get(1));
                result.put("devices", probe.loginProbe(appCredentials.get(0), true, account, null));
                result.put("success", true);
                appCredentials.clear();
            }
        } catch (Exception error) {
            result.clear();
            result.put("success", false);
            result.put("error", probe == null ? "cloud_worker_failed" : probe.lastCloudError);
            result.put("failureType", error.getClass().getSimpleName());
        } finally {
            if (probe != null) {
                try {
                    probe.close();
                } catch (Exception ignored) {
                }
            }
        }
        String encoded = result.toJSONString();
        if (encoded.getBytes(StandardCharsets.UTF_8).length > 512 * 1024) {
            encoded = "{\"success\":false,\"error\":\"cloud_result_too_large\"}";
        }
        channel.println(encoded);
        channel.flush();
        result.clear();
    }

    private static void run(String[] args) throws Exception {
        com.alibaba.fastjson.parser.ParserConfig.getGlobalInstance().setSafeMode(true);
        if (args.length != 3 && args.length != 4 && args.length != 6 && args.length != 8) {
            throw new IllegalArgumentException(
                    "Usage: NativeProbe <base.apk> <lib-dir> <credential-file> [--token-probe|--login-probe|--device-probe] [--account-file <private.json>]"
            );
        }
        if (args.length >= 4 && !"--token-probe".equals(args[3])
                && !"--login-probe".equals(args[3]) && !"--device-probe".equals(args[3])) {
            throw new IllegalArgumentException("Unknown mode");
        }
        if (args.length >= 6 && (!"--account-file".equals(args[4]) || "--token-probe".equals(args[3]))) {
            throw new IllegalArgumentException("Invalid account file mode");
        }
        java.nio.file.Path exportPath = null;
        if (args.length == 8) {
            if (!"--device-probe".equals(args[3]) || !"--export-file".equals(args[6])) {
                throw new IllegalArgumentException("Invalid export mode");
            }
            exportPath = new File(args[7]).toPath().toAbsolutePath().normalize();
            java.nio.file.Path accountDirectory = new File(args[5]).toPath().toRealPath().getParent();
            if (!exportPath.getParent().toRealPath().equals(accountDirectory)
                    || Files.exists(exportPath, java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
                throw new IllegalArgumentException("Export must be a new file beside the private account file");
            }
        }
        List<String> credentials = Files.readAllLines(
                new File(args[2]).toPath(),
                StandardCharsets.UTF_8
        );
        if (credentials.size() != 2) {
            throw new IllegalArgumentException("Credential file must contain exactly two lines");
        }
        String appId = credentials.get(0);
        String appSecret = credentials.get(1);
        try (NativeProbe probe = new NativeProbe(new File(args[0]), new File(args[1]))) {
            probe.initializeSecurity(appId, appSecret);
            if (args.length == 4 && "--token-probe".equals(args[3])) {
                probe.request(appId, "thing.m.user.username.token.get", "2.0",
                        "{\"countryCode\":\"84\",\"username\":\"0000000000\",\"isUid\":false}",
                        null, null, null);
                return;
            }
            if (args.length >= 4 && ("--login-probe".equals(args[3]) || "--device-probe".equals(args[3]))) {
                try (LoginInput account = args.length >= 6
                        ? LoginInput.fromFile(new File(args[5]).toPath()) : probe.readConsoleLogin()) {
                    probe.loginProbe(appId, "--device-probe".equals(args[3]), account, exportPath).clear();
                }
                return;
            }
            String chKey = probe.getChKey(appId);
            byte[] postKey = probe.encryptPostData("probe-key", "probe-data".getBytes(StandardCharsets.UTF_8));
            String digest = probe.computeDigest("probe-data", "probe-key");
            String signature = probe.sign("a=probe||time=1||v=1.0");
            String repeatedSignature = probe.sign("a=probe||time=1||v=1.0");
            byte[] encryptionKey = probe.getEncryptoKey("offline-test-request", null);
            if (chKey == null || chKey.length() != 8 || postKey == null || postKey.length != 16
                    || digest == null || digest.length() != 32 || signature == null
                    || signature.length() != 64 || !signature.equals(repeatedSignature)) {
                throw new IllegalStateException("Native smoke test failed");
            }
            Arrays.fill(encryptionKey, (byte) 0);
            System.out.println("chKey.length=" + (chKey == null ? -1 : chKey.length()));
            System.out.println("postKey.length=" + (postKey == null ? -1 : postKey.length));
            System.out.println("digest.length=" + (digest == null ? -1 : digest.length()));
            System.out.println("signature.length=" + (signature == null ? -1 : signature.length()));
            System.out.println("signature.stable=" + (
                    signature != null && signature.equals(repeatedSignature)
            ));
        }
    }
}
