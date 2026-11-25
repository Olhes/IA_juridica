'use strict';
const $ = id => document.getElementById(id);
const BASE = '/sat-graph/review';
const API = '/sat-graph/api';
const kinds = {document:'Documento',instrument:'Norma',libro:'Libro',titulo:'Título',capitulo:'Capítulo',subcapitulo:'Subcapítulo',article:'Artículo',numeral:'Numeral',inciso:'Inciso',subinciso:'Subinciso',disposition:'Disposición',disposition_group:'Grupo de disposiciones',amendment_payload:'Texto modificatorio'};
let library = [], doc = null, draft = null, draftCpOffsets = new Uint32Array([0]), draftCpLength = 0, draftBaselineJson = '', selected = null, folded = new Set(), dirty = false, formDirty = false, busy = false, selection = null;
let draftById = new Map(), draftChildren = new Map(), draftOrderedRows = [], rowElements = new Map();
let currentVersions = new Map(), historyDocument = null, historyRenderToken = 0;
let candidates = [], showingCandidates = false;
let parentSelectHydratedFor = null, searchDebounceTimer = null;
const positionKey='sat-review-position-v1';
function readPosition(){
  try{return JSON.parse(localStorage.getItem(positionKey))||{};}catch{return {};}
}
function savePosition(){
  if(!doc)return;
  try{localStorage.setItem(positionKey,JSON.stringify({
    id:doc.id, node:selected, tab:document.querySelector('[data-tab][aria-selected="true"]')?.dataset.tab,
  }));}catch{/* El almacenamiento local puede estar deshabilitado. */}
}
let draftSaveTimer, inspectorGeneration = 0, previousBodyLabel = '';
const labelFromText = text => (text.trimStart().split(/\r?\n/u,1)[0]??'').replace(/^#{1,6}\s+/u,'').trim();
const grouping = new Set();
let pendingGroup = null;
let draggedNode = null;
const cp = text => Array.from(text);
function buildCpOffsets(text){
  const offsets=[];
  let utf16=0;
  for(const ch of text){offsets.push(utf16);utf16+=ch.length;}
  offsets.push(utf16);
  return Uint32Array.from(offsets);
}
function sliceDraft(start,end){
  if(!draft?.markdown)return '';
  return draft.markdown.slice(draftCpOffsets[start]??0,draftCpOffsets[end]??draft.markdown.length);
}
const clone = value => structuredClone(value);
const el = (tag, text, cls) => { const e = document.createElement(tag); if(text !== undefined) e.textContent = text; if(cls) e.className = cls; return e; };
function yieldToMain(){
  if(typeof window!=='undefined'&&'scheduler' in window&&window.scheduler&&'yield' in window.scheduler){
    return window.scheduler.yield();
  }
  return new Promise(resolve=>setTimeout(resolve,0));
}
function notice(text, error=false) { $('notice').textContent = text; $('notice').classList.toggle('error',error); }
async function request(path, options={}) {
  const response = await fetch(path,{credentials:'same-origin',cache:'no-store',...options,headers:{'Content-Type':'application/json','X-SAT-Review':'1',...options.headers}});
  if(!response.ok) { let body; try {body=await response.json();} catch {body={};} const detail=body.detail; throw new Error(response.status===403 ? 'Se requiere una sesión administradora. Inicia sesión y vuelve a conectar.' : typeof detail==='string' ? detail : detail ? JSON.stringify(detail) : `Error HTTP ${response.status}`); }
  return response.json();
}
const post = (path, body) => request(path,{method:'POST',body:JSON.stringify(body)});
function saveFile(text, name, type) { const url=URL.createObjectURL(new Blob([text],{type})); const a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
function canLeave() { return !(dirty||formDirty) || confirm('Hay cambios sin publicar. ¿Descartarlos y continuar?'); }
function setDirty(recompute=true) {
  if(recompute)dirty=JSON.stringify(draft)!==draftBaselineJson;
  $('draft-state').textContent=dirty?'Borrador sin publicar':doc?.published?'Fuente ya publicada':doc?.candidate?'Candidato sin publicar':'Sin cambios';
  $('publish').disabled=busy||!doc?.editable||(!dirty&&!doc?.candidate);
  $('discard').disabled=!(dirty||formDirty)||busy;
}
function versionFor(n) {return currentVersions.get(n.id);}
function textFor(n) {return sliceDraft(n.start,n.end);}
function previewFor(n) {return sliceDraft(n.start,Math.min(n.end,n.start+150));}
function options(select, entries, value) {
  const frag=document.createDocumentFragment();
  for(const [id,label] of entries){const option=el('option',label);option.value=id;frag.append(option);}
  select.replaceChildren(frag);
  select.value=value??'';
}
function syncDraftIndex(){
  draftCpOffsets=buildCpOffsets(draft?.markdown||'');
  draftCpLength=Math.max(0,draftCpOffsets.length-1);
  draftById=new Map();
  draftChildren=new Map();
  draftOrderedRows=[];
  if(!draft)return;
  for(const n of draft.components){
    draftById.set(n.id,n);
    const key=n.parent_id||'';
    let list=draftChildren.get(key);
    if(!list){list=[];draftChildren.set(key,list);}
    list.push(n);
  }
  for(const list of draftChildren.values()){
    list.sort((a,b)=>a.start-b.start||b.end-a.end||a.label.localeCompare(b.label));
  }
  const visited=new Set();
  const walk=(parent,depth)=>{
    for(const n of draftChildren.get(parent)||[]){
      if(visited.has(n.id))continue;
      visited.add(n.id);
      draftOrderedRows.push({n,depth,hasChildren:draftChildren.has(n.id)});
      walk(n.id,depth+1);
    }
  };
  walk('',0);
  for(const n of draft.components){
    if(!visited.has(n.id))draftOrderedRows.push({n,depth:0,hasChildren:false});
  }
}
function updateGroupButtons(){
  $('group-nodes').disabled=!grouping.size;
  $('promote-nodes').disabled=!grouping.size;
  $('clear-group').disabled=!grouping.size;
  $('group-nodes').textContent=grouping.size?`Crear padre (${grouping.size})`:'Crear padre';
}
function libraryRender(){
  const frag=document.createDocumentFragment();
  const filter=$('document-search').value.toLocaleLowerCase();
  const items=showingCandidates?candidates:library;
  for(const d of items){
    if(filter&&!(d.title+' '+d.id).toLocaleLowerCase().includes(filter))continue;
    const b=el('button',d.title,doc?.id===d.id?'active':'');
    b.append(el('small',d.candidate?(d.published?'Ya publicado':d.reference_only?'Publicable como referencia':'Pendiente de revisión'):`${d.components} componentes · ${d.retrievable} recuperables`));
    b.onclick=()=>{if(!busy&&canLeave())openDocument(d.id);};
    frag.append(b);
  }
  $('documents').replaceChildren(frag);
  $('doc-count').textContent=items.length;
  $('global-count').textContent=`${library.reduce((n,d)=>n+d.retrievable,0)} componentes`;
}
$('candidate-library').onclick=async()=>{
  if(busy)return;
  try{
    if(!showingCandidates)candidates=await request(`${BASE}/candidates`);
    showingCandidates=!showingCandidates;
    $('candidate-library').setAttribute('aria-pressed',String(showingCandidates));
    $('candidate-library').textContent=showingCandidates?'Ver corpus publicado':'Ver candidatos procesados';
    $('document-search').value='';libraryRender();
  }catch(error){notice(error.message,true);}
};
async function connect(){
  if(busy)return;busy=true;
  try{
    const result=await request(`${BASE}/documents`);library=result.documents;
    const position=readPosition();
    if(typeof position.id==='string'&&position.id.startsWith('candidate:')){
      try{candidates=await request(`${BASE}/candidates`);}catch{candidates=[];}
      showingCandidates=candidates.some(item=>item.id===position.id);
    }else showingCandidates=false;
    $('candidate-library').setAttribute('aria-pressed',String(showingCandidates));
    $('candidate-library').textContent=showingCandidates?'Ver corpus publicado':'Ver candidatos procesados';
    $('access').hidden=true;$('workspace').hidden=false;libraryRender();
    const items=showingCandidates?candidates:library;
    const id=items.some(item=>item.id===position.id)?position.id:items[0]?.id;
    busy=false;
    if(id)await openDocument(id,position.id===id?position:null);
    else notice('La base configurada no contiene documentos con versiones CTV.');
  }
  catch(error){notice(error.message,true);$('access').hidden=true;if(!doc){$('access').hidden=false;$('workspace').hidden=true;}}
  finally{busy=false;}
}
async function openDocument(id,position=null){
  if(busy)return;busy=true;notice('Cargando el documento completo…');
  try{
    const next=await request(`${BASE}/documents/${encodeURIComponent(id)}?include_texts=false`);
    // Editable documents derive active texts directly from edition.markdown;
    // only non-editable documents without an edition hydrate active texts eagerly.
    if(!next.edition){
      const current=next.versions.filter(v=>!v.archived);
      const texts=current.length?await post(`${API}/text-units/batch-get`,{versionIds:current.map(v=>v.id),language:'es'}):[];
      const byVersion=new Map();
      for(const t of texts){
        let list=byVersion.get(t.sourceId);
        if(!list){list=[];byVersion.set(t.sourceId,list);}
        list.push({id:t.id,language:t.language,text:t.content});
      }
      for(const v of current)v.texts=byVersion.get(v.id)||[];
    }
    showDocument(next,position);
    notice(doc.published?'Esta extracción es solo de consulta. Para corregir la edición activa, abre el documento desde «Ver corpus publicado».':doc.candidate?`Candidato sin publicar · ${doc.components} componentes · ${doc.diagnostics} avisos del parser. Contrasta con el PDF antes de publicar.`:`${doc.components} componentes cargados completos. ${doc.retrievable} disponibles para recuperación SAT; los demás organizan la estructura o no cumplen la selección vigente.`);
  }catch(error){notice(error.message,true);}finally{busy=false;setDirty(false);}
}
function showDocument(next,position=null){
    grouping.clear();
    clearTimeout(searchDebounceTimer);
    doc=next;draft=clone(doc.edition);draftBaselineJson=JSON.stringify(doc.edition);
    syncDraftIndex();
    dirty=false;formDirty=false;folded.clear();selected=draft?.components[0]?.id||null;
    if(position?.node&&draftById.has(position.node))selected=position.node;
    currentVersions=new Map(doc.versions.filter(v=>!v.archived).map(v=>[v.component_id,v]));
    historyDocument=null;historyRenderToken++;$('history').replaceChildren();$('all-versions').replaceChildren();
    $('component-search').value='';$('open-pdf').disabled=!(doc.directory||doc.candidate||doc.candidate_pdf);$('doc-title').textContent=doc.title;
    $('publish').textContent=doc.candidate?(doc.reference_only?'Publicar como referencia ↗':'Publicar candidato ↗'):'Aplicar al SAT-Graph ↗';
    $('doc-subtitle').textContent=`${doc.id} · Fuente original conservada · ${doc.editable?'Edición disponible':doc.published?'Solo lectura: fuente ya publicada':'Solo lectura: versiones no unívocas'}`;
    $('component-count').textContent=doc.components;$('retrievable-count').textContent=doc.retrievable;$('version-count').textContent=doc.versions.length;
    $('full-markdown').value=draft?.markdown||'Sin edición documental asociada. Consulta todas las versiones en Historial.';
    libraryRender();renderTree();renderInspector();
    setTab(['structure','markdown','history'].includes(position?.tab)?position.tab:'structure');setDirty(false);
    if(position?.node&&selected===position.node&&position.tab==='structure')
      rowElements.get(selected)?.scrollIntoView?.({block:'nearest'});
}
function syncSelectionRow(previousId,nextId){
  const prev=previousId?rowElements.get(previousId):null;
  if(prev){prev.classList.remove('selected');prev.setAttribute('aria-selected','false');}
  const next=nextId?rowElements.get(nextId):null;
  if(next){next.classList.add('selected');next.setAttribute('aria-selected','true');}
}
function updateRowInPlace(node){
  const row=rowElements.get(node.id);
  if(!row)return false;
  const labelSpan=row.querySelector('.node-select > span:last-child');
  if(labelSpan)labelSpan.textContent=node.label;
  const textBox=row.querySelector('.text-box');
  if(textBox)textBox.textContent=previewFor(node);
  const textBtn=row.querySelector('.text-cell');
  if(textBtn)textBtn.setAttribute('aria-label','Leer texto completo de '+node.label);
  const check=row.querySelector('.group-check');
  if(check)check.setAttribute('aria-label',`Agrupar ${node.label}`);
  if(dirty){
    for(const cellLabel of $('tree').querySelectorAll('.version-cell .cell-label')){
      if(cellLabel.firstChild&&cellLabel.firstChild.nodeType===3)cellLabel.firstChild.nodeValue='Borrador';
    }
  }
  return true;
}
function renderTree(){
  const editable=Boolean(doc?.editable&&draft);
  for(const id of ['group-nodes','promote-nodes','clear-group','group-hint'])$(id).hidden=!editable;
  updateGroupButtons();
  const tree=$('tree');
  rowElements=new Map();
  if(!draft){tree.replaceChildren(el('p','No hay estructura documental editable. Puedes leer todas las versiones en Historial.','empty'));return;}
  const query=$('component-search').value.trim().toLocaleLowerCase();
  const rows=draftOrderedRows;
  const matches=new Set();
  if(query){
    // Walk bottom-up: if any descendant matched, ancestors are already matched
    // so we never re-scan multi-hundred-KB parent container spans.
    for(let i=rows.length-1;i>=0;i--){
      const {n}=rows[i];
      if(matches.has(n.id)){
        let p=n.parent_id;
        while(p&&draftById.has(p)&&!matches.has(p)){matches.add(p);p=draftById.get(p).parent_id;}
        continue;
      }
      if(n.label.toLocaleLowerCase().includes(query)||textFor(n).toLocaleLowerCase().includes(query)){
        matches.add(n.id);
        let p=n.parent_id;
        while(p&&draftById.has(p)&&!matches.has(p)){matches.add(p);p=draftById.get(p).parent_id;}
      }
    }
  }
  const frag=document.createDocumentFragment();
  let count=0;
  for(const {n,depth,hasChildren} of rows){
    if(query&&!matches.has(n.id))continue;
    if(!query&&folded.size){
      let p=n.parent_id,hide=false;
      while(p&&draftById.has(p)){if(folded.has(p)){hide=true;break;}p=draftById.get(p).parent_id;}
      if(hide)continue;
    }
    count++;
    const row=el('div',undefined,'graph-row'+(selected===n.id?' selected':''));
    row.setAttribute('role','treeitem');
    row.setAttribute('aria-level',String(depth+1));
    row.setAttribute('aria-selected',String(selected===n.id));
    if(hasChildren)row.setAttribute('aria-expanded',String(!folded.has(n.id)));
    row.dataset.nodeId=n.id;
    const component=el('div',undefined,'component-cell');
    component.style.setProperty('--indent',`${10+Math.min(depth,12)*17}px`);
    if(editable){
      const check=el('input',undefined,'group-check');
      check.type='checkbox';
      check.checked=grouping.has(n.id);
      check.setAttribute('aria-label',`Agrupar ${n.label}`);
      component.append(check);
    }
    const fold=el('button',hasChildren?(folded.has(n.id)?'▸':'▾'):'·','fold');
    fold.setAttribute('aria-label',`${folded.has(n.id)?'Expandir':'Contraer'} ${n.label}`);
    fold.disabled=!hasChildren;
    const select=el('button',undefined,'node-select');
    select.append(el('span',undefined,'orb'+(!n.parent_id?' norm':'')),el('span',n.label));
    component.append(fold,select);
    row.append(component);
    if(editable){
      select.draggable=Boolean(n.parent_id);
      select.ondragstart=event=>{
        if(busy||!n.parent_id){event.preventDefault();return;}
        draggedNode=n.id;event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',n.label);
      };
      select.ondragend=()=>{draggedNode=null;$('tree').querySelectorAll('.drop-parent').forEach(item=>item.classList.remove('drop-parent'));};
      row.ondragover=event=>{
        if(!draggedNode||busy||draggedNode===n.id)return;
        event.preventDefault();event.dataTransfer.dropEffect='move';row.classList.add('drop-parent');
      };
      row.ondragleave=event=>{if(!row.contains(event.relatedTarget))row.classList.remove('drop-parent');};
      row.ondrop=event=>{
        if(!draggedNode)return;
        event.preventDefault();row.classList.remove('drop-parent');
        const source=draggedNode;draggedNode=null;void moveToParent(source,n.id);
      };
    }
    const v=versionFor(n);
    const version=el('button',undefined,'version-cell');
    const vl=el('span',dirty?'Borrador':v?.retrievable?'Vigente en SAT':'Estructural','cell-label');
    vl.append(el('small',v?'CTV · '+v.id.slice(-6):'Nueva al publicar'));
    version.append(el('span',undefined,'orb'),vl);
    const language=el('button',undefined,'language-cell');
    language.append(el('span',undefined,'orb'),el('span','es','cell-label'));
    const text=el('button',undefined,'text-cell');
    text.append(el('span',previewFor(n),'text-box'));
    text.setAttribute('aria-label','Leer texto completo de '+n.label);
    row.append(version,language,text);
    rowElements.set(n.id,row);
    frag.append(row);
  }
  if(!count)frag.append(el('p','No se encontraron componentes. Prueba otro término.','empty'));
  tree.replaceChildren(frag);
  $('tree-summary').textContent=`${count} de ${draft.components.length} componentes visibles · sin límite top-k · estructura y texto de la misma edición`;
}
$('tree').addEventListener('change',event=>{
  const check=event.target.closest?.('.group-check');
  if(!check)return;
  const id=check.closest('.graph-row')?.dataset.nodeId;
  if(!id)return;
  check.checked?grouping.add(id):grouping.delete(id);
  updateGroupButtons();
});
$('tree').addEventListener('click',event=>{
  const row=event.target.closest?.('.graph-row');
  if(!row)return;
  const id=row.dataset.nodeId;
  if(!id)return;
  if(event.target.closest('.fold')){
    if(event.target.closest('.fold').disabled)return;
    folded.has(id)?folded.delete(id):folded.add(id);
    renderTree();
    return;
  }
  if(event.target.closest('.group-check'))return;
  if(event.target.closest('.node-select,.version-cell,.language-cell,.text-cell')){
    void selectNode(id);
  }
});
async function selectNode(id){
  if(busy)return;
  if(formDirty&&!(await stage()))return;
  const previous=selected;
  selected=id;
  syncSelectionRow(previous,id);
  renderInspector();
  savePosition();
}
function invalidParentIds(nodeId){
  const invalid=new Set([nodeId]);
  const queue=[nodeId];
  for(let i=0;i<queue.length;i++){
    for(const child of draftChildren.get(queue[i])||[]){
      if(!invalid.has(child.id)){invalid.add(child.id);queue.push(child.id);}
    }
  }
  return invalid;
}
function hydrateParentOptions(node){
  if(!node||!draft||parentSelectHydratedFor===node.id)return;
  const invalid=invalidParentIds(node.id);
  const current=$('node-parent').value;
  options($('node-parent'),[['','Sin padre (raíz)'],...draft.components.filter(x=>!invalid.has(x.id)).map(x=>[x.id,x.label])],current);
  parentSelectHydratedFor=node.id;
}
$('node-parent').addEventListener('pointerdown',()=>{const n=draftById.get(selected);if(n)hydrateParentOptions(n);});
$('node-parent').addEventListener('focus',()=>{const n=draftById.get(selected);if(n)hydrateParentOptions(n);});
function renderInspector(){
  const n=draftById.get(selected);
  $('edit-form').hidden=!n||!doc.editable;$('readonly-info').hidden=true;
  $('create-child').hidden=$('split-section').hidden=$('split-section-hint').hidden=!n||!doc?.editable;
  if(!n){$('selected-title').textContent='Texto y estructura';$('selected-status').textContent='Selecciona un componente.';return;}
  $('selected-title').textContent=n.label;const v=versionFor(n);$('selected-status').textContent=v?.retrievable?'● Este componente alimenta al recuperador SAT.':'○ Componente organizativo o no recuperable en la selección actual.';
  if(!doc.editable){$('readonly-info').hidden=false;$('readonly-info').textContent=textFor(n);return;}
  $('node-label').value=n.label;
  if(!$('node-kind').options.length||$('node-kind').options.length!==Object.keys(kinds).length){
    options($('node-kind'),Object.entries(kinds),n.kind);
  }else{$('node-kind').value=n.kind;}
  if(!kinds[n.kind]){$('node-kind').append(new Option(n.kind,n.kind));$('node-kind').value=n.kind;}
  parentSelectHydratedFor=null;
  const parentNode=n.parent_id?draftById.get(n.parent_id):null;
  const initialParents=[['','Sin padre (raíz)']];
  if(parentNode)initialParents.push([parentNode.id,parentNode.label]);
  options($('node-parent'),initialParents,n.parent_id);
  $('node-text').value=textFor(n);previousBodyLabel=labelFromText($('node-text').value);$('node-start').value=n.start;$('node-end').value=n.end;
  $('node-ids').textContent=`Componente: ${n.id}\nItem: ${v?.work_id||'Nuevo'}\nVersion / CTV: ${v?.id||'Nueva'}\nTextUnit / CLV: ${v?.texts[0]?.id||'Nueva'}\nEdición: ${draft.revision}`;formDirty=false;
}
function updateDraft(edition){
  draft=edition;
  syncDraftIndex();
  grouping.clear();formDirty=false;
  $('full-markdown').value=draft.markdown;
  setDirty(true);renderTree();renderInspector();
}
async function moveToParent(sourceId,parentId){
  if(busy||!doc?.editable||!draft)return;
  if(formDirty&&!(await stage()))return;
  const next=clone(draft), nodes=new Map(next.components.map(n=>[n.id,n]));
  const source=nodes.get(sourceId), parent=nodes.get(parentId);
  if(!source?.parent_id||!parent||source.parent_id===parentId)return;
  const ancestors=[], seen=new Set([sourceId]);
  for(let n=parent;n;n=nodes.get(n.parent_id)){
    if(seen.has(n.id)){notice('No se puede mover un nodo dentro de sí mismo ni de sus descendientes.',true);return;}
    seen.add(n.id);ancestors.push(n);
  }
  let start=source.start,end=source.end,expanded=false;
  for(const n of ancestors){
    start=Math.min(start,n.start);end=Math.max(end,n.end);
    expanded||=start!==n.start||end!==n.end;
    n.start=start;n.end=end;
  }
  source.parent_id=parentId;
  for(const n of ancestors)folded.delete(n.id);
  selected=sourceId;updateDraft(next);savePosition();
  notice(`«${source.label}» ahora está bajo «${parent.label}» en el borrador.${expanded?' Se ampliaron los rangos necesarios; el Markdown no cambió.':''}`);
}
function scheduleDraftSave(){
  clearTimeout(draftSaveTimer);
  draftSaveTimer=setTimeout(()=>stage(),500);
}
async function stage(event){
  event?.preventDefault();clearTimeout(draftSaveTimer);
  if(busy||!doc?.editable||!selected)return false;
  if(!formDirty)return true;
  busy=true;setDirty(false);
  const generation=inspectorGeneration;
  try{
    let next=clone(draft),n=next.components.find(x=>x.id===selected);
    const start=Number($('node-start').value),end=Number($('node-end').value);
    if(start!==n.start||end!==n.end)throw new Error('Primero pulsa «Cargar rango» para confirmar los límites.');
    const body=$('node-text').value,label=$('node-label').value.trim(),kind=$('node-kind').value,parentId=$('node-parent').value||null;
    if(!label||!body.trim())throw new Error('La etiqueta y el texto no pueden estar vacíos.');
    const originalCount=next.components.length;
    const originalParent=n.parent_id;
    const textChanged=body!==textFor(n);
    if(textChanged)next=await post(`${BASE}/preview`,{edition:next,component_id:n.id,text:body});
    if(generation!==inspectorGeneration)return false;
    n=next.components.find(x=>x.id===selected);n.label=label;n.kind=kind;n.parent_id=parentId;
    const parent=next.components.find(x=>x.id===n.parent_id);if(parent&&!(parent.start<=n.start&&n.end<=parent.end))throw new Error('El nuevo padre debe contener este fragmento. Ajusta sus rangos primero.');
    draft=next;syncDraftIndex();formDirty=false;
    $('full-markdown').value=next.markdown;$('selected-title').textContent=label;
    $('node-start').value=n.start;$('node-end').value=n.end;
    busy=false;setDirty(true);
    const removed=originalCount-next.components.length;
    if(removed||parentId!==originalParent||textChanged||!updateRowInPlace(n)){
      renderTree();
    }
    notice(removed?`Borrador guardado: se retiraron ${removed} nodo(s) cuyo texto borraste por completo.`:'Cambios guardados automáticamente en el borrador.');
    return true;
  }catch(error){if(generation===inspectorGeneration)notice(error.message,true);return false;}
  finally{busy=false;setDirty(false);if(generation!==inspectorGeneration&&formDirty)scheduleDraftSave();}
}
async function hydrateVersionDetails(details,v){
  if(details.dataset.loaded)return;
  details.dataset.loaded='1';
  details.append(el('pre',`Item: ${v.work_id}\nVersion: ${v.id}\nProcedencia: ${v.provenance}`));
  let texts=v.texts||[];
  const needsFetch=!texts.length||texts.some(t=>t.text===undefined);
  if(needsFetch){
    const activeNode=!v.archived&&draftById.get(v.component_id);
    if(activeNode){
      texts=[{id:texts[0]?.id||'',language:texts[0]?.language||'es',text:textFor(activeNode)}];
    }else{
      const status=el('p','Cargando texto almacenado…','muted');
      details.append(status);
      try{
        const units=await post(`${API}/text-units/batch-get`,{versionIds:[v.id],language:'es'});
        texts=units.map(t=>({id:t.id,language:t.language,text:t.content}));
        v.texts=texts;
      }catch(error){
        status.textContent=error.message;
        return;
      }
      status.remove();
    }
  }
  for(const t of texts)details.append(el('div',t.text,'readonly-body'));
}
async function renderHistory(){
  const token=++historyRenderToken;
  const hFrag=document.createDocumentFragment();
  if(!doc.history.length)hFrag.append(el('p','Todavía no hay correcciones publicadas desde este editor.','empty'));
  for(const h of doc.history){
    const div=el('div',undefined,'history-entry');
    div.append(el('strong',h.reason),el('p',`${h.component_count} componentes · ${h.reviewer}`),el('small',h.recorded_at+' · '+h.revision));
    hFrag.append(div);
  }
  $('history').replaceChildren(hFrag);
  const container=$('all-versions');
  container.replaceChildren();
  const versions=doc.versions||[];
  let deadline=(typeof performance!=='undefined'?performance.now():Date.now())+50;
  let batch=document.createDocumentFragment();
  for(let i=0;i<versions.length;i++){
    if(token!==historyRenderToken)return;
    const v=versions[i];
    const details=el('details');
    details.dataset.versionIndex=String(i);
    details.append(el('summary',`${v.archived?'Archivada':v.retrievable?'Recuperable':'Estructural / no seleccionada'} · ${v.label}`));
    batch.append(details);
    if(i>0&&i%200===0&&(typeof performance!=='undefined'?performance.now():Date.now())>=deadline){
      container.append(batch);
      batch=document.createDocumentFragment();
      await yieldToMain();
      deadline=(typeof performance!=='undefined'?performance.now():Date.now())+50;
    }
  }
  if(token===historyRenderToken)container.append(batch);
}
$('all-versions').addEventListener('toggle',event=>{
  const details=event.target;
  if(!(details instanceof Element)||details.tagName!=='DETAILS'||!details.open)return;
  const index=Number(details.dataset.versionIndex);
  const v=doc?.versions?.[index];
  if(v)void hydrateVersionDetails(details,v);
},true);
function setTab(tab){for(const b of document.querySelectorAll('[data-tab]'))b.setAttribute('aria-selected',String(b.dataset.tab===tab));for(const name of ['structure','markdown','history'])$(name+'-view').hidden=name!==tab;if(tab==='history'&&doc&&historyDocument!==doc){void renderHistory();historyDocument=doc;}savePosition();}
async function publish(){
  if(busy||!doc?.editable||!draft)return;
  if(formDirty&&!(await stage()))return;
  if(!dirty&&!doc.candidate)return;
  if(doc.candidate&&!confirm(doc.reference_only
    ?'¿Publicar esta edición como referencia documental, sin incorporarla al recuperador del chat?'
    :'¿Confirmas que revisaste el PDF y la estructura, y quieres incorporar esta edición al corpus del chat?'))return;
  busy=true;setDirty(false);$('review-grid').inert=true;notice('Aplicando revisión al SAT-Graph…');
  try{
    const result=await post(`${BASE}/documents/${encodeURIComponent(doc.id)}`,{edition:draft,reason:'Aplicación directa desde el editor SAT'});
    if(doc.candidate){
      candidates=candidates.map(item=>item.id===doc.id?{...item,published:true}:item);
      if(!library.some(item=>item.id===result.id))library.push(result);
    }
    library=library.map(item=>item.id===result.id?{...item,components:result.components,retrievable:result.retrievable}:item);
    showDocument(result);
    notice(result.origin_candidate?'Revisión aplicada al SAT-Graph.':'Revisión aplicada. La edición anterior quedó archivada.');
  }catch(error){notice(error.message,true);}finally{busy=false;$('review-grid').inert=false;setDirty(false);}
}
function addSelection(){
  if(!doc?.editable)return;const ta=$('full-markdown');const start=cp(ta.value.slice(0,ta.selectionStart)).length,end=cp(ta.value.slice(0,ta.selectionEnd)).length;
  if(end<=start){notice('Selecciona primero el texto del componente en el Markdown.',true);return;}
  pendingGroup=null;$('add-title').textContent='Completar la estructura';$('add-parent').disabled=false;
  selection={start,end};$('add-range').textContent=`Caracteres ${start}–${end} · ${end-start} caracteres Unicode`;$('add-label').value='';options($('add-kind'),Object.entries(kinds),'article');
  const parents=draft.components.filter(n=>n.start<=start&&end<=n.end).sort((a,b)=>(a.end-a.start)-(b.end-b.start));options($('add-parent'),[['','Sin padre (raíz)'],...parents.map(n=>[n.id,n.label])],parents[0]?.id);$('add-dialog').showModal();
}
function prepareGroup(){
  if(busy||!doc?.editable||!grouping.size)return;
  if(formDirty){notice('Guarda primero los cambios del inspector en el borrador.',true);return;}
  const children=draft.components.filter(n=>grouping.has(n.id));
  const parentId=children[0].parent_id;
  if(children.some(n=>n.parent_id!==parentId)){
    notice('Marca solo filas que tengan el mismo padre actual. Sus descendientes se moverán con ellas.',true);return;
  }
  const start=Math.min(...children.map(n=>n.start)), end=Math.max(...children.map(n=>n.end));
  const parent=draftById.get(parentId);
  const siblings=draft.components.filter(n=>n.parent_id===parentId&&!grouping.has(n.id));
  // Some imported instruments already cover their sibling titles' ranges.
  // Enclosing spans are not gaps between the selected children.
  if(siblings.some(n=>n.start<end&&n.end>start&&!(n.start<start&&n.end>=end))){
    notice('Hay un componente sin marcar dentro del bloque. Márcalo también o crea grupos separados.',true);return;
  }
  const lower=Math.max(parent?.start??0,...siblings.filter(n=>n.end<=start).map(n=>n.end));
  const prefix=sliceDraft(lower,start);
  const heading=prefix.match(/(?:^|\n)(#{1,6}[ \t]+[^\r\n]+)\s*$/u);
  pendingGroup={ids:new Set(grouping),parentId,start,end,heading:heading?{start:lower+cp(prefix.slice(0,heading.index+heading[0].indexOf(heading[1]))).length,label:heading[1].replace(/^#+\s+/u,'').trim()}:null};
  $('add-title').textContent='Crear padre para los componentes marcados';
  $('add-label').value=pendingGroup.heading?.label??'';
  options($('add-kind'),Object.entries(kinds),'instrument');
  options($('add-parent'),[[parentId??'',parent?.label??'Sin padre (raíz)']],parentId);
  $('add-parent').disabled=true;
  $('add-range').textContent=`${children.length} componentes pasarán al nuevo padre con todos sus descendientes.`;
  $('add-dialog').showModal();
}
$('group-nodes').onclick=prepareGroup;
$('promote-nodes').onclick=async ()=>{
  if(busy||!doc?.editable||!grouping.size)return;
  if(formDirty&&!(await stage()))return;
  const next=clone(draft), nodes=new Map(next.components.map(n=>[n.id,n]));
  const children=next.components.filter(n=>grouping.has(n.id));
  const parent=nodes.get(children[0]?.parent_id);
  if(!parent||children.some(n=>n.parent_id!==parent.id)){
    notice('Marca componentes que tengan el mismo padre y que no estén ya en la raíz.',true);return;
  }
  const grandparent=nodes.get(parent.parent_id);
  if(grandparent&&children.some(n=>n.start<grandparent.start||n.end>grandparent.end)){
    notice('El padre de destino no contiene todos los rangos seleccionados.',true);return;
  }
  for(const child of children)child.parent_id=parent.parent_id??null;
  const first=Math.min(...children.map(n=>n.start));
  // Trim only a trailing block, leaving all remaining children covered.
  if(first>parent.start&&!next.components.some(n=>n.parent_id===parent.id&&n.end>first)){
    parent.end=first;
  }
  selected=children[0].id;updateDraft(next);
  notice(`${children.length} componente(s) quedaron al mismo nivel que «${parent.label}» en el borrador.`);
};
$('clear-group').onclick=()=>{grouping.clear();renderTree();};
function planBranchMove(parentId,start,end){
  const moved=[],trim=[];
  function visit(id){
    for(const n of draftChildren.get(id)||[]){
      if(n.end<=start||n.start>=end)continue;
      if(n.end>end)throw new Error(`La selección termina dentro de «${n.label}». Extiéndela hasta el final de ese nodo.`);
      if(n.start>=start)moved.push(n);
      else{trim.push(n);visit(n.id);}
    }
  }
  visit(parentId);
  return {moved,trim};
}
$('create-child').onclick=()=>{
  const parent=draftById.get(selected);
  if(busy||!doc?.editable||!parent)return;
  const hint=$('split-section-hint');
  if(formDirty){hint.textContent='Guarda los cambios del inspector antes de crear el hijo.';return;}
  const input=$('node-text'), text=textFor(parent);
  if(input.value!==text){hint.textContent='El texto no coincide con el borrador. Usa la selección en Markdown completo.';return;}
  const fragment=text.slice(input.selectionStart,input.selectionEnd);
  if(!fragment.trim()){hint.textContent='Marca en el cuadro de texto el fragmento que quieres convertir en hijo.';return;}
  const start=parent.start+cp(text.slice(0,input.selectionStart)).length;
  const end=start+cp(fragment).length;
  let plan;
  try{plan=planBranchMove(parent.id,start,end);}catch(error){hint.textContent=error.message;return;}
  const {moved,trim}=plan;
  pendingGroup={ids:new Set(moved.map(n=>n.id)),trimIds:new Set(trim.map(n=>n.id)),start,end};
  selection={start,end};
  $('add-title').textContent='Crear hijo dentro del componente';
  const label=fragment.trim().split(/\r?\n/u,1)[0].replace(/^#+\s+/u,'');
  $('add-label').value=label;
  options($('add-kind'),Object.entries(kinds),/^LIBRO\b/iu.test(label)?'libro':/^(?:[-*]\s+)?[\p{L}][.)]\s/u.test(label)?'inciso':'numeral');
  options($('add-parent'),[[parent.id,parent.label]],parent.id);$('add-parent').disabled=true;
  $('add-range').textContent=moved.length||trim.length
    ?`${moved.length} componente(s) pasarán al nuevo nodo con sus descendientes. ${trim.length?`Se ajustará el final de ${trim.map(n=>n.label).join(', ')} al inicio de la selección. `:''}El Markdown no cambia.`
    :'El texto y los rangos del padre y de sus demás hijos no cambiarán.';
  $('add-dialog').showModal();
};
$('split-section').onclick=()=>{
  const source=draftById.get(selected);
  if(busy||!doc?.editable||!source)return;
  if(formDirty){notice('Guarda primero los cambios del inspector y luego selecciona el texto.',true);return;}
  const input=$('node-text'), text=textFor(source);
  // Textareas normalize CRLF; do not apply offsets to a different string.
  if(input.value!==text){notice('El texto del inspector no coincide con el borrador. Usa la vista Markdown para editar los rangos.',true);return;}
  const start=source.start+cp(text.slice(0,input.selectionStart)).length;
  const end=source.start+cp(text.slice(0,input.selectionEnd)).length;
  if(start<=source.start||end<=start||end>source.end){notice('Selecciona desde el encabezado de la nueva sección hasta el final de su texto.',true);return;}
  let plan;
  try{plan=planBranchMove(source.id,start,end);}catch(error){$('split-section-hint').textContent=error.message;return;}
  if((draftChildren.get(source.id)||[]).some(n=>n.start>=end)){
    $('split-section-hint').textContent='Para separar como hermana, incluye también los hijos posteriores o usa «Crear hijo».';
    return;
  }
  const label=text.slice(input.selectionStart,input.selectionEnd).trim().split(/\r?\n/,1)[0]?.replace(/^#+\s*/,'').trim();
  if(!label){notice('Incluye el encabezado de la nueva sección en la selección.',true);return;}
  const {moved,trim}=plan;
  if(!confirm(`¿Crear «${label}» al mismo nivel que «${source.label}», mover ${moved.length} componente(s) y ajustar ${trim.length} rango(s) internos?`))return;
  const next=clone(draft), id='new:'+crypto.randomUUID();
  next.components.find(n=>n.id===source.id).end=start;
  next.components.push({id,label,kind:source.kind,parent_id:source.parent_id,start,end});
  const movedIds=new Set(moved.map(n=>n.id));
  const trimIds=new Set(trim.map(n=>n.id));
  for(const n of next.components)if(trimIds.has(n.id))n.end=start;
  for(const n of next.components)if(movedIds.has(n.id))n.parent_id=id;
  selected=id;updateDraft(next);
  notice('Sección separada en el borrador. Revisa el árbol antes de aplicar al SAT-Graph.');
};
$('edit-form').addEventListener('submit',stage);
$('edit-form').addEventListener('input',event=>{
  if(event.target.id==='node-text'){
    const label=labelFromText(event.target.value);
    if(label&&label!==previousBodyLabel)$('node-label').value=label;
    previousBodyLabel=label;
  }
  inspectorGeneration++;formDirty=true;setDirty(false);
  if(event.target.id==='node-start'||event.target.id==='node-end')clearTimeout(draftSaveTimer);
  else scheduleDraftSave();
});
$('load-span').onclick=()=>{const n=draftById.get(selected),start=Number($('node-start').value),end=Number($('node-end').value);if(!Number.isInteger(start)||!Number.isInteger(end)||start<0||end<=start||end>draftCpLength){notice('Rango inválido.',true);return;}if(!confirm('Se cargará este rango del Markdown y se descartará el texto no guardado del inspector. ¿Continuar?'))return;const next=clone(draft);Object.assign(next.components.find(x=>x.id===n.id),{start,end});updateDraft(next);notice('Rango actualizado en borrador. Comprueba la relación con sus hijos y padre antes de publicar.');};
$('remove-node').onclick=()=>{const n=draftById.get(selected);if(!confirm(`¿Quitar «${n.label}» de la estructura? Se conserva el Markdown y los hijos subirán al padre de este nodo.`))return;const next=clone(draft);next.components=next.components.filter(x=>x.id!==n.id).map(x=>x.parent_id===n.id?{...x,parent_id:n.parent_id}:x);selected=next.components[0]?.id||null;updateDraft(next);};
$('add-form').onsubmit=event=>{
  event.preventDefault();
  if(busy||!doc?.editable)return;
  const label=$('add-label').value.trim();
  if(!label){notice('Escribe el nombre del componente.',true);return;}
  const next=clone(draft);
  const range=pendingGroup?{start:pendingGroup.heading?.label===label?pendingGroup.heading.start:pendingGroup.start,end:pendingGroup.end}:selection;
  const n={id:'new:'+crypto.randomUUID(),label,kind:$('add-kind').value,parent_id:$('add-parent').value||null,...range};
  if(pendingGroup){
    for(const child of next.components)if(pendingGroup.trimIds?.has(child.id))child.end=n.start;
    for(const child of next.components)if(pendingGroup.ids.has(child.id))child.parent_id=n.id;
    $('component-search').value='';
  }
  next.components.push(n);selected=n.id;pendingGroup=null;updateDraft(next);$('add-dialog').close();setTab('structure');
  notice('Componente creado en el borrador. Revisa el árbol antes de aplicar al SAT-Graph.');
};
$('add-selection').onclick=addSelection;$('cancel-add').onclick=()=>$('add-dialog').close();$('publish').onclick=publish;
$('discard').onclick=()=>{if(confirm('¿Descartar todos los cambios no publicados?')){selected=doc.edition.components[0]?.id;updateDraft(clone(doc.edition));notice('Borrador descartado. El grafo no cambió.');}};
$('download').onclick=()=>{if(draft)saveFile(draft.markdown,`${doc.id.replaceAll(':','-')}${dirty?'-borrador':''}.md`,'text/markdown;charset=utf-8');};
$('download-draft').onclick=()=>{if(draft)saveFile(JSON.stringify(draft,null,2),'sat-borrador.json','application/json');};
$('open-pdf').onclick=()=>{if(doc)window.open(`${BASE}/documents/${encodeURIComponent(doc.id)}/pdf`,'_blank','noopener');};
$('expand').onclick=()=>{folded.clear();renderTree();};$('collapse').onclick=()=>{folded=new Set(draft?.components.map(n=>n.id)||[]);renderTree();};
$('component-search').oninput=()=>{
  clearTimeout(searchDebounceTimer);
  if((draft?.components?.length||0)>250){
    searchDebounceTimer=setTimeout(renderTree,120);
  }else{
    renderTree();
  }
};
$('document-search').oninput=libraryRender;
for(const b of document.querySelectorAll('[data-tab]'))b.onclick=()=>setTab(b.dataset.tab);
$('reload').onclick=()=>{if(canLeave())connect();};$('retry').onclick=connect;
$('toggle-inspector').onclick = () => {
  const inspector = $('component-inspector');
  const collapsed = !inspector.hidden;
  inspector.hidden = collapsed;
  $('review-grid').classList.toggle('inspector-collapsed', collapsed);
  $('toggle-inspector').setAttribute('aria-expanded', String(!collapsed));
  $('toggle-inspector').textContent = collapsed ? 'Mostrar inspector' : 'Ocultar inspector';
};
$('collapse-inspector').onclick = () => {
  $('toggle-inspector').click();
  $('toggle-inspector').focus();
};
window.addEventListener('beforeunload',event=>{if(dirty||formDirty){event.preventDefault();event.returnValue='';}});
connect();
