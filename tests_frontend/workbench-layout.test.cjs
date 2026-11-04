const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const css=fs.readFileSync(path.join(__dirname,'../frontend/css/app.css'),'utf8');

function declarations(selector){
 return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(match=>match[1].trim()===selector).map(match=>match[2]).join(';');
}

test('看样台用剩余空间限制图框，共享版位比例且图片完整包含',()=>{
 assert.match(declarations('.sample-stage'),/display:flex;flex-direction:column/);
 assert.match(declarations('.sample-stage #sets'),/flex:1;min-height:0;container-type:size/);
 const cell=declarations('.sample-stage .cell');
 assert.match(cell,/100cqh\s*-\s*156px/);
 assert.match(cell,/width:min\(100%,calc\(var\(--sample-image-height\)\s*\*\s*var\(--image-ratio\)\)\)/);
 assert.match(cell,/max-height:var\(--sample-image-height\)/);
 assert.match(declarations('.sample-stage .cell img'),/object-fit:contain/);
});

test('需去框标签清除旧的右下定位，保持小标签且不截获图片点击',()=>{
 const note=declarations('.sample-stage .frame-note');
 assert.match(note,/bottom:auto/);assert.match(note,/right:auto/);
 assert.match(note,/pointer-events:none/);
});

test('更多菜单重置摘要外边距和三角，弹层在按钮下方右对齐',()=>{
 const summary=declarations('.pick-more>summary');
 assert.match(summary,/margin:0/);assert.match(summary,/height:32px/);
 assert.match(declarations('.pick-more>summary::before,.pick-more[open]>summary::before'),/content:none/);
 const panel=declarations('.pick-more>div');
 assert.match(panel,/right:0/);assert.match(panel,/top:calc\(100%\s*\+\s*6px\)/);
});
