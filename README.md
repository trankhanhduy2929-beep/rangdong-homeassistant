# Rạng Đông Smart for Home Assistant

Custom HACS integration for **Rạng Đông Smart** devices that supports direct
Tuya LAN control and keeps the previous QR authorization flow as an optional
fallback.

> Local mode is the recommended path when the Rạng Đông app shows
> “please use the designated app to scan the code to log in”.

[Open this repository in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=trankhanhduy2929-beep&repository=rangdong-homeassistant&category=integration)

## Features

- UDP LAN discovery of Tuya-compatible Rạng Đông Wi-Fi devices.
- Automatic detection of the device IP, device ID, product ID and protocol
  version where the device announces them.
- Direct TCP control on port `6668`; no cloud or MQTT connection is used in
  Local LAN mode.
- Automatic protocol probing for Tuya `3.5` through `3.1`.
- One-time `local_key` retrieval from a user-controlled Tuya IoT Cloud
  project. The project Access ID and Access Secret are not stored.
- One-time import from TinyTuya, Tuya API and common LocalTuya JSON exports.
- Authenticated Android bridge for one-time local helper uploads and automatic
  Device ID listing in the setup flow.
- Reuse of a `local_key` already present in a working Rạng Đông QR/cloud entry.
- A switch entity for each boolean DP and a diagnostic LAN status sensor with
  the current DP snapshot.
- `rangdong_smart.send_command` for numeric local DPs and legacy cloud DPs.
- Existing QR entries continue to work and can still be selected explicitly.

## Important limitation

LAN discovery does **not** reveal the device's `local_key`. The key is a
per-device credential and is required by the encrypted Tuya local protocol.
The setup flow scans the IP/ID first, then lets you retrieve the key once from
an authorized source, import a JSON export or enter it manually. The key is
verified against the LAN device before the entry is created.

Do not use the Rạng Đông account password as the local key. Never put a local
key, account password, token or APK secret in an issue, public log or GitHub
repository.

## HACS installation

1. Install and open HACS in Home Assistant.
2. Open **HACS → Integrations → ⋮ → Custom repositories**.
3. Add `trankhanhduy2929-beep/rangdong-homeassistant` and select **Integration**.
4. Download **Rạng Đông Smart** and restart Home Assistant.
5. Open **Settings → Devices & services → Add integration** and select
   **Rạng Đông Smart**.

## Local setup

1. Select **Local LAN (recommended)**.
2. Keep the Rạng Đông Wi-Fi device powered on and on the same LAN as Home
   Assistant.
3. Select the device found by the scan. If the list is empty, choose
   **Enter manually** and enter its IP address and device ID.
4. Select a local-key source:
   - **Android bridge** after a local helper has uploaded the Rạng Đông app
     records;
   - **Fetch once from Tuya Cloud** for a linked Tuya IoT developer project;
   - **Import JSON export** for TinyTuya/LocalTuya/Tuya API data;
   - **Existing authorized cloud entry** when a working QR entry already has
     the same device; or
   - **Enter local key manually**.
5. Leave **Auto** selected for protocol version unless the device requires a
   known version. The flow reads the device before saving the configuration.

The flow creates one config entry per device. Run **Add integration** again
for each additional Wi-Fi device.

### Where to obtain the local key

The official app normally does not display this key. Supported ways to obtain
it include:

- an authorized Tuya/Rạng Đông device export or local integration already
  containing the key;
- the Tuya developer/cloud device details for an account you control; or
- a private, consent-based extraction from your own logged-in Android device.

### Automatic one-time Tuya Cloud retrieval

The integration can retrieve keys from a Tuya IoT Cloud project that you
control:

1. Create or open a cloud project in the Tuya IoT Platform.
2. Link the Tuya/Rạng Đông app account or the exact device to that project and
   enable the device-management API permissions needed to list devices.
3. In the integration, select **Fetch once from Tuya Cloud**.
4. Enter the project **Access ID**, **Access Secret**, data center and Device
   ID.
5. Confirm the LAN address. The integration verifies the key locally and saves
   only the resulting local device configuration.

The Access ID, Access Secret and cloud response are not saved in the Home
Assistant config entry or diagnostics. The project can be disabled after a
successful import if it is not needed elsewhere.

Rạng Đông is an OEM app, so some accounts cannot be linked to a normal Tuya
IoT project. That server-side restriction cannot be bypassed by the
integration. Use a trusted JSON export or a private extraction from your own
Android phone when linking is unavailable.

### JSON import

Select **Import JSON export** and paste trusted data containing a Device ID and
one of these key fields: `key`, `local_key`, `localKey` or `localkey`. Supported
layouts include:

- TinyTuya `devices.json` arrays;
- Tuya Cloud/mobile API device objects;
- common LocalTuya exports; and
- dictionaries keyed by Device ID.

The JSON is processed in memory once. It is not stored or shown again. If the
export contains multiple devices, the setup flow shows a key-free device list
for selection.

APK analysis confirms that the logged-in Android SDK keeps the key in its
private device cache and exposes it to the app as `DeviceBean.localKey`. Reading
that private cache normally requires a rooted/debuggable test device or a
runtime inspection tool such as Frida. Do this only on your own account and
phone, keep the extracted key private, and never commit it to this repository.

