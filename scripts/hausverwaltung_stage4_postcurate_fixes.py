#!/usr/bin/env python3
import argparse,csv,os


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--output',required=True)
    a=ap.parse_args()
    with open(a.input,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=99:
        raise SystemExit(f'Expected 99 rows, got {len(rows)}')
    found=False
    for r in rows:
        if r.get('no')=='20':
            found=True
            r['override_personal_email']='f.hoermann@pmv.at'
            r['override_email_type']='A_PERSONAL_VERIFIED'
            r['override_email_verified']='yes'
            r['override_email_source_url']='https://pmv.at/ueber-uns/'
            r['contact_confidence']='HIGH'
            r['research_notes']='Official PMV management page explicitly publishes Florian Hörmann as Geschäftsführer with f.hoermann@pmv.at; EVI confirms him as current PMV Geschäftsführer since 27.04.2026. The IMV-group address is not used as the PMV row source of truth.'
            urls=[x.strip() for x in (r.get('additional_source_urls') or '').split(' | ') if x.strip() and 'imv.co.at/uber-uns' not in x]
            for u in ('https://pmv.at/ueber-uns/','https://www.evi.gv.at/f/332655z'):
                if u not in urls: urls.append(u)
            r['additional_source_urls']=' | '.join(urls)
    if not found:
        raise SystemExit('PMV row #20 not found')
    os.makedirs(os.path.dirname(a.output) or '.',exist_ok=True)
    with open(a.output,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys())
        w.writeheader();w.writerows(rows)
    print('postcurate_fixes=1 row20_pmv_email=f.hoermann@pmv.at')

if __name__=='__main__':main()
