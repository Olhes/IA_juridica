// Standalone workstation test. SAT_EDITOR_URL must point at an ISOLATED COPY
// of the database: this test deliberately publishes one editorial correction.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';

const url = process.env.SAT_EDITOR_URL;
if (!url || process.env.SAT_EDITOR_TEST_COPY !== '1') throw new Error('Provide SAT_EDITOR_URL and SAT_EDITOR_TEST_COPY=1 for an isolated database.');
const browser = await chromium.launch({headless:true, ...(process.env.PLAYWRIGHT_CHANNEL ? {channel:process.env.PLAYWRIGHT_CHANNEL} : {})});
const page = await browser.newPage({viewport:{width:1600,height:1000}});
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text());});
page.on('dialog',dialog=>dialog.accept());
await mkdir('temp/sat-editor-screenshots',{recursive:true});
try {
  await page.goto(url);
  await page.waitForFunction(()=>document.querySelectorAll('#documents button').length===8);
  await page.waitForFunction(()=>document.querySelectorAll('.graph-row').length>0);
  const titles=await page.locator('#documents button').allTextContents();
  assert.equal(titles.length,8);
  // Exhaustively open all eight documents: no top-k truncation in the viewer.
  for(let i=0;i<8;i++){
    await page.locator('#documents button').nth(i).click();
    await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('componentes cargados completos'));
    const expected=Number(await page.locator('#component-count').textContent());
    await page.waitForFunction(count=>document.querySelectorAll('.graph-row').length===count,expected);
  }
  await page.locator('#document-search').fill('28970');
  await page.locator('#documents button').click();
  await page.waitForFunction(()=>document.querySelectorAll('.graph-row').length===22);
  await page.locator('#document-search').fill('');
  await page.locator('.node-select').nth(2).click();
  for(const [width,height] of [[1440,900],[1600,1000],[1920,1080],[390,844]]){
    await page.setViewportSize({width,height});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:`temp/sat-editor-screenshots/${width}.png`,fullPage:true});
  }
  await page.setViewportSize({width:1600,height:1000});
  await page.emulateMedia({colorScheme:'dark'});
  assert.equal(await page.locator('html').evaluate(node=>getComputedStyle(node).colorScheme),'dark');
  await page.screenshot({path:'temp/sat-editor-screenshots/dark.png',fullPage:true});
  await page.emulateMedia({colorScheme:'light'});
  assert.equal(await page.locator('html').evaluate(node=>getComputedStyle(node).colorScheme),'light');
  await page.locator('#collapse').click();
  assert.ok(await page.locator('.graph-row').count()<22);
  await page.locator('#expand').click();
  assert.equal(await page.locator('.graph-row').count(),22);
  await page.locator('#component-search').fill('deudores');
  assert.ok(await page.locator('.graph-row').count()>0);
  await page.locator('#component-search').fill('');
  await page.locator('[data-tab=markdown]').click();
  assert.ok((await page.locator('#full-markdown').inputValue()).length>10000);
  const [pdfTab]=await Promise.all([page.waitForEvent('popup'),page.locator('#open-pdf').click()]);
  await pdfTab.waitForURL('**/pdf');
  const pdf=await page.request.get(pdfTab.url());
  await pdfTab.close();
  assert.equal(pdf.status(),200);
  assert.ok(pdf.headers()['content-type'].includes('application/pdf'));
  await page.locator('[data-tab=structure]').click();
  await page.locator('.node-select').nth(2).click();
  const label=await page.locator('#node-label').inputValue();
  assert.notEqual(await page.locator('#node-kind').inputValue(),'disposition_group');
  assert.ok(await page.locator('#split-section').isVisible());
  await page.locator('#node-label').fill(label+' · revisión visual de prueba');
  const inspectorToggle = page.locator('#toggle-inspector');
  const canvas = page.locator('.canvas-panel');
  const originalWidth = (await canvas.boundingBox()).width;
  await inspectorToggle.click();
  assert.equal(await inspectorToggle.getAttribute('aria-expanded'), 'false');
  assert.equal(await page.locator('#component-inspector').isVisible(), false);
  assert.ok((await canvas.boundingBox()).width > originalWidth);
  await inspectorToggle.click();
  assert.equal(await page.locator('#node-label').inputValue(), label+' · revisión visual de prueba');
  await page.waitForFunction(()=>!document.getElementById('publish').disabled);
  await page.locator('#publish').click();
  await page.waitForFunction(()=>document.getElementById('notice').textContent.startsWith('Revisión aplicada'),{timeout:30000});
  await page.reload();
  await page.waitForFunction(()=>document.querySelectorAll('.graph-row').length>0);
  await page.locator('#document-search').fill('28970');
  await page.locator('#documents button').click();
  await page.waitForFunction(()=>document.querySelectorAll('.graph-row').length===22);
  assert.ok((await page.locator('#tree').textContent()).includes('revisión visual de prueba'));
  assert.deepEqual(errors,[]);
  console.log('PASS: eight documents, all nodes, four viewports, dark mode, search, PDF, draft, publish, reload.');
} finally {await browser.close();}
