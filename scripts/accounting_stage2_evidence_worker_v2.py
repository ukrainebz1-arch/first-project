#!/usr/bin/env python3
# Safety-hardened wrapper around the Stage 2 evidence worker.
# The original worker remains as the crawler/classifier; this module tightens
# employee-number extraction so years, partners, offices and monetary figures
# cannot be promoted as headcount.
import argparse,csv,json,os,re,time,random
import accounting_stage2_evidence_worker as w

w.BAD = tuple(set(w.BAD) | {
    'jahr','jahre','jährig','jaehrig','partner','partnerin','partner:innen',
    'standort','standorte','büro','buro','buero','büros','bueros','filiale',
    'million','millionen','mio.','euro','eur','mandate','mandat','kunden',
    'gesellschaften','länder','laender','niederlassung','niederlassungen'
})
# Every generic company/team numeric statement must now explicitly say employees.
# This removes the old optional-EMP branch such as "Kanzlei mit 50 Jahren Erfahrung".
w.EXPLICIT = [
    re.compile(r'(?i)(?:wir\s+)?(?:besch[aä]ftigen|z[aä]hlen|umfassen|haben|sind)\s+(?:derzeit\s+)?(rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)?\s*(\d{1,4})\+?\s+'+w.EMP),
    re.compile(r'(?i)(?:team|kanzlei|unternehmen|gruppe)\s+(?:mit|von|umfasst|besteht\s+aus|z[aä]hlt)\s+(rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)?\s*(\d{1,4})\+?\s+'+w.EMP),
    re.compile(r'(?i)(rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)\s*(\d{2,4})\+?\s+'+w.EMP),
]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-jsonl',required=True);a=ap.parse_args()
    rows=list(csv.DictReader(open(a.input_csv,encoding='utf-8-sig',newline='')))
    os.makedirs(os.path.dirname(a.output_jsonl) or '.',exist_ok=True)
    with open(a.output_jsonl,'w',encoding='utf-8') as out:
        for i,row in enumerate(rows,1):
            try:
                research=w.collect(row)
                obj=w.result(row,research)
            except Exception as e:
                obj=w.make(row,'UNRESOLVED',None,None,'UNKNOWN','LOW',f'Public-web evidence worker encountered {type(e).__name__}; no reliable conclusion was promoted.',[],'Execution error forced a safe unresolved verdict.')
            out.write(json.dumps(obj,ensure_ascii=False)+'\n');out.flush()
            print(f'{i}/{len(rows)} {row["group_name"]} -> {obj["verdict"]} {obj["employee_low"]}',flush=True)
            time.sleep(random.uniform(.03,.10))
if __name__=='__main__':main()
