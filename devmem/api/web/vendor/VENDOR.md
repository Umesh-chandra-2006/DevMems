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
