// lat/lon <-> local meters around the station, the same flat-earth math the boat uses (boat-pi/nav.py).
//
// three.js axes: x = east, y = up, z = SOUTH (so north is -z). Heading 0 = north, clockwise,
// which makes the model's yaw = -heading.

export const M_PER_DEG = 111320;

let origin = [39.0912, -77.1534];   // replaced by the station's real origin from the `world` message

export function setOrigin(o) { origin = o; }

export function toXZ(lat, lon) {
  const cos = Math.cos(origin[0] * Math.PI / 180);
  return [(lon - origin[1]) * M_PER_DEG * cos, -(lat - origin[0]) * M_PER_DEG];
}

export function toLatLon(x, z) {
  const cos = Math.cos(origin[0] * Math.PI / 180);
  return [origin[0] + -z / M_PER_DEG, origin[1] + x / (M_PER_DEG * cos)];
}

export const headingToYaw = (deg) => -deg * Math.PI / 180;

// -180..180
export const wrapDeg = (d) => ((d + 540) % 360) - 180;

// exponential smoothing that behaves the same at 30 fps and 144 fps
export const damp = (current, target, rate, dt) => current + (target - current) * (1 - Math.exp(-rate * dt));
