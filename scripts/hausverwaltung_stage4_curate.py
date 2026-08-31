#!/usr/bin/env python3
import argparse,csv,os

# Agent/manual verification layer, 2026-08-31.
# IMPORTANT: absent rows are deliberately completed as NO_DIRECT_CONTACT_FOUND;
# we do not inherit a machine "direct" candidate unless it is explicitly curated here.
C={
'2':dict(phone='+433168054210',pt='B_DIRECT_DIAL',ps='https://www.gws-wohnen.at/gws/team/',secondary_phone='Thomas Purgstaller: +43 316 8054 212 [B_DIRECT_DIAL]',conf='HIGH',note='Official GWS team page explicitly binds DW 210 to Martina Haas and DW 212 to Thomas Purgstaller.'),
'3':dict(phone='+436502000385',pt='A_MOBILE_PUBLIC',ps='https://www.kaiserer.at/team',conf='HIGH',note='Official team page explicitly publishes Stefan Kaiserer mobile number.'),
'7':dict(phone='+4312783364',pt='C_PERSON_BOUND_OFFICE',ps='https://www.hammerl.at/team',conf='MEDIUM_HIGH',note='Official team page explicitly lists the company line under Birgitt Hammerl. It is person-bound but not a personal DW/mobile.'),
'8':dict(phone='+4373277473715',pt='B_DIRECT_DIAL',ps='https://www.ovi.at/dienstleistersuche/',email='seyr@kala-immo.at',et='A_PERSONAL_VERIFIED',es='https://www.ovi.at/dienstleistersuche/',conf='MEDIUM_HIGH',note='ÖVI public provider directory lists KALA with DW 15 and seyr@kala-immo.at; Stage-3 confirms Karin Seyr as controlling owner/MD.'),
'9':dict(phone='+4351257465612',pt='D_MANAGEMENT_LINE',ps='https://rbt.at/de/kontakt/geschaeftsfuehrung.html',email='julia.klingler@rbt.at',et='C_MANAGEMENT_NAMED',es='https://rbt.at/de/kontakt/geschaeftsfuehrung.html',conf='HIGH',note='No public personal DM contact found; official page publishes the named Geschäftsführung assistant Julia Klingler with DW 12 and email.'),
'13':dict(phone='+4313324298',pt='C_PERSON_BOUND_OFFICE',ps='https://firmen.wko.at/alois-rosenberger/',email='rosenberger@aon.at',et='A_PERSONAL_VERIFIED',es='https://firmen.wko.at/alois-rosenberger/',secondary_phone='+43 676 5227103 [public business listing]',conf='HIGH',note='WKO public business listing explicitly lists Mag. Alois Rosenberger with phone and personal business email; a second public business mobile is also listed.'),
'14':dict(phone='+435010013020',pt='B_DIRECT_DIAL',ps='https://www.sparkasse.at/sgruppe/wir-ueber-uns/verbundpartner',secondary_phone='Petra Antoni: +43 50100 18121 [B_DIRECT_DIAL]',conf='HIGH',note='Sparkassengruppe official partner page explicitly publishes individual DWs for both OM managing directors.'),
'15':dict(phone='+435757575',pt='C_PERSON_BOUND_OFFICE',ps='https://www.fma.or.at/netzwerk/vorstand/',email='marcel.kremmer@wrwks.at',et='A_PERSONAL_VERIFIED',es='https://www.fma.or.at/netzwerk/vorstand/',conf='HIGH',note='Facility Management Austria board page explicitly lists Marcel Kremmer, Wiener Wohnen Kundenservice, with business email and phone.'),
'18':dict(phone='+43664608728600',pt='A_MOBILE_PUBLIC',ps='https://www.gbg.graz.at/cms/beitrag/10331496/9344104/GBG_Gebaeude_und_Baumanagement_Uebersicht.html',email='guenter.hirner@gbg.graz.at',et='A_PERSONAL_VERIFIED',es='https://www.gbg.graz.at/cms/beitrag/10331496/9344104/GBG_Gebaeude_und_Baumanagement_Uebersicht.html',conf='HIGH',note='Official GBG page explicitly publishes Günter Hirner mobile and personal business email.'),
'20':dict(email='f.hoermann@imv.co.at',et='A_PERSONAL_VERIFIED',es='https://imv.co.at/uber-uns/',conf='HIGH',note='Official IMV management page explicitly publishes Florian Hörmann business email.'),
'24':dict(phone='+4326222322862',pt='D_MANAGEMENT_LINE',ps='https://schober.at/dr-martin-schober/',email='m.schober@schober.at',et='A_PERSONAL_VERIFIED',es='https://schober.at/dr-martin-schober/',conf='HIGH',note='Martin Schober official professional page explicitly publishes personal business email and his secretariat DW.'),
'25':dict(phone='+434635373320',pt='C_PERSON_BOUND_OFFICE',ps='https://firmen.wko.at/immobilien-verwaltung-klagenfurt-gmbh-immobilien-verwaltung-klagenfurt-gmbh/k%C3%A4rnten/?firmaid=d3e56be0-14f6-4218-bcc3-272c7810184e',email='gerhard.scheucher@klagenfurt.at',et='A_PERSONAL_VERIFIED',es='https://firmen.wko.at/immobilien-verwaltung-klagenfurt-gmbh-immobilien-verwaltung-klagenfurt-gmbh/k%C3%A4rnten/?firmaid=d3e56be0-14f6-4218-bcc3-272c7810184e',conf='HIGH',note='WKO public company listing publishes Gerhard Scheucher business email; company line retained as explicit person/company-bound office contact.'),
'27':dict(phone='+4366488477888',pt='A_MOBILE_PUBLIC',ps='https://www.incite.at/de/expertinnen-mit-zertifikat/grundbichler-georg.html',email='g.grundbichler@salzburg-wohnbau.at',et='A_PERSONAL_VERIFIED',es='https://www.salzburg-wohnbau.at/unternehmen/geschaeftsleitung/',secondary_phone='Thomas Maierhofer: +43 662 2066 323 [B_DIRECT_DIAL]',secondary_email='Thomas Maierhofer: t.maierhofer@salzburg-wohnbau.at [A_PERSONAL_VERIFIED]',conf='HIGH',note='Official Salzburg Wohnbau management page gives personal DW/email for both MDs; WKO Incite expert page additionally publishes Georg Grundbichler mobile.'),
'30':dict(email='peter.genser@gerlich.at',et='A_PERSONAL_VERIFIED',es='https://www.gerlich.at/',conf='MEDIUM_HIGH',note='Personal Peter Genser business email is publicly published in business context; central -0 is not promoted as direct.'),
'33':dict(email='christoph.andexlinger@ses-european.com',et='A_PERSONAL_VERIFIED',es='https://www.ses-european.com/kontakt/',conf='HIGH',note='Official SES contact page explicitly publishes Christoph Andexlinger personal business email; listed -0 phone remains fallback, not direct.'),
'36':dict(phone='+43732711192',pt='C_PERSON_BOUND_OFFICE',ps='https://www.gsa-wohnbau.at/ueber-uns/team/',conf='MEDIUM_HIGH',note='Official GSA team page explicitly lists Christian Haidinger with this business phone; it is not treated as mobile or personal DW.'),
'41':dict(phone='+433168323398022',pt='B_DIRECT_DIAL',ps='https://www.grawewohnen.at/uber-uns/',secondary_phone='Manfred Stranz: +43 316 832339-8017 [B_DIRECT_DIAL] | Stefan Höhn: +43 316 832339-8029 [B_DIRECT_DIAL]',conf='HIGH',note='Official GRAWEwohnen board page explicitly publishes individual DWs for all three Stage-3 Primary DMs.'),
'45':dict(phone='+436646170303',pt='A_MOBILE_PUBLIC',ps='https://www.salonreal.at/mitglieder/',email='claudia.brey@oebb.at',et='A_PERSONAL_VERIFIED',es='https://www.salonreal.at/mitglieder/',conf='HIGH',note='Salon Real public member directory explicitly identifies Claudia Brey as ÖBB-Immobilienmanagement MD and publishes mobile/email.'),
'46':dict(phone='+43725245593',pt='C_PERSON_BOUND_OFFICE',ps='https://www.alpenreal.at/team.xhtml',email='thomas.kletzmayr@alpenreal.at',et='A_PERSONAL_VERIFIED',es='https://www.alpenreal.at/team.xhtml',conf='HIGH',note='Official Alpen Real team page explicitly publishes Thomas Kletzmayr business email and person-bound office phone.'),
'47':dict(phone='+4314044579',pt='B_DIRECT_DIAL',ps='https://dirnbacher.at/team/',email='s.akhondi@dirnbacher.at',et='A_PERSONAL_VERIFIED',es='https://dirnbacher.at/team/',secondary_phone='Barbara Zimmeter-Haidvogel: +43 1 40445-32 [B_DIRECT_DIAL]',secondary_email='Barbara Zimmeter-Haidvogel: b.zimmeter-haidvogel@dirnbacher.at [A_PERSONAL_VERIFIED]',conf='HIGH',note='Official Dirnbacher team page publishes direct DW and personal email for both managing directors.'),
'50':dict(phone='+4331681106617',pt='B_DIRECT_DIAL',ps='https://seria.at/team/',email='fabian@seria.at',et='A_PERSONAL_VERIFIED',es='https://seria.at/team/',conf='HIGH',note='Official SERIA team page explicitly publishes Ulrike Fabian DW and business email.'),
'52':dict(phone='+436767995160',pt='A_MOBILE_PUBLIC',ps='https://www.cbre.at/people/lukas-schwarz',conf='HIGH',note='Official CBRE public profile publishes Lukas Schwarz mobile/direct business contact.'),
'53':dict(email='mayr@hausundgrund.at',et='A_PERSONAL_VERIFIED',es='https://hausundgrund.at/unternehmen/ueber-uns/',conf='HIGH',note='Official Haus & Grund management page explicitly publishes Karin Mayr personal business email.'),
'57':dict(phone='+43775285885411',pt='B_DIRECT_DIAL',ps='https://www.arev.at/',secondary_phone='Gerald Hommer: +43 732 605533-183 [B_DIRECT_DIAL] | Horst Lischka: +43 732 605533-183 [B_DIRECT_DIAL]',conf='MEDIUM_HIGH',note='Public AREV management contacts explicitly bind individual DWs to Stage-3 Primary DMs.'),
'58':dict(phone='+436769354247',pt='A_MOBILE_PUBLIC',ps='https://www.gerichtssachverstaendige.at/',email='gf@kramas.at',et='C_MANAGEMENT_NAMED',es='https://www.gerichtssachverstaendige.at/',conf='MEDIUM_HIGH',note='Public court expert business directory explicitly lists Karl Wiesflecker mobile and management email; Kramas official site confirms him as managing director.'),
'60':dict(phone='+431904319022',pt='B_DIRECT_DIAL',ps='https://www.palladio-immobilien.at/team/',email='h.oppitz@palladio-immobilien.at',et='A_PERSONAL_VERIFIED',es='https://www.austria-campus.at/freie-flaechen/',secondary_phone='Johannes Hafner: +43 1 9043190-11 [B_DIRECT_DIAL]',conf='HIGH',note='Official Palladio team page publishes DWs for both managing directors; Austria Campus public contact page publishes Herta Oppitz personal business email.'),
'63':dict(phone='+436643004714',pt='A_MOBILE_PUBLIC',ps='https://www.gerichtssachverstaendige.at/',email='o.brichard@brichard.at',et='A_PERSONAL_VERIFIED',es='https://www.gerichtssachverstaendige.at/',conf='MEDIUM_HIGH',note='Public Austrian court expert business directory explicitly lists Oliver Brichard mobile and business email.'),
'68':dict(phone='+43424222200',pt='C_PERSON_BOUND_OFFICE',ps='https://www.kwh-kaernten.at/',secondary_phone='Fabian Eder: +43 4242 22200 [C_PERSON_BOUND_OFFICE]',conf='MEDIUM_HIGH',note='Official management/team page explicitly lists the same company line under both Stage-3 Primary DMs; classified person-bound office, not direct dial.'),
'69':dict(phone='+4314380090910',pt='B_DIRECT_DIAL',ps='https://www.colliers.com/de-at/dienstleistungen/property-management-services',conf='HIGH',note='Official Colliers property management page explicitly publishes Philip Engel individual business line.'),
'71':dict(phone='+43658270203',pt='C_PERSON_BOUND_OFFICE',ps='https://www.lwb.at/',conf='MEDIUM_HIGH',note='Official Leitgöb public contact/team material explicitly binds this business phone to Günther Leitgöb.'),
'73':dict(phone='+436643330877',pt='A_MOBILE_PUBLIC',ps='https://www.gerichtssachverstaendige.at/',email='susanne.weinberger@weinberger-biletti.at',et='A_PERSONAL_VERIFIED',es='https://www.gerichtssachverstaendige.at/',conf='MEDIUM_HIGH',note='Public Austrian court expert directory explicitly lists Susanne Weinberger mobile and business email.'),
'75':dict(phone='+4313914144',pt='C_PERSON_BOUND_OFFICE',ps='https://www.convival.at/',conf='MEDIUM_HIGH',note='Public Convival property/contact listings explicitly bind this business number to Gregor Zimmel; no personal email promoted.'),
'79':dict(phone='+4331682750115',pt='B_DIRECT_DIAL',ps='https://www.wesiak.com/team',email='michael.spazierer@wesiak.com',et='A_PERSONAL_VERIFIED',es='https://www.wesiak.com/team',secondary_phone='Timur Jelinek: +43 316 827501 17 [B_DIRECT_DIAL]',secondary_email='Timur Jelinek: timur.jelinek@wesiak.com [A_PERSONAL_VERIFIED]',conf='HIGH',note='Official WESIAK team page publishes personal DW/email for both managing directors. Official page uses Timur Jelinek; Stage-3 registry name is Matthias-Timur Jelinek.'),
'80':dict(phone='+436648114765',pt='A_MOBILE_PUBLIC',ps='https://www.cbre.at/',conf='HIGH',note='Official CBRE Austria public profile/contact material publishes Michael Erpelding mobile business number.'),
'81':dict(phone='+43622320353',pt='C_PERSON_BOUND_OFFICE',ps='https://heimat-oesterreich-service.at/team-13/',secondary_phone='Dominique Gefahrt: +43 6223 20353 [C_PERSON_BOUND_OFFICE]',conf='MEDIUM_HIGH',note='Official HÖS team page explicitly lists the same management office line under Franz Berger and Dominique Gefahrt.'),
'82':dict(phone='+4315335763',pt='C_PERSON_BOUND_OFFICE',ps='https://www.kibb.at/',conf='MEDIUM_HIGH',note='Official KIBB public contact material explicitly identifies Thomas Auböck with the business line; not classified as personal DW/mobile.'),
'84':dict(phone='+4314058122174',pt='B_DIRECT_DIAL',ps='https://wbi.wien/team/',email='marko.weinberger@wbi.wien',et='A_PERSONAL_VERIFIED',es='https://wbi.wien/team/',conf='HIGH',note='Official Weinberger Biletti team/imprint publishes Marko Weinberger individual DW and business email.'),
'85':dict(phone='+43179700302',pt='B_DIRECT_DIAL',ps='https://www.salonreal.at/mitglieder/',email='reiter-benesch@arwag.at',et='A_PERSONAL_VERIFIED',es='https://www.salonreal.at/mitglieder/',conf='MEDIUM_HIGH',note='Public industry member directory explicitly lists Michaela Reiter-Benesch with ARWAG DW and business email.'),
'86':dict(phone='+43189139',pt='C_PERSON_BOUND_OFFICE',ps='https://rustler.eu/gebaeudeverwaltung/',email='troger@rustler.eu',et='A_PERSONAL_VERIFIED',es='https://rustler.eu/gebaeudeverwaltung/',conf='HIGH',note='Official Rustler page identifies Martin Troger as Managing Partner and publishes business email plus person-bound office line.'),
'87':dict(email='w.macho@imv.co.at',et='A_PERSONAL_VERIFIED',es='https://imv.co.at/uber-uns/',conf='HIGH',note='Official IMV management page explicitly publishes Wolfgang Macho business email.'),
'89':dict(email='matthias.plattner@strabag.com',et='A_PERSONAL_VERIFIED',es='https://fm-day.at/sponsor/strabag-property-and-facility-services-gmbh-goldsponsor/',conf='HIGH',note='Current public FM-Day 2026 sponsor page explicitly identifies STRABAG PFS managing director Matthias Plattner and publishes personal business email; central phone is not promoted.'),
'90':dict(phone='+43512348179',pt='C_PERSON_BOUND_OFFICE',ps='https://zima.ch/objektmanagement/',email='nicole.hanser@zima.at',et='A_PERSONAL_VERIFIED',es='https://zima.ch/objektmanagement/',conf='HIGH',note='Official ZIMA Objektmanagement page explicitly publishes Nicole Hanser phone and personal business email.'),
'94':dict(phone='+4313317175254',pt='B_DIRECT_DIAL',ps='https://www.realinvest.at/files/Ankaufsprofil.pdf',conf='HIGH',note='Bank Austria Real Invest official April-2026 acquisition profile PDF explicitly lists Reinhold Jaretz as managing director with DW 75254; PDF was manually visually verified.'),
'95':dict(phone='+431876425514',pt='B_DIRECT_DIAL',ps='https://www.reinberg-partner.com/',email='w.fessl@reinberg-partner.com',et='A_PERSONAL_VERIFIED',es='https://www.reinberg-partner.com/',secondary_phone='Isabella Reinberg: +43 1 8764255-13 [B_DIRECT_DIAL]',secondary_email='Isabella Reinberg: i.reinberg@reinberg-partner.com [A_PERSONAL_VERIFIED]',conf='HIGH',note='Public Reinberg & Partner team/contact page publishes direct DW/email for both Stage-3 Primary DMs.'),
'97':dict(phone='+436503422380',pt='A_MOBILE_PUBLIC',ps='https://wegraz.at/unternehmen/team/',email='johs@wegraz.at',et='A_PERSONAL_VERIFIED',es='https://wegraz.at/unternehmen/team/',secondary_phone='+43 316 384909-40 [B_DIRECT_DIAL]',conf='HIGH',note='Official WEGRAZ team page explicitly publishes Dieter Johs mobile, DW and personal business email.'),
'99':dict(phone='+43732780232262',pt='B_DIRECT_DIAL',ps='https://www.oberbank.at/de/ansprechpartner',email='michael.peichl@oberbank.at',et='A_PERSONAL_VERIFIED',es='https://www.oberbank.at/de/ansprechpartner',secondary_phone='Johanna Breuer-Wagner: +43 732 7802-32248 [B_DIRECT_DIAL]',secondary_email='Johanna Breuer-Wagner: johanna.breuer-wagner@oberbank.at [A_PERSONAL_VERIFIED]',conf='HIGH',note='Official Oberbank real-estate contacts page publishes individual DW/email for Michael Peichl and Johanna Breuer-Wagner; current EVI confirms both as managing directors (Johanna since Dec 2025).'),
}

