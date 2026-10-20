const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/app.js','utf8');
const implementation=source.slice(source.indexOf('function loadTable(id)'),source.indexOf("\n$('#new-table')"));
function setup(selected='',lines=[],orders=[]) {
  const context=vm.createContext({busy:false,selectedTable:selected,orderRevision:'',lineCounter:0,cart:new Map(lines),state:{orders},navigations:0,renders:0,messages:[],select:{value:selected}});
  vm.runInContext(`const document={querySelector:()=>({click:()=>navigations++})};const $=()=>select;function render(){renders++}function message(text){messages.push(text)};${implementation}`,context);
  return context;
}
// Reopening an already selected table must actually navigate to the sale.
let context=setup('1');
vm.runInContext("loadTable('1')",context);
assert.equal(context.navigations,1);
// Assign the current counter order to an empty table without losing its products.
context=setup('',[[1,{id:8,quantity:2,notes:'Media carga'}]]);
vm.runInContext("loadTable('2')",context);
assert.equal(context.navigations,1);
assert.equal(context.selectedTable,'2');
assert.equal(context.cart.get(1).notes,'Media carga');
// Restore saved products and revision when opening another table.
context=setup('',[],[{table_id:3,revision:'saved',items:[{id:9,quantity:1,notes:'Sin cebolla'}]}]);
vm.runInContext("loadTable('3')",context);
assert.equal(context.navigations,1);
assert.equal(context.orderRevision,'saved');
assert.equal([...context.cart.values()][0].notes,'Sin cebolla');
// An unsaved order still cannot be overwritten by switching to another table.
context=setup('1',[[1,{id:8,quantity:2}]]);
vm.runInContext("loadTable('2')",context);
assert.equal(context.navigations,0);
assert.equal(context.selectedTable,'1');
assert.equal(context.cart.size,1);
assert.equal(context.messages.length,1);
console.log('Mesas: abrir seleccionada, asignar pedido, restaurar guardado y proteger cambios: OK');
