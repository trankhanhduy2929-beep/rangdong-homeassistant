package local.rangdong;

import com.github.unidbg.AndroidEmulator;
import com.github.unidbg.arm.backend.Unicorn2Factory;
import com.github.unidbg.linux.android.AndroidEmulatorBuilder;

public final class BackendSmoke {
    public static void main(String[] args) throws Exception {
        try (AndroidEmulator emulator = AndroidEmulatorBuilder.for32Bit()
                .addBackendFactory(new Unicorn2Factory(true)).build()) {
            if (emulator.getBackend() == null) {
                throw new IllegalStateException("Native backend unavailable");
            }
        }
        System.out.println("Native backend smoke passed");
    }
}
