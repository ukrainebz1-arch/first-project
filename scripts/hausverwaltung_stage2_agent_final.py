import csv, json, os, re, unicodedata

SRC='data/hausverwaltung/size_strict_v2/size_screening_strict_v2.csv'
OUTDIR='data/hausverwaltung/size_agent_first'

def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    s=s.replace('&',' und ')
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

# Final sales-recall classes. D intentionally includes credible 11-30 / 15-30 cases:
# for this pipeline the cost of a false negative is higher than one extra sales call.
CORE={'A_CORE_30_PLUS_DIRECT','B_CORE_30_PLUS_GROUP','C_CORE_20_PLUS_RANGE','D_CORE_RECALL_11_30'}

def row_state(r):
    sc=r.get('size_class_strict_v2','U_NOT_PROVEN')
    if sc=='A_TARGET_30_PLUS': c='A_CORE_30_PLUS_DIRECT'
    elif sc=='B_LIKELY_30_PLUS_GROUP': c='B_CORE_30_PLUS_GROUP'
    elif sc=='C_BORDERLINE_20_30': c='D_CORE_RECALL_11_30'
    else: c='U_NOT_PROVEN'
    return {'agent_class':c,'group_key':r.get('company_name',''),'scope':'core','decision_reason':'baseline strict signal retained unless agent override','agent_evidence_url':'','confidence':'medium'}

OV={}
def put(names,c,reason,scope='core',group=None,url='',conf='high'):
    if isinstance(names,str): names=[names]
    for n in names:
        OV[norm(n)]={'agent_class':c,'group_key':group or n,'scope':scope,'decision_reason':reason,'agent_evidence_url':url,'confidence':conf}

# --- Strict A reviewed: true core vs adjacent/non-core/small ---
put(['Apleona Real Estate AT GmbH','AREALIS Liegenschaftsmanagement GmbH','AREV Immobilien Gesellschaft m.b.H.','Brichard Immobilien GmbH','GWS Bau- und Verwaltungsgesellschaft m.b.H.','HÖS Heimat Österreich Service GesmbH','IG Immobilien Management GmbH','Immobilienkanzlei Mag. Wolf-Dietrich Schneeweiss e.U.','Immobilienverwaltung Mag. Alois Rosenberger GmbH','IMV Immobilien Management GmbH','PMV Immobilien Management GmbH','Salzburg Wohnbau GmbH','Stiller & Hohla Immobilientreuhänder GmbH'],'A_CORE_30_PLUS_DIRECT','agent review confirmed direct 30+ employer / official operational scale')
put('KAPPACHER-SELINA Hausverwaltung GmbH','A_CORE_30_PLUS_DIRECT','31-50 direct employer evidence; primary legal target in SELINA group',group='SELINA/Kappacher group')
put('ZIMA Objektmanagement GmbH','B_CORE_30_PLUS_GROUP','group clearly 30+; standalone Hausverwaltung entity not isolated',group='ZIMA group')
put(['APCOA Austria GmbH','at home FM Services GmbH','BOE Gebäudemanagement Gesellschaft m.b.H.','CBRE GmbH','Erste Group Immorent GmbH','GBG Gebäude- und Baumanagement Graz GmbH','International Campus Austria Management GmbH','McArthurGlen Management Gesellschaft m.b.H.','Porsche Immobilien Gesellschaft m.b.H.','REIWAG Facility Services GmbH','SEE.HAUS Weiden Betriebs GmbH','SES Center Management GmbH','Supernova Invest GmbH','UBM Development AG','WSE Wiener Standortentwicklung GmbH'],'E_ADJACENT_30_PLUS','30+ scale confirmed but business is adjacent/internal/FM/development/commercial rather than classic external Hausverwaltung',scope='adjacent')
put(['Marktgemeinde Perchtoldsdorf','Plansee Group Functions Austria GmbH','Siemens Aktiengesellschaft Österreich','Steirische Wirtschaftsförderungsgesellschaft m.b.H.','Wirtschaftsagentur Burgenland GmbH'],'EXCLUDE_NON_CORE','public/non-core organisation, not a Hausverwaltung sales target',scope='exclude')
put('IMMOTOTAL Immobilientreuhandgesellschaft m.b.H.','EXCLUDE_SMALL','agent review corrected parser false-positive; actual team is small',scope='exclude')
put('TFM BAU GmbH','EXCLUDE_NON_CORE','construction business rather than core Hausverwaltung',scope='exclude')

