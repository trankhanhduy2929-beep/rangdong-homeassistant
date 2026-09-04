# Rạng Đông Key Helper

This Home Assistant app (formerly called an add-on) imports `local_key` values
from the original Rạng Đông Android app on a phone you control. It does not
require a Tuya IoT Cloud project.

## Requirements

- Home Assistant OS with the **Rạng Đông Smart** custom integration installed.
- An Android phone on the same LAN as Home Assistant.
- The official Rạng Đông app installed as `com.rd.smart`.
- The phone is **rooted**, and its root manager can grant root to the ADB shell.
- Android **Developer options → Wireless debugging** is enabled.

Wireless ADB by itself is not enough on an unrooted phone. The Rạng Đông APK is
not debuggable and disables Android backup, so the helper cannot attach to the
private app process without root.

## First-time ADB pairing

1. On Android, open **Developer options → Wireless debugging**.
2. Select **Pair device with pairing code**.
3. Enter the phone IP, temporary pairing port and six-digit code in the helper.
4. Select **Pair ADB** before the Android pairing screen expires.
5. Return to the main Wireless debugging screen and copy its separate
   **IP address & port** into **ADB connection port**.
6. Approve the root request from Magisk or the installed root manager when the
   helper first checks the device.

Android often assigns different pairing and connection ports. A successful
pairing does not mean port `5555` is the correct connection port.

## Import with an existing app session

1. Sign in to the Rạng Đông app on the phone and let its home/device list load.
2. Open the helper Ingress page and select **Scan using current app session**.
3. Wait for the helper to show only masked key values.
4. In Home Assistant, open **Settings → Devices & services → Add integration →
   Rạng Đông Smart**.
5. Select **Local LAN → Android bridge**, choose the imported Device ID and
   finish setup. The integration verifies the key against the LAN device.

## Sign in from the helper

If the Android app is signed out, enter the country code, phone number and
password, then select **Sign in & scan**. The Linux container does not imitate
the private cloud protocol. Instead, Frida invokes
`ThingHomeSdk.getUserInstance().loginWithPhonePassword(...)` inside the
original app process, then asks that SDK for the user's homes and devices.

The password is not written to add-on options, files, logs or the repository.
It exists temporarily in browser, Python and Android process memory during the
request. If the provider requires a captcha, verification ticket or another
interactive challenge, sign in with the official app and use the existing
session method.

## Security behavior

- The web UI is available only through administrator-only Home Assistant
  Ingress, verifies `X-Remote-User-Id` against Home Assistant's administrator
  group and uses a per-process CSRF token.
- A Frida server release is downloaded from the official Frida GitHub release,
  matched to the Android ABI and verified against a pinned SHA-256 checksum.
- Frida binds to Android loopback and is reached through a container-local ADB
  port forward. The helper stops its Frida process after each operation.
- Full local keys are sent only to the authenticated Home Assistant bridge.
  The UI, successful responses and logs contain masked values only.
- Imported bridge records live in Home Assistant memory until consumed,
  cleared or Home Assistant restarts. A key accepted by local setup is then
  stored in that integration config entry because it is required for encrypted
  Tuya LAN communication.

Stop or uninstall the helper after completing the import if it is no longer
needed. Use **Clear temporary bridge keys** before stopping if setup was not
completed.

Project-authored code is MIT licensed. The image and compiled agent also use
Frida components under their upstream licenses; see `THIRD_PARTY_NOTICES.md`
and `LICENSE.frida.txt` in the repository and container image.

## Troubleshooting

- **ADB pairing failed:** generate a new pairing code and use the temporary
  port shown in the pairing dialog.
- **ADB connection failed:** use the port on the main Wireless debugging page,
  which commonly changes after a reboot or toggle.
- **Root required:** grant root to `shell`/ADB in the root manager. A non-rooted
  device is not supported.
- **App not logged in:** sign in through the helper or open the official app,
  complete any captcha and retry with its current session.
- **No local keys:** open the device list in the app first. Hub subdevices may
  not have an independently usable LAN key or IP address.
- **SDK missing after an app update:** the OEM may have changed its package or
  ThingClips SDK classes; update the helper before trying again.
