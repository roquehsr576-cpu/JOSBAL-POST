const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('static/preparation-options.js', 'utf8'), context);
function profile(product) {
  context.product = product;
  return JSON.parse(vm.runInContext('JSON.stringify(preparationProfile(product))', context));
}
for (const category of ['Hamburguesas', 'Hamburguesas con papas']) {
  const options = profile({category}).options;
  assert.ok(options.includes('Sin cátsup'));
  assert.ok(options.includes('Sin cebolla'));
  assert.ok(!options.includes('Sin crema batida'));
}
assert.deepEqual(profile({category:'Frappés'}).options, ['Sin azúcar añadida','Sin crema batida','Sin chocolate']);
for (const category of ['Tizanas calientes','Tés']) {
  assert.deepEqual(profile({category}).options, ['Sin azúcar añadida']);
}
assert.deepEqual(profile({category:'Bebidas sobre las rocas'}).options,['Sin azúcar añadida','Sin hielo']);
assert.deepEqual(profile({category:'Pasteles'}).options, []);
assert.deepEqual(profile({category:'Frappés',preparation_profile:'none'}).options, []);
assert.deepEqual(profile({category:'Especiales',preparation_profile:'burger'}).options, profile({category:'Hamburguesas'}).options);
context.notes='Sin cebolla, Sin chocolate, salsa aparte';
const notes=JSON.parse(vm.runInContext("JSON.stringify(splitPreparationNotes(notes, preparationProfile({category:'Frappés'}).options))",context));
assert.deepEqual(notes, {selected:['Sin chocolate'],other:'Sin cebolla, salsa aparte'});
console.log('Opciones por categoría, configuración por producto e indicaciones previas: OK');

assert.ok(profile({category:'Hamburguesas con papas'}).options.includes('Cambiar a papas gajo (+$7)'));
assert.ok(!profile({category:'Hamburguesas'}).options.includes('Cambiar a papas gajo (+$7)'));
assert.equal(vm.runInContext("unitPrice({category:'Hamburguesas con papas',price:10000},'Sin cebolla, Cambiar a papas gajo (+$7)')",context),10700);
assert.equal(vm.runInContext("unitPrice({category:'Hamburguesas con papas',price:10000},'')",context),10000);
for (const product of [
  {category:'Bebidas calientes',name:'Americano · Chico'},
  {category:'Bebidas calientes',name:'Capuchino · Grande'},
  {category:'Bebidas sobre las rocas',name:'Latte sobre rocas · Grande'},
  {category:'Frappés',name:'Frappé café'}
]) {
  context.product=product;
  assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(coffeeLoadOptions(product))',context)),['Carga completa','Media carga']);
}
for (const product of [
  {category:'Bebidas calientes',name:'Chocolate de leche · Chico'},
  {category:'Bebidas calientes',name:'Matcha caliente · Grande'},
  {category:'Hamburguesas',name:'Hamburguesa clásica'},
  {category:'Bebidas calientes',name:'Americano · Chico',preparation_profile:'none'}
]) {
  context.product=product;
  assert.equal(vm.runInContext('coffeeLoadOptions(product).length',context),0);
}
context.notes='Sin azúcar añadida, Media carga, leche tibia';
assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(splitPreparationNotes(notes,['Sin azúcar añadida',...COFFEE_LOAD_OPTIONS]))",context)),{selected:['Sin azúcar añadida','Media carga'],other:'leche tibia'});
