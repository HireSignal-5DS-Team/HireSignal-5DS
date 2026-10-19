"""Build gold labels from the human-checked AI pre-labels (method C). Written by the Brain, 2026-10-18.
Sources: ai_pass/ai_prelabels_for_review.xlsx (40 pairs) + ai_pass/ai_prelabels_EXTRA_for_review.xlsx (12 targeted pairs).
gold = human decision where a human decision is written (CHECK=CHANGED), else the AI decision (CHECK=OK).
Decision log applied: J2 r6 is nice-to-have (Approver, 2026-10-18).
Split: P01-P40 odd = dev, even = test; P41-P52 assigned by hand (fixed before any model run) to balance outcomes: dev P41 P42 P45 P48 P50 P51, test P43 P44 P46 P47 P49 P52. Run from the repo root: python data/labels/gold/build_gold.py"""
import csv, json, openpyxl, os
from collections import Counter
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
L=os.path.join(ROOT,'data','labels'); G=os.path.join(L,'gold'); CV=os.path.join(ROOT,'data','processed','cvs')
NICE_OVERRIDE={('J2','r6')}
FILES=[('main','ai_prelabels_for_review.xlsx'),('extra','ai_prelabels_EXTRA_for_review.xlsx')]
def cvtext(f): return open(os.path.join(CV,f),encoding='utf-8').read()
rows=[];prs=[];stats=Counter();pstats=Counter();flags=[]
for batch,fn in FILES:
    path=os.path.join(L,'ai_pass',fn)
    if not os.path.exists(path): continue
    wb=openpyxl.load_workbook(path,data_only=True)
    for r in wb['requirements'].iter_rows(min_row=2,values_only=True):
        pid,job,cvf,rid,kind,cat,miny,req,aid,aiq,chk,hd,hq,note=r
        chk=(chk or '').strip().upper(); hd=(hd or '').strip().upper() or None; hq=(hq or '').strip() or None
        if chk!='CHANGED' and hd in ('MET','MISSING','UNCERTAIN'):
            flags.append(f'{pid} {rid}: CHECK={chk or "empty"} but human decision {hd} written; human decision used'); chk='CHANGED'
        src,dec,q='ai_checked_ok',aid,aiq or ''
        if chk=='CHANGED':
            if hd in ('MET','MISSING','UNCERTAIN'): src,dec,q='human_changed',hd,hq or ''
            else: src='changed_without_decision'; flags.append(f'{pid} {rid}: CHANGED without a decision; AI kept')
        elif chk!='OK': src='unchecked'
        if (job,rid) in NICE_OVERRIDE: kind='nice'
        exact=(q.strip() in cvtext(cvf)) if q.strip() else None
        if dec=='MET' and not exact: flags.append(f'{pid} {rid}: gold MET quote not exact')
        stats[src]+=1
        rows.append(dict(pair_id=pid,job=job,cv_file=cvf,req_id=rid,kind=kind,category=cat,min_years=miny or '',requirement=req,
            gold_decision=dec,gold_quote=q.strip(),quote_exact=exact,source=src,ai_decision=aid,batch=batch,note=note or ''))
    for r in wb['pairs'].iter_rows(min_row=2,values_only=True):
        pid,job,cvf,ao,ar,chk,ho,hr=r; chk=(chk or '').strip().upper()
        if cvf=='(existing pair)':      # proposed change to an existing pair, applied when checked
            if chk=='OK' or (chk=='CHANGED' and ho):
                o=(ho or ao).strip().lower()
                for x in prs:
                    if x['pair_id']==pid: x.update(gold_outcome=o,source='decision_update_checked',reason=hr or ar)
            else: flags.append(f'{pid}: proposed outcome change ({ao}) not checked yet')
            continue
        if chk=='CHANGED' and ho: o,src=ho.strip().lower(),'human_changed'
        elif chk=='OK': o,src=ao,'ai_checked_ok'
        else: o,src=ao,'unchecked'
        pstats[src]+=1
        prs.append(dict(pair_id=pid,job=job,cv_file=cvf,gold_outcome=o,source=src,ai_outcome=ao,reason=(hr or ar),batch=batch))
EXTRA_DEV={'P41','P42','P45','P48','P50','P51'}
def _split(p):
    n=int(p[1:])
    if n>40: return 'dev' if p in EXTRA_DEV else 'test'
    return 'dev' if n%2==1 else 'test'
split={x['pair_id']:_split(x['pair_id']) for x in prs}
for x in rows: x['split']=split[x['pair_id']]
for x in prs: x['split']=split[x['pair_id']]
for name,data in (('requirements_gold.csv',rows),('pairs_gold.csv',prs)):
    with open(os.path.join(G,name),'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
summary=dict(pairs=len(prs),requirement_rows=len(rows),row_sources=dict(stats),
    changed_rate_checked=round(stats['human_changed']/max(1,len(rows)-stats['unchecked']),4),
    gold_decisions=dict(Counter(x['gold_decision'] for x in rows)),pair_sources=dict(pstats),
    gold_outcomes=dict(Counter(x['gold_outcome'] for x in prs)),
    outcomes_by_split={s:dict(Counter(x['gold_outcome'] for x in prs if x['split']==s)) for s in ('dev','test')},
    decision_log=['J2 r6 must -> nice (Approver, 2026-10-18)'],flags=flags)
json.dump(summary,open(os.path.join(G,'summary.json'),'w'),indent=1); print(json.dumps(summary,indent=1))