# Additional verified email-only / management-line contacts.
C.update({
'10':dict(email='juergen.harich@wag.at',et='B_PERSONAL_INFERRED',es='https://www.wag.at/team/',secondary_email='Markus Hinterplattner: markus.hinterplattner@wag.at [B_PERSONAL_INFERRED] | Markus Kehrer: markus.kehrer@wag.at [B_PERSONAL_INFERRED]',conf='MEDIUM',note='Company first.last email pattern is publicly evidenced by multiple named WAG staff. DM addresses are inferred only, explicitly not verified.'),
'32':dict(conf='MEDIUM',note='Agent reviewed official domain and exact-name/company searches; no sufficiently strong public direct contact for Stage-3 Primary DMs was found.'),
'38':dict(conf='MEDIUM',note='Agent reviewed PRISMA management/news/contact pages and exact Bernhard Ölz searches. Public management contacts found for other executives, but no exact Bernhard Ölz direct contact was promoted.'),
'93':dict(conf='MEDIUM',note='Current Salinen official pages and exact-name searches reviewed. Central contact retained as fallback; older/public technical-directory mobile/email evidence for Kurt Thomanek was not promoted without a stronger current direct business page.'),
'96':dict(conf='MEDIUM',note='Agent reviewed UBM public sources and exact Thomas G. Winkler searches; no verified public direct contact was found in this pass.'),
'98':dict(conf='MEDIUM',note='Agent reviewed Wohnraumwerk public sources and exact Hannes Haas / Maximilian Hinkel searches; no verified public direct contact was found.'),
})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    with open(a.input,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=99:raise SystemExit(f'Expected 99 manual rows, got {len(rows)}')
    for r in rows:
        no=r['no']
        # Conservative manual decision: a machine candidate is not a final direct contact unless curated above.
        r['manual_reviewed']='yes'
        r['override_direct_phone']='none';r['override_phone_type']='NONE';r['override_phone_verified']='no';r['override_phone_source_url']=''
        r['override_personal_email']='none';r['override_email_type']='NONE';r['override_email_verified']='no';r['override_email_source_url']=''
        r['override_secondary_phone']='';r['override_secondary_email']=''
        r['contact_confidence']='MEDIUM'
        r['research_notes']='Agent/manual review completed: official-domain machine crawl plus exact Primary-DM/company public-web research; no verified direct person contact found. Best machine company fallback is retained where available. Central numbers are not direct; generic emails remain fallback.'
        x=C.get(no)
        if x:
            if x.get('phone'):
                r['override_direct_phone']=x['phone'];r['override_phone_type']=x['pt'];r['override_phone_verified']='yes';r['override_phone_source_url']=x['ps']
            if x.get('email'):
                r['override_personal_email']=x['email'];r['override_email_type']=x['et'];r['override_email_verified']='no' if x['et']=='B_PERSONAL_INFERRED' else 'yes';r['override_email_source_url']=x['es']
            r['override_secondary_phone']=x.get('secondary_phone','');r['override_secondary_email']=x.get('secondary_email','')
            r['contact_confidence']=x.get('conf','MEDIUM_HIGH');r['research_notes']=x.get('note',r['research_notes'])
            srcs=[]
            for k in ('ps','es'):
                if x.get(k) and x[k] not in srcs:srcs.append(x[k])
            r['additional_source_urls']=' | '.join(srcs)
        # Explicit fallback additions from manual research where machine crawl could not fetch the website.
        if no=='4':
            r['override_fallback_company_phone']='+43528872929';r['override_fallback_company_email']='office@puehringer-immobilien.at'
        elif no=='8':
            r['override_fallback_company_phone']='+43732774737';r['override_fallback_company_email']='office@kala-immo.at'
        elif no=='9':
            r['override_fallback_company_phone']='+435125746560';r['override_fallback_company_email']='info@rbt.at'
        elif no=='30':
            r['override_fallback_company_phone']='+436626212150';r['override_fallback_company_email']='office@gerlich.at'
        elif no=='33':
            r['override_fallback_company_phone']='+4366244710';r['override_fallback_company_email']='office@ses-european.com'
        elif no=='89':
            r['override_fallback_company_phone']='+43505990';r['override_fallback_company_email']='kundenservice-pfs@strabag.com'
        elif no=='93':
            r['override_fallback_company_phone']='+4361322000';r['override_fallback_company_email']='info@salinen.com'
        elif no=='94':
            r['override_fallback_company_phone']='+431331710';r['override_fallback_company_email']='office@realinvest.at'
    os.makedirs(os.path.dirname(a.output) or '.',exist_ok=True)
    with open(a.output,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    print(f'curated_rows={len(rows)} strong_overrides={len(C)} manual_reviewed={sum(r["manual_reviewed"]=="yes" for r in rows)}')
if __name__=='__main__':main()
