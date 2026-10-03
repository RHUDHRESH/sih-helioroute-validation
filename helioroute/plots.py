"""Plots are constructed solely from generated CSV/JSON, never hand-drawn data."""
import csv
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'helioroute-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

LABELS = {'conventional':'Conventional','routed_greedy':'Loss-aware greedy','routed_restricted_optimizer':'Restricted solver','routed_link_first':'Forced link-first'}
COLORS = {'conventional':'#4c6079','routed_greedy':'#159a8c','routed_restricted_optimizer':'#ed9748','routed_link_first':'#c95467'}


def make_plots(directory):
    directory = Path(directory)
    target = directory/'plots'
    target.mkdir(exist_ok=True)
    report = json.loads((directory/'summary.json').read_text())
    results = {r['scenario']:r for r in report['scenario_results']}
    with (directory/'dispatch.csv').open() as f:
        rows = list(csv.DictReader(f))
    with (directory/'inputs.csv').open() as f:
        inputs = list(csv.DictReader(f))
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                         'figure.facecolor':'#ffffff','axes.titlesize':12,'savefig.facecolor':'white'})
    fig,axs = plt.subplots(1,3,figsize=(13,4.7),layout='constrained')
    for ax,sid,title in zip(axs,['golden_bottleneck','unconstrained_transfer','standby_negative'],
                            ['Bottleneck: added path helps','Existing path sufficient: no benefit','No PV: standby costs energy']):
        policies = ['conventional','routed_greedy','routed_restricted_optimizer']
        if sid == 'unconstrained_transfer': policies=['conventional','routed_restricted_optimizer','routed_link_first']
        values = [results[sid]['variants'][p]['energy_wh']['total_grid_import_wh'] for p in policies]
        ax.bar(range(len(policies)),values,color=[COLORS[p] for p in policies],width=.65)
        ax.set_xticks(range(len(policies)),[LABELS[p].replace(' ','\n',1) for p in policies])
        ax.set_title(title)
        ax.set_ylabel('Grid import (Wh)')
        ax.set_ylim(0,max(values)*1.2)
        for n,v in enumerate(values):ax.text(n,v+max(values)*.025,f'{v:g}',ha='center')
        demand=results[sid]['variants']['conventional']['energy_wh']['total_demand_wh']
        ax.text(.5,.91,f'Same useful service: {demand:g} Wh',ha='center',transform=ax.transAxes,fontsize=9)
    fig.suptitle('HELIOROUTE | Synthetic energy-flow simulation, not hardware measurements',fontsize=14)
    fig.savefig(target/'comparison_boundaries.png',dpi=180)
    plt.close(fig)

    day = [r for r in inputs if r['scenario']=='asymmetric_day']
    t = [float(r['time_s'])/3600 for r in day]
    fig,axs = plt.subplots(4,1,figsize=(11,11),sharex=True,layout='constrained')
    for field,label,c in [('pv_a_w','PV A','#e5a92b'),('pv_b_w','PV B','#b47914'),
                          ('load_a_w','Useful load A','#516279'),('load_b_w','Useful load B','#172f50')]:
        axs[0].plot(t,[float(r[field]) for r in day],label=label,color=c)
    axs[0].set_ylabel('Common input (W)');axs[0].legend(ncol=4,loc='upper left')
    for policy in ('conventional','routed_greedy','routed_restricted_optimizer'):
        data=[r for r in rows if r['scenario']=='asymmetric_day' and r['policy']==policy]
        style='--' if policy=='routed_restricted_optimizer' else '-'
        axs[1].plot(t,[float(r['total_grid_import_w']) for r in data],style,label=LABELS[policy],color=COLORS[policy])
    axs[1].set_ylabel('Grid import (W)');axs[1].legend(ncol=3)
    opt=[r for r in rows if r['scenario']=='asymmetric_day' and r['policy']=='routed_restricted_optimizer']
    for field,label,c in [('link_signed_w','Added link A→B','#159a8c'),('conventional_signed_w','Existing path A→B','#516279'),('total_loss_w','All conversion/path loss','#c95467')]:
        axs[2].plot(t,[float(r[field]) for r in opt],label=label,color=c)
    axs[2].set_ylabel('Flow / loss (W)');axs[2].legend(ncol=3)
    axs[3].plot(t,[float(r['balance_residual_w']) for r in opt],color='#7258a5')
    axs[3].axhline(0,color='#777',linewidth=.5)
    axs[3].set_ylabel('Ledger residual (W)');axs[3].set_xlabel('Synthetic hour (no measured weather)')
    axs[3].ticklabel_format(axis='y',style='sci',scilimits=(-2,2))
    for ax in axs:ax.grid(alpha=.15)
    fig.suptitle('Same PV and useful loads | Loss-aware greedy and restricted surplus-sharing solver coincide',fontsize=14)
    fig.savefig(target/'synthetic_day.png',dpi=180);plt.close(fig)

    fig,ax=plt.subplots(figsize=(10,5.5),layout='constrained')
    labels=['Conventional\ninputs','Conventional\noutputs','Added link\ninputs','Added link\noutputs']
    series={key:np.zeros(4) for key in ['PV available','Grid import','Useful service','Curtailment','All losses','Controller standby']}
    for offset,policy in [(0,'conventional'),(2,'routed_restricted_optimizer')]:
        e=results['golden_bottleneck']['variants'][policy]['energy_wh']
        series['PV available'][offset]=e['total_available_pv_wh']
        series['Grid import'][offset]=e['total_grid_import_wh']
        series['Useful service'][offset+1]=e['total_served_wh']
        series['Curtailment'][offset+1]=e['total_curtailment_wh']
        series['All losses'][offset+1]=e['total_loss_wh']
        series['Controller standby'][offset+1]=e['auxiliary_grid_wh']
    bottom=np.zeros(4)
    for (name,values),color in zip(series.items(),['#e5a92b','#516279','#159a8c','#d4d8df','#c95467','#7258a5']):
        ax.bar(range(4),values,bottom=bottom,label=name,color=color,width=.65)
        for n,v in enumerate(values):
            if v:ax.text(n,bottom[n]+v/2,f'{v:g}',ha='center',va='center',color='white' if name in ('Grid import','Useful service') else 'black')
        bottom+=values
    ax.set_xticks(range(4),labels);ax.set_ylabel('One-hour energy (Wh)')
    baseline_service=results['golden_bottleneck']['variants']['conventional']['energy_wh']['total_served_wh']
    route_service=results['golden_bottleneck']['variants']['routed_restricted_optimizer']['energy_wh']['total_served_wh']
    ax.set_title(f'Golden fixture | Every Wh accounted for; useful service {baseline_service:g} vs {route_service:g} Wh')
    ax.legend(ncol=3,loc='upper center',bbox_to_anchor=(.5,-.1))
    fig.savefig(target/'golden_energy_ledger.png',dpi=180);plt.close(fig)

    fig,axs=plt.subplots(1,2,figsize=(11,4.8),layout='constrained')
    for ax,sid in zip(axs,['stale_telemetry','link_failure']):
        data=[r for r in rows if r['scenario']==sid and r['policy']=='routed_restricted_optimizer']
        times=[float(r['time_s'])/60 for r in data]
        ax.step(times,[float(r['link_send_w']) for r in data],where='post',label='Applied added-link power',color='#159a8c')
        ax.step(times,[float(r['total_grid_import_w']) for r in data],where='post',label='Grid fallback',color='#516279')
        ax.set_title(sid.replace('_',' ').capitalize());ax.set_xlabel('Synthetic minutes');ax.set_ylabel('Power (W)')
        ax.set_ylim(bottom=0);ax.legend(fontsize=8)
    fig.suptitle('Instantaneous step-level fallback assumption | No hardware trip timing measured',fontsize=13)
    fig.savefig(target/'fault_fallback.png',dpi=180);plt.close(fig)
