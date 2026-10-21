import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../worker.js';

test('immutable cache applies only to fingerprinted successful assets',async()=>{
 for(const [path,immutable] of [['/static/0123456789abcdef/app.js',true],['/static/0123456789abcdef.webp',true],['/assets/slides/e.pdf',false],['/style.css',false]]){
  let requested;
  const response=await worker.fetch(new Request('https://xiaosang.cc/podcast-atlas'+path),{ASSETS:{fetch:async r=>{requested=new URL(r.url).pathname;return new Response('asset',{headers:{'Cache-Control':'public, max-age=0'}});}}});
  assert.equal(requested,path);assert.equal(response.headers.get('Cache-Control').includes('immutable'),immutable);
 }
});
test('missing fingerprinted resources and redirects are not cached forever',async()=>{
 const response=await worker.fetch(new Request('https://xiaosang.cc/podcast-atlas/static/0123456789abcdef.json'),{ASSETS:{fetch:async()=>new Response('missing',{status:404})}});
 assert.equal(response.headers.get('Cache-Control'),null);
 const redirected=await worker.fetch(new Request('https://xiaosang.cc/podcast-atlas/topics'),{ASSETS:{fetch:async()=>new Response(null,{status:308,headers:{location:'/topics/'}})}});
 assert.equal(redirected.headers.get('location'),'https://xiaosang.cc/podcast-atlas/topics/');
});
test('conditional cache validation keeps the immutable policy',async()=>{
 const response=await worker.fetch(new Request('https://xiaosang.cc/podcast-atlas/static/0123456789abcdef/app.js'),{ASSETS:{fetch:async()=>new Response(null,{status:304,headers:{'Cache-Control':'public, max-age=0'}})}});
 assert.equal(response.status,304);
 assert(response.headers.get('Cache-Control').includes('immutable'));
});