# --- Strict B reviewed ---
put('Frieda Rustler Gebäudeverwaltung GmbH & Co KG','B_CORE_30_PLUS_GROUP','Rustler group 30+ and core property management',group='Rustler group')
put('IMMOcontract Real Estate Management GmbH','A_CORE_30_PLUS_DIRECT','agent review found direct 57-65 employee evidence')
put('LIM-MANAGEMENT GmbH','B_CORE_30_PLUS_GROUP','group >30; standalone entity not separately proven',group='LIM group')
put('WESIAK Gesellschaft m.b.H.','B_CORE_30_PLUS_GROUP','group 40+ and core Hausverwaltung',group='WESIAK group')
put('Bundesimmobiliengesellschaft m.b.H.','E_ADJACENT_30_PLUS','large state real-estate operator; not classic private external Hausverwaltung',scope='adjacent',group='BIG group')
put(['ista Österreich GmbH','Realverwaltung GmbH','Salinen Immobilien GmbH','STRABAG Property and Facility Services GmbH'],'E_ADJACENT_30_PLUS','large adjacent/internal/FM/commercial property operator',scope='adjacent')
put('Expertis Group GmbH','EXCLUDE_NON_CORE','not a core Hausverwaltung target',scope='exclude')

# --- Strict C reviewed ---
put(['Franz Kramas Gebäudeverwaltung G.m.b.H.','Hammerl Immobilien Management GmbH','Haus & Grund Immobilien Management GmbH','Immobilien Verwaltung Klagenfurt GmbH','Raiffeisen Realitäten Betreuung Tirol GmbH','Weinberger Biletti Immobilien GmbH','Weinberger Biletti Immobilien Graz GmbH','Wohnbau 2000 Gesellschaft mbH'],'C_CORE_20_PLUS_RANGE','agent review confirmed roughly 20-30 / exact 20-30 operational size')
put(['"Die Kärntner"-Wohnbau und Hausverwaltungsgesellschaft m.b.H.','"Hausverwaltung Franz Dangl" Gesellschaft m.b.H.','Alpen Real Immobilien GmbH','convival Immobilien GmbH','Dr. Martin Schober Immobilienverwaltung GmbH','Dr. Peter Dirnbacher Immobilientreuhand GmbH & Co KG','Gutwerk Immobilien Treuhand GmbH','Immobilientreuhand Kluger GmbH','KALA Immobilienmanagement GmbH','Ludwig Hallas, Immobilienverwaltung Gesellschaft m.b.H.','Palladio Immobilien GmbH','Ulreich VerwaltungsGmbH','Venta Immobilien Service GmbH','WARIWODA & RICHTER Immobilientreuhandgesellschaft m.b.H.','Woge Realitäten Gesellschaft m.b.H.'],'D_CORE_RECALL_11_30','core Hausverwaltung with credible 11-30 / team-scale signal; retained for sales recall')
put(['Bank Austria Real Invest Asset Management GmbH','FLE GmbH','GOLDBECK Parking Services GmbH','GSA Wohnbauträger GmbH','IBT Immobilien Besitz und Treuhand GmbH','IVB Immobilienverwaltungs- und Bauträger GmbH','KIBB Immobilien GmbH','Reinberg & Partner Immobilienberatung GmbH','Reischauer Consulting GmbH','U.M. Bau AG','VIVIR Holding GmbH','WEGRAZ Gesellschaft für Stadterneuerung und Assanierung m.b.H.','Wohnraumwerk Bauträger- und Projektentwicklungs GmbH','Zurich Immobilien Liegenschaftsverwaltungs-GesmbH'],'E_ADJACENT_30_PLUS','borderline employer signal but business is asset/development/internal/advisory rather than target Hausverwaltung',scope='adjacent')
put(['IM-Quadrat Immobilien Vermittlung & Verwaltung GmbH','Realkanzlei Ferdinand König Gesellschaft m.b.H.','Regelsberger Liegenschaftsverwaltungs GmbH','Schantl ITH Immobilientreuhand GmbH','Schönberg Immobilientreuhand GmbH','wohn3 Management GmbH'],'EXCLUDE_SMALL','agent review found team below target range',scope='exclude')

