import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { Flip } from "gsap/Flip";

gsap.registerPlugin(useGSAP, Flip);
gsap.defaults({ overwrite: "auto" });

export { Flip, gsap, useGSAP };

