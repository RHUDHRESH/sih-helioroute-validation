/* DOM-free JavaScript control/render tests. This is NOT browser visual QA. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const output=path.resolve(process.argv[2]||path.join(root,'results/latest'));
const replay=JSON.parse(fs.readFileSync(path.join(output,'replay.json')));
const manifest=JSON.parse(fs.readFileSync(path.join(output,'manifest.json')));
const checks=[];
function check(name,fn){fn();checks.push({test:name,status:'pass'});}
class Element{
 constructor(id){this.id=id;this.value=id==='comparison'?'hardware':id==='step'?'0':'';this.textContent='';this.innerHTML='';this.disabled=false;this.max=0;this.events={};this.children=[];}
 addEventListener(name,fn){this.events[name]=fn;}
 append(child){this.children.push(child);if(!this.value)this.value=child.value;}
 getContext(){return new Proxy({}, {get:()=>()=>{},set:()=>true});}
}
const ids=['scenario','comparison','step','start','play','next','time','description','pv','demand','fault','cards','delta','fairness','chart','legend','provenance'];
const elements=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
elements.chart.width=780;elements.chart.height=240;
let interval=null;
const context=vm.createContext({document:{getElementById:id=>elements[id],createElement:()=>new Element('option')},
 setInterval:fn=>{interval=fn;return 1;},clearInterval:()=>{interval=null;},console,
 fetch:async url=>({ok:true,json:async()=>url.includes('replay')?replay:manifest})});
vm.runInContext(fs.readFileSync(path.join(root,'viewer/app.js'),'utf8'),context);
setImmediate(()=>{
 try{
  check('initial golden replay values',()=>{assert.match(elements.cards.innerHTML,/70 <small>W/);assert.match(elements.cards.innerHTML,/25 <small>W/);assert.match(elements.delta.textContent,/45 Wh grid reduction/);assert.equal(elements.scenario.children.length,15);});
  check('single-step controls disabled',()=>{assert.equal(elements.play.disabled,true);assert.equal(elements.step.disabled,true);assert.equal(elements.next.disabled,true);});
  elements.comparison.value='controller';elements.comparison.events.change();
  check('same-hardware controller comparison equality',()=>{assert.match(elements.delta.textContent,/0 Wh grid reduction.*equal result/);assert.match(elements.cards.innerHTML,/Loss-aware greedy/);assert.match(elements.cards.innerHTML,/Restricted surplus-sharing solver/);});
  elements.scenario.value='stale_telemetry';elements.scenario.events.change();
  check('scenario resets timeline',()=>{assert.equal(elements.step.value,0);assert.equal(elements.step.max,3);assert.equal(elements.play.disabled,false);});
  elements.next.events.click();
  check('next updates shared step and flags',()=>{assert.equal(elements.step.value,1);assert.match(elements.time.textContent,/Step 2 \/ 4/);assert.match(elements.fault.textContent,/Stale/);assert.match(elements.cards.innerHTML,/Added link 0 W/);});
  elements.play.events.click();assert.equal(typeof interval,'function');interval();
  check('play advances computed replay',()=>{assert.equal(elements.step.value,2);assert.equal(elements.play.textContent,'Pause');});
  elements.play.events.click();
  check('pause cancels timer',()=>{assert.equal(interval,null);assert.equal(elements.play.textContent,'Play');});
  elements.start.events.click();
  check('first resets replay',()=>{assert.equal(elements.step.value,0);assert.match(elements.fault.textContent,/Fresh/);});
  elements.scenario.value='local_first_counterexample';elements.scenario.events.change();
  check('known policy failure is visible and not a savings claim',()=>{assert.match(elements.cards.innerHTML,/physical infeasibility NOT proven/);assert.match(elements.delta.textContent,/No valid savings claim/);assert.match(elements.cards.innerHTML,/100 <small>W/);});
  elements.scenario.value='infeasible_supply_bound';elements.scenario.events.change();
  check('supply-bound infeasibility is distinguished',()=>{assert.match(elements.cards.innerHTML,/total supply insufficient/);});
  elements.comparison.value='hardware';elements.scenario.value='standby_negative';elements.scenario.events.change();
  check('standby negative result is visible',()=>{assert.match(elements.delta.textContent,/2 Wh grid increase/);assert.match(elements.cards.innerHTML,/102 <small>W/);});
  elements.scenario.value='asymmetric_day';elements.scenario.events.change();elements.step.value='143';elements.step.events.input();
  check('final step disables Next and playback restarts at beginning',()=>{assert.equal(elements.next.disabled,true);elements.play.events.click();assert.equal(elements.step.value,0);elements.play.events.click();});
  console.log(JSON.stringify({status:'pass',test_type:'DOM-free JavaScript control/render logic; not a real browser',tests_run:checks.length,checks},null,2));
 }catch(error){console.error(JSON.stringify({status:'fail',checks,error:String(error)},null,2));process.exitCode=1;}
});