### Android bridge (one-time local import)

The custom component cannot read another Android application's private storage
by itself. To avoid a Tuya IoT Cloud project, use a helper on the phone you
control to export records from the already logged-in Rạng Đông app, then send
that export to the authenticated Home Assistant endpoint:

```sh
curl -X POST \
  -H "Authorization: Bearer YOUR_HOME_ASSISTANT_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @rangdong-devices.json \
  http://HOME_ASSISTANT:8123/api/rangdong_smart/key-import
```

The payload can use `devId`/`deviceId` together with `localKey`, `local_key` or
`key`, plus optional `name`, `ip`, `productId` and `version`. After the POST,
choose **Android bridge** in the setup flow and press **Refresh key list**.
The flow lists Device IDs without displaying the raw key, probes each selected
device over LAN, and saves only the working local configuration. The bridge
keeps imported keys in memory only and removes a key after it is consumed.

To inspect only masked metadata or clear the transient registry:

```sh
curl -H "Authorization: Bearer YOUR_HOME_ASSISTANT_TOKEN" \
  http://HOME_ASSISTANT:8123/api/rangdong_smart/key-import

curl -X DELETE \
  -H "Authorization: Bearer YOUR_HOME_ASSISTANT_TOKEN" \
  http://HOME_ASSISTANT:8123/api/rangdong_smart/key-import
```

Use HTTPS or a trusted LAN when uploading an export. Never put the Rạng Đông
password, a Home Assistant token or a raw local key in a public issue or
repository. This bridge is an import channel; it does not pretend that a
username/password alone can bypass the OEM app's mobile API identity checks.

The LAN scanner itself cannot derive the key from the broadcast packet. Without
a matching local key, the integration can identify the device but cannot decrypt
status packets or send local commands.

## Network requirements

- Home Assistant and the device must be on the same IPv4 LAN/VLAN.
- Allow UDP discovery ports `6666`, `6667` and `7000`.
- Allow TCP device control port `6668`.
- Docker installations may need host networking so broadcast packets reach the
  physical LAN. For Home Assistant Container, use `network_mode: host` or an
  equivalent network design that forwards these ports.
- Guest Wi-Fi isolation, client isolation and routed VLANs commonly prevent
  discovery or control.

## Wi-Fi versus Zigbee devices

This local flow controls Tuya-compatible **Wi-Fi** devices. A Zigbee lamp or
sensor usually appears only behind its gateway and will not expose a usable
Wi-Fi local key. For Zigbee devices, pair the device with ZHA or Zigbee2MQTT,
or configure the gateway through a supported cloud/local integration.

## Raw DP command

Local devices use numeric DP IDs. The LAN status sensor shows the current DP
map in its attributes. Example for a power DP:

```yaml
action: rangdong_smart.send_command
data:
  device_id: "device-id-from-the-LAN-status-sensor"
  dp_id: 1
  value: true
```

Legacy QR/cloud entries continue to accept a named DP code:

```yaml
action: rangdong_smart.send_command
data:
  device_id: "device-id-from-the-cloud-status-sensor"
  code: switch_led
  value: true
```

Only send values supported by the device. An invalid DP type can be rejected
by the device.

## QR fallback

Selecting **Legacy cloud QR** keeps the previous User Code and QR flow. If the
Rạng Đông app repeatedly reports a designated-app error such as `E0020003`,
that is a server-side authorization restriction; changing the QR prefix does
not bypass it. Use Local LAN mode instead when a local key is available.

## Manual installation

Copy `custom_components/rangdong_smart` into:

```text
<config>/custom_components/rangdong_smart
```

Restart Home Assistant, then add **Rạng Đông Smart** from **Settings →
Devices & services**.

## Troubleshooting

- **No devices found:** verify host networking, same subnet, broadcast rules,
  and that the device is awake; try manual IP/ID entry.
- **Cannot connect:** check TCP `6668`, firewall rules and Wi-Fi client
  isolation.
- **Invalid local key:** confirm the key belongs to that exact device; leave
  protocol on Auto and retry.
- **Tuya Cloud key error:** verify the project data center, API permissions,
  linked account/device and Access ID/Secret. OEM Rạng Đông accounts might not
  support Tuya IoT linking.
- **Key not found in JSON:** ensure the export contains the exact Device ID and
  a 16-byte local key; do not paste the Rạng Đông account password.
- **Device is Zigbee:** use ZHA/Zigbee2MQTT or the gateway integration; the
  Wi-Fi scan cannot pair a Zigbee child directly.
- **IP changed:** open the integration entry and choose **Reconfigure**, then
  enter the new address and local key. A DHCP reservation is recommended for
  stable operation.

## Development

The installable component is under `custom_components/rangdong_smart`.
Validation commands used by the project are:

```sh
ruff check custom_components/rangdong_smart tests
PYTHONPATH=custom_components pytest -q
```

The repository intentionally contains no real account credentials, local
keys, cloud tokens or APK application secrets.

## License

The integration code is released under the MIT License. Rạng Đông, ThingClips,
Tuya and related product names are trademarks of their respective owners.
