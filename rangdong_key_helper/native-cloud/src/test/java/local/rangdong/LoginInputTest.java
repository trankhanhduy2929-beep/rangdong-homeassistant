package local.rangdong;

import com.alibaba.fastjson.JSONObject;

public final class LoginInputTest {
    public static void main(String[] args) throws Exception {
        JSONObject data = new JSONObject();
        data.put("country_code", "84");
        data.put("phone", "");
        data.put("Gmail", "test@example.invalid");
        data.put("password", " test password ");
        try (LoginInput input = LoginInput.fromJson(data)) {
            check(input.api().equals("thing.m.user.email.password.login"));
            check(input.version().equals("3.0"));
            check(input.accountField().equals("email"));
            check(input.consumePasswordMd5().equals(Protocol.md5(" test password ")));
        }
        data.remove("Gmail");
        data.put("phone", "0000000000");
        try (LoginInput input = LoginInput.fromJson(data)) {
            check(input.api().equals("thing.m.user.mobile.passwd.login"));
            check(input.version().equals("4.0"));
            check(input.accountField().equals("mobile"));
        }
        data.put("email", "other@example.invalid");
        try {
            LoginInput.fromJson(data);
            throw new AssertionError("Ambiguous account accepted");
        } catch (IllegalArgumentException expected) {
            count++;
        }
        data.remove("phone");
        data.put("password", "");
        try {
            LoginInput.fromJson(data);
            throw new AssertionError("Empty password accepted");
        } catch (IllegalArgumentException expected) {
            count++;
        }
        java.nio.file.Path directory = java.nio.file.Files.createTempDirectory("rd-login-test-");
        java.nio.file.Path accountFile = directory.resolve("account.json");
        java.nio.file.Path exportFile = directory.resolve("keys.json");
        try {
            data.put("password", "test password");
            java.nio.file.Files.write(accountFile, data.toJSONString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
            java.nio.file.Files.setPosixFilePermissions(accountFile,
                    java.nio.file.attribute.PosixFilePermissions.fromString("rw-------"));
            try (LoginInput input = LoginInput.fromFile(accountFile)) {
                check(input.accountField().equals("email"));
            }
            java.nio.file.Files.setPosixFilePermissions(accountFile,
                    java.nio.file.attribute.PosixFilePermissions.fromString("rw-r--r--"));
            try {
                LoginInput.fromFile(accountFile);
                throw new AssertionError("Public account file accepted");
            } catch (IllegalArgumentException expected) {
                count++;
            }
            NativeProbe.writePrivateExport(exportFile, new com.alibaba.fastjson.JSONArray());
            check(java.nio.file.Files.getPosixFilePermissions(exportFile).equals(
                    java.nio.file.attribute.PosixFilePermissions.fromString("rw-------")));
            try {
                NativeProbe.writePrivateExport(exportFile, new com.alibaba.fastjson.JSONArray());
                throw new AssertionError("Existing key file overwritten");
            } catch (java.nio.file.FileAlreadyExistsException expected) {
                count++;
            }
        } finally {
            java.nio.file.Files.deleteIfExists(accountFile);
            java.nio.file.Files.deleteIfExists(exportFile);
            java.nio.file.Files.delete(directory);
        }
        System.out.println("loginInput.testsPassed=" + count);
    }

    private static int count;

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Login input test failed");
        }
        count++;
    }
}
