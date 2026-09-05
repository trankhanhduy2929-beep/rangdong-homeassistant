package local.rangdong;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

final class Protocol {
    private static final Set<String> SIGNED_KEYS = new HashSet<>(Arrays.asList(
            "a", "v", "lat", "lon", "lang", "deviceId", "appVersion", "ttid", "isH5",
            "h5Token", "os", "clientId", "postData", "time", "requestId", "et", "n4h5", "sid", "chKey", "sp"));

    private Protocol() {
    }

    static String encrypt(byte[] key, byte[] plaintext, byte[] nonce) throws GeneralSecurityException {
        if (nonce.length != 12) {
            throw new IllegalArgumentException("Nonce must contain 12 bytes");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
        byte[] ciphertext = cipher.doFinal(plaintext);
        byte[] envelope = Arrays.copyOf(nonce, nonce.length + ciphertext.length);
        System.arraycopy(ciphertext, 0, envelope, nonce.length, ciphertext.length);
        return Base64.getEncoder().encodeToString(envelope);
    }

    static byte[] decrypt(byte[] key, String encoded) throws GeneralSecurityException {
        if (encoded.length() > 1048576) {
            throw new IllegalArgumentException("Encrypted response too large");
        }
        byte[] envelope = Base64.getDecoder().decode(encoded);
        if (envelope.length < 28) {
            throw new IllegalArgumentException("Encrypted response too short");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"),
                new GCMParameterSpec(128, Arrays.copyOfRange(envelope, 0, 12)));
        return cipher.doFinal(Arrays.copyOfRange(envelope, 12, envelope.length));
    }

    static String canonical(Map<String, String> params) throws GeneralSecurityException {
        StringBuilder canonical = new StringBuilder();
        for (Map.Entry<String, String> entry : new TreeMap<>(params).entrySet()) {
            String value = entry.getValue();
            if (!SIGNED_KEYS.contains(entry.getKey()) || value == null || value.isEmpty()) {
                continue;
            }
            if ("postData".equals(entry.getKey())) {
                String digest = md5(value);
                value = digest.substring(8, 16) + digest.substring(0, 8)
                        + digest.substring(24, 32) + digest.substring(16, 24);
            }
            if (canonical.length() > 0) {
                canonical.append("||");
            }
            canonical.append(entry.getKey()).append('=').append(value);
        }
        return canonical.toString();
    }

    static void verifyResponse(byte[] key, String result, long time, String signature)
            throws GeneralSecurityException {
        if (signature == null || !signature.matches("[A-Fa-f0-9]{32}")) {
            throw new GeneralSecurityException("Missing or invalid response signature");
        }
        String expected = md5("result=" + result + "||t=" + time + "||"
                + new String(key, StandardCharsets.UTF_8));
        if (!MessageDigest.isEqual(expected.getBytes(StandardCharsets.US_ASCII),
                signature.toLowerCase(java.util.Locale.ROOT).getBytes(StandardCharsets.US_ASCII))) {
            throw new GeneralSecurityException("Response signature verification failed");
        }
    }

    static String md5(String value) throws GeneralSecurityException {
        return hex(MessageDigest.getInstance("MD5").digest(value.getBytes(StandardCharsets.UTF_8)));
    }

    static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte value : bytes) {
            result.append(String.format("%02x", value & 255));
        }
        return result.toString();
    }
}
