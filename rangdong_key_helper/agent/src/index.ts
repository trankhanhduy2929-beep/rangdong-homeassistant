import Java from "frida-java-bridge";

type DeviceRecord = {
  device_id: string;
  local_key: string;
  name?: string;
  host?: string;
  product_id?: string;
  protocol_version?: string;
};

const retainedCallbacks: unknown[] = [];
let callbackCounter = 0;

function perform<T>(operation: () => T | Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    Java.perform(() => {
      try {
        Promise.resolve(operation()).then(resolve, reject);
      } catch (error) {
        reject(error);
      }
    });
  });
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function javaText(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  try {
    return String((value as { toString(): string }).toString()).trim();
  } catch (_error) {
    return String(value).trim();
  }
}

function safeGetter(instance: any, names: string[]): string {
  for (const name of names) {
    try {
      const method = instance[name];
      if (typeof method === "function") {
        const value = javaText(method.call(instance));
        if (value.length > 0) {
          return value;
        }
      }
    } catch (_error) {
      continue;
    }
  }
  return "";
}

function recordFromBean(instance: any, homeName = ""): DeviceRecord | null {
  const deviceId = safeGetter(instance, ["getDevId", "getGwId", "getId"]);
  const localKey = safeGetter(instance, ["getLocalKey"]);
  if (deviceId.length < 4 || localKey.length !== 16) {
    return null;
  }
  const name = safeGetter(instance, ["getName", "getDeviceName"]) || homeName;
  const host = safeGetter(instance, ["getIp", "getLocalIp", "getLastIp"]);
  const productId = safeGetter(instance, ["getProductId", "getProductKey"]);
  const protocolVersion = safeGetter(instance, ["getPv", "getProtocolVersion"]);
  return {
    device_id: deviceId,
    local_key: localKey,
    ...(name ? { name } : {}),
    ...(host ? { host } : {}),
    ...(productId ? { product_id: productId } : {}),
    ...(protocolVersion ? { protocol_version: protocolVersion } : {}),
  };
}

function listItems(list: any): any[] {
  if (list === null || list === undefined) {
    return [];
  }
  if (Array.isArray(list)) {
    return list;
  }
  try {
    const size = Number(list.size());
    const items: any[] = [];
    for (let index = 0; index < size; index += 1) {
      items.push(list.get(index));
    }
    return items;
  } catch (_error) {
    return [];
  }
}

function mergeRecord(records: Map<string, DeviceRecord>, record: DeviceRecord | null): void {
  if (record === null) {
    return;
  }
  const previous = records.get(record.device_id);
  records.set(record.device_id, {
    device_id: record.device_id,
    local_key: record.local_key,
    name: record.name || previous?.name,
    host: record.host || previous?.host,
    product_id: record.product_id || previous?.product_id,
    protocol_version: record.protocol_version || previous?.protocol_version,
  });
}

function collectHomeBeans(homeList: any): Map<string, DeviceRecord> {
  const records = new Map<string, DeviceRecord>();
  for (const home of listItems(homeList)) {
    const homeName = safeGetter(home, ["getName"]);
    for (const getter of ["getDeviceList", "getSharedDeviceList"]) {
      let devices: any = null;
      try {
        devices = home[getter]();
      } catch (_error) {
        continue;
      }
      for (const device of listItems(devices)) {
        mergeRecord(records, recordFromBean(device, homeName));
      }
    }
  }
  return records;
}

function retainCallback(instance: unknown): () => void {
  retainedCallbacks.push(instance);
  return () => {
    const index = retainedCallbacks.indexOf(instance);
    if (index >= 0) {
      retainedCallbacks.splice(index, 1);
    }
  };
}

function callbackName(label: string): string {
  callbackCounter += 1;
  return `com.rangdong.helper.${label}${Date.now()}${callbackCounter}`;
}

function login(countryCode: string, phone: string, suppliedPassword: string): Promise<object> {
  return perform(() => new Promise((resolve) => {
    const ThingHomeSdk = Java.use("com.thingclips.smart.home.sdk.ThingHomeSdk");
    const LoginCallback = Java.use(
      "com.thingclips.smart.android.user.api.ILoginCallback",
    );
    const user = ThingHomeSdk.getUserInstance();
    if (user === null) {
      resolve({ ok: false, code: "sdk_not_ready", message: "SDK chưa sẵn sàng." });
      return;
    }
    if (Boolean(user.isLogin())) {
      const currentUser = user.getUser();
      const currentPhone = safeGetter(currentUser, ["getMobile", "getUsername"])
        .replace(/\D/g, "");
      const requestedPhone = phone.replace(/\D/g, "");
      if (
        currentPhone.length >= 4
        && requestedPhone.length >= 4
        && currentPhone.slice(-4) !== requestedPhone.slice(-4)
      ) {
        resolve({
          ok: false,
          code: "different_account",
          message: "App đang đăng nhập tài khoản khác. Hãy đăng xuất trên điện thoại trước.",
        });
        return;
      }
      resolve({ ok: true, already_logged_in: true });
      return;
    }

    let finished = false;
    let release = () => {};
    const complete = (result: object): void => {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timeout);
      release();
      resolve(result);
    };
    const Callback = Java.registerClass({
      name: callbackName("LoginCallback"),
      implements: [LoginCallback],
      methods: {
        onSuccess(_user: unknown): void {
          complete({ ok: true, already_logged_in: false });
        },
        onError(code: unknown, message: unknown): void {
          complete({
            ok: false,
            code: javaText(code).slice(0, 64),
            message: javaText(message).slice(0, 240),
          });
        },
      },
    });
    const callback = Callback.$new();
    release = retainCallback(callback);
    const timeout = setTimeout(
      () => complete({ ok: false, code: "timeout", message: "Đăng nhập quá thời gian." }),
      45000,
    );

    let password = suppliedPassword;
    Java.scheduleOnMainThread(() => {
      try {
        user.loginWithPhonePassword(countryCode, phone, password, callback);
      } catch (error) {
        complete({
          ok: false,
          code: "sdk_exception",
          message: javaText(error).slice(0, 240),
        });
      } finally {
        password = "";
        suppliedPassword = "";
      }
    });
  }));
}

