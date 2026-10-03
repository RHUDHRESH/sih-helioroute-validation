'use strict';
const $ = id => document.getElementById(id);
const names={conventional:'Conventional topology',routed_greedy:'Loss-aware greedy',routed_restricted_optimizer:'Restricted surplus-sharing solver'};
let data, timer=null, loaded=false;
const fmt=(x,d=2)=>Number(x).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:0});
const power=x=>`${fmt(x)} W`;
function stop(){if(timer)clearInterval(timer);timer=null;$('play').textContent='Play';}
function selected(){return data.scenarios.find(s=>s.scenario===$('scenario').value);}
function policies(){return $('comparison').value==='hardware'?['conventional','routed_restricted_optimizer']:['routed_greedy','routed_restricted_optimizer'];}
function rowFor(policy,index){return data.rows.find(r=>r.scenario===$('scenario').value&&r.policy===policy&&r.step_index===index);}
function inputFor(index){return data.inputs.find(r=>r.scenario===$('scenario').value&&r.step_index===index);}
function metric(label,value,unit='W'){return `<div class="metric"><span>${label}</span><strong>${fmt(value)} <small>${unit}</small></strong></div>`;}
function card(policy,r){
 const forward=r.direction>=0, flowLabel=r.direction===0?'No cross-feeder flow':forward?'A → B':'B → A';
 const arrowStart=forward?155:445,arrowEnd=forward?445:155;
 const status=r.service_status==='met'?'Required useful service met':r.physical_infeasibility_proven?'Service shortfall · total supply insufficient':'Policy shortfall · physical infeasibility NOT proven';
 return `<article class="card" data-policy="${policy}"><h2>${names[policy]}</h2><span class="badge ${r.service_status==='met'?'':'fail'}">${status}</span>
 <svg class="topology" viewBox="0 0 600 160" aria-label="${flowLabel}; existing ${power(r.conventional_send_w)}; added link ${power(r.link_send_w)}">
 <defs><marker id="arrow-${policy}" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#159a8c"/></marker></defs>
 <rect x="15" y="38" width="135" height="88" rx="10" fill="#edf3f1"/><rect x="450" y="38" width="135" height="88" rx="10" fill="#edf3f1"/>
 <text x="82" y="62" text-anchor="middle" font-size="14" fill="#17414a">Feeder A</text><text x="82" y="86" text-anchor="middle" font-size="12" fill="#526976">PV ${power(r.pv_available_a_w)}</text><text x="82" y="107" text-anchor="middle" font-size="12" fill="#526976">Load ${power(r.demand_a_w)}</text>
 <text x="518" y="62" text-anchor="middle" font-size="14" fill="#17414a">Feeder B</text><text x="518" y="86" text-anchor="middle" font-size="12" fill="#526976">PV ${power(r.pv_available_b_w)}</text><text x="518" y="107" text-anchor="middle" font-size="12" fill="#526976">Load ${power(r.demand_b_w)}</text>
 <line x1="${arrowStart}" x2="${arrowEnd}" y1="58" y2="58" stroke="#718992" stroke-width="2" ${r.conventional_send_w>0?`marker-end="url(#arrow-${policy})"`:''}/><text x="300" y="45" text-anchor="middle" font-size="12" fill="#526976">Existing path ${power(r.conventional_send_w)}</text>
 <line x1="${arrowStart}" x2="${arrowEnd}" y1="107" y2="107" stroke="${policy==='conventional'?'#cbd8d4':'#159a8c'}" stroke-width="3" ${policy==='conventional'?'stroke-dasharray="5,5"':''} ${r.link_send_w>0?`marker-end="url(#arrow-${policy})"`:''}/><text x="300" y="94" text-anchor="middle" font-size="12" fill="#126e64">${policy==='conventional'?'Added link absent':`Added link ${power(r.link_send_w)}`}</text>
 <text x="300" y="142" text-anchor="middle" font-size="11" fill="#526976">${flowLabel} · sending-bus power</text></svg>
 <div class="metrics">${metric('Total grid import',r.total_grid_import_w)}${metric('Useful service',r.total_served_w)}${metric('Unmet useful demand',r.total_unmet_w)}${metric('PV curtailed',r.total_curtailment_w)}${metric('All conversion / path loss',r.total_loss_w)}${metric('Controller standby',r.auxiliary_grid_w)}</div>
 <p class="residual">Ledger residual: ${Number(r.balance_residual_w).toExponential(2)} W · PV-derived useful service: ${power(r.total_renewable_served_w)}</p></article>`;
}
function drawChart(a,b,index){
 const c=$('chart'),ctx=c.getContext('2d'),W=c.width,H=c.height,L=42,R=12,T=10,B=30;
 const ra=data.rows.filter(r=>r.scenario===$('scenario').value&&r.policy===a),rb=data.rows.filter(r=>r.scenario===$('scenario').value&&r.policy===b);
 const max=Math.max(1,...ra.map(r=>r.total_grid_import_w),...rb.map(r=>r.total_grid_import_w));
 const x=i=>L+i/Math.max(1,ra.length-1)*(W-L-R),y=v=>T+(1-v/max)*(H-T-B);
 ctx.clearRect(0,0,W,H);ctx.strokeStyle='#bed0ca';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(L,T);ctx.lineTo(L,H-B);ctx.lineTo(W-R,H-B);ctx.stroke();
 ctx.fillStyle='#526976';ctx.font='13px sans-serif';ctx.fillText(`${fmt(max,0)} W`,0,20);ctx.fillText('0',20,H-B);ctx.fillText('Common simulation steps',W/2-65,H-3);
 for(const [rs,color] of [[ra,'#526c80'],[rb,'#119a84']]){ctx.strokeStyle=color;ctx.lineWidth=3;ctx.beginPath();rs.forEach((r,i)=>i?ctx.lineTo(x(i),y(r.total_grid_import_w)):ctx.moveTo(x(i),y(r.total_grid_import_w)));ctx.stroke();if(rs.length===1){ctx.fillStyle=color;ctx.beginPath();ctx.arc(x(0),y(rs[0].total_grid_import_w),5,0,Math.PI*2);ctx.fill();}}
 ctx.strokeStyle='#e69b44';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(x(index),T);ctx.lineTo(x(index),H-B);ctx.stroke();
 $('legend').textContent=`Slate: ${names[a]} · Green: ${names[b]} · Orange: selected step`;
}
function render(){if(!loaded)return;const scenario=selected(),index=Number($('step').value),input=inputFor(index),[a,b]=policies();
 $('description').textContent=scenario.description;$('time').textContent=`Step ${index+1} / ${scenario.n_steps} · t = ${fmt(index*scenario.dt_s/60)} min`;
 $('pv').textContent=power(input.pv_a_w+input.pv_b_w);$('demand').textContent=power(input.load_a_w+input.load_b_w);$('fault').textContent=`${input.link_available?'Available':'Failed'} / ${input.telemetry_fresh?'Fresh':'Stale'}`;
 $('cards').innerHTML=card(a,rowFor(a,index))+card(b,rowFor(b,index));
 const paired=scenario[$('comparison').value==='hardware'?'comparison_A_hardware':'comparison_B_controller'];
 $('delta').textContent=paired.status==='pass'?`${fmt(paired.valid_grid_saving_wh)} Wh ${paired.valid_grid_saving_wh<0?'grid increase':'grid reduction'}${Math.abs(paired.valid_grid_saving_wh)<1e-7?' · equal result':''}`:'No valid savings claim: service shortfall';
 if(paired.valid_grid_saving_wh<0)$('delta').textContent=`${fmt(-paired.valid_grid_saving_wh)} Wh grid increase`;
 $('fairness').textContent=`${paired.reason}. ${$('comparison').value==='controller'?'Same hardware and observations; solver is restricted to local-first surplus sharing.':'Added path and its losses/standby are part of the hardware intervention.'}`;
 $('next').disabled=scenario.n_steps<=1||index===scenario.n_steps-1;$('play').disabled=scenario.n_steps<=1;$('step').disabled=scenario.n_steps<=1;
 drawChart(a,b,index);
}
function changeScenario(){stop();$('step').max=selected().n_steps-1;$('step').value=0;render();}
$('scenario').addEventListener('change',changeScenario);$('comparison').addEventListener('change',render);$('step').addEventListener('input',()=>{stop();render();});$('start').addEventListener('click',()=>{stop();$('step').value=0;render();});$('next').addEventListener('click',()=>{stop();$('step').value=Math.min(Number($('step').value)+1,selected().n_steps-1);render();});
$('play').addEventListener('click',()=>{if(timer){stop();return;}if(Number($('step').value)>=selected().n_steps-1){$('step').value=0;render();}$('play').textContent='Pause';timer=setInterval(()=>{let n=Number($('step').value)+1;if(n>=selected().n_steps){stop();return;}$('step').value=n;render();},350);});
Promise.all([fetch('../results/latest/replay.json').then(r=>{if(!r.ok)throw Error('Run ./run.sh to generate replay.json');return r.json();}),fetch('../results/latest/manifest.json').then(r=>r.json())]).then(([replay,manifest])=>{if(replay.schema_version!==1||manifest.schema_version!==1)throw Error('Unsupported replay schema');data=replay;for(const scenario of data.scenarios){const o=document.createElement('option');o.value=scenario.scenario;o.textContent=scenario.scenario;$('scenario').append(o);}loaded=true;$('provenance').textContent=`Run ${manifest.run_id} · source SHA256 ${manifest.source_tree_sha256} · deterministic seed ${manifest.seed}`;changeScenario();}).catch(err=>{$('description').textContent=`Replay unavailable: ${err.message}. Serve the project using ./serve.sh; do not open this page as a file.`;});
