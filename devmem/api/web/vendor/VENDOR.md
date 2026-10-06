# Vendored frontend libraries (Phase 8)

Approved by the PM for Phase 8 only: react@18.3.1 and react-dom@18.3.1, production UMD builds, MIT licensed, from registry.npmjs.org.
Nothing else is vendored. No npm install, no package.json, no lockfile, no node_modules, no package scripts were run; the tarballs were fetched
with a plain download into a scratch folder outside the repository and discarded after extracting only the files below.

| Package | Version | Tarball | dist.integrity (published by npm, verified before extracting) |
|---|---|---|---|
| react | 18.3.1 | https://registry.npmjs.org/react/-/react-18.3.1.tgz | sha512-wS+hAgJShR0KhEvPJArfuPVN1+Hz1t0Y6n5jLrGQbkb4urgPE/0Rve+1kMB1v/oWgHgm4WIcV+i7F2pTVj+2iQ== |
| react-dom | 18.3.1 | https://registry.npmjs.org/react-dom/-/react-dom-18.3.1.tgz | sha512-5m4nQKp+rZRb09LNH59GM4BxTh9251/ylbKIbpe7TpGxfJ+9kv6BLkLBXIjjspbgbnIBNqlI23tRnTWT0snUIw== |

The sha512 of each downloaded tarball, computed locally with openssl, equals the published integrity value for both packages (compared
before extraction).

Extracted files (sha256 of the extracted files):
- `react.production.min.js` (package/umd/react.production.min.js): d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd
- `react-dom.production.min.js` (package/umd/react-dom.production.min.js): 35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d
- `LICENSE-react.txt`, `LICENSE-react-dom.txt` (MIT, identical text, from each package)

The frontend uses `React.createElement` through a tiny local helper (no JSX, no in-browser compiler) and makes no network request at runtime.

## Phaser (Phase 8 Stop 2, the town replay)

Required by the PM rule: upstream's own pages (`reverie/environment/frontend_server/templates/home/home.html` line 76 and
`templates/demo/demo.html` line 110) load `https://cdn.jsdelivr.net/npm/phaser@3.55.2/dist/phaser.js`. The exact version and the same file are
vendored here so the town replay runs offline.

| Package | Version | Tarball | dist.integrity (published by npm, verified before extracting) |
|---|---|---|---|
| phaser | 3.55.2 | https://registry.npmjs.org/phaser/-/phaser-3.55.2.tgz (10,710,882 bytes) | sha512-amKXsbb2Ht29dGPKvt1edq3yGGYKtq8373GpJYGKPNPnneYY6MtVTOgjHDuZwtmUyK4v86FugkT3hzW/N4tjxQ== |

The locally computed sha512 of the tarball equals the published integrity value. Extracted only `package/dist/phaser.js` (6,838,115 bytes; the
unminified file upstream references, sha256 494b0609ea5de72cf9dc22401343247d01a955aa48f92670f121868296418381) and `package/LICENSE.md` (MIT,
kept as `LICENSE-phaser.md`). No npm install, no package scripts, no node_modules, package.json or lockfile; the tarball was fetched with a plain
download into a scratch folder outside the repository and discarded.

Upstream's `templates/base.html` also loads Bootstrap 3.4.1 (CSS and JS) and jQuery ("latest") from CDNs. The inspector's town replay does NOT use
them (it is its own page, not a Django template), so they are NOT vendored. Upstream's viewer keeps working as before with its own CDN links.