function queryHomes(): Promise<Map<string, DeviceRecord>> {
  return new Promise((resolve, reject) => {
    const ThingHomeSdk = Java.use("com.thingclips.smart.home.sdk.ThingHomeSdk");
    const HomeListCallback = Java.use(
      "com.thingclips.smart.home.sdk.callback.IThingGetHomeListCallback",
    );
    const manager = ThingHomeSdk.getHomeManagerInstance();
    if (manager === null) {
      reject(new Error("Home manager is unavailable"));
      return;
    }

    let finished = false;
    let release = () => {};
    const complete = (records: Map<string, DeviceRecord> | Error): void => {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timeout);
      release();
      if (records instanceof Error) {
        reject(records);
      } else {
        resolve(records);
      }
    };
    const Callback = Java.registerClass({
      name: callbackName("HomeListCallback"),
      implements: [HomeListCallback],
      methods: {
        onSuccess(homes: unknown): void {
          const summaries = listItems(homes);
          Promise.all(summaries.map(async (summary) => {
            try {
              return await queryHomeDetail(manager, summary);
            } catch (_error) {
              return summary;
            }
          })).then(
            (details) => complete(collectHomeBeans(details)),
            (error) => complete(error instanceof Error ? error : new Error(javaText(error))),
          );
        },
        onError(code: unknown, message: unknown): void {
          complete(new Error(`${javaText(code)}: ${javaText(message)}`));
        },
      },
    });
    const callback = Callback.$new();
    release = retainCallback(callback);
    const timeout = setTimeout(
      () => complete(new Error("Home list timeout")),
      35000,
    );
    Java.scheduleOnMainThread(() => manager.queryHomeList(callback));
  });
}

function queryHomeDetail(manager: any, summary: any): Promise<any> {
  return new Promise((resolve, reject) => {
    const HomeCallback = Java.use(
      "com.thingclips.smart.home.sdk.callback.IThingHomeResultCallback",
    );
    const homeIdText = safeGetter(summary, ["getHomeId"]);
    const homeId = Number(homeIdText);
    if (!Number.isSafeInteger(homeId) || homeId <= 0) {
      resolve(summary);
      return;
    }

    let finished = false;
    let release = () => {};
    const complete = (result: any, error?: Error): void => {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timeout);
      release();
      if (error !== undefined) {
        reject(error);
      } else {
        resolve(result);
      }
    };
    const Callback = Java.registerClass({
      name: callbackName("HomeDetailCallback"),
      implements: [HomeCallback],
      methods: {
        onSuccess(home: unknown): void {
          complete(home || summary);
        },
        onError(code: unknown, message: unknown): void {
          complete(null, new Error(`${javaText(code)}: ${javaText(message)}`));
        },
      },
    });
    const callback = Callback.$new();
    release = retainCallback(callback);
    const timeout = setTimeout(
      () => complete(null, new Error("Home detail timeout")),
      30000,
    );
    Java.scheduleOnMainThread(() => manager.queryHomeInfo(homeId, callback));
  });
}

function chooseClass(className: string): Promise<DeviceRecord[]> {
  return new Promise((resolve) => {
    const records: DeviceRecord[] = [];
    try {
      Java.choose(className, {
        onMatch(instance: unknown): void {
          const record = recordFromBean(instance);
          if (record !== null) {
            records.push(record);
          }
        },
        onComplete(): void {
          resolve(records);
        },
      });
    } catch (_error) {
      resolve(records);
    }
  });
}

async function collect(): Promise<DeviceRecord[]> {
  return perform(async () => {
    let records: Map<string, DeviceRecord>;
    try {
      records = await queryHomes();
    } catch (_error) {
      records = new Map<string, DeviceRecord>();
    }
    const candidateClasses = [
      "com.thingclips.smart.sdk.bean.DeviceBean",
      "com.thingclips.sdk.config.bean.LocalDeviceBean",
      "com.thingclips.smart.interior.device.bean.GwDevResp",
      "com.thingclips.smart.interior.device.bean.GroupRespBean",
    ];
    for (const className of candidateClasses) {
      const heapRecords = await chooseClass(className);
      for (const record of heapRecords) {
        mergeRecord(records, record);
      }
    }
    return Array.from(records.values());
  });
}

function status(): Promise<object> {
  return perform(() => {
    const ThingHomeSdk = Java.use("com.thingclips.smart.home.sdk.ThingHomeSdk");
    const user = ThingHomeSdk.getUserInstance();
    return {
      logged_in: user !== null && Boolean(user.isLogin()),
    };
  });
}

function ping(): Promise<object> {
  return perform(async () => {
    Java.use("com.thingclips.smart.home.sdk.ThingHomeSdk");
    Java.use("com.thingclips.smart.sdk.bean.DeviceBean");
    const ThingHomeSdk = Java.use("com.thingclips.smart.home.sdk.ThingHomeSdk");
    for (let attempt = 0; attempt < 20; attempt += 1) {
      try {
        if (ThingHomeSdk.getUserInstance() !== null) {
          return { ok: true, java: Java.available };
        }
      } catch (_error) {
      }
      await delay(500);
    }
    return { ok: false, java: Java.available };
  });
}

rpc.exports = {
  collect,
  login,
  ping,
  status,
};
