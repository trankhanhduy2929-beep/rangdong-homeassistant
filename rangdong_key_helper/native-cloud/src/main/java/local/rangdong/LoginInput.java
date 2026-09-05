package local.rangdong;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Arrays;
import java.util.Locale;
import java.util.Set;

final class LoginInput implements AutoCloseable {
    final String username;
    final String countryCode;
    private final char[] password;

    private LoginInput(String username, String countryCode, char[] password) {
        this.username = username;
        this.countryCode = countryCode;
        this.password = password;
    }

    static LoginInput fromFile(Path path) throws Exception {
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.size(path) > 16384) {
            throw new IllegalArgumentException("Invalid account file");
        }
        Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS);
        for (PosixFilePermission permission : permissions) {
            if (!permission.name().startsWith("OWNER_")) {
                throw new IllegalArgumentException("Account file must be private to owner");
            }
        }
        byte[] bytes = Files.readAllBytes(path);
        JSONObject data = null;
        try {
            data = JSON.parseObject(new String(bytes, StandardCharsets.UTF_8));
            return fromJson(data);
        } finally {
            Arrays.fill(bytes, (byte) 0);
            if (data != null) {
                data.clear();
            }
        }
    }

    static LoginInput fromJson(JSONObject data) {
        if (data == null) {
            throw new IllegalArgumentException("Missing account data");
        }
        String username = null;
        String countryCode = "84";
        String password = null;
        for (String key : data.keySet()) {
            Object raw = data.get(key);
            if (!(raw instanceof String)) {
                throw new IllegalArgumentException("Account fields must be strings");
            }
            String value = (String) raw;
            String field = key.trim().toLowerCase(Locale.ROOT);
            if (Arrays.asList("phone", "email", "gmail", "e-mail", "mail", "username").contains(field)) {
                value = value.trim();
                if (value.isEmpty()) {
                    continue;
                }
                if (username != null && !username.equals(value)) {
                    throw new IllegalArgumentException("Conflicting account identifiers");
                }
                username = value;
            } else if ("country_code".equals(field)) {
                countryCode = value.trim();
            } else if ("password".equals(field)) {
                if (password != null) {
                    throw new IllegalArgumentException("Duplicate password field");
                }
                password = value;
            } else {
                throw new IllegalArgumentException("Unrecognized account field");
            }
        }
        if (username == null || username.length() > 254
                || !(username.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+") || username.matches("[0-9]{6,15}"))
                || !countryCode.matches("[1-9][0-9]{0,3}")
                || password == null || password.length() < 4 || password.length() > 128) {
            throw new IllegalArgumentException("Invalid account input");
        }
        return new LoginInput(username, countryCode, password.toCharArray());
    }

    String api() {
        return username.contains("@") ? "thing.m.user.email.password.login" : "thing.m.user.mobile.passwd.login";
    }

    String version() {
        return username.contains("@") ? "3.0" : "4.0";
    }

    String accountField() {
        return username.contains("@") ? "email" : "mobile";
    }

    String consumePasswordMd5() throws Exception {
        try {
            return Protocol.md5(new String(password));
        } finally {
            close();
        }
    }

    @Override
    public void close() {
        Arrays.fill(password, '\0');
    }
}
