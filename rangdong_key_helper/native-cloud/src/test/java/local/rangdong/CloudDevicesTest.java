package local.rangdong;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import java.util.ArrayList;
import java.util.List;

public final class CloudDevicesTest {
    private static int count;

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Cloud device test failed: " + (count + 1));
        }
        count++;
    }

    private static JSONObject ok(Object result) {
        JSONObject response = new JSONObject();
        response.put("success", true);
        response.put("result", result);
        return response;
    }

    private static JSONArray homes() {
        return JSON.parseArray("[{\"gid\":123},{\"id\":123}]");
    }

    public static void main(String[] args) throws Exception {
        List<String> calls = new ArrayList<>();
        JSONArray devices = CloudDevices.collect((api, version, payload) -> {
            calls.add(api);
            if (api.equals("m.life.group.location.list")) {
                check(version.equals("7.0") && payload == null);
                return ok(homes());
            }
            if (api.equals("m.life.my.group.device.list")) {
                check(version.equals("2.2") && payload.getLongValue("gid") == 123);
                return ok(JSON.parseArray("[{\"devId\":\"test_device\",\"localKey\":\"0123456789abcdef\","
                        + "\"name\":\"Đèn thử\",\"devKey\":\"not-exported\"},"
                        + "{\"devId\":\"bad_length\",\"localKey\":\"short\"},"
                        + "{\"devId\":\"missing_local_key\",\"devKey\":\"0123456789abcdef\"} ]"));
            }
            check(api.equals("m.life.app.smart.local.device.list") && version.equals("1.1"));
            check(payload.getLongValue("homeId") == 123 && payload.getString("groupType").equals("homeGroup"));
            return ok(JSON.parseObject("{\"deviceList\":[{\"devId\":\"test_device\","
                    + "\"localKey\":\"0123456789abcdef\",\"productId\":\"test_product\"}]}"));
        });
        check(calls.size() == 3 && devices.size() == 1);
        JSONObject device = devices.getJSONObject(0);
        check(device.getString("device_id").equals("test_device"));
        check(device.getString("name").equals("Đèn thử"));
        check(!device.containsKey("devKey") && device.getString("product_id").equals("test_product"));
        check(CloudDevices.collect((api, version, payload) -> ok(new JSONArray())).isEmpty());
        JSONArray withoutLocalDevices = CloudDevices.collect((api, version, payload) -> {
            if (payload == null) {
                return ok(homes());
            }
            if (payload.containsKey("gid")) {
                return ok(JSON.parseArray("[{\"devId\":\"test_device\",\"localKey\":\"0123456789abcdef\"}]"));
            }
            return ok(new JSONObject());
        });
        check(withoutLocalDevices.size() == 1);
        int[] rejectedCalls = {0};
        try {
            CloudDevices.collect((api, version, payload) -> {
                rejectedCalls[0]++;
                return JSON.parseObject("{\"success\":false,\"errorCode\":\"SESSION_INVALID\"}");
            });
            throw new AssertionError("Rejected session accepted");
        } catch (IllegalStateException expected) {
            check(rejectedCalls[0] == 1);
        }
        try {
            CloudDevices.collect((api, version, payload) -> ok(JSON.parseArray("[{\"gid\":\"../../invalid\"}]")));
            throw new AssertionError("Invalid home ID accepted");
        } catch (IllegalStateException expected) {
            count++;
        }
        try {
            CloudDevices.collect((api, version, payload) -> {
                if (payload == null) {
                    return ok(homes());
                }
                if (payload.containsKey("gid")) {
                    return ok(JSON.parseArray("[{\"devId\":\"test_device\",\"localKey\":\"0123456789abcdef\"}]"));
                }
                return ok(JSON.parseObject("{\"deviceList\":[{\"devId\":\"test_device\",\"localKey\":\"abcdef0123456789\"}]}"));
            });
            throw new AssertionError("Conflicting local keys accepted");
        } catch (IllegalStateException expected) {
            count++;
        }
        try {
            CloudDevices.collect((api, version, payload) -> ok(new JSONObject()));
            throw new AssertionError("Unknown response shape accepted");
        } catch (IllegalStateException expected) {
            count++;
        }
        System.out.println("cloudDevices.testsPassed=" + count);
    }
}
