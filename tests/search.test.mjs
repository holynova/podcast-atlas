import test from 'node:test';
import assert from 'node:assert/strict';
import {searchEntries} from '../search.js';
const entries = [
 {id:'apple',title:'苹果从爱好做成生意',original_title:'No.54 苹果简史',show:'半拿铁',topic:'苹果公司简史',date:'2023-06-07',ready:true,text:'乔布斯与沃兹尼亚克。VisiCalc 电子表格改变电脑销量。'},
 {id:'stock-a',title:'中国股市的故事',original_title:'No.10 中国股市',show:'半拿铁',topic:'中国股市往事',date:'2026-01-01',ready:true,text:'交易所的历史。'},
 {id:'stock-b',title:'投资中国股市',original_title:'E10 中国股市',show:'知行小酒馆',topic:'中国股市往事',date:'2026-02-01',ready:false,text:''}
];
test('searches processed body and requires every keyword',()=> {
 assert.deepEqual(searchEntries(entries,'沃兹尼亚克 电子表格').map(x=>x.id),['apple']);
 assert.equal(searchEntries(entries,'沃兹尼亚克 房地产').length,0);
});
test('same topic remains isolated by podcast',()=>assert.deepEqual(searchEntries(entries,'中国股市','知行小酒馆').map(x=>x.id),['stock-b']));
test('supports fullwidth Latin input and case folding',()=>assert.equal(searchEntries(entries,'ｖｉｓｉｃａｌｃ')[0].id,'apple'));
test('empty query recommends ready articles only',()=>assert.deepEqual(searchEntries(entries,'   ').map(x=>x.id),['stock-a','apple']));
test('literal markup has no special search meaning',()=>assert.equal(searchEntries(entries,'<script>').length,0));
test('lightweight summaries remain searchable before full text arrives',()=>assert.equal(searchEntries([{...entries[0],text:'',summary:'融资与组织协作的变化'}],'组织协作')[0].id,'apple'));