# --- Agent-first rescues from U_NOT_PROVEN ---
put(['WAG Wohnungsanlagen Gesellschaft m.b.H.','OM Objektmanagement GmbH','Dr.Gerlich + Co.Hausverwaltung & Facility Management GmbH','Sabo+Mandl & Tomaschek Immobilien GmbH'],'A_CORE_30_PLUS_DIRECT','agent-first recall found direct 30+ evidence missed by strict parser')
put('BUWOG - Bauen und Wohnen Gesellschaft mbH','B_CORE_30_PLUS_GROUP','large housing/property-management group; core operational target',group='BUWOG group')
put('ÖRAG Liegenschaftsverwaltung Gesellschaft m.b.H.','B_CORE_30_PLUS_GROUP','ÖRAG group scale ~330 and direct Liegenschaftsverwaltung',group='ÖRAG group')
put('ARWAG Immobilientreuhand Gesellschaft m.b.H.','B_CORE_30_PLUS_GROUP','ARWAG group has 30+ visible scale; direct entity is property management',group='ARWAG group')
put('COLLIERS Immobilienverwaltung GmbH','B_CORE_30_PLUS_GROUP','direct property-management entity sits inside large Colliers Austria group',group='Colliers Austria')
put('Leitgöb Hausverwaltung GmbH','B_CORE_30_PLUS_GROUP','Hausverwaltung standalone 1-10 but parent Leitgöb Wohnbau employer is 31-50; retained under group rule',group='Leitgöb Wohnbau group',url='https://www.karriere.at/f/leitg%C3%B6b-wohnbau-bautr%C3%A4ger')
put('Wohnfit Hausverwaltungs GmbH','B_CORE_30_PLUS_GROUP','direct Immobilienverwaltung entity is owned partly by teamneunzehn.at Hausverwaltung; related employer group is 101-500',group='teamneunzehn group',url='https://www.karriere.at/f/teamneunzehn-at-immobilienmanagement')
put('PÜHRINGER Hausverwaltung & Immobilien GmbH & Co KG','C_CORE_20_PLUS_RANGE','Herold reports 21-50 employees for the operating Hausverwaltung',url='https://www.herold.at/gelbe-seiten/bruck-am-ziller/4mP8b/puehringer-hausverwaltung-und-immobilien/')
put(['WEVIG Wohnungseigentumsverwaltungs- und Immobilientreuhand-Gesellschaft m.b.H.','NV Immobilien GmbH','be real Immobilienmanagement GmbH','Kaiserer Immobilien und Hausverwaltungs GmbH','SERIA Immobilien & Treuhand GmbH','Ing. Werner Wilhelm Bayer','Immobilien Treuhand Hanke & Bodner KG','RES Immobilienverwaltung GmbH','Pusta & Partner HausverwaltungsGmbH'],'D_CORE_RECALL_11_30','agent-first team/company-size evidence makes this a worthwhile recall target despite no hard 30+ proof')

