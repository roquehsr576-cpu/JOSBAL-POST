// Category illustrations share one image file to avoid 158 separate downloads.
const FOOD_CATEGORIES = [
  'Desayunos', 'Huevos al gusto', 'Baguettes', 'Bague-pizza',
  'Croissants salados', 'Algo sano', 'Para acompañar', 'Alitas',
  'Hamburguesas', 'Hamburguesas con papas', 'Extras', 'Hot dogs',
  'Combos', 'Bebidas calientes', 'Tizanas calientes', 'Tés',
  'Refrescantes', 'Chamoyadas', 'Bebidas sobre las rocas', 'Sodas italianas',
  'Frappés', 'Malteadas', 'Smoothies', 'Pasteles',
  'Croissants dulces', 'Crepas dulces', 'Waffles'
];
const PRODUCT_IMAGES = {
  "Chilaquiles": "/images/products/01-chilaquiles-rojos-con-huevo-v1.png",
  "Entomatadas": "/images/products/02-entomatadas-con-huevo-v1.png",
  "Enfrijoladas": "/images/products/03-enfrijoladas-con-huevo-v1.png",
  "Omelette chila": "/images/products/04-omelette-chila-v1.png",
  "Huevos a la mexicana": "/images/products/05-huevos-a-la-mexicana-v1.png",
  "Huevos con jamón": "/images/products/06-huevos-con-jamon-v1.png",
  "Omelette de jamón y queso": "/images/products/07-omelette-jamon-y-queso-v1.png",
  "Huevos con chorizo": "/images/products/08-huevos-con-chorizo-v1.png",
  "Baguette de milanesa": "/images/products/09-baguette-milanesa-v1.png",
  "Baguette de chorizo": "/images/products/10-baguette-chorizo-v1.png"
};
function foodImage(category, name) {
  if (PRODUCT_IMAGES[name]) {
    const alt=String(name).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    return `<img class="food-photo product-photo" src="${PRODUCT_IMAGES[name]}" alt="Imagen ilustrativa de ${alt}" loading="lazy" decoding="async" width="1254" height="1254">`;
  }
  const index = FOOD_CATEGORIES.indexOf(category);
  if (index < 0) return '';
  const x = (index % 4) * 100 / 3;
  const y = Math.floor(index / 4) * 100 / 6;
  // Categories come from a fixed list, never from unescaped product input.
  return `<div class="food-photo" role="img" aria-label="Imagen ilustrativa de ${FOOD_CATEGORIES[index]}" style="background-position:${x}% ${y}%"></div>`;
}
