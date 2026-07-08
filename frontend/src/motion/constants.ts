export const motion = {
  duration: {
    micro: 0.08,
    fast: 0.12,
    base: 0.18,
    panel: 0.24,
    window: 0.28,
    loop: 1.2
  },
  ease: {
    out: "power2.out",
    in: "power2.in",
    inOut: "power3.inOut",
    sharp: "power4.out",
    softBack: "back.out(1.18)",
    none: "none"
  },
  stagger: {
    tight: 0.025,
    normal: 0.04,
    loose: 0.065
  }
} as const;

export function getMotionDuration(duration: number, reduceMotion?: boolean) {
  return reduceMotion ? 0.01 : duration;
}