# Group duplicates / adjacent rescues / false positives
put(['BUWOG Group GmbH','BUWOG Facility Management GmbH','BUWOG Süd GmbH'],'EXCLUDE_DUPLICATE','same BUWOG outreach group; primary entity retained separately',scope='duplicate',group='BUWOG group')
put('EHL Immobilien Management GmbH','EXCLUDE_DUPLICATE','historical name / same FN as PMV Immobilien Management GmbH',scope='duplicate',group='PMV Immobilien Management GmbH')
put(['ÖRAG Immobilien Vermittlung GmbH'],'EXCLUDE_DUPLICATE','same ÖRAG outreach group; Liegenschaftsverwaltung entity retained',scope='duplicate',group='ÖRAG group')
put(['BIG Operations GmbH'],'EXCLUDE_DUPLICATE','same BIG outreach group as Bundesimmobiliengesellschaft',scope='duplicate',group='BIG group')
put(['SELINA Hausverwaltung u. Facility-Management GmbH','Selina Verwaltung und Gebäudemanagement GmbH'],'EXCLUDE_DUPLICATE','same SELINA/Kappacher group; primary target retained',scope='duplicate',group='SELINA/Kappacher group')
put(['ÖBB-Immobilienmanagement Gesellschaft mbH','CBRE GWS Austria GmbH','Stadt Wien - Wiener Wohnen Kundenservice GmbH','PRISMA Zentrum für Standort- und Regionalentwicklung GmbH','Unibail-Rodamco Austria Verwaltungs GmbH','GRAWE IMMO AG','IMMOFINANZ AG','Wohnservice Wien Ges.m.b.H.'],'E_ADJACENT_30_PLUS','agent review confirmed scale but target is internal/public/FM/development/commercial rather than classic external Hausverwaltung',scope='adjacent')
put(['AI Immobilienverwertung GmbH.','PFG Liegenschaftsbewirtschaftungs GmbH & Co KG','Oberbank Infrastruktur Management GmbH'],'E_ADJACENT_30_PLUS','group/internal real-estate operation; adjacent rather than core Hausverwaltung',scope='adjacent')
put(['Immo-Pro Immobilien GmbH','AUREA Hausverwaltung KG','Immobilienverwaltung Cvitkovits KG','Karin Schuster KG Immobilienverwaltung','Reikersdorfer Hausverwaltung GmbH','at home Immobilien-GmbH','Bischof Immobilien Ges.m.b.H.','Dr. Friedrich Noszek GmbH','Steinkogler Immobilientreuhand GmbH','Terra Immobilien Gesellschaft m.b.H.','Viviamo Immobilien GmbH','Zirm Immobilien GmbH','Alwog-Allgemeine Wohnbaugesellschaft m.b.H.','GFR Gebäude- und Facilitymanagement GmbH','huna eleven Shopping Center GmbH','Norikum Wohnungsbaugesellschaft m.b.H.','Pilger Facility Management GmbH','PROCON Wohnbau GmbH','Rella Facility GmbH','SDD Gebäudemanagement GmbH','SE Facility Management OG','SMG Facility Management GmbH','Steinkogler Projektentwicklungs GmbH','Steinkogler Wohnbau und Vermietungs GmbH','VB - REAL Volksbank NÖ GmbH','Volksbank Salzburg Immobilien GmbH','Wohnbauservice Immobiliengesellschaft mit beschränkter Haftung'],'EXCLUDE_SMALL','agent review / public employee evidence indicates small team below useful outreach threshold',scope='exclude')
put(['Allgemeine Unfallversicherungs- Betriebsgesellschaft m.b.H.(AUVB)','Best in Parking Garagen GmbH & Co KG','BFM Facility Management GmbH','BWF Wohnbau GmbH','FM-Plus Facility Management GmbH für Wissenschaft + Kultur in NOE','Globale Baugesellschaft m.b.H. & Co. KG.','H & R Wohnbau GmbH','HAGA Wohnbau GmbH','IMMOGARANT GEBÄUDEMANAGEMENT Gesellschaft m.b.H.','ISSUK Projektentwicklungs GmbH','Kaswurm Immobilien & Wohnbau GmbH','Krenn Wohnbauservice KG','LSH Facility GmbH','LUC Facility- und Brandschutzmanagement e.U.','REAL-WOHNBAUGESELLSCHAFT M.B.H.','REALITÄTEN - INVEST Immobilientreuhand- und Wohnbaugesellschaft m.b.H','Schwechater Wohnbau GmbH','Stadtgemeinde Gmünd','Steiner & Wanner Wohnbau Gesellschaft mbH','Technopark Raaba Projektentwicklung GmbH','Victoria Projektentwicklungs GmbH','WEGRAZ Haring Projektentwicklungs GmbH','Wert-Heim Versicherungsservice GmbH & Co KG','ZHS Office- & Facilitymanagement GmbH','KONE Aktiengesellschaft','PORR Bau GmbH','STRABAG BRVZ GmbH','VAMED Standortentwicklung und Engineering GmbH'],'EXCLUDE_NON_CORE','agent review identifies non-core/developer/FM/public/internal business, not target Hausverwaltung',scope='exclude')

