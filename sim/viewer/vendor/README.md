# vendor

Third-party files the viewer loads, copied here so the page works on the ground station's own
Wi-Fi with no internet. Don't edit them; to upgrade, download the new version over the old one
and update this table.

| File | Package | Version | License |
| --- | --- | --- | --- |
| `three/three.module.js`, `three/three.core.js` | three | 0.185.1 | MIT |
| `three/addons/…` (OrbitControls, Sky, CSS2DRenderer, lines/) | three (examples/jsm) | 0.185.1 | MIT |
| `tailwind.js` | @tailwindcss/browser | 4.3.3 | MIT |
| `motion.js` | motion (dist/motion.js, global `Motion`) | 13.4.0 | MIT |
| `fonts/instrument-sans.woff2` | @fontsource-variable/instrument-sans (latin) | 5.3.0 | OFL-1.1 |
| `fonts/inter.woff2` | @fontsource-variable/inter (latin) | 5.2.8 | OFL-1.1 |
| `fonts/jetbrains-mono.woff2` | @fontsource-variable/jetbrains-mono (latin) | 5.2.8 | OFL-1.1 |

Source for all of them: `https://cdn.jsdelivr.net/npm/<package>@<version>/…`
