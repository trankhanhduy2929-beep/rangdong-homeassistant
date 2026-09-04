# Third-party notices

The Rạng Đông Key Helper project-authored source code is released under the
repository's MIT License. The helper also distributes or downloads the
following third-party software:

## Frida Java bridge 7.0.13

The compiled agent at
`rootfs/app/rangdong_helper/frida_agent.js` includes the unmodified
`frida-java-bridge` npm package, version `7.0.13`.

- Upstream source: `https://github.com/frida/frida-java-bridge/tree/v7.0.13`
- Package source: `https://registry.npmjs.org/frida-java-bridge/-/frida-java-bridge-7.0.13.tgz`
- Upstream license declaration: `LGPL-2.0 WITH WxWindows-exception-3.1`

The exact dependency is pinned in `agent/package-lock.json`. The preferred
form for modification is available from the upstream source above and can be
rebundled with:

```sh
cd rangdong_key_helper/agent
npm ci
npm run build
```

## Frida 17.17.0

The container installs the Frida Python bindings version `17.17.0`. During an
authorized operation, it may download the matching official Frida server
version `17.17.0` for the user's Android architecture. Downloaded assets are
verified against pinned SHA-256 checksums before use.

- Upstream source: `https://github.com/frida/frida/tree/17.17.0`
- Release assets: `https://github.com/frida/frida/releases/tag/17.17.0`
- License: wxWindows Library Licence, Version 3.1

The applicable GNU Library General Public License version 2 text and the
wxWindows exception are reproduced in `LICENSE.frida.txt`. Nothing in this
notice changes the licenses granted by the respective copyright holders.
