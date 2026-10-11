const PREPARATION_PROFILES = {
  burger: {title: 'Personaliza tu hamburguesa', options: ['Sin cebolla', 'Sin picante', 'Sin mostaza', 'Sin mayonesa', 'Sin cátsup'], placeholder: 'Ejemplo: sin tomate, salsas aparte…'},
  frappe: {title: 'Personaliza tu frappé', options: ['Sin azúcar añadida', 'Sin crema batida', 'Sin chocolate'], placeholder: 'Ejemplo: menos dulce, chocolate aparte…'},
  tea: {title: 'Personaliza tu bebida', options: ['Sin azúcar añadida'], placeholder: 'Ejemplo: sin endulzante, menos caliente…'},
  cold_drink: {title: 'Personaliza tu bebida', options: ['Sin azúcar añadida', 'Sin hielo'], placeholder: 'Ejemplo: poco hielo, menos dulce…'},
  none: {title: 'Indicaciones de preparación', options: [], placeholder: 'Escribe aquí la indicación que pidió el cliente…'}
};
function preparationProfile(product) {
  let key = product.preparation_profile || 'auto';
  if (key === 'auto') {
    key = {
      'Hamburguesas': 'burger', 'Hamburguesas con papas': 'burger',
      'Frappés': 'frappe', 'Tizanas calientes': 'tea', 'Tés': 'tea',
      'Bebidas calientes': 'tea', 'Bebidas sobre las rocas': 'cold_drink'
    }[product.category] || 'none';
  }
  return PREPARATION_PROFILES[key] || PREPARATION_PROFILES.none;
}
// Recognize only exact options; preserve previous instructions as free text.
function splitPreparationNotes(notes, options) {
  const parts = notes.split(', ');
  return {selected: options.filter(option => parts.includes(option)), other: parts.filter(part => !options.includes(part)).join(', ')};
}
