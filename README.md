# Rạng Đông Smart for Home Assistant

Custom HACS integration for **Rạng Đông Smart** devices using the
ThingClips/Tuya cloud authorization flow. It uses a case-sensitive **User Code
and QR approval** and never asks Home Assistant users to enter their phone
number or account password.

> Experimental fallback integration: use Home Assistant's built-in **Tuya**
> integration first when it already exposes the required device entities.

[Open this repository in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=trankhanhduy2929-beep&repository=rangdong-homeassistant&category=integration)

## Features

- QR/User Code authorization with token refresh handled by the Tuya sharing SDK.
- Cloud-push device updates through the SDK-managed MQTT connection.
- One generic cloud-status sensor for each discovered device.
- Redacted DP/status attributes for diagnosing unsupported models.
- `rangdong_smart.send_command` for a manually specified Tuya data point.
- Redacted Home Assistant diagnostics.

The integration does not implement direct local LAN or BLE control and does not
yet create model-specific light, switch, climate, or cover entities.
It declares Home Assistant's built-in Tuya integration as a dependency, so
Home Assistant supplies the matching SDK version instead of letting two
integrations compete over different SDK versions.

## HACS installation

1. Install and open HACS in Home Assistant.
2. Use the link above, or open **HACS → Integrations → ⋮ → Custom repositories**.
3. Add `trankhanhduy2929-beep/rangdong-homeassistant` and choose **Integration**.
4. Download **Rạng Đông Smart (Tuya QR)** and restart Home Assistant.
5. Open **Settings → Devices & services → Add integration** and choose
   **Rạng Đông Smart (Tuya QR)**.

The repository is intended to be installed as a custom repository until it is
accepted into the default HACS catalog.

## Authorization

1. In Rạng Đông Smart, open **Settings → Account and Security → User Code**.
2. Enter the code in the Home Assistant config flow; preserve capitalization.
3. Scan the QR code shown by Home Assistant with Rạng Đông Smart and approve
   the authorization.
4. Return to Home Assistant and finish the flow.

Never put an account password, access token, refresh token, local key, or QR
token in this repository, an issue, or a public log.

## Manual installation

Copy `custom_components/rangdong_smart` into:

```text
<config>/custom_components/rangdong_smart
```

Restart Home Assistant and add the integration from **Settings → Devices &
services**.

## Sending a raw DP command

Use the service only when the device DP code and value type are known:

```yaml
action: rangdong_smart.send_command
data:
  device_id: "device-id-from-summary-sensor"
  code: switch_led
  value: true
```

An invalid DP command can make a device reject the request. Prefer the built-in
Tuya integration's model-specific entities for everyday control.

## Releases

The installable integration lives under `custom_components/rangdong_smart`.
HACS installs that source directory from the repository. Pushing a tag such as
`v0.1.1` also runs the release workflow and attaches a clean
`rangdong_smart-v0.1.1.zip` archive for manual downloads. The ZIP is generated
at release time and is intentionally not committed to the source tree.

For a new release, update the integration version in
`custom_components/rangdong_smart/manifest.json`, commit it, and push a tag
with the same version, for example:

```sh
git tag -a v0.1.1 -m "Release v0.1.1"
git push origin main v0.1.1
```

The release workflow reruns Hassfest and HACS validation, then checks that the
tag and manifest versions match before it publishes the release.

## Repository owner checklist

Before requesting inclusion in the default HACS catalog, keep the repository
public, enable Issues, set a short GitHub description, and add useful topics
such as `home-assistant`, `hacs`, `custom-component`, `rang-dong`, and `tuya`.
The HACS and Home Assistant validation workflows must pass, and a published
GitHub Release should exist.

## Troubleshooting

- If QR authorization expires, restart the config flow and generate a new QR.
- If a newly added device is missing, reload the integration or restart Home
  Assistant.
- If diagnostics are requested, use Home Assistant's **Download diagnostics**;
  do not share raw config-entry data.

## Status

Static checks, import smoke tests, and helper tests pass with Home Assistant
2026.8.3, Python 3.14, and `tuya-device-sharing-sdk` 0.2.14. Real account and
physical-device testing is still required for a production claim.

## License

The integration code is released under the MIT License. Rạng Đông, ThingClips,
Tuya, and related product names are trademarks of their respective owners.
