const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function lines(items){return items.map(item=>`<li><strong>${item.quantity} × ${esc(item.name)}</strong>${item.notes?`<p class="notes">${esc(item.notes)}</p>`:''}</li>`).join('');}
// Compares the previous and current lists by product and preparation, so a changed instruction shows as quitar + agregar.
function ticketDiff(previous,current){
 const group=list=>{const m=new Map();for(const i of list){const k=i.id+'|'+(i.notes||''),e=m.get(k)||{...i,quantity:0};e.quantity+=i.quantity;m.set(k,e);}return m;};
 const before=group(previous),after=group(current),added=[],removed=[];
 for(const [k,i] of after){const n=i.quantity-(before.get(k)?.quantity||0);if(n>0)added.push({...i,quantity:n});}
 for(const [k,i] of before){const n=i.quantity-(after.get(k)?.quantity||0);if(n>0)removed.push({...i,quantity:n});}
 return {added,removed};
}
function changeKind(t){return !t.changes.previous?'':t.items.length?'modified':'withdrawn';}
function changeAlert(t){
 const kind=changeKind(t);if(!kind)return '';
 const {added,removed}=ticketDiff(t.changes.previous,t.items);
 const list=(items,sign)=>items.map(i=>`<li><strong>${sign} ${i.quantity} × ${esc(i.name)}</strong>${i.notes?`<p class="notes">${esc(i.notes)}</p>`:''}</li>`).join('');
 return `<div class="alert ${kind}"><strong class="alert-title">${kind==='withdrawn'?'✕ CANCELADO · NO PREPARAR':'⚠ CAMBIO EN LA COMANDA'}</strong>`
  +(added.length?`<p class="alert-label">Agregar</p><ul class="added">${list(added,'+')}</ul>`:'')
  +(removed.length?`<p class="alert-label">Quitar · no preparar</p><ul class="removed">${list(removed,'−')}</ul>`:'')
  +`</div>`;
}
