const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const menu = JSON.parse(fs.readFileSync('catalog/menu.json')).items;
const images = JSON.parse(fs.readFileSync('catalog/product-images.json'));
const batches = JSON.parse(fs.readFileSync('catalog/image-batches.json'));
const normalize = name => name.replace(/ · (Chico|Grande)$/, '');
const expected = new Set(menu.filter(p => p.category !== 'Extras').map(p => normalize(p.name)));
assert.deepEqual(new Set(images.map(p => p.name)), expected);
assert.equal(images.length, 123);
assert.deepEqual(batches.flat().sort(), images.map(p => p.url).sort());
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('static/food-images.js', 'utf8'), context);
for (const product of menu.filter(p => p.category !== 'Extras')) {
  const image = images.find(p => p.name === normalize(product.name));
  context.product = product;
  const markup = vm.runInContext('foodImage(product.category, product.name)', context);
  assert.ok(markup.includes(`src="${image.url}"`), product.name);
}
for (const image of images) {
  const header = Buffer.alloc(24);
  const fd = fs.openSync('static' + image.url, 'r');
  try { fs.readSync(fd, header, 0, 24, 0); } finally { fs.closeSync(fd); }
  assert.equal(header.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(header.readUInt32BE(16), header.readUInt32BE(20));
  assert.ok(header.readUInt32BE(16) >= 1024);
}
console.log('123 imágenes: cobertura completa, tamaños compartidos, archivos y lotes verificados.');
