// Browser orientation is Z (alpha), then X (beta), then Y (gamma).
// A quaternion avoids the flat-phone Euler-angle flip that breaks simple subtraction.
const radians = degrees => degrees * Math.PI / 180;
const wrap = angle => Math.atan2(Math.sin(angle), Math.cos(angle));

function orientation(alpha, beta, gamma) {
  const [z, x, y] = [alpha, beta, gamma].map(value => radians(value) / 2);
  const [cz, sz, cx, sx, cy, sy] = [Math.cos(z), Math.sin(z), Math.cos(x), Math.sin(x), Math.cos(y), Math.sin(y)];
  return [cz * cx * cy - sz * sx * sy, cz * sx * cy - sz * cx * sy,
    cz * cx * sy + sz * sx * cy, sz * cx * cy + cz * sx * sy];
}

function relative(base, current) {
  const [a, b, c, d] = [base[0], -base[1], -base[2], -base[3]];
  const [w, x, y, z] = current;
  return [a * w - b * x - c * y - d * z, a * x + b * w + c * z - d * y,
    a * y - b * z + c * w + d * x, a * z + b * y - c * x + d * w];
}

class Axis {
  reset(value) { this.raw = this.filtered = this.emitted = value; }
  update(value, dt) {
    const change = wrap(value - this.raw);
    this.raw = value;
    // Smooth more at rest, less during a deliberate sweep.
    const cutoff = 1.5 + 8 * Math.abs(change / dt);
    this.filtered = wrap(this.filtered + (1 - Math.exp(-2 * Math.PI * cutoff * dt)) * wrap(value - this.filtered));
    const distance = wrap(this.filtered - this.emitted);
    const delta = Math.sign(distance) * Math.max(0, Math.abs(distance) - 0.001);
    this.emitted = wrap(this.emitted + delta);
    return delta;
  }
}

export class Motion {
  constructor() { this.x = new Axis(); this.y = new Axis(); this.reset(); }
  reset() { this.base = null; this.time = null; }
  update(alpha, beta, gamma, seconds, gain = 900) {
    if (![alpha, beta, gamma, seconds, gain].every(Number.isFinite) || gain <= 0) return [0, 0];
    const current = orientation(alpha, beta, gamma);
    this.base ??= current;
    const [w, x, y, z] = relative(this.base, current);
    const horizontal = -Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
    const vertical = -Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));
    const dt = seconds - this.time;
    const jump = this.time === null || dt <= 0 || dt > 0.2
      || Math.abs(wrap(horizontal - this.x.raw)) > 0.35
      || Math.abs(wrap(vertical - this.y.raw)) > 0.35;
    this.time = seconds;
    if (jump) {
      this.x.reset(horizontal); this.y.reset(vertical);
      return [0, 0];
    }
    return [this.x.update(horizontal, dt) * gain, this.y.update(vertical, dt) * gain];
  }
}

// Native keyboards may replace a whole word when autocorrect completes.
export function textEdit(previous, current) {
  let prefix = 0;
  while (prefix < previous.length && previous[prefix] === current[prefix]) prefix++;
  return {type: "text", remove: previous.length - prefix, text: current.slice(prefix)};
}
