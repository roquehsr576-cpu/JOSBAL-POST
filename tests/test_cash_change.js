const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/app.js','utf8');
const nodes=new Map();
function $(id){if(!nodes.has(id))nodes.set(id,{hidden:false,textContent:'',classList:{toggle(name,value){this[name]=value;}},showModal(){this.open=true;},close(){this.open=false;}});return nodes.get(id);}
$('#checkout').elements={payment:{value:'cash'},received:{value:'200'}};
const context=vm.createContext({$,cart:new Map([[1,{quantity:1}]]),total:()=>18800,money:n=>'$'+(n/100).toFixed(2)});
vm.runInContext(source.slice(source.indexOf('function cashAmounts('),source.indexOf("\ndocument.addEventListener('click'")),context);
vm.runInContext('updateChange()',context);
assert.equal($('#change-label').textContent,'Cambio por entregar');
assert.equal($('#change-amount').textContent,'$12.00');
$('#checkout').elements.received.value='100';
vm.runInContext('updateChange()',context);
assert.equal($('#change-label').textContent,'Falta por pagar');
assert.equal($('#change-amount').textContent,'$88.00');
$('#checkout').elements.received.value='188';
vm.runInContext('updateChange()',context);
assert.equal($('#change-amount').textContent,'$0.00');
for(const raw of ['', 'abc', '-10']){
  context.raw=raw;
  assert.equal(vm.runInContext('cashAmounts(18800,raw).valid',context),false);
}
$('#checkout').elements.payment.value='card';
vm.runInContext('updateChange()',context);
assert.equal($('#change').hidden,true);
vm.runInContext("showPaymentResult({id:12,total:18800,change:1200},'cash','Mesa 2')",context);
assert.equal($('#payment-result').open,true);
assert.equal($('#payment-result-received').textContent,'$200.00');
assert.equal($('#payment-result-change').textContent,'$12.00');
vm.runInContext("showPaymentResult({id:13,total:18800,change:0},'card','Mesa 2')",context);
assert.equal($('#payment-result-change-row').hidden,true);
console.log('Cambio visible al escribir y después de cobrar; faltantes, pago exacto y tarjeta: OK');
