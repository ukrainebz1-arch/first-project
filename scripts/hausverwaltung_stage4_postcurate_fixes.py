#!/usr/bin/env python3
import argparse,csv,os


def add_urls(r, *new_urls, drop_contains=()):
    urls=[x.strip() for x in (r.get('additional_source_urls') or '').split(' | ') if x.strip()]
    if drop_contains:
        urls=[u for u in urls if not any(s in u for s in drop_contains)]
    for u in new_urls:
        if u and u not in urls:
            urls.append(u)
    r['additional_source_urls']=' | '.join(urls)


def set_phone(r, phone, phone_type, source, confidence, note, secondary=None):
    r['override_direct_phone']=phone
    r['override_phone_type']=phone_type
    r['override_phone_verified']='yes'
    r['override_phone_source_url']=source
    if secondary is not None:
        r['override_secondary_phone']=secondary
    r['contact_confidence']=confidence
    r['research_notes']=note
    add_urls(r, source)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--output',required=True)
    a=ap.parse_args()
    with open(a.input,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=99:
        raise SystemExit(f'Expected 99 rows, got {len(rows)}')

    seen=set()
    for r in rows:
        no=r.get('no')

        if no=='20':
            seen.add(no)
            r['override_personal_email']='f.hoermann@pmv.at'
            r['override_email_type']='A_PERSONAL_VERIFIED'
            r['override_email_verified']='yes'
            r['override_email_source_url']='https://pmv.at/ueber-uns/'
            r['contact_confidence']='HIGH'
            r['research_notes']='Official PMV management page explicitly publishes Florian Hörmann as Geschäftsführer with f.hoermann@pmv.at; EVI confirms him as current PMV Geschäftsführer since 27.04.2026. The IMV-group address is not used as the PMV row source of truth.'
            add_urls(r,'https://pmv.at/ueber-uns/','https://www.evi.gv.at/f/332655z',drop_contains=('imv.co.at/uber-uns',))

        elif no=='13':
            seen.add(no)
            set_phone(
                r,'+436765227103','A_MOBILE_PUBLIC','https://firmen.wko.at/alois-rosenberger/','HIGH',
                'WKO public business listing explicitly lists Mag. Alois Rosenberger with public business mobile +43 676 5227103, office phone and personal business email rosenberger@aon.at. Mobile is promoted to primary contact according to Stage-4 priority; office line is secondary.',
                '+43 1 3324298 [C_PERSON_BOUND_OFFICE]')

        elif no=='1':
            seen.add(no)
            set_phone(
                r,'+43502441160','D_MANAGEMENT_LINE','https://www.big.at/ueber-uns/personen-organisation/big-geschaeftsfuehrung','HIGH',
                'Official BIG management page publishes Gerald Beck management assistant Michaela Meyer at +43 5 0244-1160 and Christine Dornaus assistant Angela Schrammel at +43 5 0244-1406. These are named management lines, not personal DM numbers.',
                'Christine Dornaus / Assistenz Angela Schrammel: +43 5 0244-1406 [D_MANAGEMENT_LINE]')
            r['override_fallback_company_phone']='+43502440'
            add_urls(r,'https://www.big.at/allgemein/kontaktinformationen')

        elif no=='11':
            seen.add(no)
            set_phone(
                r,'+436646013928500','A_MOBILE_PUBLIC','https://www.salonreal.at/mitglieder/','HIGH',
                'Salon Real public professional directory explicitly lists Mag.(FH) Ivana Krenstetter, Arealis Liegenschaftsmanagement GmbH Geschäftsführerin, with mobile +43 664 60 139-28500. Exact company and role remove identity ambiguity.')

        elif no=='19':
            seen.add(no)
            # Data-quality correction only: official Werner Bayer management page shows central -0.
            r['override_fallback_company_phone']='+433352326600'
            r['research_notes']='Phone-only deep audit found no verified personal mobile/DW for Werner Bayer. Official SV Bayer management page explicitly lists Werner Bayer with +43 3352 32660-0; malformed machine fallback was corrected, but the -0 number remains fallback only.'
            add_urls(r,'https://www.svbayer.at/ueber-uns')

        elif no=='25':
            seen.add(no)
            set_phone(
                r,'+434635373325','B_DIRECT_DIAL','https://www.klagenfurt-wohnen.at/kontakt','HIGH',
                'Official Klagenfurt Wohnen contact page explicitly assigns +43 463 537-3325 to Geschäftsführer Gerhard Scheucher. The previously promoted -3320 belongs to Assistenz der Geschäftsführung Melinda Schuppe and is retained only as secondary management line.',
                'Assistenz der Geschäftsführung Melinda Schuppe: +43 463 537-3320 [D_MANAGEMENT_LINE]')

        elif no=='32':
            seen.add(no)
            set_phone(
                r,'+436648481968','A_MOBILE_PUBLIC','https://www.ogni.at/unser-netzwerk/jurgen-narath','HIGH',
                'ÖGNI public professional profile explicitly publishes Stage-3 Primary DM Jürgen Narath mobile +43 664 8481968. This is a direct public professional mobile and outranks any company central line.')

        elif no=='34':
            seen.add(no)
            set_phone(
                r,'+4373277911112','D_MANAGEMENT_LINE','https://wohnbau2000.com/unternehmen/team/','HIGH',
                'Official Wohnbau 2000 team page identifies Prok. Christine Spitzl as Büroleitung/Personalwesen and Assistentin der Geschäftsführung with +43 732 779111-12. No public personal Jörg Rigger number was verified; the named management-assistant line is a valid D_MANAGEMENT_LINE.',
                None)
            r['override_fallback_company_phone']='+43732779111'

        elif no=='36':
            seen.add(no)
            set_phone(
                r,'+4373271119218','B_DIRECT_DIAL','https://www.gsa-wohnbau.at/assets/2024-07_BROSCHUeRE_DRUCK.pdf','HIGH',
                'Official GSA project brochure explicitly lists Geschäftsführer Mag. Christian Haidinger with +43 732 711192 / 18 and christian.haidinger@gsa-wohnbau.at. The extension /18 is promoted over the generic person-bound office line.')
            r['override_personal_email']='christian.haidinger@gsa-wohnbau.at'
            r['override_email_type']='A_PERSONAL_VERIFIED'
            r['override_email_verified']='yes'
            r['override_email_source_url']='https://www.gsa-wohnbau.at/assets/2024-07_BROSCHUeRE_DRUCK.pdf'

        elif no=='44':
            seen.add(no)
            set_phone(
                r,'+4317866110','C_PERSON_BOUND_OFFICE','https://firmen.wko.at/mag-hans-j%C3%B6rg-ulreich/wien/?firmaid=cd8204d6-b31c-47a4-a19f-574bdd1d2b1c','MEDIUM_HIGH',
                'WKO public professional listing for Mag. Hans Jörg Ulreich publishes +43 1 7866110. It is an exact-person business contact in his real-estate activity, but not presented as a personal mobile/DW for Ulreich VerwaltungsGmbH, so it is conservatively classified C_PERSON_BOUND_OFFICE.')

        elif no=='48':
            seen.add(no)
            set_phone(
                r,'+4314023169','C_PERSON_BOUND_OFFICE','https://schneeweiss.at/kontakt.php','HIGH',
                'Official Immobilienkanzlei Schneeweiss contact page explicitly identifies Mag. Wolf-Dietrich Schneeweiss and publishes +43 1 4023169. As the owner-operated e.U. office line it is person-bound, but not claimed to be a personal mobile/DW.')

        elif no=='61':
            seen.add(no)
            set_phone(
                r,'+436626585110','C_PERSON_BOUND_OFFICE','https://stiller-hohla.at/immobilien/','HIGH',
                'Official Stiller & Hohla property page lists Leo Hohla under Ihre Ansprechpartner with +43 662 6585-110. The same -110 is also used for several sales contacts, so it is conservatively C_PERSON_BOUND_OFFICE rather than B_DIRECT_DIAL.')

        elif no=='68':
            seen.add(no)
            set_phone(
                r,'+434635681921','B_DIRECT_DIAL','https://ksw-wohn.at/ueber-uns/ueber-uns/','MEDIUM_HIGH',
                'Current KWH page confirms Mag. Daniela Sampl-Lutz as KWH Geschäftsführerin. Related Kärntner Siedlungswerk public team page lists the same Daniela Sampl-Lutz as Prokuristin/Leitung Rechnungswesen with individual DW +43 463 56819-21. This is a public cross-group professional direct dial; source context is explicitly retained.',
                'Fabian Eder / KWH office: +43 4242 22200 [C_PERSON_BOUND_OFFICE]')
            add_urls(r,'https://www.kwh-kaernten.at/ueber-uns/','https://www.evi.gv.at/f/96682f')

        elif no=='72':
            seen.add(no)
            set_phone(
                r,'+4369917771727','A_MOBILE_PUBLIC','https://firmen.wko.at/dr-klaus-pfoser/wien/?firmaid=296d0028-9f3d-43cc-a4cb-989ec5cf259f','HIGH',
                'WKO exact-person public business profile explicitly publishes Dr. Klaus Pfoser mobile 0699/17 77 17 27 and pfoser@res.at. Mobile is a verified public professional contact.')
            r['override_personal_email']='pfoser@res.at'
            r['override_email_type']='A_PERSONAL_VERIFIED'
            r['override_email_verified']='yes'
            r['override_email_source_url']='https://firmen.wko.at/dr-klaus-pfoser/wien/?firmaid=296d0028-9f3d-43cc-a4cb-989ec5cf259f'

        elif no=='76':
            seen.add(no)
            set_phone(
                r,'+43476298236','C_PERSON_BOUND_OFFICE','https://www.willhaben.at/jobs/firma/immobilien-treuhand-hanke-bodner-kg/6158551','MEDIUM_HIGH',
                'Public willhaben company profile explicitly names Christina Bodner as the company contact and binds +43 4762 98236 to her. Because this is also the company office line and no unique extension/mobile is shown, it is C_PERSON_BOUND_OFFICE.')

        elif no=='77':
            seen.add(no)
            set_phone(
                r,'+436601834002','A_MOBILE_PUBLIC','https://mitglieder.gerichts-sv.at/Limberg/','HIGH',
                'Official Austrian court-expert profile explicitly publishes MMag. Dr. Clemens Limberg mobile 0660/1834002 and states his long-standing Geschäftsführer role at LIMBERG GmbH. This is a verified public professional mobile.')

        elif no=='78':
            seen.add(no)
            # Data-quality correction only; official SMT website shows the central number with -0.
            r['override_fallback_company_phone']='+43172002020'
            r['research_notes']='Phone-only deep audit did not find a unique personal mobile/DW for Ferenc Sabo or Evelyn Mandl. Official SMT site confirms +43 1 7200202-0 as company central; malformed machine fallback was corrected and remains fallback only.'
            add_urls(r,'https://www.smt-immobilien.at/')

        elif no=='83':
            seen.add(no)
            set_phone(
                r,'+4315239300','C_PERSON_BOUND_OFFICE','https://suche.gerichts-sv.at/Default.aspx?SV=W259345','HIGH',
                'Official Austrian court-expert registry lists KommRat Viktor Wagner, Beruf Firmeninhaber, at REIWAG address with +43 1 5239300 and wagner@reiwag.at. The same line is also a business/consular office line, so it is C_PERSON_BOUND_OFFICE rather than a personal DW/mobile.')
            r['override_personal_email']='wagner@reiwag.at'
            r['override_email_type']='A_PERSONAL_VERIFIED'
            r['override_email_verified']='yes'
            r['override_email_source_url']='https://suche.gerichts-sv.at/Default.aspx?SV=W259345'
            r['override_fallback_company_phone']='+4315239300'

    required={'1','11','13','19','20','25','32','34','36','44','48','61','68','72','76','77','78','83'}
    missing=required-seen
    if missing:
        raise SystemExit(f'Missing post-curation rows: {sorted(missing)}')

    os.makedirs(os.path.dirname(a.output) or '.',exist_ok=True)
    with open(a.output,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys())
        w.writeheader();w.writerows(rows)
    print('postcurate_phone_deep_fixes=18 rows=' + ','.join(sorted(seen,key=int)))

if __name__=='__main__':main()
