# Local React Bits adaptations

Source baseline: `DavidHDev/react-bits@271b49c3ba1db60686e53c8c9a28b7583d5477d5`.

Upstream references:

- https://reactbits.dev/components/animated-list
- https://reactbits.dev/animations/animated-content
- https://reactbits.dev/text-animations/scroll-reveal
- https://reactbits.dev/components/card-nav
- https://reactbits.dev/components/circular-gallery
- https://reactbits.dev/components/tilted-card

The local adapters use the project's Framer Motion dependency, GSAP 3.15, OGL 1.0.11 and Lucide icons. Keyboard listeners are scoped to focused widgets; GSAP cleanup is scoped to each component; reduced motion renders content immediately; demo-fixed dimensions and colors are replaced by responsive parent sizing and project CSS variables. Preserve the upstream license notice when syncing newer source.
