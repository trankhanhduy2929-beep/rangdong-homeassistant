"""Constants for the Rạng Đông Android helper."""

from __future__ import annotations

from dataclasses import dataclass

ADDON_PORT = 8099
DEFAULT_ADB_PORT = 5555
DEFAULT_PACKAGE_NAME = "com.rd.smart"
FRIDA_VERSION = "17.17.0"
FRIDA_LOCAL_PORT = 27889
FRIDA_REMOTE_PORT = 27888
FRIDA_REMOTE_PATH = f"/data/local/tmp/rd-frida-server-{FRIDA_VERSION}"
FRIDA_PID_PATH = f"{FRIDA_REMOTE_PATH}.pid"
FRIDA_RELEASE_BASE = f"https://github.com/frida/frida/releases/download/{FRIDA_VERSION}"
HOME_ASSISTANT_BRIDGE_URL = "http://supervisor/core/api/rangdong_smart/key-import"
HOME_ASSISTANT_FLOW_URL = "http://supervisor/core/api/config/config_entries/flow"
MAX_FRIDA_DOWNLOAD_BYTES = 128 * 1024 * 1024
MAX_REQUEST_BYTES = 16 * 1024


@dataclass(frozen=True, slots=True)
class FridaAsset:
    """Describe a verified Frida server release asset."""

    platform_arch: str
    sha256: str
    executable_sha256: str

    @property
    def filename(self) -> str:
        """Return the GitHub release filename."""

        return f"frida-server-{FRIDA_VERSION}-android-{self.platform_arch}.xz"

    @property
    def url(self) -> str:
        """Return the fixed release URL."""

        return f"{FRIDA_RELEASE_BASE}/{self.filename}"


FRIDA_ASSETS = {
    "arm64-v8a": FridaAsset(
        "arm64",
        "09d1fad867b27d69562a79289f4c412e85867f5d38ab72877036ed35e4223021",
        "55ef78c3f3e7a55122ca7e0051e2a356d0ff1d9744d84c1660291f90400588e7",
    ),
    "armeabi-v7a": FridaAsset(
        "arm",
        "a102c7f83fce8089394c3cc9a05812c841e8f254a80bcf7162280d7c1cbea208",
        "ae099158c275b2235a0278e6a6ea881beabb64f0155de36d4b2df0bc5cd7e21e",
    ),
    "x86": FridaAsset(
        "x86",
        "18ceb75ccf4f5619b2104b1e3852f0a87fabc38838074d1e0b4179cd370220db",
        "63fed00f7cb418d28fea35d92d7b290f266688288258e7ec1f03202b9adca243",
    ),
    "x86_64": FridaAsset(
        "x86_64",
        "5f0671fbeaee0b1ee66b1536c3eae966d58765b7e3954ea49932e5931e43bd6c",
        "b34a33bdbcd2f737ef59811ca57a4c2675a528b7ffae71acd4c35337d3cb93f5",
    ),
}
