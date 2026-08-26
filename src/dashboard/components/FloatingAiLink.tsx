"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import styles from "./FloatingAiLink.module.css";

export default function FloatingAiLink() {
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const drag = useRef({ active: false, moved: false, offsetX: 0, offsetY: 0 });

  const onPointerDown = (event: React.PointerEvent<HTMLAnchorElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    drag.current = {
      active: true,
      moved: false,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLAnchorElement>) => {
    if (!drag.current.active) return;
    drag.current.moved = true;
    setPosition({
      x: Math.max(8, Math.min(window.innerWidth - 84, event.clientX - drag.current.offsetX)),
      y: Math.max(80, Math.min(window.innerHeight - 84, event.clientY - drag.current.offsetY)),
    });
  };

  const stopDragging = () => {
    drag.current.active = false;
  };

  return (
    <Link
      draggable={false}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={stopDragging}
      onPointerCancel={stopDragging}
      onClick={(event) => {
        if (drag.current.moved) {
          event.preventDefault();
          drag.current.moved = false;
        }
      }}
      style={position ? { left: position.x, top: position.y, right: "auto", bottom: "auto" } : undefined}
      className={styles.floatingAi}
      href="/chatbot"
      aria-label="Pusula AI sayfasını aç veya sürükleyerek taşı"
    >
      <span className={styles.orbit} aria-hidden="true" />
      <span className={styles.sparkle} aria-hidden="true">✦</span>
      <strong>Pusula AI</strong>
    </Link>
  );
}
