// The water. A mirror (three's Reflector renders the scene upside down into a texture every
// frame), bent by the waves, mixed with the sky by the Fresnel rule, tinted shallow near the
// bank, with a foam line at the shore.
//
// The waves are defined once (WAVES) and used twice: by the shader for the look, and by
// waveHeight()/waveSlope() so the boat bobs on the same water you see. They are small on
// purpose; this is a lake, not the sea.

import * as THREE from 'three';
import { Reflector } from 'three/addons/objects/Reflector.js';

const G = 9.81;
const WAVES = [
  // direction (x, z), wavelength m, amplitude m
  { d: [0.83, 0.55], len: 7.0, amp: 0.03 },
  { d: [-0.42, 0.91], len: 4.3, amp: 0.018 },
  { d: [0.97, -0.24], len: 2.6, amp: 0.008 },
  { d: [0.20, -0.98], len: 11.0, amp: 0.035 },
].map((w, i) => {
  const k = (2 * Math.PI) / w.len;
  return { ...w, k, omega: Math.sqrt(G * k), phase: i * 1.7 };
});

export function waveHeight(x, z, t) {
  let h = 0;
  for (const w of WAVES) h += w.amp * Math.sin(w.k * (w.d[0] * x + w.d[1] * z) - w.omega * t + w.phase);
  return h;
}

// d(height)/dx and d(height)/dz
export function waveSlope(x, z, t) {
  let sx = 0, sz = 0;
  for (const w of WAVES) {
    const c = w.amp * w.k * Math.cos(w.k * (w.d[0] * x + w.d[1] * z) - w.omega * t + w.phase);
    sx += c * w.d[0]; sz += c * w.d[1];
  }
  return [sx, sz];
}

// The near shoreline, as the z (south) coordinate where land starts for a given x. The station
// sits at the origin, a couple of meters inland. terrain.js builds the bank from this too.
export function shoreZ(x) {
  return -4.0 + 1.6 * Math.sin(x * 0.045 + 0.7) + 0.7 * Math.sin(x * 0.13 + 2.1) + 0.25 * Math.sin(x * 0.37);
}

const f = (n) => n.toFixed(5);
const wavesGLSL = WAVES.map((w) =>
  `    a = ${f(w.k)} * dot(vec2(${f(w.d[0])}, ${f(w.d[1])}), p) - ${f(w.omega)} * t + ${f(w.phase)};
    g += ${f(w.amp * w.k)} * cos(a) * vec2(${f(w.d[0])}, ${f(w.d[1])});`).join('\n');

