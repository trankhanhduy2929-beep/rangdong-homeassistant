package local.rangdong;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

final class CloudDevices {
    interface Api {
        JSONObject request(String api, String version, JSONObject payload) throws Exception;
    }

    private CloudDevices() {
    }

    static JSONArray collect(Api api) throws Exception {
        JSONObject homesResponse = api.request("m.life.group.location.list", "7.0", null);
        requireSuccess(homesResponse);
        JSONArray homes = array(homesResponse.get("result"));
        if (homes.size() > 100) {
            throw new IllegalStateException("Too many homes; refusing unbounded scan");
        }
        Set<Long> homeIds = new LinkedHashSet<>();
        for (Object item : homes) {
            if (!(item instanceof JSONObject)) {
                throw new IllegalStateException("Invalid home record");
            }
            JSONObject home = (JSONObject) item;
            Object rawId = home.get("gid");
            if (rawId == null) {
                rawId = home.get("id");
            }
            String homeId = String.valueOf(rawId);
            if (!homeId.matches("[1-9][0-9]{0,18}")) {
                throw new IllegalStateException("Invalid home ID");
            }
            homeIds.add(Long.parseLong(homeId));
        }
        Map<String, JSONObject> records = new LinkedHashMap<>();
        for (long homeId : homeIds) {
            JSONObject ownedPayload = new JSONObject();
            ownedPayload.put("gid", homeId);
            JSONObject owned = api.request("m.life.my.group.device.list", "2.2", ownedPayload);
            requireSuccess(owned);
            merge(records, array(owned.get("result")));
            JSONObject localPayload = new JSONObject();
            localPayload.put("homeId", homeId);
            localPayload.put("groupType", "homeGroup");
            JSONObject local = api.request("m.life.app.smart.local.device.list", "1.1", localPayload);
            requireSuccess(local);
            Object localResult = local.get("result");
            if (!(localResult instanceof JSONObject)) {
                throw new IllegalStateException("Invalid local-device result");
            }
            Object localDevices = ((JSONObject) localResult).get("deviceList");
            if (localDevices != null) {
                merge(records, array(localDevices));
            }
        }
        JSONArray result = new JSONArray();
        result.addAll(records.values());
        return result;
    }

    private static void requireSuccess(JSONObject response) {
        if (response == null || !Boolean.TRUE.equals(response.get("success"))) {
            throw new IllegalStateException("Cloud request rejected; scan stopped");
        }
    }

    private static JSONArray array(Object value) {
        if (!(value instanceof JSONArray)) {
            throw new IllegalStateException("Unexpected list response");
        }
        JSONArray array = (JSONArray) value;
        if (array.size() > 5000) {
            throw new IllegalStateException("Device list too large");
        }
        return array;
    }

    private static void merge(Map<String, JSONObject> records, JSONArray devices) {
        for (Object item : devices) {
            if (!(item instanceof JSONObject)) {
                throw new IllegalStateException("Invalid device record");
            }
            JSONObject device = (JSONObject) item;
            Object rawId = device.get("devId");
            Object rawKey = device.get("localKey");
            if (!(rawId instanceof String) || !(rawKey instanceof String)) {
                continue;
            }
            String deviceId = (String) rawId;
            String localKey = (String) rawKey;
            if (!deviceId.matches("[A-Za-z0-9_-]{4,128}")
                    || localKey.getBytes(StandardCharsets.UTF_8).length != 16
                    || localKey.codePoints().anyMatch(Character::isISOControl)) {
                continue;
            }
            JSONObject previous = records.get(deviceId);
            if (previous != null && !localKey.equals(previous.getString("local_key"))) {
                throw new IllegalStateException("Conflicting keys; refusing mixed snapshot");
            }
            JSONObject record = previous == null ? new JSONObject() : previous;
            record.put("device_id", deviceId);
            record.put("local_key", localKey);
            copyText(device, record, "name", "name");
            copyText(device, record, "productId", "product_id");
            records.put(deviceId, record);
            if (records.size() > 5000) {
                throw new IllegalStateException("Too many device records");
            }
        }
    }

    private static void copyText(JSONObject source, JSONObject destination, String from, String to) {
        Object value = source.get(from);
        if (value instanceof String && !((String) value).isEmpty() && ((String) value).length() <= 256) {
            destination.put(to, value);
        }
    }
}
