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
