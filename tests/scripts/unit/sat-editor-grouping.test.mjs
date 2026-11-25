import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {JSDOM} from 'jsdom';

test('group titles, create a child and autosave a changed heading without publishing', async () => {
  const assets = new URL('../../../backend/static/sat-review/', import.meta.url);
  const dom = new JSDOM(readFileSync(new URL('index.html', assets), 'utf8'), {
    runScripts: 'outside-only',
    url: 'http://localhost:8010/sat-graph/review',
  });
  const {window} = dom;
  window.structuredClone = structuredClone;
  window.HTMLDialogElement.prototype.showModal = function () {this.open = true;};
  window.HTMLDialogElement.prototype.close = function () {this.open = false;};
  const markdown = 'Decreto\n\n## REGLAMENTO\n\n## TÍTULO I\nArtículo\n## TÍTULO II\n## TÍTULO III\n';
  const title1 = markdown.indexOf('## TÍTULO I');
  const title2 = markdown.indexOf('## TÍTULO II');
  const title3 = markdown.indexOf('## TÍTULO III');
  const node = (id, label, start, end, parent_id, kind = 'titulo') => ({id,label,start,end,parent_id,kind});
  window.fixture = {id:'fixture',title:'Fixture',editable:true,history:[],versions:[],components:6,retrievable:0,
    edition:{markdown,components:[
      node('root','Documento',0,markdown.length,null,'document'),
      node('decree','Decreto',0,markdown.length,'root','instrument'),
      node('i','Título I',title1,title2,'root'),
      node('article','Artículo',markdown.indexOf('Artículo'),title2,'i','article'),
      node('ii','Título II',title2,title3,'root'),
      node('iii','Título III',title3,markdown.length,'root'),
    ]},
  };
  try {
    window.eval(readFileSync(new URL('editor.js', assets), 'utf8').replace(/\bconnect\(\);\s*$/u, 'window.loadFixture=position=>showDocument(window.fixture,position); window.loadFixture(); window.readDraft=()=>draft;'));
    const $ = id => window.document.getElementById(id);
    const mark = id => window.document.querySelector(`[data-node-id="${id}"] .group-check`).click();
    mark('i'); mark('iii');
    $('group-nodes').click();
    assert.match($('notice').textContent,/sin marcar/);
    mark('ii');
    $('group-nodes').click();
    assert.equal($('add-label').value,'REGLAMENTO');
    assert.equal($('add-kind').value,'instrument');
    $('add-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
    const result = window.readDraft();
    const parent = result.components.find(n=>n.label==='REGLAMENTO');
    assert.equal(parent.parent_id,'root');
    assert.equal(parent.start,markdown.indexOf('## REGLAMENTO'));
    assert.equal(parent.end,markdown.length);
    for (const id of ['i','ii','iii']) assert.equal(result.components.find(n=>n.id===id).parent_id,parent.id);
    assert.equal(result.components.find(n=>n.id==='article').parent_id,'i');
    assert.equal(result.components.find(n=>n.id==='decree').parent_id,'root');
    assert.equal(result.markdown,markdown);
    assert.equal($('draft-state').textContent,'Borrador sin publicar');
    const articleRow=window.document.querySelector('[data-node-id="article"] .node-select');
    articleRow.click();
    $('node-text').select();
    $('create-child').click();
    assert.equal($('add-parent').value,'article');
    $('add-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
    const withChild=window.readDraft();
    assert.equal(withChild.components.at(-1).parent_id,'article');
    assert.deepEqual(JSON.stringify(withChild.components.find(n=>n.id==='article')),JSON.stringify(result.components.find(n=>n.id==='article')));
    assert.equal(withChild.markdown,markdown);
    const child=withChild.components.at(-1);
    window.fetch=async (url,options)=>{
      assert.equal(url,'/sat-graph/review/preview');
      const {edition,text}=JSON.parse(options.body);
      assert.equal(text,'## Artículo corregido\n');
      return {ok:true,json:async()=>edition};
    };
    $('node-text').value='## Artículo corregido\n';
    $('node-text').dispatchEvent(new window.Event('input',{bubbles:true}));
    assert.equal($('node-label').value,'Artículo corregido');
    for(let i=0;i<30&&window.readDraft().components.at(-1).label===child.label;i++){
      await new Promise(resolve=>setTimeout(resolve,50));
    }
    assert.equal(window.readDraft().components.at(-1).label,'Artículo corregido');
    mark('ii'); mark('iii');
    await $('promote-nodes').onclick();
    const promoted=window.readDraft();
    for(const id of ['ii','iii'])assert.equal(promoted.components.find(n=>n.id===id).parent_id,'root');
    assert.equal(promoted.components.find(n=>n.id===parent.id).end,title2);
    assert.equal(promoted.components.find(n=>n.id==='i').parent_id,parent.id);
    assert.equal(promoted.markdown,markdown);
    // Use a source without the intentionally overlapping decree from the first fixture.
    window.fixture.edition.components.find(n=>n.id==='decree').end=title1;
    window.loadFixture();
    window.document.querySelector('[data-node-id="root"] .node-select').click();
    $('node-text').setSelectionRange(title2,markdown.length-2);
    $('create-child').click();
    assert.match($('split-section-hint').textContent,/termina dentro.*Título III/);
    $('node-text').setSelectionRange(title2,markdown.length);
    $('create-child').click();
    $('add-label').value='LIBRO PRIMERO';
    $('add-kind').value='libro';
    $('add-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
    const wrapped=window.readDraft(), book=wrapped.components.at(-1);
    assert.equal(book.kind,'libro');
    assert.equal(book.parent_id,'root');
    for(const id of ['ii','iii'])assert.equal(wrapped.components.find(n=>n.id===id).parent_id,book.id);
    assert.equal(wrapped.markdown,markdown);
    window.fixture.edition.components.find(n=>n.id==='decree').end=title2;
    window.loadFixture();
    $('node-text').setSelectionRange(title1+3,markdown.length);
    $('create-child').click();
    assert.match($('add-range').textContent,/Se ajustará el final de Decreto, Título I/);
    $('cancel-add').click();
    const cut=markdown.indexOf('Artículo')+2;
    $('node-text').setSelectionRange(cut,markdown.length);
    $('create-child').click();
    assert.match($('add-range').textContent,/Título I, Artículo/);
    $('add-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
    assert.equal(window.readDraft().components.find(n=>n.id==='article').end,cut);
    assert.equal(window.readDraft().markdown,markdown);
    window.loadFixture();
    $('node-text').setSelectionRange(title1,markdown.length);
    $('create-child').click();
    assert.match($('add-range').textContent,/Se ajustará el final de Decreto/);
    $('add-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
    assert.equal(window.readDraft().components.find(n=>n.id==='decree').end,title1);
    window.document.querySelector('[data-node-id="iii"] .node-select').click();
    window.document.querySelector('[data-tab="markdown"]').click();
    const position=JSON.parse(window.localStorage.getItem('sat-review-position-v1'));
    assert.deepEqual(position,{id:'fixture',node:'iii',tab:'markdown'});
    window.loadFixture(position);
    assert.equal($('node-label').value,'Título III');
    assert.equal($('markdown-view').hidden,false);
    window.loadFixture();
    const titleRow=window.document.querySelector('[data-node-id="i"]');
    const targetRow=window.document.querySelector('[data-node-id="ii"]');
    titleRow.querySelector('.node-select').ondragstart({dataTransfer:{setData(){}}});
    targetRow.ondrop({preventDefault(){}});
    const moved=window.readDraft();
    assert.equal(moved.components.find(n=>n.id==='i').parent_id,'ii');
    assert.equal(moved.components.find(n=>n.id==='ii').start,title1);
    assert.equal(moved.components.find(n=>n.id==='article').parent_id,'i');
    assert.equal(moved.markdown,markdown);
    window.document.querySelector('[data-node-id="ii"] .node-select').ondragstart({dataTransfer:{setData(){}}});
    window.document.querySelector('[data-node-id="article"]').ondrop({preventDefault(){}});
    assert.match($('notice').textContent,/descendientes/);
  } finally {window.close();}
});

test('selection reuses tree DOM, parent options hydrate on focus, and history loads on toggle', async () => {
  const assets = new URL('../../../backend/static/sat-review/', import.meta.url);
  const dom = new JSDOM(readFileSync(new URL('index.html', assets), 'utf8'), {
    runScripts: 'outside-only',
    url: 'http://localhost:8010/sat-graph/review',
  });
  const {window} = dom;
  window.structuredClone = structuredClone;
  const markdown = 'Norma 😀\n## Artículo 1\nTexto ñ único.\n';
  const cpLen = s => Array.from(s).length;
  const artStart = cpLen(markdown.slice(0, markdown.indexOf('## Artículo 1')));
  const totalCp = cpLen(markdown);
  window.fixture = {
    id: 'pe:ley:test',
    title: 'Ley de prueba',
    editable: true,
    history: [],
    components: 2,
    retrievable: 1,
    versions: [
      {
        id: 'v-active',
        work_id: 'w-art1',
        component_id: 'art1',
        label: 'Artículo 1',
        retrievable: true,
        archived: false,
        provenance: 'user_attested_snapshot',
        texts: [{id: 't-active', language: 'es'}],
      },
      {
        id: 'v-archived',
        work_id: 'w-art1',
        component_id: 'art1-old',
        label: 'Artículo 1 (anterior)',
        retrievable: false,
        archived: true,
        provenance: 'user_attested_snapshot',
        texts: [{id: 't-archived', language: 'es'}],
      },
    ],
    edition: {
      revision: 'rev-1',
      markdown,
      components: [
        {id: 'root', label: 'Norma', kind: 'document', parent_id: null, start: 0, end: totalCp},
        {id: 'art1', label: 'Artículo 1', kind: 'article', parent_id: 'root', start: artStart, end: totalCp},
      ],
    },
  };
  try {
    window.eval(
      readFileSync(new URL('editor.js', assets), 'utf8').replace(
        /\bconnect\(\);\s*$/u,
        'window.loadFixture=()=>showDocument(window.fixture); window.loadFixture();',
      ),
    );
    const $ = id => window.document.getElementById(id);

    // 1. Unicode non-BMP (emoji) slicing matches exact codepoint offsets.
    const artRowBefore = window.document.querySelector('[data-node-id="art1"]');
    artRowBefore.querySelector('.node-select').click();
    await new Promise(resolve => setTimeout(resolve, 10));
    const artRowAfter = window.document.querySelector('[data-node-id="art1"]');
    assert.equal(artRowAfter, artRowBefore, 'selectNode must toggle classes in place without rebuilding #tree');
    assert.equal(artRowAfter.getAttribute('aria-selected'), 'true');
    assert.equal($('node-text').value, '## Artículo 1\nTexto ñ único.\n');

    // 2. Parent dropdown starts minimal and hydrates full valid options on focus (excluding self/descendants).
    assert.equal($('node-parent').options.length, 2);
    $('node-parent').dispatchEvent(new window.Event('focus'));
    assert.deepEqual(
      Array.from($('node-parent').options, o => o.value),
      ['', 'root'],
    );

    // 3. History tab renders collapsed <details> lazily and fetches archived text only on toggle.
    let batchCalls = 0;
    window.fetch = async (url, options) => {
      batchCalls++;
      assert.equal(url, '/sat-graph/api/text-units/batch-get');
      const body = JSON.parse(options.body);
      assert.deepEqual(body.versionIds, ['v-archived']);
      return {
        ok: true,
        json: async () => [{id: 't-archived', sourceId: 'v-archived', language: 'es', content: 'Texto histórico archivado'}],
      };
    };
    window.document.querySelector('[data-tab="history"]').click();
    await new Promise(resolve => setTimeout(resolve, 10));
    const details = window.document.querySelectorAll('#all-versions details');
    assert.equal(details.length, 2);
    assert.equal(window.document.querySelectorAll('#all-versions .readonly-body').length, 0);
    assert.equal(batchCalls, 0);

    // Expanding active version reads from draft markdown without network call.
    details[0].open = true;
    details[0].dispatchEvent(new window.Event('toggle'));
    await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(batchCalls, 0);
    assert.match(details[0].textContent, /Texto ñ único/);

    // Expanding archived version hydrates via batch-get once.
    details[1].open = true;
    details[1].dispatchEvent(new window.Event('toggle'));
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(batchCalls, 1);
    assert.match(details[1].textContent, /Texto histórico archivado/);
  } finally {window.close();}
});