# New all-universe team-probe: retain only credible sales-recall rescues, reject confirmed noise/small.
put(['Immobilien Treuhandschaft Padelek & Padelek GmbH','Avon Immobilien GmbH','Immobilienverwaltung Mag. Wölfl GmbH','Immobilia Obergruber GmbH','Immoplus Immobilienverwaltungs GmbH','Schwarzataler Immobilien Treuhandgesellschaft m.b.H.','Dr. Böck Immobilien Treuhand GmbH','Die Hausverwalter Pro Immo GesmbH','IC-HAUSVERWALTUNG GmbH','Prof Dr Thomas Keppert Immobilientreuhand GmbH','Mag. Pfeifer Immobilien GmbH','Dr. Roell Hausverwaltungs-, Baubetreuungs- und Realitätengesellschaft m.b.H.','WEISS-TESSBACH Hausverwaltung GmbH','Leitgöb Hausverwaltung GmbH'],'EXCLUDE_SMALL','official/team/directory review shows standalone team below target range',scope='exclude')
# restore Leitgöb as group target after standalone small override
put('Leitgöb Hausverwaltung GmbH','B_CORE_30_PLUS_GROUP','standalone 1-10 but parent Leitgöb Wohnbau employer 31-50; group-level sales target',group='Leitgöb Wohnbau group',url='https://www.karriere.at/f/leitg%C3%B6b-wohnbau-bautr%C3%A4ger')
put(['VIVATRO GmbH','Lang & Partner Financial Advisory GmbH','SAVONAROLA Baumanagement GmbH','BOE Baumanagement Gesellschaft m.b.H.','Waldviertel Immobilien-Vermittlung GmbH','Infranorm Technologie GmbH','Spiegelfeld Immobilien GmbH'],'EXCLUDE_NON_CORE','team-probe escalation was not a core Hausverwaltung operation',scope='exclude')

# Related group entity: keep team19 Wohnservice out of legal core count, but group evidence is captured via Wohnfit.
put('team19 Wohnservice GmbH','EXCLUDE_DUPLICATE','related teamneunzehn group; Wohnfit Hausverwaltungs GmbH retained as the core WKO legal target',scope='duplicate',group='teamneunzehn group')

rows=list(csv.DictReader(open(SRC,encoding='utf-8-sig',newline='')))
out=[]
for r in rows:
    s=row_state(r)
    ov=OV.get(norm(r.get('company_name','')))
    if ov: s=ov.copy()
    cls=s['agent_class']
    rr=dict(r)
    rr.update(s)
    rr['sales_include']='yes' if cls in CORE else 'no'
    out.append(rr)

# Stable group key normalization for all core rows.
for r in out:
    if r['sales_include']=='yes' and not r.get('group_key'):
        r['group_key']=r['company_name']

fields=list(out[0].keys())
os.makedirs(OUTDIR,exist_ok=True)
with open(f'{OUTDIR}/size_agent_first_final_2026-08-31.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(out)
core=[r for r in out if r['sales_include']=='yes']
adj=[r for r in out if r['agent_class']=='E_ADJACENT_30_PLUS']
counts={}
for r in out: counts[r['agent_class']]=counts.get(r['agent_class'],0)+1
core_groups={norm(r['group_key']):r['group_key'] for r in core}
adj_groups={norm(r['group_key']):r['group_key'] for r in adj}
summary={
 'total_canonical_companies':len(out),
 'class_counts':dict(sorted(counts.items())),
 'core_sales_target_legal_entities':len(core),
 'core_sales_target_outreach_groups':len(core_groups),
 'adjacent_30plus_legal_entities':len(adj),
 'adjacent_30plus_groups':len(adj_groups),
 'core_definition':'A direct 30+ OR B group 30+ OR C direct 20+ range OR D agent-first recall 11-30/credible operational team; optimized for sales recall, not statistical purity',
 'stage3_started':False,
}
json.dump(summary,open(f'{OUTDIR}/summary_agent_first_final_2026-08-31.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
core_fields=['company_name','agent_class','group_key','states_seen','wko_standort_count','website','size_class_strict_v2','decision_reason','agent_evidence_url','confidence']
with open(f'{OUTDIR}/core_sales_targets_agent_first_2026-08-31.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=core_fields); w.writeheader(); w.writerows([{k:r.get(k,'') for k in core_fields} for r in core])
print(json.dumps(summary,ensure_ascii=False,indent=2))
