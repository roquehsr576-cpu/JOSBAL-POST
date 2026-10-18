function groupPresentations(products) {
  const groups=[], sizes=new Map();
  for (const product of products) {
    const match=product.name.match(/^(.*) · (Chico|Grande)$/);
    const key=match?JSON.stringify([product.category,match[1]]):null;
    let group=key?sizes.get(key):null;
    if (!group) {
      group={...product,baseName:match?match[1]:product.name,variants:[]};
      groups.push(group);
      if (key) sizes.set(key,group);
    }
    group.variants.push({...product,size:match?match[2]:''});
  }
  for (const group of groups) {
    group.variants.sort((a,b)=>(a.size==='Chico'?0:1)-(b.size==='Chico'?0:1));
    if (group.variants.length>1) group.name=group.baseName;
  }
  return groups;
}
