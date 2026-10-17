// GPU particles. Each particle is written once, when it's born (start, velocity, drag, gravity,
// life); the vertex shader works out where it is at any time from those. So the CPU never
// touches a live particle and thousands of them cost almost nothing.
//
// Three kinds, chosen per system:
//   foam   flat on the water, a noisy blob that grows and erodes as it ages (wakes, prop wash)
//   spray  camera-facing soft dots with gravity (droplets off the conveyor, bow spray, dust)
//   ring   flat expanding circle (ripples, radio pulses, waypoint reached)

import * as THREE from 'three';

const vertexShader = /* glsl */`
  attribute vec3 iStart;
  attribute vec3 iVel;
  attribute vec2 iTime;     // birth, life
  attribute vec2 iSize;     // size at birth, size at death (diameter, m)
  attribute vec4 iColor;    // rgb, alpha
  attribute vec3 iPhys;     // drag, gravity (or ring width for rings), seed
  uniform float uTime;
  varying vec2 vUv;
  varying float vT;
  varying float vAlpha;
  varying float vSeed;
  varying float vRingW;
  varying vec3 vColor;

  void main() {
    float age = uTime - iTime.x;
    float t = age / iTime.y;
    if (t < 0.0 || t > 1.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }

    float k = iPhys.x;
    vec3 c = iStart + (k > 0.001 ? iVel * (1.0 - exp(-k * age)) / k : iVel * age);
    float size = mix(iSize.x, iSize.y, 1.0 - (1.0 - t) * (1.0 - t));    // grows fast, then settles

    vAlpha = iColor.a * smoothstep(0.0, 0.05, t) * (1.0 - smoothstep(0.4, 1.0, t));
#ifdef BILLBOARD
    c.y -= 0.5 * iPhys.y * age * age;
    if (c.y < -0.02) vAlpha = 0.0;                                       // fell back into the water
    vec4 mv = viewMatrix * vec4(c, 1.0);
    mv.xy += position.xy * size;
    gl_Position = projectionMatrix * mv;
#else
    float a = iPhys.z * 6.2832;
    vec2 q = mat2(cos(a), -sin(a), sin(a), cos(a)) * position.xy * size;
    // quad y -> world -z, so the triangles still face up (y -> +z would mirror them and they'd be culled)
    gl_Position = projectionMatrix * viewMatrix * vec4(c.x + q.x, c.y, c.z - q.y, 1.0);
#endif
    vUv = uv;
    vT = t;
    vSeed = iPhys.z;
    vRingW = iPhys.y / max(size * 0.5, 0.001);
    vColor = iColor.rgb;
  }
`;

