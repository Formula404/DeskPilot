import { gsap } from "./register";
import { motion } from "./constants";

export function animatePress(target: Element | null) {
  if (!target) {
    return;
  }
  gsap.timeline()
    .to(target, { scale: 0.965, duration: motion.duration.micro, ease: motion.ease.inOut })
    .to(target, { scale: 1, duration: motion.duration.fast, ease: motion.ease.out });
}
