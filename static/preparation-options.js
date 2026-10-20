const GAJO_OPTION = 'Cambiar a papas gajo (+$7)';
function unitPrice(product,notes=''){return (product?.price||0)+(product?.category==='Hamburguesas con papas'&&notes.split(', ').includes(GAJO_OPTION)?700:0);}
const PREPARATION_PROFILES = {
  hotdog: {title: 'Personaliza tu hot dog', options: ['Sin cebolla', 'Sin tomate', 'Sin mostaza', 'Sin mayonesa', 'Sin picante'], placeholder: 'Ejemplo: salsas aparte…'},
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
      'Hot dogs': 'hotdog', 'Hamburguesas': 'burger', 'Hamburguesas con papas': 'burger',
      'Frappés': 'frappe', 'Tizanas calientes': 'tea', 'Tés': 'tea',
      'Bebidas calientes': 'tea', 'Bebidas sobre las rocas': 'cold_drink'
    }[product.category] || (product.category==='Combos'&&/^combo hot dog$/i.test(product.name||'')?'hotdog':'none');
  }
  const profile=PREPARATION_PROFILES[key] || PREPARATION_PROFILES.none;
  return product.category==='Hamburguesas con papas'?{...profile,options:[...profile.options,GAJO_OPTION]}:profile;
}
// Recognize only exact options; preserve previous instructions as free text.
function splitPreparationNotes(notes, options) {
  const parts = notes.split(', ');
  return {selected: options.filter(option => parts.includes(option)), other: parts.filter(part => !options.includes(part)).join(', ')};
}

const COFFEE_LOAD_OPTIONS=['Carga completa','Media carga'];
function coffeeLoadOptions(product) {
  if (product.preparation_profile==='none') return [];
  const name=(product.name||'').replace(/ · (Chico|Grande)$/,'');
  const coffees={
    'Bebidas calientes':['Espresso','Affogato','Americano','Capuchino','Latte','Moka','Moka blanco','Latte caramel'],
    'Bebidas sobre las rocas':['Americano sobre rocas','Latte sobre rocas','Moka sobre rocas','Blanco sobre rocas','Caramelo sobre rocas'],
    'Frappés':['Frappé café','Frappé moka','Frappé frapuchino Oreo']
  };
  return coffees[product.category]?.includes(name)?COFFEE_LOAD_OPTIONS:[];
}