const fragmentShader = /* glsl */`
  varying vec2 vUv;
  varying float vT;
  varying float vAlpha;
  varying float vSeed;
  varying float vRingW;
  varying vec3 vColor;

  float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
  float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
  }

  void main() {
    vec2 q = vUv * 2.0 - 1.0;
    float d = length(q);
    float a;
#if defined(FOAM)
    // foam: a soft blob whose inside dissolves into lace as it ages
    float n = 0.65 * vnoise(q * 2.6 + vSeed * 31.0) + 0.35 * vnoise(q * 6.5 - vSeed * 17.0);
    float body = smoothstep(1.0, 0.25, d);
    float erode = mix(0.15, 0.72, vT);
    a = body * smoothstep(erode, erode + 0.22, n * 0.85 + body * 0.3);
#elif defined(RING)
    a = 1.0 - smoothstep(0.0, vRingW, abs(d - (1.0 - vRingW)));
    a *= step(d, 1.0);
#else
    a = smoothstep(1.0, 0.0, d);
    a *= a;
#endif
    a *= vAlpha;
    if (a < 0.004) discard;
    gl_FragColor = vec4(vColor, a);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

const LAYOUT = { iStart: 3, iVel: 3, iTime: 2, iSize: 2, iColor: 4, iPhys: 3 };

export class Particles {
  /**
   * @param {number} max     how many can be alive at once (oldest are recycled)
   * @param {'foam'|'spray'|'ring'} kind
   * @param {{additive?: boolean, renderOrder?: number}} [opts]
   */
  constructor(max, kind, opts = {}) {
    this.max = max;
    this.cursor = 0;
    this.dirtyFrom = Infinity;
    this.dirtyTo = -1;

    const geo = new THREE.InstancedBufferGeometry();
    const quad = new THREE.PlaneGeometry(1, 1);
    geo.index = quad.index;
    geo.setAttribute('position', quad.getAttribute('position'));
    geo.setAttribute('uv', quad.getAttribute('uv'));
    this.attrs = {};
    for (const [name, size] of Object.entries(LAYOUT)) {
      const a = new THREE.InstancedBufferAttribute(new Float32Array(max * size), size);
      a.setUsage(THREE.DynamicDrawUsage);
      geo.setAttribute(name, a);
      this.attrs[name] = a;
    }
    // everything starts dead: born at -inf
    this.attrs.iTime.array.fill(-1e6);
    this.attrs.iTime.array.forEach((_, i) => { if (i % 2) this.attrs.iTime.array[i] = 1; });
    geo.instanceCount = max;

    const defines = { foam: { FOAM: '' }, spray: { BILLBOARD: '' }, ring: { RING: '' } }[kind];
    this.material = new THREE.ShaderMaterial({
      vertexShader, fragmentShader, defines,
      uniforms: { uTime: { value: 0 } },
      transparent: true,
      depthWrite: false,
      blending: opts.additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    });
    this.mesh = new THREE.Mesh(geo, this.material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = opts.renderOrder ?? 2;
  }

  /**
   * One particle. Everything in meters / seconds.
   * @param {{x:number,y:number,z:number}} p   start position
   * @param {{x:number,y:number,z:number}} v   start velocity
   */
  emit(p, v, { life = 2, size = 0.2, grow = 1, color = 0xffffff, alpha = 1, drag = 0, gravity = 0, width = 0.06 }) {
    const i = this.cursor;
    this.cursor = (this.cursor + 1) % this.max;
    const c = _color.set(color);
    const A = this.attrs;
    A.iStart.array.set([p.x, p.y, p.z], i * 3);
    A.iVel.array.set([v.x, v.y, v.z], i * 3);
    A.iTime.array.set([this.material.uniforms.uTime.value, life], i * 2);
    A.iSize.array.set([size, size * grow], i * 2);
    A.iColor.array.set([c.r, c.g, c.b, alpha], i * 4);
    A.iPhys.array.set([drag, this.material.defines.RING !== undefined ? width : gravity, Math.random()], i * 3);
    this.dirtyFrom = Math.min(this.dirtyFrom, i);
    this.dirtyTo = Math.max(this.dirtyTo, i);
  }

  /** Call once a frame with the shared clock. Uploads only what changed. */
  update(time) {
    this.material.uniforms.uTime.value = time;
    if (this.dirtyTo < 0) return;
    for (const [name, size] of Object.entries(LAYOUT)) {
      const a = this.attrs[name];
      a.clearUpdateRanges();
      a.addUpdateRange(this.dirtyFrom * size, (this.dirtyTo - this.dirtyFrom + 1) * size);
      a.needsUpdate = true;
    }
    this.dirtyFrom = Infinity;
    this.dirtyTo = -1;
  }
}

const _color = new THREE.Color();

// Emitting "n per second" at a variable frame rate: carry the fraction over to the next frame
// so a slow trickle still comes out evenly.
export class Rate {
  constructor() { this.acc = 0; }
  take(perSecond, dt) {
    this.acc += Math.max(0, perSecond) * dt;
    const n = Math.floor(this.acc);
    this.acc -= n;
    return n;
  }
}
