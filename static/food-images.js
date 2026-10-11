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
function foodImage(category) {
  const index = FOOD_CATEGORIES.indexOf(category);
  if (index < 0) return '';
  const x = (index % 4) * 100 / 3;
  const y = Math.floor(index / 4) * 100 / 6;
  // Categories come from a fixed list, never from unescaped product input.
  return `<div class="food-photo" role="img" aria-label="Imagen ilustrativa de ${FOOD_CATEGORIES[index]}" style="background-position:${x}% ${y}%"></div>`;
}