const shader = {
  name: 'LakeSurface',
  uniforms: {
    color: { value: null },            // Reflector sets these three
    tDiffuse: { value: null },
    textureMatrix: { value: null },
    uTime: { value: 0 },
    uSunDir: { value: new THREE.Vector3(0, 1, 0) },
    uSunColor: { value: new THREE.Color(1, 1, 1) },
    uEnv: { value: null },
    uDeep: { value: new THREE.Color(0x071c26) },
    uShallow: { value: new THREE.Color(0x1d3b3a) },
    uFogColor: { value: new THREE.Color() },
    uFogDensity: { value: 0.0016 },
    uGrid: { value: 1 },
    uRingMax: { value: 150 },
    uBoat: { value: new THREE.Vector3(0, 0, -1e5) },   // x, z, heading (rad): darkens the water right under the hull
  },
  vertexShader: /* glsl */`
    uniform mat4 textureMatrix;
    varying vec4 vMirror;
    varying vec3 vWorld;
    void main() {
      vMirror = textureMatrix * vec4(position, 1.0);
      vec4 wp = modelMatrix * vec4(position, 1.0);
      vWorld = wp.xyz;
      gl_Position = projectionMatrix * viewMatrix * wp;
    }
  `,
  fragmentShader: /* glsl */`
    uniform sampler2D tDiffuse;
    uniform samplerCube uEnv;
    uniform float uTime;
    uniform vec3 uSunDir;
    uniform vec3 uSunColor;
    uniform vec3 uDeep;
    uniform vec3 uShallow;
    uniform vec3 uFogColor;
    uniform float uFogDensity;
    uniform float uGrid;
    uniform float uRingMax;
    uniform vec3 uBoat;
    varying vec4 vMirror;
    varying vec3 vWorld;

    float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
    float vnoise(vec2 p) {
      vec2 i = floor(p), f = fract(p);
      vec2 u = f * f * (3.0 - 2.0 * f);
      return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
    }
    float fbm(vec2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.5; } return s; }
    vec2 noiseGrad(vec2 p) {
      float e = 0.07;
      return vec2(vnoise(p + vec2(e, 0)) - vnoise(p - vec2(e, 0)), vnoise(p + vec2(0, e)) - vnoise(p - vec2(0, e))) / (2.0 * e);
    }
    vec2 waveGrad(vec2 p, float t) {
      vec2 g = vec2(0.0); float a;
${wavesGLSL}
      return g;
    }
    float shoreZ(float x) {
      return -4.0 + 1.6 * sin(x * 0.045 + 0.7) + 0.7 * sin(x * 0.13 + 2.1) + 0.25 * sin(x * 0.37);
    }
    float gridLine(vec2 p, float size, float width) {
      vec2 q = p / size;
      vec2 g = abs(fract(q - 0.5) - 0.5) / fwidth(q);
      return 1.0 - smoothstep(width - 0.5, width + 0.5, min(g.x, g.y));
    }

    void main() {
      vec2 p = vWorld.xz;
      float dist = length(vWorld - cameraPosition);
      vec3 V = normalize(cameraPosition - vWorld);
      float shore = p.y - shoreZ(p.x);              // < 0 out on the water, meters

      // surface normal: the big waves, plus small ripples that fade out with distance (no shimmer)
      vec2 g = waveGrad(p, uTime) * 2.2;
      float detail = 1.0 - smoothstep(20.0, 120.0, dist);
      g += detail * 0.09 * noiseGrad(p * 1.7 + vec2(uTime * 0.33, uTime * 0.19));
      g += detail * 0.045 * noiseGrad(p * 4.3 - vec2(uTime * 0.25, -uTime * 0.29));
      vec3 N = normalize(vec3(-g.x, 1.0, -g.y));

      // the mirror image of the scene, pushed around by the ripples
      vec4 m = vMirror;
      m.xy += N.xz * 0.045 * m.w * (0.4 + 0.6 * detail);
      vec3 mirror = texture2DProj(tDiffuse, m).rgb;
      vec3 R = reflect(-V, N); R.y = abs(R.y);
      vec3 sky = textureCube(uEnv, R).rgb;
      // where the mirror sees only sky, the analytic sky is smoother; elsewhere trust the mirror
      vec3 refl = mix(mirror, sky, 0.1);

      float cosV = max(dot(N, V), 0.0);
      float fres = 0.02 + 0.98 * pow(1.0 - cosV, 5.0);
      fres = mix(fres, 1.0, 0.14);                  // lakes are never fully see-through at a glance

      float depth = clamp(-shore / 10.0, 0.0, 1.0);
      vec3 body = mix(uShallow, uDeep, depth);
      body *= 0.5 + 0.5 * max(dot(N, uSunDir), 0.0);

      vec3 col = mix(body, refl, fres);
      float glint = pow(max(dot(R, uSunDir), 0.0), 260.0);
      col += uSunColor * glint * 1.6;

      // the hull shades the water under and right around it
      vec2 bq = p - uBoat.xy;
      float c = cos(uBoat.z), s = sin(uBoat.z);
      vec2 bl = vec2(c * bq.x + s * bq.y, -s * bq.x + c * bq.y);
      float hull = 1.0 - smoothstep(0.0, 0.55, length(vec2(bl.x / 0.75, bl.y / 0.95)) - 0.55);
      col *= 1.0 - 0.35 * hull;

      // foam where small waves break on the bank
      float foamBand = smoothstep(-1.4, 0.0, shore);
      float foamNoise = fbm(p * 2.2 + vec2(0.0, uTime * 0.4));
      float foam = foamBand * smoothstep(0.5 - 0.3 * foamBand, 0.78, foamNoise + 0.15 * sin(uTime * 1.3 + p.x * 0.6));
      col = mix(col, vec3(0.8, 0.84, 0.85), foam * 0.5);

      // survey overlay: 10 m / 50 m grid and range rings round the station, faint like a chart
      float fade = (1.0 - smoothstep(100.0, 380.0, dist)) * uGrid;
      float minor = gridLine(p, 10.0, 0.6) * (1.0 - smoothstep(50.0, 160.0, dist));
      float major = gridLine(p, 50.0, 0.8);
      float r = length(p);
      float rq = r / 50.0;
      float ring = (1.0 - smoothstep(0.3, 1.4, abs(fract(rq - 0.5) - 0.5) / fwidth(rq))) * step(r, uRingMax + 1.0);
      col = mix(col, vec3(0.85, 0.92, 1.0), fade * (minor * 0.03 + major * 0.05 + ring * 0.12));

      float fog = 1.0 - exp(-pow(dist * uFogDensity, 2.0));
      col = mix(col, uFogColor, fog);

      gl_FragColor = vec4(col, 1.0);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }
  `,
};

export function createSurface(renderer, { envCube, sky, sunDir, sunColor, fogColor, fogDensity }) {
  const size = new THREE.Vector2();
  renderer.getDrawingBufferSize(size);
  const mesh = new Reflector(new THREE.PlaneGeometry(9000, 9000), {
    shader,
    // half resolution is plenty once the ripples bend it
    textureWidth: Math.max(256, Math.round(size.x * 0.5)),
    textureHeight: Math.max(256, Math.round(size.y * 0.5)),
    clipBias: 0.003,
    multisample: 0,
  });
  mesh.rotation.x = -Math.PI / 2;
  mesh.name = 'surface';
  // The sun disc is far brighter than the mirror's half-float texture can hold; one infinite
  // pixel, smeared by the ripples, turns the whole lake white. Hide it while the mirror renders;
  // the shader adds its own sun glint.
  const renderMirror = mesh.onBeforeRender;
  mesh.onBeforeRender = (...args) => {
    const disc = sky.material.uniforms.showSunDisc;
    disc.value = 0;
    renderMirror.apply(mesh, args);
    disc.value = 1;
  };
  const u = mesh.material.uniforms;
  u.uEnv.value = envCube;
  u.uSunDir.value.copy(sunDir);
  u.uSunColor.value.copy(sunColor);
  u.uFogColor.value.copy(fogColor);
  u.uFogDensity.value = fogDensity;
  // keep the mirror texture matched to the screen as the window resizes or quality adapts
  mesh.resize = (w, h) => mesh.getRenderTarget().setSize(Math.max(256, Math.round(w * 0.5)), Math.max(256, Math.round(h * 0.5)));
  return mesh;
}
