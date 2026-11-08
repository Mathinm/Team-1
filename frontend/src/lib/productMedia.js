// Product pictures for the Products screen and product form (look only).
// Finds a photo from the product's name or SKU (frontend/public/img/products/<key>.jpg),
// else from its category (frontend/public/img/categories/<key>.jpg). If the file is missing, or
// the product is not recognised, an emoji on a soft tint is shown instead,
// so every product always has a picture. Nothing here is saved or sent.

const BY_WORD = [
  ["banana", /banana|kela/, "🍌", "#fff3c4"],
  ["tomato", /tomato|tamatar/, "🍅", "#fde0da"],
  ["milk", /milk|doodh/, "🥛", "#e8f1fb"],
  ["paneer", /paneer|cheese/, "🧀", "#fff0c9"],
  ["bread", /bread|bun|loaf|pav/, "🍞", "#f6e3c8"],
  ["spinach", /spinach|palak|lettuce|greens|coriander|mint/, "🥬", "#dff2e3"],
  ["apple", /apple|seb/, "🍎", "#fde0da"],
  ["mango", /mango|aam/, "🥭", "#ffe9b8"],
  ["carrot", /carrot|gajar/, "🥕", "#ffe2cc"],
  ["potato", /potato|aloo/, "🥔", "#f1e4d2"],
  ["onion", /onion|pyaz/, "🧅", "#f5e3ef"],
  ["curd", /curd|yogurt|yoghurt|dahi/, "🥣", "#eef3fb"],
  ["egg", /egg|anda/, "🥚", "#fbf0dc"],
  ["chicken", /chicken|mutton|meat/, "🍗", "#fde3d6"],
  ["fish", /fish|prawn|salmon/, "🐟", "#dcecf7"],
];

const BY_CATEGORY = {
  Vegetables: ["vegetables", "🥦", "#dff2e3"],
  Fruits: ["fruits", "🍓", "#fde0e6"],
  Dairy: ["dairy", "🥛", "#e8f1fb"],
  Bakery: ["bakery", "🥐", "#f6e3c8"],
  "Meat & Fish": ["meat-fish", "🍗", "#fde3d6"],
};

const photo = (key) => `/img/products/${key}.jpg`;
const categoryPhoto = (key) => `/img/categories/${key}.jpg`;

/** @returns {{ photo: string|null, emoji: string, tint: string }} */
export function productMedia(name = "", sku = "", category = "") {
  const text = `${name} ${sku}`.toLowerCase();
  for (const [key, re, emoji, tint] of BY_WORD) {
    if (re.test(text)) return { photo: photo(key), emoji, tint };
  }
  const cat = BY_CATEGORY[category];
  if (cat) return { photo: categoryPhoto(cat[0]), emoji: cat[1], tint: cat[2] };
  return { photo: null, emoji: "🧺", tint: "#f3ead9" };
}
