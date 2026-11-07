import { useState } from "react";
import { productMedia } from "../lib/productMedia.js";

/** Product picture: real photo if one exists, otherwise an emoji on a tint. Decorative only. */
export default function ProductThumb({ name, sku, category, size = "md" }) {
  const m = productMedia(name, sku, category);
  const [broken, setBroken] = useState(null); // remembers which photo failed to load
  const showPhoto = m.photo && broken !== m.photo;
  return (
    <span className={`pthumb pthumb--${size}`} style={{ background: m.tint }} aria-hidden="true">
      {showPhoto ? (
        <img src={m.photo} alt="" onError={() => setBroken(m.photo)} />
      ) : (
        <span className="pthumb__emoji">{m.emoji}</span>
      )}
    </span>
  );
}
