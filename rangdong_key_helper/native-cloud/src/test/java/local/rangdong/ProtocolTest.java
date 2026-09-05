package local.rangdong;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.Base64;
import java.util.Map;
import java.util.TreeMap;

public final class ProtocolTest {
    private static int count;

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Protocol test failed: " + (count + 1));
        }
        count++;
    }

    public static void main(String[] args) throws Exception {
        byte[] key = new byte[16];
        byte[] nonce = new byte[12];
        byte[] plaintext = new byte[16];
        String encrypted = Protocol.encrypt(key, plaintext, nonce);
        check(Protocol.hex(Base64.getDecoder().decode(encrypted)).equals(
                "0000000000000000000000000388dace60b6a392f328c2b971b2fe78ab6e47d42cec13bdf53a67b21257bddf"));
        check(Arrays.equals(Protocol.decrypt(key, encrypted), plaintext));
        byte[] changed = Base64.getDecoder().decode(encrypted);
        changed[changed.length - 1] ^= 1;
        try {
            Protocol.decrypt(key, Base64.getEncoder().encodeToString(changed));
            throw new AssertionError("Tampered GCM tag accepted");
        } catch (GeneralSecurityException expected) {
            count++;
        }
        try {
            Protocol.decrypt(key, "AA==");
            throw new AssertionError("Truncated envelope accepted");
        } catch (IllegalArgumentException expected) {
            count++;
        }
        try {
            Protocol.encrypt(key, plaintext, new byte[8]);
            throw new AssertionError("Invalid nonce accepted");
        } catch (IllegalArgumentException expected) {
            count++;
        }
        Map<String, String> params = new TreeMap<>();
        params.put("v", "2.0");
        params.put("a", "probe");
        params.put("postData", "abc");
        params.put("lang", "");
        params.put("sdkVersion", "unsigned");
        params.put("sign", "unsigned");
        check(Protocol.canonical(params).equals(
                "a=probe||postData=3cd24fb09001509828e17f72d6963f7d||v=2.0"));
        check(params.get("postData").equals("abc"));
        byte[] responseKey = "0123456789abcdef".getBytes(StandardCharsets.UTF_8);
        String signature = Protocol.md5("result=payload||t=123||0123456789abcdef");
        Protocol.verifyResponse(responseKey, "payload", 123, signature);
        count++;
        try {
            Protocol.verifyResponse(responseKey, "changed", 123, signature);
            throw new AssertionError("Tampered response signature accepted");
        } catch (GeneralSecurityException expected) {
            count++;
        }
        try {
            Protocol.verifyResponse(responseKey, "payload", 123, null);
            throw new AssertionError("Missing response signature accepted");
        } catch (GeneralSecurityException expected) {
            count++;
        }
        System.out.println("protocol.testsPassed=" + count);
    }
}
